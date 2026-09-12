"""Tests for non-git analysis: LOC counting, walking, structure, entrypoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from archaeologist.analyzers.structure import (
    analyze_entrypoints, analyze_languages, analyze_structure, classify_dir)
from archaeologist.loc_counter import count_loc
from archaeologist.walker import walk_repo


def make_file(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_loc_python(tmp_path):
    src = "# comment\n\ndef f():\n    return 1  # trailing\n"
    loc = count_loc(src, "Python")
    assert loc.total == 4
    assert loc.comment == 1
    assert loc.blank == 1
    assert loc.code == 2  # "def f():" and "return 1" (trailing comment still code)


def test_loc_c_block_comments(tmp_path):
    src = "/* block\nstill comment */\nint x;\n// line comment\n\nint y;\n"
    loc = count_loc(src, "C++")
    assert loc.comment == 3
    assert loc.code == 2
    assert loc.blank == 1


def test_walk_ignores_vendor_and_caches(tmp_path):
    make_file(root=tmp_path, rel="src/a.py", content="x = 1\n")
    make_file(root=tmp_path, rel="node_modules/pkg/i.js", content="var i;\n")
    make_file(root=tmp_path, rel="__pycache__/a.cpython.pyc", content="\x00\x00")
    make_file(root=tmp_path, rel=".git/config", content="[core]\n")
    res = walk_repo(tmp_path)
    rels = {f.rel for f in res.files}
    assert rels == {"src/a.py"}
    assert "node_modules" in " ".join(res.skipped_dirs) or res.skipped_dirs


def test_walk_non_git_includes_gitignored_dirs(tmp_path):
    # Without git tracking, .gitignore is not consulted; walker still skips its own list
    make_file(root=tmp_path, rel="build/out.obj", content="\x00")
    make_file(root=tmp_path, rel="src/a.py", content="x = 1\n")
    res = walk_repo(tmp_path)
    assert {f.rel for f in res.files} == {"src/a.py"}


def test_classify_dir():
    assert classify_dir("src") == "main source code"
    assert classify_dir("tests") == "tests"
    assert classify_dir("docs") == "documentation"
    assert classify_dir("flibbidy") is None


def test_language_stats(tmp_path):
    make_file(tmp_path, "src/a.py", "x = 1\n# c\n\n")
    make_file(tmp_path, "src/b.py", "y = 2\n")
    make_file(tmp_path, "lib/c.rs", "fn main() {}\n")
    walk = walk_repo(tmp_path)
    stats = analyze_languages(walk)
    names = {s.name for s in stats}
    assert "Python" in names and "Rust" in names
    py = next(s for s in stats if s.name == "Python")
    assert py.files == 2
    assert py.code == 2  # "x = 1" and "y = 2"


def test_structure_roles(tmp_path):
    make_file(tmp_path, "src/a.py", "x = 1\n" * 3)
    make_file(tmp_path, "tests/test_a.py", "def test(): pass\n")
    make_file(tmp_path, "docs/index.md", "# Hi\n")
    walk = walk_repo(tmp_path)
    langs = analyze_languages(walk)
    dirs = {d.rel: d for d in analyze_structure(walk, langs)}
    assert dirs["src"].role == "main source code"
    assert dirs["tests"].role == "tests"
    assert dirs["docs"].role == "documentation"


def test_entrypoints_python_main(tmp_path):
    make_file(tmp_path, "pkg/cli.py", 'if __name__ == "__main__":\n    run()\n')
    make_file(tmp_path, "pkg/mod.py", "value = 1\n")
    walk = walk_repo(tmp_path)
    eps = analyze_entrypoints(walk)
    paths = [e.path for e in eps]
    assert "pkg/cli.py" in paths
    assert "pkg/mod.py" not in paths


def test_entrypoints_c_main(tmp_path):
    make_file(tmp_path, "src/main.c", "int main(void) { return 0; }\n")
    walk = walk_repo(tmp_path)
    paths = [e.path for e in analyze_entrypoints(walk)]
    assert "src/main.c" in paths


def test_unicode_and_space_paths(tmp_path):
    d = tmp_path / "中文 目录"
    d.mkdir()
    (d / "模块.py").write_text("x = 1\n", encoding="utf-8")
    walk = walk_repo(tmp_path)
    assert any(f.rel == "中文 目录/模块.py" for f in walk.files)
