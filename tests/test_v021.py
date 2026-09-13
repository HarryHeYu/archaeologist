"""Tests for standalone v0.2.1 commands: hot, recent, contributors, search."""

from __future__ import annotations

from tests.test_git_analysis import git_repo  # noqa: F401  (pytest fixture)

from archaeologist.analyzers.history import (
    analyze_contributors, analyze_hot_files, analyze_recent)
from archaeologist.analyzers.search import search
from archaeologist.cli import build_analysis
from archaeologist.render import render_hot, render_recent, render_contributors


def test_hot_standalone(git_repo):
    hot = analyze_hot_files(git_repo and __import__("archaeologist.gitcmd", fromlist=["GitRepo"]).GitRepo(git_repo),
                            ["src/core.py", "README.md"])
    paths = [h.path for h in hot]
    assert "src/core.py" in paths
    # dotfiles and unrecognized files are filtered out of hot candidates
    assert all(not p.split("/")[-1].startswith(".") for p in paths)


def test_recent_standalone(git_repo):
    from archaeologist.gitcmd import GitRepo
    r = analyze_recent(GitRepo(git_repo), days=30)
    assert r.commits == 2
    lines = render_recent(r)
    assert any("2 commits" in l for l in lines)


def test_contributors_render(git_repo):
    from archaeologist.gitcmd import GitRepo
    c = analyze_contributors(GitRepo(git_repo))
    lines = render_contributors(c)
    assert any("Alice" in l for l in lines)
    assert any("Bob" in l for l in lines)


def test_search_paths_commits_contributors(git_repo):
    res = search(git_repo, "core")
    assert "src/core.py" in res["paths"]
    commits = search(git_repo, "expand")
    assert any("expand core" in c["subject"] for c in commits["commits"])
    contribs = search(git_repo, "alice")
    assert any(c["name"] == "Alice" for c in contribs["contributors"])
    assert search(git_repo, "zzz-nothing")["paths"] == []


def test_timeline(git_repo):
    from archaeologist.analyzers.timeline import build_timeline, render_timeline
    from archaeologist.gitcmd import GitRepo
    t = build_timeline(git_repo, GitRepo(git_repo))
    assert t is not None
    assert any(y["commits"] > 0 for y in t["years"].values())
    out = render_timeline(t)
    assert "Repository Timeline" in out
    assert "largest change" in out
