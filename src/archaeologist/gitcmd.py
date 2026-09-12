"""Thin wrapper around the `git` command line.

All git data comes from real git invocations; we never guess. The wrapper
raises :class:`GitError` on failure so callers can degrade gracefully.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """A git command failed or git is unavailable."""


@dataclass
class Commit:
    hash: str
    author: str
    email: str
    date: str  # ISO 8601
    subject: str


class GitRepo:
    """A handle on a git repository rooted at `path`."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _run(self, *args: str, text: bool = True, check: bool = True):
        cmd = ["git", "-C", str(self.path), *args]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=text, encoding="utf-8",
                errors="replace", check=False,
            )
        except FileNotFoundError as exc:  # git not installed
            raise GitError("git executable not found") from exc
        if check and proc.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed: {proc.stderr.strip()[:300]}"
            )
        return proc

    def out(self, *args: str) -> str:
        return self._run(*args).stdout.strip()

    def try_out(self, *args: str) -> str | None:
        """Like `out` but returns None instead of raising."""
        proc = self._run(*args, check=False)
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    def lines(self, *args: str) -> list[str]:
        return [l for l in self.out(*args).splitlines() if l.strip()]

    # -- repository identity -------------------------------------------------

    def is_repo(self) -> bool:
        proc = self._run("rev-parse", "--is-inside-work-tree", check=False)
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def is_shallow(self) -> bool:
        return self.try_out("rev-parse", "--is-shallow-repository") == "true"

    def head(self) -> str | None:
        return self.try_out("rev-parse", "--short", "HEAD")

    def branch(self) -> str | None:
        b = self.try_out("rev-parse", "--abbrev-ref", "HEAD")
        return None if b in (None, "HEAD") else b  # detached HEAD

    def remote_url(self) -> str | None:
        return self.try_out("remote", "get-url", "origin")

    def commit_count(self) -> int:
        n = self.try_out("rev-list", "--count", "HEAD")
        return int(n) if n else 0

    def first_commit(self) -> Commit | None:
        hash_ = self.try_out("rev-list", "--max-parents=0", "HEAD")
        if not hash_:
            return None
        return self._commit_of(hash_.splitlines()[-1])

    def last_commit(self) -> Commit | None:
        return self._commit_of()

    def _commit_of(self, *args: str) -> Commit | None:
        raw = self.try_out(
            "log", "-1", "--format=%H%x1f%an%x1f%ae%x1f%cI%x1f%s", *args
        )
        if not raw:
            return None
        parts = raw.split("\x1f")
        return Commit(*parts)

    def commit_date(self, rev: str) -> str | None:
        return self.try_out("log", "-1", "--format=%cI", rev)

    # -- history queries -----------------------------------------------------

    def numstat(self, rev_range: str | None = None) -> list[tuple[str, str, str]]:
        """Return (added, deleted, path) triples; renames yield the new path."""
        args = ["log", "--numstat", "--format=%x00"]
        if rev_range:
            args.append(rev_range)
        raw = self._run(*args).stdout
        result: list[tuple[str, str, str]] = []
        for line in raw.splitlines():
            if not line or line.startswith("\x00"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                added, deleted, path = parts[0], parts[1], parts[2]
                if "\t" in path:  # "old => new" or "old{a => b}new" rename forms
                    path = path.split("\t")[-1]
                if path.startswith('"'):
                    # quoted non-ascii path; ask git to re-encode later -- keep raw
                    path = path.strip('"')
                result.append((added, deleted, path))
        return result

    def log(self, fmt: str, extra: list[str] | None = None) -> list[str]:
        args = ["log", f"--format={fmt}"]
        if extra:
            args.extend(extra)
        return self.lines(*args)

    def commits_since(self, since: str) -> int:
        n = self.try_out("rev-list", "--count", f"--since={since}", "HEAD")
        return int(n) if n else 0
