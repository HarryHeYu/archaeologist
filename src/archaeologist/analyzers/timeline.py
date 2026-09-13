"""`arch timeline` — repository evolution timeline by year.

Derived purely from git data: commit counts, change magnitude per year, when
top-level areas first appeared, and the largest commits per year. No semantic
interpretation — statements describe the data, they don't guess intent.
"""

from __future__ import annotations

import posixpath
from collections import defaultdict

from ..gitcmd import GitRepo, GitError
from ..walker import DEFAULT_IGNORE_DIRS
from .history import MAX_HISTORY_COMMITS


def build_timeline(root, git: GitRepo, max_years: int = 12) -> dict | None:
    try:
        if not git.is_repo():
            return None
    except GitError:
        return None
    raw = git.try_out("log", f"-n{MAX_HISTORY_COMMITS}", "--date=short", "--numstat",
                      "--reverse", "--format=%x01%ad%x1f%s")
    if not raw:
        return None

    years: dict[str, dict] = defaultdict(lambda: {
        "commits": 0, "lines": 0, "dirs": set(), "biggest": (0, "", "")})
    seen_dirs: set[str] = set()

    for block in raw.split("\x01"):
        if not block.strip():
            continue
        head, _, rest = block.partition("\n")
        date, subject = (head.split("\x1f") + ["", ""])[:2]
        year = date[:4]
        y = years[year]
        y["commits"] += 1
        lines = 0
        top_dirs = set()
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            path = cols[-1].split("\t")[-1]
            if "=>" in path or path.startswith('"'):
                continue  # rename artifacts, not a clean path
            top = posixpath.dirname(path).split("/")[0] if posixpath.dirname(path) else "(root)"
            if top in DEFAULT_IGNORE_DIRS or top.startswith("."):
                continue
            top_dirs.add(top)
            try:
                lines += int(cols[0] if cols[0] != "-" else 0)
                lines += int(cols[1] if cols[1] != "-" else 0)
            except ValueError:
                pass
        y["lines"] += lines
        for d in top_dirs:
            if d not in seen_dirs:
                seen_dirs.add(d)
                y["dirs"].add(d)
        if lines > y["biggest"][0]:
            y["biggest"] = (lines, date, subject)

    ordered = dict(sorted(years.items())[-max_years:])
    return {"years": ordered,
            "note": "new areas = top-level directories first seen in that year's diffs"}


def render_timeline(t: dict) -> str:
    L = ["", "Repository Timeline", "───────────────────"]
    for year, y in t["years"].items():
        L.append(f"{year}")
        stmt = f"  {y['commits']} commits, {y['lines']:,} lines changed"
        if y["dirs"]:
            areas = ", ".join(f"`{d}/`" if d != "(root)" else d
                              for d in sorted(y["dirs"])[:5])
            more = f" (+{len(y['dirs']) - 5} more)" if len(y["dirs"]) > 5 else ""
            stmt += f";  new areas: {areas}{more}"
        L.append(stmt)
        lines, date, subject = y["biggest"]
        if lines:
            L.append(f"  largest change: {date} +-{lines:,}  {subject[:66]}")
    L.append("")
    L.append(f"_{t['note']}._")
    return "\n".join(L) + "\n"
