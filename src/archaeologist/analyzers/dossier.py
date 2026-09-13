"""Per-file dossier (`arch file`), importance evidence (`arch why`),
and co-change relation extraction. All git data is real, never guessed."""

from __future__ import annotations

import datetime as _dt
from collections import Counter, defaultdict
from pathlib import Path

from ..gitcmd import GitRepo, GitError
from ..loc_counter import file_loc
from ..models import Analysis
from ..walker import read_text_safe


def _git_or_none(git: GitRepo | None) -> GitRepo | None:
    try:
        if git is not None and git.is_repo():
            return git
    except GitError:
        pass
    return None


def file_commits(git: GitRepo, rel: str, limit: int = 200) -> list[dict]:
    raw = git.try_out("log", f"-n{limit}", "--follow", "--date=short",
                      "--name-status",
                      "--format=%x01%h%x1f%an%x1f%ad%x1f%s", "--", rel)
    out = []
    if not raw:
        return out
    for block in raw.split("\x01"):
        if not block.strip():
            continue
        head, _, rest = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) != 4:
            continue
        h, author, date, subject = parts
        changes = []
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) >= 2 and cols[0] in ("A", "D", "M", "R100", "R"):
                changes.append(cols[0][0])
            elif len(cols) >= 3 and cols[0].startswith("R"):
                changes.append("R")
        out.append({"hash": h, "author": author, "date": date,
                    "subject": subject, "changes": changes,
                    "renamed": "R" in changes})
    return out


def analyze_file(root: Path, a: Analysis, rel: str) -> dict | None:
    """Build the `arch file` dossier for a repo-relative path."""
    abs_path = root / rel
    if not abs_path.is_file():
        return None
    from ..walker import language_for
    lang = language_for(abs_path)
    from ..walker import RepoFile
    size = abs_path.stat().st_size
    loc = file_loc(RepoFile(path=abs_path, rel=rel, language=lang,
                            size=size, binary=False)) if lang else None

    git = _git_or_none(GitRepo(root))
    dossier: dict = {
        "path": rel, "language": lang, "size": size,
        "loc": loc, "git": git is not None,
        "created": None, "last_modified": None, "commits": 0,
        "contributors": [], "main_contributor": None,
        "co_changed": [], "imports": [], "history_events": [],
    }

    # imports/includes (from the file itself, no git needed)
    text = read_text_safe(abs_path)
    if text is not None and lang:
        from .deps import extract_deps, build_header_index
        all_files = [f.rel for f in a.walk.files]
        if lang in ("C", "C++", "C/C++ Header"):
            build_header_index(root, all_files)
        d = extract_deps(root, rel, text)
        dossier["imports"] = d.internal + [f"{e} (external)" for e in d.external[:8]]
    # top-level symbols (only if tree-sitter extras are installed)
    dossier["symbols"] = []
    if text is not None and lang:
        from . import symbols as sym
        if sym.HAS_TS and lang in sym.GRAMMARS:
            dossier["symbols"] = sym.extract_symbols(lang, rel, text)

    if git:
        log = file_commits(git, rel)
        if log:
            authors = Counter(e["author"] for e in log)
            dossier["commits"] = len(log)
            dossier["contributors"] = [a for a, _ in authors.most_common()]
            dossier["main_contributor"] = authors.most_common(1)[0][0]
            dossier["created"] = log[-1]["date"]
            dossier["last_modified"] = log[0]["date"]
            # co-change: files modified in the same commits (sample of recent 60)
            raw = git.try_out("log", "-n60", "--name-only", "--format=%x01", "--", rel)
            partners: Counter = Counter()
            if raw:
                for block in raw.split("\x01")[1:]:
                    for line in block.splitlines():
                        line = line.strip()
                        if line and line != rel:
                            partners[line] += 1
            dossier["co_changed"] = [p for p, n in partners.most_common(8) if n >= 2]
            # notable events: renames, big diffs (from numstat with follow)
            numstat = git.try_out("log", "-n200", "--follow", "--numstat",
                                  "--date=short",
                                  "--format=%x01%ad%x1f%s")
            events = []
            if numstat:
                for block in numstat.split("\x01"):
                    if not block.strip():
                        continue
                    head, _, rest = block.partition("\n")
                    date, subject = (head.split("\x1f") + ["", ""])[:2]
                    total = 0
                    for line in rest.splitlines():
                        cols = line.split("\t")
                        if len(cols) >= 3 and rel in (cols[2], cols[2].split("\t")[-1]):
                            try:
                                total += int(cols[0] if cols[0] != "-" else 0)
                                total += int(cols[1] if cols[1] != "-" else 0)
                            except ValueError:
                                pass
                    if total >= 200:
                        events.append({"date": date, "kind": "large rewrite",
                                       "detail": f"+-{total:,}", "subject": subject})
                    elif "rename" in subject.lower() or "move" in subject.lower():
                        events.append({"date": date, "kind": "possible rename/move",
                                       "detail": "", "subject": subject})
            dossier["history_events"] = events[:8]
    return dossier


