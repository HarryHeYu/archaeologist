"""Repository overview analysis (Phase 1)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from ..gitcmd import GitRepo, GitError
from ..models import Overview
from ..walker import WalkResult


def analyze_overview(root: Path, git: GitRepo | None, walk: WalkResult) -> Overview:
    name = root.resolve().name
    ov = Overview(name=name, path=str(root.resolve()), is_git=False)

    if git is None:
        ov.notes.append("Not a git repository: git-derived sections are unavailable.")
        ov.tracked_files = len(walk.files)
        ov.size_mb = walk.total_bytes / (1024 * 1024)
        return ov

    try:
        ov.is_git = git.is_repo()
    except GitError:
        ov.is_git = False
    if not ov.is_git:
        ov.notes.append("Not a git repository: git-derived sections are unavailable.")
        ov.tracked_files = len(walk.files)
        ov.size_mb = walk.total_bytes / (1024 * 1024)
        return ov

    ov.branch = git.branch()
    ov.head = git.head()
    ov.remote_url = git.remote_url()
    ov.shallow = git.is_shallow()
    first = git.first_commit()
    last = git.last_commit()
    ov.first_commit = first
    ov.last_commit = last
    ov.total_commits = git.commit_count()

    # contributor count
    emails = git.try_out("log", "--format=%ae")
    if emails:
        ov.contributors = len({e.strip().lower() for e in emails.splitlines() if e.strip()})

    if first and first.date:
        try:
            d0 = _dt.datetime.fromisoformat(first.date)
            d1 = _dt.datetime.now(_dt.timezone.utc)
            ov.age_days = max(0, (d1 - d0).days)
        except ValueError:
            pass

    # tracked file count (without .gitignore noise)
    ls = git.try_out("ls-files", "-z")
    tracked = 0
    if ls:
        tracked = len([p for p in ls.split("\x00") if p])
    ov.tracked_files = tracked or len(walk.files)
    ov.size_mb = walk.total_bytes / (1024 * 1024)

    if ov.shallow:
        ov.notes.append("Shallow clone: history-based statistics are lower bounds.")
    if ov.branch is None and ov.head:
        ov.notes.append("Detached HEAD.")
    return ov
