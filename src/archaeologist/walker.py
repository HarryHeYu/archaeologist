"""Filesystem walking with ignore rules, binary detection, and language mapping."""

from __future__ import annotations

import fnmatch
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# -- ignore configuration -----------------------------------------------------

DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".venv", "venv", "env", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".ipynb_checkpoints",
    "build", "dist", "out", "target", "cmake-build-debug", "Debug", "Release",
    "vendor", "third_party", "thirdparty", "external",
    ".gradle", ".idea", ".vscode", ".vs", "Pods", "packages",
    ".archaeologist", "coverage", "htmlcov", ".eggs", "*.egg-info",
    "obj", "bin", "_build", "deps", "site-packages",
}

DEFAULT_IGNORE_PATTERNS = [
    "*.min.js", "*.min.css", "*.map", "*.lock", "package-lock.json",
    "yarn.lock", "poetry.lock", "Cargo.lock",
]

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".svg",  # svg text-ish but count as asset
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".a", ".lib", ".o", ".obj",
    ".bin", ".dat", ".iso", ".img", ".wasm", ".pyc", ".pyo", ".class",
    ".jar", ".war", ".whl", ".egg", ".nupkg", ".deb", ".rpm",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".db", ".sqlite", ".sqlite3", ".pdb", ".mdb",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac", ".ogg",
    ".psd", ".ai", ".blend", ".ttf",
}

MAX_FILE_BYTES = 1_500_000  # skip counting content of larger text files

# -- language table ------------------------------------------------------------
# extension -> (language name, comment prefixes, block comment open/close)

LANGUAGES: dict[str, dict] = {
    ".c":      {"name": "C", "line": ["//"], "block": ("/*", "*/")},
    ".h":      {"name": "C/C++ Header", "line": ["//"], "block": ("/*", "*/")},
    ".cpp":    {"name": "C++", "line": ["//"], "block": ("/*", "*/")},
    ".cc":     {"name": "C++", "line": ["//"], "block": ("/*", "*/")},
    ".cxx":    {"name": "C++", "line": ["//"], "block": ("/*", "*/")},
    ".hpp":    {"name": "C++", "line": ["//"], "block": ("/*", "*/")},
    ".hh":     {"name": "C++", "line": ["//"], "block": ("/*", "*/")},
    ".py":     {"name": "Python", "line": ["#"], "block": None},
    ".pyi":    {"name": "Python", "line": ["#"], "block": None},
    ".rs":     {"name": "Rust", "line": ["//"], "block": ("/*", "*/")},
    ".java":   {"name": "Java", "line": ["//"], "block": ("/*", "*/")},
    ".go":     {"name": "Go", "line": ["//"], "block": ("/*", "*/")},
    ".js":     {"name": "JavaScript", "line": ["//"], "block": ("/*", "*/")},
    ".jsx":    {"name": "JavaScript", "line": ["//"], "block": ("/*", "*/")},
    ".mjs":    {"name": "JavaScript", "line": ["//"], "block": ("/*", "*/")},
    ".ts":     {"name": "TypeScript", "line": ["//"], "block": ("/*", "*/")},
    ".tsx":    {"name": "TypeScript", "line": ["//"], "block": ("/*", "*/")},
    ".sh":     {"name": "Shell", "line": ["#"], "block": None},
    ".bash":   {"name": "Shell", "line": ["#"], "block": None},
    ".zsh":    {"name": "Shell", "line": ["#"], "block": None},
    ".ps1":    {"name": "PowerShell", "line": ["#"], "block": ("<#", "#>")},
    ".cmake":  {"name": "CMake", "line": ["#"], "block": None},
    "CMakeLists.txt": {"name": "CMake", "line": ["#"], "block": None},
    ".md":     {"name": "Markdown", "line": [], "block": None},
    ".rst":    {"name": "reStructuredText", "line": [], "block": None},
    ".json":   {"name": "JSON", "line": [], "block": None},
    ".yaml":   {"name": "YAML", "line": ["#"], "block": None},
    ".yml":    {"name": "YAML", "line": ["#"], "block": None},
    ".toml":   {"name": "TOML", "line": ["#"], "block": None},
    ".rb":     {"name": "Ruby", "line": ["#"], "block": None},
    ".php":    {"name": "PHP", "line": ["//", "#"], "block": ("/*", "*/")},
    ".swift":  {"name": "Swift", "line": ["//"], "block": ("/*", "*/")},
    ".kt":     {"name": "Kotlin", "line": ["//"], "block": ("/*", "*/")},
    ".scala":  {"name": "Scala", "line": ["//"], "block": ("/*", "*/")},
    ".lua":    {"name": "Lua", "line": ["--"], "block": ("--[[", "]]")},
    ".sql":    {"name": "SQL", "line": ["--"], "block": ("/*", "*/")},
    ".html":   {"name": "HTML", "line": [], "block": ("<!--", "-->")},
    ".css":    {"name": "CSS", "line": [], "block": ("/*", "*/")},
    ".cs":     {"name": "C#", "line": ["//"], "block": ("/*", "*/")},
    ".m":      {"name": "Objective-C", "line": ["//"], "block": ("/*", "*/")},
    ".vim":    {"name": "Vim script", "line": ['"'], "block": None},
    ".tex":    {"name": "TeX", "line": ["%"], "block": None},
}