def analyze_why(root: Path, a: Analysis, rel: str) -> dict | None:
    """Evidence-based importance verdict for one file."""
    d = analyze_file(root, a, rel)
    if d is None:
        return None
    git = _git_or_none(GitRepo(root))
    evidence: dict = {"dossier": d, "git_signals": [], "structural_signals": [],
                      "change_signals": [], "related": d["co_changed"],
                      "verdict": "UNKNOWN", "score": 0.0}
    if not git:
        return evidence

    total_commits = max(a.overview.total_commits, 1)
    commits = d["commits"]
    n_contrib = len(d["contributors"])
    evidence["git_signals"] = [
        f"{commits} commit(s) touched this file",
        f"{n_contrib} contributor(s)"
        + (f", main: {d['main_contributor']}" if d["main_contributor"] else ""),
        f"active from {d['created']} to {d['last_modified']}" if d["created"] else "",
    ]

    # included-by count (reverse include/import edge)
    included_by = []
    text = read_text_safe(root / rel)
    stem = Path(rel).stem
    from ..walker import language_for
    lang = language_for(root / rel)
    for f in a.walk.files:
        if f.binary or f.language is None or f.size > 1_500_000:
            continue
        ft = read_text_safe(f.path)
        if ft is None:
            continue
        if lang in ("C", "C++", "C/C++ Header"):
            if f'#include "{Path(rel).name}"' in ft:
                included_by.append(f.rel)
        elif lang == "Python" and rel.endswith(".py"):
            mod = rel[:-3].replace("/", ".")
            if re_search_module(ft, mod, stem):
                included_by.append(f.rel)
    evidence["structural_signals"] = [
        f"included/imported by {len(included_by)} file(s)"
        + (f" (e.g. {', '.join(included_by[:3])})" if included_by else ""),
    ]

    # recent touch rate: commits in last 90d vs total
    recent = git.commits_since(
        (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=90)).strftime("%Y-%m-%d")
    )
    touched_recent = git.try_out(
        "log", "-n5", "--since=" + (_dt.datetime.now(_dt.timezone.utc)
                                    - _dt.timedelta(days=90)).strftime("%Y-%m-%d"),
        "--format=%h", "--", rel)
    evidence["change_signals"] = [
        f"{len(touched_recent or [])} of the repository's last commits (90d window) touched it"
        if touched_recent else "not touched in the last 90 days",
        f"repository has {total_commits} total commits; this file has {commits}",
    ]
    evidence["included_by"] = included_by

    # crude weighted verdict — always shown WITH its evidence
    score = min(commits, 30) / 30 * 40 + min(len(included_by), 10) / 10 * 30 \
        + min(n_contrib, 6) / 6 * 20 + (10 if touched_recent else 0)
    evidence["score"] = round(score, 1)
    evidence["verdict"] = "HIGH" if score >= 60 else "MEDIUM" if score >= 30 else "LOW"
    return evidence


def re_search_module(text: str, dotted: str, stem: str) -> bool:
    import re
    top = dotted.split(".")[0]
    if re.search(rf"^\s*(?:from\s+{re.escape(top)}[.\s]|import\s+{re.escape(top)})", text, re.M):
        return True
    return False


def analyze_deps_view(root: Path, a: Analysis, rel: str) -> dict | None:
    """`arch deps`: direct internal dependencies and reverse importers."""
    abs_path = root / rel
    if not abs_path.is_file():
        return None
    from .deps import extract_deps, build_header_index
    text = read_text_safe(abs_path)
    if text is None:
        return None
    from ..walker import language_for
    lang = language_for(abs_path)
    all_files = [f.rel for f in a.walk.files]
    if lang in ("C", "C++", "C/C++ Header"):
        build_header_index(root, all_files)
    deps = extract_deps(root, rel, text)

    used_by: list[str] = []
    target_name = Path(rel).name
    if lang in ("C", "C++", "C/C++ Header") and rel.endswith((".h", ".hpp", ".hh")):
        for f in a.walk.files:
            if f.binary or f.language is None:
                continue
            ft = read_text_safe(f.path)
            if ft and f'#include "{target_name}"' in ft:
                used_by.append(f.rel)
    else:
        # reverse of python/ts/c internal resolution: scan importers
        for f in a.walk.files:
            if f.rel == rel or f.binary or f.language is None or f.size > 1_500_000:
                continue
            ft = read_text_safe(f.path)
            if not ft:
                continue
            fd = extract_deps(root, f.rel, ft)
            if rel in fd.internal:
                used_by.append(f.rel)

    return {"path": rel, "language": lang,
            "depends_on": deps.internal,
            "external": deps.external,
            "used_by": sorted(used_by)[:20]}
