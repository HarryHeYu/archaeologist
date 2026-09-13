"""Tests for tree-sitter symbol extraction (skipped if extras not installed)."""

from __future__ import annotations

import pytest

from tests.test_git_analysis import git, git_repo  # noqa: F401
from archaeologist.analyzers import symbols as sym

pytestmark = pytest.mark.skipif(not sym.HAS_TS, reason="tree-sitter extras not installed")


def test_extract_python_symbols():
    src = '''def top_level(): pass

class Store:
    def __init__(self): pass
    def sessions(self): pass
'''
    syms = sym.extract_symbols("Python", "pkg/mod.py", src)
    names = {s.name for s in syms}
    assert "top_level" in names and "Store" in names
    store = next(s for s in syms if s.name == "Store")
    assert store.kind == "class"
    assert {c.name for c in store.children} == {"__init__", "sessions"}
    assert store.start_line == 3


def test_extract_c_symbols(tmp_path):
    src = '''
struct Point { int x; int y; };

int add(int a, int b) {
    return a + b;
}
'''
    syms = sym.extract_symbols("C", "src/point.c", src)
    kinds = {s.kind: s.name for s in syms}
    assert kinds.get("struct") == "Point"
    assert "add" in kinds.values()


def test_find_symbols_matching_order():
    syms = sym.extract_symbols("Python", "m.py",
                               "def parse(): pass\ndef parse_file(): pass\nclass Parser: pass\n")
    assert len(sym.find_symbols(syms, "parse")) == 1          # exact first
    assert [s.name for s in sym.find_symbols(syms, "Parser")] == ["Parser"]
    prefixed = sym.find_symbols(syms, "parse_f")
    assert [s.name for s in prefixed] == ["parse_file"]


def test_symbol_command_on_fixture(git_repo):
    from archaeologist.cli import build_analysis
    from archaeologist.walker import walk_repo
    from archaeologist.gitcmd import GitRepo
    (git_repo / "src" / "engine.py").write_text(
        "class Engine:\n    def start(self):\n        pass\n",
        encoding="utf-8")
    git("add", ".", cwd=git_repo)
    git("-c", "user.name=Alice", "-c", "user.email=alice@example.com",
        "commit", "-m", "add engine", cwd=git_repo)
    ls = GitRepo(git_repo).try_out("ls-files", "-z")
    tracked = {p for p in ls.split("\x00") if p}
    files = walk_repo(git_repo, tracked_only=tracked).files
    all_syms = sym.index_symbols(files, git_repo)
    matches = sym.find_symbols(all_syms, "Engine")
    assert matches and matches[0].kind == "class"
    assert any(c.name == "start" for c in matches[0].children)
