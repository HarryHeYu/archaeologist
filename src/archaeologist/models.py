"""Shared analysis context and result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .gitcmd import Commit, GitRepo, GitError
from .walker import WalkResult, walk_repo


@dataclass
class Overview:
    name: str
    path: str
    is_git: bool
    branch: Optional[str] = None
    head: Optional[str] = None
    remote_url: Optional[str] = None
    age_days: Optional[int] = None
    first_commit: Optional[Commit] = None
    last_commit: Optional[Commit] = None
    total_commits: int = 0
    contributors: int = 0
    tracked_files: int = 0
    size_mb: float = 0.0
    shallow: bool = False
    detached: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class LanguageStat:
    name: str
    files: int = 0
    total: int = 0
    code: int = 0
    comment: int = 0
    blank: int = 0


@dataclass
class StructureDir:
    rel: str            # e.g. "src"
    role: str           # e.g. "main source code"
    files: int
    code: int


@dataclass
class Entrypoint:
    path: str
    evidence: str


@dataclass
class HotFile:
    path: str
    commits: int
    contributors: int
    lines_changed: int
    recent_commits: int
    score: float


@dataclass
class RecentChanges:
    since_days: int
    commits: int
    added: int
    deleted: int
    areas: list[tuple[str, int]]            # (label, lines changed) top areas
    new_files: list[str]
    deleted_files: list[str]
    renamed: list[str]
    big_commits: list[tuple[str, str, int]]  # (subject, author_date, lines)


@dataclass
class Contributor:
    name: str
    email: str
    commits: int
    lines_changed: int
    files_touched: int
    top_areas: list[str]
    last_commit: str


@dataclass
class Analysis:
    root: Path
    overview: Overview
    languages: list[LanguageStat]
    structure: list[StructureDir]
    entrypoints: list[Entrypoint]
    hot_files: list[HotFile]
    recent: RecentChanges
    contributors: list[Contributor]
    walk: WalkResult
