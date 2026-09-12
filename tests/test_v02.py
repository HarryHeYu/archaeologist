"""Tests for v0.2 commands: tree, file dossier, why, deps, history."""

from __future__ import annotations

from pathlib import Path

import pytest

from archaeologist.analyzers.deps import extract_deps
from archaeologist.analyzers.dossier import analyze_deps_view, analyze_file, analyze_why
from archaeologist.analyzers.evolution import file_evolution, keyword_evolution
from archaeologist.analyzers.tree import build_tree
from archaeologist.cli import build_analysis
from tests.test_git_analysis import git, git_repo  # reuse fixture


def test_deps_python_relative_and_absolute(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "store.py").write_text("class Store: pass\n", encoding="utf-8")
    (pkg / "cli.py").write_text(
        "from .store import Store\nfrom . import x\nimport os\n", encoding="utf-8")
    d = extract_deps(tmp_path, "pkg/cli.py", (pkg / "cli.py").read_text(encoding="utf-8"))
    assert "pkg/store.py" in d.internal
    assert "pkg/__init__.py" in d.internal
    assert "os" in d.external


def test_deps_c_includes(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "util.h").write_text("#pragma once\n", encoding="utf-8")
    (tmp_path / "src" / "local.h").write_text("#pragma once\n", encoding="utf-8")
    src = '#include "local.h"\n#include "util.h"\n#include <stdio.h>\nint x;\n'
    from archaeologist.analyzers.deps import build_header_index
    build_header_index(tmp_path, ["src/local.h", "include/util.h"])
    d = extract_deps(tmp_path, "src/main.c", src)
    assert "src/local.h" in d.internal
    assert "include/util.h" in d.internal
    assert "stdio.h" in d.external


def test_deps_reverse(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "store.py").write_text("class Store: pass\n", encoding="utf-8")
    (pkg / "cli.py").write_text("from .store import Store\n", encoding="utf-8")
    a = build_analysis(tmp_path)
    view = analyze_deps_view(tmp_path, a, "pkg/store.py")
    assert view is not None
    assert "pkg/cli.py" in view["used_by"]


def test_tree_groups_and_roles(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "t.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# r\n", encoding="utf-8")
    a = build_analysis(tmp_path)
    lines = build_tree(a)
    text = "\n".join(lines)
    assert "src/" in text
    assert "tests/" in text
    assert "# tests" in text
    assert "README.md" in text


def test_file_dossier_git(git_repo: Path):
    a = build_analysis(git_repo)
    d = analyze_file(git_repo, a, "src/core.py")
    assert d["git"] is True
    assert d["commits"] == 2
    assert set(d["contributors"]) == {"Alice", "Bob"}
    assert d["created"] is not None
    assert d["main_contributor"] in ("Alice", "Bob")


def test_why_evidence_and_verdict(git_repo: Path):
    a = build_analysis(git_repo)
    ev = analyze_why(git_repo, a, "src/core.py")
    assert ev["verdict"] in ("HIGH", "MEDIUM", "LOW")
    assert any("commit" in s for s in ev["git_signals"])
    # non-git repo: degrade, no verdict
    (git_repo.parent / "plain" / "a.py").parent.mkdir(parents=True, exist_ok=True)
    plain = git_repo.parent / "plain"
    (plain / "a.py").write_text("x = 1\n", encoding="utf-8")
    a2 = build_analysis(plain)
    ev2 = analyze_why(plain, a2, "a.py")
    assert ev2["verdict"] == "UNKNOWN"


def test_file_evolution(git_repo: Path):
    evo = file_evolution(git_repo, "src/core.py")
    assert evo is not None
    assert evo["created"] is not None
    assert evo["contributors"] == 2
    assert evo["yearly"]


def test_keyword_evolution(git_repo: Path):
    evo = keyword_evolution(git_repo, "core")
    assert evo is not None
    assert any("core" in p for p in evo["related_paths"])
    assert evo["yearly"]
