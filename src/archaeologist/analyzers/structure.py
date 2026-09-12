"""Language statistics and repository-structure classification."""

from __future__ import annotations

import datetime as _dt
import os
from collections import Counter, defaultdict
from pathlib import Path

from ..loc_counter import Loc, file_loc
from ..models import Entrypoint, LanguageStat, StructureDir
from ..walker import RepoFile, WalkResult, read_text_safe

# Directory role heuristics: canonical name -> human description.
DIR_ROLES = [
    (("src", "lib", "source", "core"), "main source code"),
    (("include", "headers"), "public headers / interfaces"),
    (("tests", "test", "spec", "specs", "unittests", "e2e", "integration"), "tests"),
    (("docs", "doc", "documentation", "manual", "man"), "documentation"),
    (("examples", "example", "samples", "demo", "demos", "tutorials"), "examples"),
    (("tools", "tool", "scripts", "script", "bin", "utils"), "tooling / scripts"),
    (("benchmarks", "benchmark", "bench"), "benchmarks"),
    (("third_party", "thirdparty", "vendor", "external", "deps", "submodules"), "third-party dependencies"),
    (("build", "dist", "out", "cmake", "obj"), "build output"),
    (("assets", "images", "icons", "fonts", "media", "static", "resources"), "assets"),
    (("ci", ".github", "azure-pipelines"), "CI configuration"),
    (("config", "configs", "settings", "conf"), "configuration"),
    (("plugins", "extensions", "addons"), "plugins / extensions"),
    (("api", "apis", "server", "backend", "service", "services"), "server / API"),
    (("frontend", "web", "ui", "client", "app"), "frontend / UI"),
    (("pkg", "packages", "modules", "apps", "cmd"), "packages / sub-projects"),
]


def classify_dir(rel: str) -> str | None:
    """Return a human role for a top-level dir name, or None if unknown."""
    name = rel.strip("/").lower()
    base = name.split("/")[-1]
    if name.startswith("."):
        return None
    for names, role in DIR_ROLES:
        if base in names:
            return role
    return None


