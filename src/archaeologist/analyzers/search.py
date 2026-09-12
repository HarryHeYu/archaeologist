"""`arch search` — unified search over paths, commit messages, contributors."""

from __future__ import annotations

from pathlib import Path

from ..gitcmd import GitRepo, GitError


def search(root: Path, query: str, limit: int = 10) -> dict:
    """Search paths, commit subjects and contributors for `query`.
    Plain substring matching, case-insensitive; no index, no AI."""
    q = query.lower()
    git = GitRepo(root)
    try:
        is_git = git.is_repo()
    except GitError:
        is_git = False

    ls = git.try_out("ls-files", "-z") if is_git else None
    if ls is not None:
        paths = [p for p in ls.split("\x00") if p]
    else:
        from ..walker import walk_repo
        paths = [f.rel for f in walk_repo(root).files]

    result: dict = {"query": query, "paths": [], "commits": [], "contributors": []}

    # paths: rank by how deep the match is (filename > directory)
    scored = []
    for p in paths:
        pl = p.lower()
        if q in pl:
            name = pl.rsplit("/", 1)[-1]
            score = 0 if q in name else 1
            scored.append((score, p))
    result["paths"] = [p for _, p in sorted(scored)[:limit]]

    if is_git:
        # commit subjects
        raw = git.try_out("log", f"-n{limit}", "--date=short", "--regexp-ignore-case",
                          "--grep", query, "--format=%ad%x1f%h%x1f%an%x1f%s")
        for line in raw.splitlines() if raw else []:
            date, h, author, subject = (line.split("\x1f") + ["", "", ""])[:4]
            result["commits"].append({"date": date, "hash": h, "author": author,
                                      "subject": subject})

        # contributors
        seen = set()
        raw = git.try_out("log", "--format=%an%x1f%ae")
        for line in raw.splitlines() if raw else []:
            name, email = (line.split("\x1f") + [""])[:2]
            if (q in name.lower() or q in email.lower()) and email not in seen:
                seen.add(email)
                result["contributors"].append({"name": name, "email": email})
    return result
