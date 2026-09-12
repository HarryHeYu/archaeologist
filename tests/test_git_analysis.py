"""Tests for git-derived analysis, using a small fixture repository."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archaeologist.analyzers.history import (
    analyze_contributors, analyze_hot_files, analyze_recent)
from archaeologist.analyzers.overview import analyze_overview
from archaeologist.cli import build_analysis
from archaeologist.gitcmd import GitRepo
from archaeologist.report import generate_report
from archaeologist.walker import walk_repo


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "core.py").write_text("value = 1\n", encoding="utf-8")
    (root / "tests" / "test_core.py").write_text("def test(): pass\n", encoding="utf-8")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    git("init", "-b", "main", cwd=root)
    git("add", ".", cwd=root)
    git("-c", "user.name=Alice", "-c", "user.email=alice@example.com",
        "commit", "-m", "initial commit", cwd=root)
    # second commit touching core.py heavily by Bob
    (root / "src" / "core.py").write_text("value = 2\n" * 30, encoding="utf-8")
    (root / "src" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    git("add", ".", cwd=root)
    git("-c", "user.name=Bob", "-c", "user.email=bob@example.com",
        "commit", "-m", "expand core", cwd=root)
    return root


def test_is_git_and_overview(git_repo: Path):
    g = GitRepo(git_repo)
    assert g.is_repo()
    walk = walk_repo(git_repo)
    ov = analyze_overview(git_repo, g, walk)
    assert ov.is_git
    assert ov.branch == "main"
    assert ov.total_commits == 2
    assert ov.contributors == 2
    assert ov.tracked_files == 4
    assert ov.last_commit is not None
    assert "expand core" in ov.last_commit.subject


def test_non_git_overview(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    walk = walk_repo(tmp_path)
    ov = analyze_overview(tmp_path, None, walk)
    assert not ov.is_git
    assert any("git" in n.lower() for n in ov.notes)


def test_hot_files(git_repo: Path):
    g = GitRepo(git_repo)
    hot = analyze_hot_files(g, ["src/core.py", "src/extra.py",
                                "tests/test_core.py", "README.md"])
    assert hot, "hot files should be found"
    assert hot[0].path == "src/core.py"
    top = hot[0]
    assert top.commits == 2
    assert top.contributors == 2


def test_contributors(git_repo: Path):
    g = GitRepo(git_repo)
    contribs = analyze_contributors(g)
    names = {c.name for c in contribs}
    assert {"Alice", "Bob"} <= names
    bob = next(c for c in contribs if c.name == "Bob")
    assert bob.commits == 1
    assert any("src" in a for a in bob.top_areas)


def test_recent(git_repo: Path):
    g = GitRepo(git_repo)
    r = analyze_recent(g, days=30)
    assert r.commits == 2
    assert r.added >= 31
    assert any("src" in name for name, _ in r.areas)
    assert "src/extra.py" in r.new_files


def test_full_scan_and_report(git_repo: Path, tmp_path: Path):
    a = build_analysis(git_repo)
    md = generate_report(a)
    assert "# Repository Archaeology Report: repo" in md
    assert "## Overview" in md
    assert "## Hot Files" in md
    assert "## Suggested Reading Order" in md
    assert "src/core.py" in md
    # UTF-8 output path with Chinese + space in name
    out = tmp_path / "报 告.md"
    out.write_text(md, encoding="utf-8")
    assert out.read_text(encoding="utf-8").startswith("# Repository")


def test_renamed_file_history(git_repo: Path):
    git("mv", "src/extra.py", "src/renamed.py", cwd=git_repo)
    git("-c", "user.name=Alice", "-c", "user.email=alice@example.com",
        "commit", "-m", "rename extra", cwd=git_repo)
    g = GitRepo(git_repo)
    # follow rename: --numstat without -M won't follow, but the commit list
    # must still show the file under its new name in recent changes
    r = analyze_recent(g, days=30)
    assert any("renamed.py" in n for n in r.new_files)
