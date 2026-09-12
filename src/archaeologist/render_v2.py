"""Renderers for v0.2 commands: tree, file, history, why, deps."""

from __future__ import annotations

from pathlib import Path

from .analyzers.dossier import analyze_deps_view
from .models import Analysis


def render_file(dossier: dict) -> str:
    d = dossier
    L = ["", d["path"], "─" * min(len(d["path"]), 70)]
    L.append(f"Language: {d['language'] or 'unknown'}   Size: {d['size']:,} B")
    if d.get("loc"):
        loc = d["loc"]
        L.append(f"LOC: {loc.code:,} code / {loc.comment:,} comment / {loc.blank:,} blank")
    if not d["git"]:
        L.append("Git history: unavailable (not a git repository)")
        return "\n".join(L) + "\n"
    L.append(f"Created:        {d['created']}")
    L.append(f"Last modified:  {d['last_modified']}")
    L.append(f"Commits:        {d['commits']}")
    contribs = ", ".join(d["contributors"][:6])
    more = f" (+{len(d['contributors']) - 6})" if len(d["contributors"]) > 6 else ""
    L.append(f"Contributors:   {contribs}{more}")
    if d["main_contributor"]:
        L.append(f"Main contributor: {d['main_contributor']}")
    if d["imports"]:
        L.append("Imports/includes:")
        for imp in d["imports"][:12]:
            L.append(f"  - {imp}")
    if d["co_changed"]:
        L.append("Often changed together with (co-change):")
        for p in d["co_changed"]:
            L.append(f"  - {p}")
    if d["history_events"]:
        L.append("Notable history events:")
        for e in d["history_events"]:
            extra = f" {e['detail']}" if e.get("detail") else ""
            L.append(f"  {e['date']}  {e['kind']}{extra}  — {e['subject']}")
    return "\n".join(L) + "\n"


def render_why(ev: dict) -> str:
    d = ev["dossier"]
    L = ["", f"Why {d['path']} appears (or not) important", "─" * 60]
    for title, key in [("Git signals", "git_signals"),
                       ("Structural signals", "structural_signals"),
                       ("Change signals", "change_signals")]:
        rows = [r for r in ev[key] if r]
        if rows:
            L.append(f"{title}")
            for r in rows:
                L.append(f"  - {r}")
    if ev.get("included_by"):
        L.append("Included/imported by (sample):")
        for p in ev["included_by"][:6]:
            L.append(f"  - {p}")
    if ev.get("related"):
        L.append("Related modules (co-change):")
        for p in ev["related"][:6]:
            L.append(f"  - {p}")
    L.append("")
    L.append(f"Importance score: {ev['verdict']}  ({ev['score']} / 100, heuristic — see evidence above)")
    return "\n".join(L) + "\n"


def render_evolution_file(evo: dict) -> str:
    L = ["", f"Evolution of {evo['path']}", "─" * 60]
    if evo["created"]:
        L.append(f"First commit: {evo['created']}   contributors: {evo['contributors']}")
    if evo["yearly"]:
        peak = max(evo["yearly"].values()) or 1
        L.append("Activity by year (lines changed):")
        for year, lines in evo["yearly"].items():
            filled = int(round(28 * lines / peak))
            L.append(f"  {year}  {'█' * filled:<28} {lines:,}")
    if evo["events"]:
        L.append("Notable events:")
        for e in evo["events"]:
            L.append(f"  {e['date']}  {e['kind']:<14} {e['detail']:<16} {e['subject']}")
    return "\n".join(L) + "\n"


def render_evolution_keyword(evo: dict) -> str:
    L = ["", f"Evolution of '{evo['keyword']}'", "─" * 60]
    if evo["related_paths"]:
        L.append(f"Related paths ({len(evo['related_paths'])} shown):")
        for p in evo["related_paths"][:10]:
            L.append(f"  - {p}")
    if evo["yearly"]:
        L.append("")
        L.append("Activity by year:")
        peak = max(v["lines"] for v in evo["yearly"].values()) or 1
        for year, v in evo["yearly"].items():
            filled = int(round(24 * v["lines"] / peak))
            L.append(f"  {year}  {'█' * filled:<24} {v['commits']:>4} commits, {v['lines']:,} lines")
    if evo["matching_commits"]:
        L.append("")
        L.append("Commit messages mentioning it (newest first):")
        for c in evo["matching_commits"][:10]:
            L.append(f"  {c['date']}  {c['hash'][:8]}  {c['subject']}")
    if not (evo["related_paths"] or evo["yearly"]):
        L.append(f"No files or commits match '{evo['keyword']}'.")
    return "\n".join(L) + "\n"


def render_deps(deps_view: dict) -> str:
    L = ["", f"Dependencies of {deps_view['path']}", "─" * 60]
    if deps_view["depends_on"]:
        L.append("Depends on:")
        for p in deps_view["depends_on"]:
            L.append(f"  - {p}")
    else:
        L.append("Depends on: (no internal dependencies found)")
    if deps_view["used_by"]:
        L.append("Used by:")
        for p in deps_view["used_by"]:
            L.append(f"  - {p}")
    else:
        L.append("Used by: (no internal importer found)")
    L.append("")
    L.append("_Best-effort include/import resolution; external packages are excluded._")
    return "\n".join(L) + "\n"


def render_tree(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"