def analyze_languages(walk: WalkResult, max_files: int = 4000) -> list[LanguageStat]:
    """Count LOC per language. Falls back to extension-only counting for
    very large trees (reading every file would be slow)."""
    by_lang: dict[str, LanguageStat] = {}
    text_files = [f for f in walk.files if not f.binary and f.language]
    if len(text_files) > max_files:
        # Fast path: count lines without classifying comments, in parallel
        # (line counting is I/O bound; threads overlap disk reads).
        by_ext_files: Counter = Counter()
        by_ext_lines: Counter = Counter()
        from concurrent.futures import ThreadPoolExecutor

        def _count(f: RepoFile) -> tuple[str, int]:
            n = 0
            try:
                with open(f.path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        n += chunk.count(b"\n")
            except OSError:
                pass
            return f.language, n

        with ThreadPoolExecutor(max_workers=16) as pool:
            for lang, n in pool.map(_count, text_files):
                by_ext_files[lang] += 1
                by_ext_lines[lang] += n
        stats = []
        for lang, files in by_ext_files.most_common():
            lines = by_ext_lines[lang]
            stats.append(LanguageStat(name=lang, files=files, total=lines, code=lines))
        return stats

    locs: dict[str, Loc] = defaultdict(Loc)
    counts: Counter = Counter()
    for f in text_files:
        counts[f.language] += 1
        locs[f.language].add(file_loc(f))
    stats = [
        LanguageStat(name=lang, files=files, total=locs[lang].total,
                     code=locs[lang].code, comment=locs[lang].comment,
                     blank=locs[lang].blank)
        for lang, files in counts.items()
    ]
    stats.sort(key=lambda s: s.code, reverse=True)
    return stats


def analyze_structure(walk: WalkResult, languages: list[LanguageStat]) -> list[StructureDir]:
    """Group files into meaningful top-level directories with roles."""
    # files per top-level dir (or top-level loose files -> "(root)")
    code_by_dir: Counter = Counter()
    files_by_dir: Counter = Counter()
    for f in walk.files:
        if f.binary or f.language is None:
            continue
        parts = Path(f.rel).parts
        top = parts[0] if len(parts) > 1 else "(root)"
        code_by_dir[top] += 0  # ensure presence; real counts added below
    # code counts need LOC; approximate with file count * avg? No: recompute cheaply
    # by sampling the per-language average code/file ratio.
    avg_code = {}
    for s in languages:
        if s.files:
            avg_code[s.name] = s.code / s.files
    for f in walk.files:
        if f.binary or f.language is None:
            continue
        parts = Path(f.rel).parts
        top = parts[0] if len(parts) > 1 else "(root)"
        files_by_dir[top] += 1
        code_by_dir[top] += int(avg_code.get(f.language, 40))

    dirs = []
    for top, files in files_by_dir.most_common():
        if top == "(root)" and files < 3:
            continue
        role = classify_dir(top) if top != "(root)" else "repo root files"
        dirs.append(StructureDir(rel=top, role=role or "unclassified",
                                 files=files, code=code_by_dir[top]))
    return dirs


# -- entrypoints ----------------------------------------------------------------

def analyze_entrypoints(walk: WalkResult) -> list[Entrypoint]:
    """Best-effort entrypoint detection via filenames and light content scans."""
    eps: list[Entrypoint] = []
    seen: set[str] = set()

    def add(path: str, evidence: str) -> None:
        if path not in seen:
            seen.add(path)
            eps.append(Entrypoint(path=path, evidence=evidence))

    for f in walk.files:
        rel = f.rel
        parts = Path(rel).parts
        name = parts[-1]
        # filename-based signals
        if name in ("main.c", "main.cpp", "main.cc", "main.rs", "Main.java", "main.m"):
            add(rel, "main file")
        elif name == "__main__.py" and "__pycache__" not in rel:
            add(rel, "python package entry (__main__.py)")
        elif name == "main.go":
            add(rel, "go main package")
        elif name in ("cli.py", "cli.ts", "cli.js", "server.py", "app.py") and len(parts) <= 3:
            add(rel, "likely CLI/server script by name")
        elif name == "setup.py" or name == "pyproject.toml":
            pass  # metadata, handled below

    # content-based signals on candidate text files
    content_checked = 0
    for f in walk.files:
        if content_checked >= 800:
            break
        if f.binary or f.language is None or f.size > 500_000:
            continue
        text = read_text_safe(f.path)
        if text is None:
            continue
        content_checked += 1
        if "if __name__ ==" in text and '__name__ == "__main__"' in text:
            add(f.rel, 'has `if __name__ == "__main__"`')
        elif "public static void main" in text:
            add(f.rel, "contains public static void main")
        elif "WinMain(" in text or "wmain(" in text or "int main(" in text:
            if f.language in ("C", "C++"):
                add(f.rel, "defines main()/WinMain()")
        elif f.language == "Rust" and "fn main(" in text:
            add(f.rel, "defines fn main()")
        # package metadata entrypoints
        if f.rel in ("pyproject.toml", "setup.py", "setup.cfg"):
            import re
            for m in re.finditer(r"console_scripts\s*\]\s*\n(.*?)(?=\n\[|\Z)", text, re.S):
                block = m.group(1)
                for line in block.splitlines():
                    if "=" in line:
                        cmd = line.split("=")[0].strip()
                        if cmd:
                            add(f.rel, f"console_script: {cmd}")
        if f.rel == "package.json":
            import json
            try:
                data = json.loads(text)
            except ValueError:
                data = {}
            if isinstance(data.get("bin"), (str, dict)):
                add(f.rel, 'package.json "bin"')
            elif data.get("main"):
                add(f.rel, f'package.json main: {data["main"]}')
            scripts = data.get("scripts") or {}
            for key in ("start", "cli"):
                if key in scripts and key == "start":
                    add(f.rel, f'npm script "start": {scripts[key]}'[:80])

    return eps
