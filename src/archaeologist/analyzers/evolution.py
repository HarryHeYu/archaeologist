"""Evolution timelines: `arch history <path>` and `arch history <keyword>`."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from ..gitcmd import GitRepo, GitError


def _git(root: Path) -> GitRepo | None:
    g = GitRepo(root)
    try:
        return g if g.is_repo() else None
    except GitError:
        return None


def file_evolution(root: Path, rel: str, max_events: int = 14) -> dict | None:
    """Timeline for one file: creation, renames, large rewrites, activity by year."""
    git = _git(root)
    if git is None or not (root / rel).is_file():
        return None
    raw = git.try_out("log", "--follow", "--date=short", "--numstat",
                      "--format=%x01%ad%x1f%h%x1f%an%x1f%s", "--", rel)
    if not raw:
        return None
    events = []
    yearly: dict[str, int] = defaultdict(int)
    contributors: set[str] = set()
    created = None
    for block in raw.split("\x01"):
        if not block.strip():
            continue
        head, _, rest = block.partition("\n")
        date, h, author, subject = (head.split("\x1f") + ["", "", "", ""])[:4]
        year = date[:4]
        contributors.add(author)
        added = deleted = 0
        touched = False
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) >= 3 and (rel in cols[2] or cols[2].endswith("/" + rel)):
                touched = True
                try:
                    added += int(cols[0]) if cols[0] != "-" else 0
                    deleted += int(cols[1]) if cols[1] != "-" else 0
                except ValueError:
                    pass
        if not touched:
            continue
        created = date  # blocks arrive newest-first; the last touched one is the oldest
        yearly[year] += added + deleted
        kind = None
        if "rename" in subject.lower() or "move" in subject.lower():
            kind = "rename/move"
        elif added + deleted >= 400:
            kind = "large rewrite"
        elif added and not deleted and added > 50:
            kind = "major addition"
        if kind or added + deleted >= 100:
            events.append({"date": date, "kind": kind or "change",
                           "detail": f"+{added:,} -{deleted:,}", "subject": subject[:70]})
    events.sort(key=lambda e: e["date"], reverse=True)
    return {"path": rel, "created": created, "commits": len(events) if not events else None,
            "events": events[:max_events], "yearly": dict(sorted(yearly.items())),
            "contributors": len(contributors)}


def keyword_evolution(root: Path, keyword: str, max_events: int = 16) -> dict | None:
    """Timeline for a module/keyword: find related paths + matching commits,
    aggregate by year. No semantic understanding — filenames, paths and
    commit messages only, as documented."""
    git = _git(root)
    if git is None:
        return None
    kw = keyword.lower()

    # related paths from the current tree
    related_paths = []
    ls = git.try_out("ls-files", "-z") or ""
    all_files = [p for p in ls.split("\x00") if p]
    for p in all_files:
        pl = p.lower()
        if kw in Path(pl).stem or kw in pl.split("/")[0].lower() or kw in Path(pl).name.lower():
            related_paths.append(p)
        if len(related_paths) >= 40:
            break

    # matching commits (subject mentions keyword)
    raw = git.try_out("log", "--date=short", "--numstat", "--format=%x01%ad%x1f%h%x1f%s")
    commits = []
    yearly: dict[str, dict] = defaultdict(lambda: {"commits": 0, "lines": 0})
    if raw:
        for block in raw.split("\x01"):
            if not block.strip():
                continue
            head, _, rest = block.partition("\n")
            date, h, subject = (head.split("\x1f") + ["", ""])[:3]
            blob = block.lower()
            subject_hit = kw in subject.lower()
            path_hit = any(kw in line.lower() for line in rest.splitlines()
                           if "\t" in line)
            if not (subject_hit or path_hit):
                continue
            lines = 0
            for line in rest.splitlines():
                cols = line.split("\t")
                if len(cols) >= 3:
                    try:
                        lines += int(cols[0] if cols[0] != "-" else 0)
                        lines += int(cols[1] if cols[1] != "-" else 0)
                    except ValueError:
                        pass
            yearly[date[:4]]["commits"] += 1
            yearly[date[:4]]["lines"] += lines
            if subject_hit:
                commits.append({"date": date, "hash": h, "subject": subject[:80]})
    return {"keyword": keyword, "related_paths": related_paths[:20],
            "yearly": dict(sorted(yearly.items())),
            "matching_commits": commits[:max_events]}
