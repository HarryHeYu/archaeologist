"""Console rendering of analysis results."""

from __future__ import annotations

import shutil

from .models import Analysis

BAR_WIDTH = 30


def _width() -> int:
    try:
        return shutil.get_terminal_size((100, 24)).columns
    except Exception:
        return 100


def bar(frac: float, width: int = BAR_WIDTH) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def render_overview(a: Analysis) -> list[str]:
    o = a.overview
    L = [""]
    L.append(f"Repository      {o.name}")
    L.append(f"Path            {o.path}")
    if o.is_git:
        L.append(f"Git             yes (branch: {o.branch or 'detached HEAD'}, HEAD: {o.head})")
        if o.remote_url:
            L.append(f"Remote          {o.remote_url}")
        L.append(f"Commits         {_fmt_int(o.total_commits)}   contributors: {o.contributors}")
        if o.first_commit and o.first_commit.date:
            L.append(f"First commit    {o.first_commit.date[:10]}  by {o.first_commit.author}"
                     f"  ({o.age_days} days ago)" if o.age_days is not None else
                     f"First commit    {o.first_commit.date[:10]}  by {o.first_commit.author}")
        if o.last_commit and o.last_commit.date:
            L.append(f"Last commit     {o.last_commit.date[:10]}  {o.last_commit.subject[:60]}")
        L.append(f"Tracked files   {_fmt_int(o.tracked_files)}   size: {o.size_mb:.1f} MB")
        if o.shallow:
            L.append("Note            shallow clone — history stats are lower bounds")
    else:
        L.append("Git             no (not a git repository; git sections unavailable)")
        L.append(f"Files           {_fmt_int(len(a.walk.files))}   size: {o.size_mb:.1f} MB")
    for n in o.notes:
        L.append(f"Note            {n}")
    return L


def render_languages(a: Analysis) -> list[str]:
    L = ["", "Languages", "─────────"]
    if not a.languages:
        L.append("  (no recognized source files)")
        return L
    total_code = sum(s.code for s in a.languages) or 1
    for s in a.languages[:10]:
        pct = 100 * s.code / total_code
        detail = ""
        if s.total and s.total != s.code:
            detail = f"  (code {s.code:,} / comment {s.comment:,} / blank {s.blank:,})"
        L.append(f"  {s.name:<16}{pct:5.1f}%  {bar(pct / 100)}  {s.files} files{detail}")
    if len(a.languages) > 10:
        others = sum(s.code for s in a.languages[10:])
        L.append(f"  {'Other':<16}{100 * others / total_code:5.1f}%")
    return L


def render_structure(a: Analysis) -> list[str]:
    L = ["", "Repository Structure", "────────────────────"]
    for d in a.structure[:14]:
        role = d.role if d.role != "unclassified" else "(purpose not obvious from name)"
        L.append(f"  {d.rel:<22}{role:<40}{d.files:>5} files  ~{d.code:,} LOC")
    if len(a.structure) > 14:
        L.append(f"  … and {len(a.structure) - 14} more directories")
    return L


def render_entrypoints(a: Analysis) -> list[str]:
    L = ["", "Likely Entrypoints", "──────────────────"]
    if not a.entrypoints:
        L.append("  (none detected)")
        return L
    for i, e in enumerate(a.entrypoints[:10], 1):
        L.append(f"  {i}. {e.path}")
        L.append(f"     {e.evidence}")
    return L


def render_hot(hot_files: list) -> list[str]:
    L = ["", "Hot Files", "─────────"]
    if not hot_files:
        L.append("  (no git history or no matching files)")
        return L
    for i, h in enumerate(hot_files, 1):
        L.append(
            f"  {i}. {h.path}")
        L.append(f"     commits: {h.commits}   contributors: {h.contributors}   "
                 f"lines changed: {_fmt_int(h.lines_changed)}   "
                 f"active recently: {'yes' if h.recent_commits else 'no'}   score: {h.score}")
    return L


def render_recent(r) -> list[str]:
    L = ["", f"Recent Changes (last {r.since_days} days)", "──────────────────────────────"]
    if r.commits == 0:
        L.append("  No commits in this window.")
        return L
    L.append(f"  {r.commits} commits, +{_fmt_int(r.added)} -{_fmt_int(r.deleted)} lines")
    if r.areas:
        L.append("  Most changed areas:")
        peak = r.areas[0][1] or 1
        for name, lines in r.areas:
            L.append(f"    {name:<20}{bar(lines / peak)}  {_fmt_int(lines)}")
    if r.new_files:
        L.append(f"  New files: {', '.join(r.new_files[:5])}"
                 + (f" (+{len(r.new_files) - 5} more)" if len(r.new_files) > 5 else ""))
    if r.deleted_files:
        L.append(f"  Deleted files: {', '.join(r.deleted_files[:5])}")
    if r.big_commits:
        L.append("  Largest commits:")
        for subject, date, lines in r.big_commits:
            L.append(f"    {date}  +-{_fmt_int(lines)}  {subject[:70]}")
    return L


def render_contributors(contributors: list) -> list[str]:
    L = ["", "Contributors", "────────────"]
    if not contributors:
        L.append("  (no git history or no matching files)")
        return L
    for c in contributors:
        L.append(f"  {c.name}")
        L.append(f"    commits: {c.commits}   files touched: {c.files_touched}   "
                 f"lines changed: {_fmt_int(c.lines_changed)}   last active: {c.last_commit[:10]}")
        if c.top_areas:
            L.append(f"    main areas: {', '.join(c.top_areas)}")
    return L


def render_scan(a: Analysis) -> str:
    sections = [
        render_overview(a),
        render_languages(a),
        render_structure(a),
        render_entrypoints(a),
        render_hot(a.hot_files),
        render_recent(a.recent),
        render_contributors(a.contributors),
    ]
    lines = []
    for s in sections:
        lines.extend(s)
    return "\n".join(lines) + "\n"
