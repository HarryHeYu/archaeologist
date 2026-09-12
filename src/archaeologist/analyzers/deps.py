"""Dependency extraction (include/import) — best effort, regex level.

Builds a file -> file dependency view. Internal edges only; external modules
(site-packages, system headers, crates.io, npm) are recognized and labeled
external instead of silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# per-language target resolution ------------------------------------------------

_C_INCLUDE = re.compile(r'^\s*#\s*include\s*([<"])([^">]+)[">]', re.M)
_PY_FROM = re.compile(r'^\s*from\s+([\w.]+)\s+import', re.M)
_PY_IMPORT = re.compile(r'^\s*import\s+([\w.,\s]+?)(?:\s+as\s+\w+)?\s*$', re.M)
_RS_USE = re.compile(r'^\s*use\s+([\w:]+)', re.M)
_RS_MOD = re.compile(r'^\s*(?:pub\s+)?mod\s+(\w+)\s*;', re.M)
_TS_IMPORT = re.compile(r'^\s*(?:import\s+[^;]*?from\s+|import\s+|require\(\s*)[\'"]([^\'"]+)[\'"]', re.M)
_GO_IMPORT_BLOCK = re.compile(r'import\s*\(([^)]*)\)', re.S)
_GO_IMPORT = re.compile(r'"([^"]+)"')
_JAVA_IMPORT = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)\s*;', re.M)


@dataclass
class FileDeps:
    path: str                                   # repo-relative
    language: Optional[str]
    internal: list[str] = field(default_factory=list)   # repo-relative targets
    external: list[str] = field(default_factory=list)   # external module names


def _resolve_python(root: Path, module: str, source_rel: str) -> Optional[str]:
    """Map a dotted module to a repo-relative file. Handles relative imports
    (`from .store import x`, `from ..pkg.mod import y`) by counting the
    leading dots as package levels above the importing file's package."""
    dots = len(module) - len(module.lstrip("."))
    parts = [p for p in module[dots:].split(".") if p]
    base = Path(source_rel).parent
    # one leading dot = the importing file's own package; each extra dot
    # climbs one package level
    for _ in range(max(0, dots - 1)):
        if base.parent == base:
            return None
        base = base.parent
    if not parts:
        # `from . import x` — the target is the current package's __init__
        pkg_init = base / "__init__.py"
        return pkg_init.as_posix() if (root / pkg_init).is_file() else None
    while True:
        cand_pkg = root / base.joinpath(*parts) / "__init__.py"
        cand_mod = root / base.joinpath(*parts).with_suffix(".py")
        if cand_pkg.is_file():
            return (base.joinpath(*parts) / "__init__.py").as_posix()
        if cand_mod.is_file():
            return base.joinpath(*parts).with_suffix(".py").as_posix()
        # absolute import not found below base — try upward if we're in a package
        if (root / base / "__init__.py").is_file() and base.parent != base:
            base = base.parent
            continue
        return None


def _resolve_ts(spec: str, source_rel: str, root: Path) -> Optional[str]:
    if not spec.startswith("."):
        return None
    base = (Path(source_rel).parent / spec)
    for cand in (base, *[base.with_suffix(s) for s in (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js")]):
        p = root / cand
        if p.is_file():
            return cand.as_posix()
    return None


def _resolve_c(include: str, source_rel: str, root: Path) -> Optional[str]:
    """Resolve #include: quoted first relative to includer, then repo-wide."""
    if include.endswith(".h") or include.endswith(".hpp"):
        rel = (Path(source_rel).parent / include)
        if (root / rel).is_file():
            return rel.as_posix()
        matches = [f for f in _C_HEADER_INDEX.get(root, []) if f.endswith("/" + include) or f == include]
        if len(matches) == 1:
            return matches[0]
    return None


_C_HEADER_INDEX: dict[Path, list[str]] = {}


def build_header_index(root: Path, all_files: list[str]) -> None:
    _C_HEADER_INDEX[root] = [f for f in all_files
                             if f.endswith((".h", ".hpp", ".hh"))]


def extract_deps(root: Path, rel: str, text: str) -> FileDeps:
    from ..walker import language_for
    path = Path(rel)
    lang = language_for(path)
    deps = FileDeps(path=rel, language=lang)

    if lang in ("C", "C++", "C/C++ Header", "Objective-C"):
        for _q, inc in _C_INCLUDE.findall(text):
            target = _resolve_c(inc, rel, root)
            if target:
                deps.internal.append(target)
            else:
                deps.external.append(inc)
    elif lang == "Python":
        modules = [m.group(1) for m in _PY_FROM.finditer(text)]
        for m in _PY_IMPORT.finditer(text):
            modules.extend(n.strip() for n in m.group(1).split(","))
        for module in modules:
            if not module:
                continue
            for name in {n.strip() for n in module.split(",") if n.strip()}:
                target = _resolve_python(root, name, rel)
                if target:
                    deps.internal.append(target)
                elif name.lstrip("."):
                    deps.external.append(name.lstrip(".").split(".")[0])
    elif lang == "Rust":
        for m in _RS_USE.finditer(text):
            crate = m.group(1).split("::")[0]
            if crate == "crate" or crate == "self" or crate == "super":
                # intra-crate: try file mapping for `use crate::foo::bar`
                rest = m.group(1).split("::")[1:2]
                if rest:
                    cand = Path(rel).parent / (rest[0] + ".rs")
                    if (root / cand).is_file():
                        deps.internal.append(cand.as_posix())
                        continue
            deps.external.append(crate)
        for m in _RS_MOD.finditer(text):
            cand = Path(rel).parent / (m.group(1) + ".rs")
            if (root / cand).is_file():
                deps.internal.append(cand.as_posix())
    elif lang in ("TypeScript", "JavaScript"):
        for m in _TS_IMPORT.finditer(text):
            target = _resolve_ts(m.group(1), rel, root)
            if target:
                deps.internal.append(target)
            else:
                deps.external.append(m.group(1).split("/")[0])
    elif lang == "Go":
        for block in _GO_IMPORT_BLOCK.findall(text):
            for m in _GO_IMPORT.finditer(block):
                deps.external.append(m.group(1))
        for m in re.finditer(r'^\s*import\s+"([^"]+)"', text, re.M):
            deps.external.append(m.group(1))
    elif lang == "Java":
        for m in _JAVA_IMPORT.finditer(text):
            deps.external.append(m.group(1))
    # dedupe, preserve order
    deps.internal = list(dict.fromkeys(deps.internal))
    deps.external = list(dict.fromkeys(deps.external))
    return deps
