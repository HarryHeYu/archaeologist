"""Markdown report generation (independent, readable without this tool)."""

from __future__ import annotations

import datetime as _dt

from . import __version__
from .models import Analysis


def generate_report(a: Analysis) -> str:
    o = a.overview
    now = _dt.date.today().isoformat()
    out: list[str] = []
    w = out.append

    w(f"# Repository Archaeology Report: {o.name}")
    w("")
    w(f"_Generated {now} by repo-archaeologist v{__version__}_")
    w("")

    # Overview
    w("## Overview")
    w("")
    w(f"- **Path:** `{o.path}`")
    if o.is_git:
        w(f"- **Git:** yes — branch `{o.branch or 'detached HEAD'}`, HEAD `{o.head}`")
        if o.remote_url:
            w(f"- **Remote:** {o.remote_url}")
        w(f"- **Commits:** {o.total_commits:,} across **{o.contributors}** contributors")
        if o.first_commit and o.first_commit.date:
            w(f"- **First commit:** {o.first_commit.date[:10]} ({o.age_days} days ago)")
        if o.last_commit and o.last_commit.date:
            w(f"- **Last commit:** {o.last_commit.date[:10]} — {o.last_commit.subject}")
        w(f"- **Tracked files:** {o.tracked_files:,} — **size:** {o.size_mb:.1f} MB")
        for n in o.notes:
            w(f"- **Note:** {n}")
    else:
        w("- **Git:** not a git repository — history sections unavailable")
        w(f"- **Files:** {len(a.walk.files):,} — **size:** {o.size_mb:.1f} MB")
    w("")

    # Languages
    w("## Languages")
    w("")
    if a.languages:
        total_code = sum(s.code for s in a.languages) or 1
        w("| Language | Share | Code LOC | Files |")
        w("|---|---:|---:|---:|")
        for s in a.languages[:12]:
            w(f"| {s.name} | {100 * s.code / total_code:.1f}% | {s.code:,} | {s.files} |")
        if len(a.languages) > 12:
            other = sum(s.code for s in a.languages[12:])
            w(f"| Other | {100 * other / total_code:.1f}% | {other:,} | — |")
    else:
        w("No recognized source files.")
    w("")

    # Structure
    w("## Structure")
    w("")
    if a.structure:
        w("| Directory | Inferred role | Files | ~LOC |")
        w("|---|---|---:|---:|")
        for d in a.structure[:16]:
            w(f"| `{d.rel}/` | {d.role} | {d.files} | ~{d.code:,} |")
    w("")

    # Entrypoints
    w("## Entrypoints")
    w("")
    if a.entrypoints:
        for e in a.entrypoints[:10]:
            w(f"- `{e.path}` — {e.evidence}")
    else:
        w("None detected.")
    w("")

    # Hot files
    w("## Hot Files")
    w("")
    w("_Most modified files per git history — a proxy for where the project's complexity lives._")
    w("")
    if a.hot_files:
        w("| File | Commits | Contributors | Lines changed | Score |")
        w("|---|---:|---:|---:|---:|")
        for h in a.hot_files[:12]:
            w(f"| `{h.path}` | {h.commits} | {h.contributors} | {h.lines_changed:,} | {h.score} |")
    else:
        w("Unavailable (no git history).")
    w("")

    # Recent
    r = a.recent
    w(f"## Recent Activity (last {r.since_days} days)")
    w("")
    if r.commits:
        w(f"{r.commits} commits, +{r.added:,} / -{r.deleted:,} lines.")
        w("")
        if r.areas:
            w("Most changed areas:")
            w("")
            for name, lines in r.areas:
                w(f"- `{name}`: {lines:,} lines")
        if r.new_files:
            w("")
            w(f"New files: {', '.join('`' + f + '`' for f in r.new_files[:6])}")
        if r.big_commits:
            w("")
            w("Largest commits:")
            w("")
            for subject, date, lines in r.big_commits:
                w(f"- {date} — {subject} (+-{lines:,})")
    else:
        w("No commits in this window.")
    w("")

    # Contributors
    w("## Contributors")
    w("")
    if a.contributors:
        w("| Contributor | Commits | Files touched | Lines changed | Main areas |")
        w("|---|---:|---:|---:|---|")
        for c in a.contributors:
            w(f"| {c.name} | {c.commits} | {c.files_touched} | {c.lines_changed:,} | "
              f"{', '.join('`' + t + '`' for t in c.top_areas) if c.top_areas else '—'} |")
        w("")
        w("_Note: activity volume says nothing about code quality or review dynamics._")
    else:
        w("Unavailable.")
    w("")

    # Suggested reading order (simple heuristic for v0.1)
    w("## Suggested Reading Order")
    w("")
    order: list[tuple[str, str]] = []
    known = {f.rel for f in a.walk.files}
    for cand, reason in [
        ("README.md", "start here: project self-description"),
        ("readme.md", "start here: project self-description"),
        ("package.json", "project metadata and scripts"),
        ("pyproject.toml", "project metadata and dependencies"),
        ("Cargo.toml", "project metadata and dependencies"),
        ("CMakeLists.txt", "build structure"),
        ("Makefile", "build structure"),
    ]:
        if cand in known:
            order.append((cand, reason))
    for e in a.entrypoints[:3]:
        if e.path not in [p for p, _ in order]:
            order.append((e.path, "entrypoint — see how the program starts"))
    for h in a.hot_files[:3]:
        if h.path not in [p for p, _ in order]:
            order.append((h.path, "hot file — most churned code"))
    if order:
        for i, (p, reason) in enumerate(order[:8], 1):
            w(f"{i}. `{p}` — {reason}")
    else:
        w("Not enough information.")
    w("")
    return "\n".join(out)