def language_for(path: Path) -> str | None:
    name = path.name
    if name in LANGUAGES:
        return LANGUAGES[name]["name"]
    if name in ("Makefile", "Dockerfile", "Justfile"):
        return {"Makefile": "Make", "Dockerfile": "Docker", "Justfile": "Just"}[name]
    return LANGUAGES.get(path.suffix.lower(), {}).get("name")


def is_binary_file(path: Path) -> bool:
    """Binary detection: extension first, then a NUL sniff on the head.

    Files whose extension already maps to a known source language skip the
    content sniff — one less open() per file, which matters on 100k-file
    trees. A binary masquerading as `.c` is rare enough to accept.
    """
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    if language_for(path) is not None or path.name in ("Makefile", "Dockerfile", "Justfile"):
        return False
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
    except OSError:
        return True
    if b"\x00" in head:
        return True
    return False


@dataclass
class RepoFile:
    path: Path              # absolute
    rel: str                # repo-relative, always "/"-separated
    language: str | None
    size: int
    binary: bool


@dataclass
class WalkResult:
    files: list[RepoFile] = field(default_factory=list)
    skipped_dirs: list[str] = field(default_factory=list)
    total_bytes: int = 0
    tracked_only: set[str] | None = None  # git ls-files set, when available


def load_ignore_config(repo_root: Path) -> tuple[set[str], set[str]]:
    """Read .archignore if present: one pattern per line, `dir/` marks a dir."""
    extra_dirs: set[str] = set()
    extra_patterns: set[str] = set()
    cfg = repo_root / ".archignore"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("/"):
                extra_dirs.add(line[:-1])
            else:
                extra_patterns.add(line)
    return extra_dirs, extra_patterns


def walk_repo(root: Path, tracked_only: set[str] | None = None) -> WalkResult:
    """Collect source files under `root`, honouring ignore rules.

    If `tracked_only` is given (a set of "/"-separated git paths), we only
    visit tracked files -- this automatically respects .gitignore in git repos.
    """
    extra_dirs, extra_patterns = load_ignore_config(root)
    ignore_dirs = DEFAULT_IGNORE_DIRS | extra_dirs
    result = WalkResult(tracked_only=tracked_only)

    def ignored_dir(name: str) -> bool:
        return name in ignore_dirs or any(
            fnmatch.fnmatch(name, pat) for pat in extra_patterns
        )

    def ignored_file(name: str) -> bool:
        return any(fnmatch.fnmatch(name, pat) for pat in DEFAULT_IGNORE_PATTERNS) or \
               any(fnmatch.fnmatch(name, pat) for pat in extra_patterns)

    if tracked_only is not None:
        for rel in sorted(tracked_only):
            p = root / rel
            parts = Path(rel).parts
            if any(ignored_dir(part) for part in parts[:-1]) or ignored_file(parts[-1]):
                continue
            _add_file(result, root, p, rel)
        return result

    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        rel_dir = d.relative_to(root)
        # prune ignored directories in-place
        keep = []
        for name in dirnames:
            if ignored_dir(name):
                result.skipped_dirs.append(str((rel_dir / name)))
            else:
                keep.append(name)
        dirnames[:] = keep
        for fname in filenames:
            if ignored_file(fname):
                continue
            p = d / fname
            rel = str(p.relative_to(root)).replace(os.sep, "/")
            _add_file(result, root, p, rel)
    return result


def _add_file(result: WalkResult, root: Path, p: Path, rel: str) -> None:
    try:
        st = p.stat()
    except OSError:
        return
    binary = is_binary_file(p)
    result.files.append(
        RepoFile(path=p, rel=rel, language=None if binary else language_for(p),
                 size=st.st_size, binary=binary)
    )
    result.total_bytes += st.st_size


def read_text_safe(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
