"""LOC counting per language, with comment/blank separation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .walker import LANGUAGES, RepoFile, read_text_safe


@dataclass
class Loc:
    total: int = 0
    code: int = 0
    comment: int = 0
    blank: int = 0

    def add(self, other: "Loc") -> None:
        self.total += other.total
        self.code += other.code
        self.comment += other.comment
        self.blank += other.blank


def count_loc(text: str, lang: str | None) -> Loc:
    """Count code/comment/blank lines.

    This is a line-based heuristic (same approach as tokei/cloc for simple
    counting): a line inside a block comment is a comment line; a line that
    only contains a line-comment prefix is a comment line; code trailing
    comments still count as code. Good enough for repo overview purposes.
    """
    loc = Loc()
    spec = None
    for key, val in LANGUAGES.items():
        if val["name"] == lang:
            spec = val
            break
    line_prefixes = spec["line"] if spec else []
    block = spec["block"] if spec else None

    in_block = False
    close_marker = None
    for raw in text.splitlines():
        loc.total += 1
        stripped = raw.strip()
        if not stripped:
            loc.blank += 1
            continue
        if in_block:
            loc.comment += 1
            if close_marker and close_marker in stripped:
                in_block = False
            continue
        if block and block[0] in stripped:
            loc.comment += 1
            close_marker = block[1]
            in_block = True
            if close_marker and close_marker in stripped.split(block[0], 1)[1]:
                in_block = False
            continue
        if line_prefixes and any(stripped.startswith(p) for p in line_prefixes):
            loc.comment += 1
            continue
        loc.code += 1
    return loc


def file_loc(f: RepoFile) -> Loc:
    if f.binary or f.language is None:
        return Loc()
    text = read_text_safe(f.path)
    if text is None:
        return Loc()
    return count_loc(text, f.language)
