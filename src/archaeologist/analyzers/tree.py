"""`arch tree` — a meaningful, pruned repository tree."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from ..models import Analysis
from .structure import classify_dir


def build_tree(a: Analysis, max_depth: int = 3, max_children: int = 24) -> list[str]:
    """Render a pruned tree: directories with file counts and inferred roles,
    source files at the top level, no dependency dumps."""
    # directory stats across the whole walk
    dir_files: Counter = Counter()
    dir_subdirs: defaultdict[str, set] = defaultdict(set)
    for f in a.walk.files:
        parts = Path(f.rel).parts
        for i in range(1, len(parts) + 1):
            dir_files["/".join(parts[:i])] += 1
        if len(parts) > 1:
            dir_subdirs["/".join(parts[:-1])].add(parts[-1])
        else:
            dir_subdirs[""].add(parts[-1])

    # top-level source files (git-root files)
    root_files = sorted(p for p in dir_subdirs.get("", set())
                        if (a.root / p).is_file())

    lines = [f"{a.root.name}/"]
    for name in root_files[:12]:
        lines.append(f"  {name}")
    if len(root_files) > 12:
        lines.append(f"  … {len(root_files) - 12} more files")

    top_dirs = sorted(
        (d for d in dir_files if "/" not in d and d in dir_subdirs),
        key=lambda d: -dir_files[d],
    )
    for d in top_dirs:
        role = classify_dir(d)
        tag = f"  # {role}" if role else ""
        lines.append(f"  {d}/{tag}")
        lines.extend(_children(d, dir_files, dir_subdirs, a,
                               depth=1, max_depth=max_depth, max_children=max_children))
    return lines


def _children(dir_path: str, dir_files: Counter, dir_subdirs, a: Analysis,
              depth: int, max_depth: int, max_children: int) -> list[str]:
    if depth >= max_depth:
        return []
    indent = "  " * (depth + 1)
    subdirs = [d for d in dir_subdirs.get(dir_path, set())
               if (a.root / dir_path / d).is_dir()]
    out = []
    for name in sorted(subdirs, key=lambda n: -dir_files[f"{dir_path}/{n}"])[:max_children]:
        child = f"{dir_path}/{name}"
        role = classify_dir(child)
        tag = f"  # {role}" if role else ""
        out.append(f"{indent}{name}/  ({dir_files[child]} files){tag}")
    if len(subdirs) > max_children:
        out.append(f"{indent}… {len(subdirs) - max_children} more subdirectories")
    return out
