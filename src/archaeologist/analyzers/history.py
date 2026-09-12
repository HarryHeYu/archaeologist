"""Hot files, recent changes, and contributor analysis (all git-derived)."""

from __future__ import annotations

import datetime as _dt
import posixpath
from collections import Counter, defaultdict
from pathlib import Path

from ..gitcmd import GitRepo
from ..models import Contributor, HotFile, RecentChanges
from ..walker import DEFAULT_IGNORE_DIRS, language_for

# non-source files that are still meaningful hot-file candidates
_META_FILES = {"README.md", "CMakeLists.txt", "Makefile", "package.json",
               "pyproject.toml", "setup.py", "Cargo.toml", "go.mod", "Dockerfile"}

# Very large histories (e.g. the Linux kernel) make full numstat passes slow.
# Cap the history window for churn/hotness scoring and say so in the output.
MAX_HISTORY_COMMITS = 10000


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def analyze_hot_files(git: GitRepo | None, tracked: list[str],
                      top_n: int = 15) -> list[HotFile]:
    """Heuristic hotness score from git history.

    score = 40 * normalized commits + 25 * normalized lines changed
          + 20 * normalized recency (commits in last 90 days)
          + 15 * normalized contributor count
    Normalization is relative to the most extreme value among candidates, so
    scores are comparable within one repository only.
    """
    if git is None or not git.is_repo():
        return []

    commits_by_file: Counter = Counter()
    contributors_by_file: defaultdict[str, set[str]] = defaultdict(set)
    lines_by_file: Counter = Counter()
    last_touch: dict[str, str] = {}

    # one pass over log with numstat + author email + date
    raw = git.try_out(
        "log", f"-n{MAX_HISTORY_COMMITS}", "--numstat", "--date=short", "--format=%x01%H%x1f%ae%x1f%cI"
    )
    if not raw:
        return []
    cutoff = (_now_utc() - _dt.timedelta(days=90)).date()
    for block in raw.split("\x01"):
        if not block.strip():
            continue
        head, _, rest = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) != 3:
            continue
        _h, email, date_s = parts
        try:
            date = _dt.datetime.fromisoformat(date_s).date()
        except ValueError:
            date = None
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            path = cols[-1]
            if "\t" in path:
                path = path.split("\t")[-1]
            if not path or path == "":
                continue
            tracked_set = tracked  # noqa: F841 (kept for clarity)
            commits_by_file[path] += 1
            contributors_by_file[path].add(email.lower())
            last_touch[path] = date_s
            try:
                a = int(cols[0]) if cols[0] != "-" else 0
            except ValueError:
                a = 0
            try:
                d = int(cols[1]) if cols[1] != "-" else 0
            except ValueError:
                d = 0
            lines_by_file[path] += a + d

    if not commits_by_file:
        return []
    tracked_set = set(tracked) if tracked else None

    def _is_candidate(path: str) -> bool:
        if tracked_set is not None and path not in tracked_set:
            return False
        parts = path.split("/")
        if any(seg in DEFAULT_IGNORE_DIRS or seg.startswith(".") for seg in parts):
            return False
        return language_for(Path(path)) is not None or parts[-1] in _META_FILES

    max_commits = max(commits_by_file.values()) or 1
    max_lines = max(lines_by_file.values()) or 1
    max_contribs = max((len(v) for v in contributors_by_file.values()), default=1) or 1
    results = []
    for path, commits in commits_by_file.items():
        if not _is_candidate(path):
            continue
        recent = 0
        if last_touch.get(path):
            try:
                if _dt.datetime.fromisoformat(last_touch[path]).date() >= cutoff:
                    # approximate recent weight: recency of last touch
                    recent = 1
            except ValueError:
                pass
        score = (
            40 * commits / max_commits
            + 25 * min(lines_by_file[path], max_lines) / max_lines
            + 20 * recent
            + 15 * len(contributors_by_file[path]) / max_contribs
        )
        results.append(HotFile(
            path=path, commits=commits, contributors=len(contributors_by_file[path]),
            lines_changed=lines_by_file[path], recent_commits=recent, score=round(score, 1),
        ))
    results.sort(key=lambda h: h.score, reverse=True)
    return results[:top_n]


def analyze_recent(git: GitRepo | None, days: int = 30) -> RecentChanges:
    empty = RecentChanges(days, 0, 0, 0, [], [], [], [], [])
    if git is None or not git.is_repo():
        return empty
    since = (_now_utc() - _dt.timedelta(days=days)).strftime("%Y-%m-%d")
    n = git.commits_since(since)
    if n == 0:
        # fall back to a one-year window so the section stays useful
        days = 365
        since = (_now_utc() - _dt.timedelta(days=days)).strftime("%Y-%m-%d")
        n = git.commits_since(since)
        if n == 0:
            return empty

    raw = git.try_out("log", f"--since={since}", "--numstat", "--format=%x01%ad%x1f%s",
                      "--date=short")
    added = deleted = 0
    dir_lines: Counter = Counter()
    new_files: list[str] = []
    deleted_files: list[str] = []
    big_commits: list[tuple[str, str, int]] = []
    commit_lines = 0
    cur_subject = cur_date = ""
    seen_names = set()

    if raw:
        for block in raw.split("\x01"):
            if not block.strip():
                continue
            head, _, rest = block.partition("\n")
            parts = head.split("\x1f")
            cur_date, cur_subject = (parts + ["", ""])[:2] if len(parts) >= 2 else ("", "")
            commit_lines = 0
            names_in_commit = []
            for line in rest.splitlines():
                cols = line.split("\t")
                if len(cols) < 3:
                    continue
                path = cols[-1].split("\t")[-1]
                names_in_commit.append(path)
                try:
                    a = int(cols[0]) if cols[0] != "-" else 0
                except ValueError:
                    a = 0
                try:
                    d = int(cols[1]) if cols[1] != "-" else 0
                except ValueError:
                    d = 0
                added += a
                deleted += d
                commit_lines += a + d
                top = posixpath.dirname(path).split("/")[0] if posixpath.dirname(path) else "(root)"
                dir_lines[top] += a + d
            if commit_lines:
                big_commits.append((cur_subject, cur_date, commit_lines))
            # creation/deletion detection via name-status in a second pass below

    # name-status pass for adds/deletes/renames
    ns = git.try_out("log", f"--since={since}", "--name-status", "--format=%x00",
                     "--diff-filter=ARD")
    if ns:
        for line in ns.splitlines():
            if not line or line.startswith("\x00"):
                continue
            cols = line.split("\t")
            if not cols:
                continue
            status, path = cols[0], cols[-1]
            if status.startswith("A") and path not in seen_names:
                new_files.append(path)
            elif status.startswith("D"):
                deleted_files.append(path)
            elif status.startswith("R"):
                old = cols[1] if len(cols) > 2 else "?"
                seen_names.add(path)
                deleted_files.append(old)
                new_files.append(path)

    areas = dir_lines.most_common(8)
    big_commits.sort(key=lambda t: t[2], reverse=True)
    return RecentChanges(
        since_days=days, commits=n, added=added, deleted=deleted,
        areas=areas, new_files=new_files[:10], deleted_files=deleted_files[:10],
        renamed=[], big_commits=big_commits[:5],
    )


def analyze_contributors(git: GitRepo | None, top_n: int = 10) -> list[Contributor]:
    if git is None or not git.is_repo():
        return []
    raw = git.try_out("log", f"-n{MAX_HISTORY_COMMITS}", "--numstat", "--date=short", "--format=%x01%an%x1f%ae%x1f%ad")
    if not raw:
        return []
    commits: Counter = Counter()
    emails: dict[str, str] = {}
    lines: Counter = Counter()
    files: defaultdict[str, set] = defaultdict(set)
    dir_hits: defaultdict[str, Counter] = defaultdict(Counter)
    last_date: dict[str, str] = {}

    for block in raw.split("\x01"):
        if not block.strip():
            continue
        head, _, rest = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) != 3:
            continue
        name, email, date = parts
        key = name.strip() or email.lower()  # aggregate by display name
        commits[key] += 1
        emails[key] = name
        last_date[key] = max(last_date.get(key, ""), date)
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            path = cols[-1].split("\t")[-1]
            files[key].add(path)
            top = posixpath.dirname(path).split("/")[0] if posixpath.dirname(path) else "(root)"
            dir_hits[key][top] += 1
            try:
                a = int(cols[0]) if cols[0] != "-" else 0
            except ValueError:
                a = 0
            try:
                d = int(cols[1]) if cols[1] != "-" else 0
            except ValueError:
                d = 0
            lines[key] += a + d

    result = []
    for key, n in commits.most_common(top_n):
        tops = [d for d, _ in dir_hits[key].most_common(3)]
        result.append(Contributor(
            name=emails[key], email=key, commits=n, lines_changed=lines[key],
            files_touched=len(files[key]), top_areas=tops, last_commit=last_date[key],
        ))
    return result
