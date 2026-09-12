"""CLI entrypoint for `arch`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .gitcmd import GitRepo
from .walker import walk_repo
from .analyzers.overview import analyze_overview
from .analyzers.structure import analyze_languages, analyze_structure, analyze_entrypoints
from .analyzers.history import analyze_hot_files, analyze_recent, analyze_contributors
from .analyzers.tree import build_tree
from .analyzers.dossier import analyze_file, analyze_why, analyze_deps_view
from .analyzers.evolution import file_evolution, keyword_evolution
from .render import render_scan
from .render_v2 import (
    render_file, render_why, render_evolution_file, render_evolution_keyword,
    render_deps, render_tree)
from .report import generate_report
from .models import Analysis, RecentChanges

log = logging.getLogger("arch")


def build_analysis(root: Path) -> Analysis:
    git = GitRepo(root)
    tracked: set[str] | None = None
    if git.try_out("rev-parse", "--is-inside-work-tree") == "true":
        ls = git.try_out("ls-files", "-z")
        if ls is not None:
            tracked = {p for p in ls.split("\x00") if p}
    walk = walk_repo(root, tracked_only=tracked)

    ov = analyze_overview(root, git, walk)
    langs = analyze_languages(walk)
    structure = analyze_structure(walk, langs)
    entrypoints = analyze_entrypoints(walk)
    tracked_list = sorted(tracked) if tracked is not None else [f.rel for f in walk.files]
    hot = analyze_hot_files(git if ov.is_git else None, tracked_list)
    recent = analyze_recent(git if ov.is_git else None)
    contributors = analyze_contributors(git if ov.is_git else None)
    return Analysis(root=root, overview=ov, languages=langs, structure=structure,
                    entrypoints=entrypoints, hot_files=hot, recent=recent,
                    contributors=contributors, walk=walk)


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    if not root.exists():
        print(f"error: path does not exist: {root}", file=sys.stderr)
        return 2
    log.info("scanning %s", root)
    a = build_analysis(root)
    if args.output:
        md = generate_report(a)
        Path(args.output).write_text(md, encoding="utf-8")
        print(render_scan(a))
        print(f"Report written to {args.output}")
    else:
        print(render_scan(a))
    return 0


def _ctx(args) -> tuple[Path, Analysis]:
    root = Path(args.repo).resolve()
    if not root.exists():
        print(f"error: path does not exist: {root}", file=sys.stderr)
        sys.exit(2)
    return root, build_analysis(root)


def _rel_path(root: Path, target: str) -> str | None:
    """Resolve a user-supplied path (absolute or relative, POSIX or Windows)
    to a repo-relative POSIX path that exists under root."""
    p = Path(target)
    if not p.is_absolute():
        p = root / p
    try:
        rel = p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    return rel if (root / rel).is_file() else None


def cmd_tree(args) -> int:
    root, a = _ctx(args)
    print(render_tree(build_tree(a, max_depth=args.depth)))
    return 0


def cmd_file(args) -> int:
    root, a = _ctx(args)
    rel = _rel_path(root, args.path)
    if rel is None:
        print(f"error: file not found in repository: {args.path}", file=sys.stderr)
        return 2
    d = analyze_file(root, a, rel)
    if d is None:
        print(f"error: cannot analyze {rel}", file=sys.stderr)
        return 2
    print(render_file(d))
    return 0


def cmd_history(args) -> int:
    root, a = _ctx(args)
    rel = _rel_path(root, args.target)
    if rel is not None:
        evo = file_evolution(root, rel)
        if evo is None:
            print("error: no git history available for this file", file=sys.stderr)
            return 1
        print(render_evolution_file(evo))
        return 0
    evo = keyword_evolution(root, args.target)
    if evo is None:
        print("error: git history unavailable (not a git repository)", file=sys.stderr)
        return 1
    print(render_evolution_keyword(evo))
    return 0


def cmd_why(args) -> int:
    root, a = _ctx(args)
    rel = _rel_path(root, args.path)
    if rel is None:
        print(f"error: file not found in repository: {args.path}", file=sys.stderr)
        return 2
    ev = analyze_why(root, a, rel)
    if ev is None:
        print(f"error: cannot analyze {rel}", file=sys.stderr)
        return 2
    print(render_why(ev))
    return 0


def cmd_deps(args) -> int:
    root, a = _ctx(args)
    rel = _rel_path(root, args.path)
    if rel is None:
        print(f"error: file not found in repository: {args.path}", file=sys.stderr)
        return 2
    view = analyze_deps_view(root, a, rel)
    if view is None:
        print(f"error: cannot analyze {rel}", file=sys.stderr)
        return 2
    print(render_deps(view))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arch",
        description="Repository Archaeologist — understand an unfamiliar repo in seconds.",
    )
    parser.add_argument("--version", action="version", version=f"arch {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="full repository overview")
    p_scan.add_argument("repo", nargs="?", default=".", help="path to repository (default: .)")
    p_scan.add_argument("-o", "--output", help="also write a Markdown report to this path")
    p_scan.set_defaults(func=cmd_scan)

    p_tree = sub.add_parser("tree", help="pruned, annotated repository tree")
    p_tree.add_argument("repo", nargs="?", default=".")
    p_tree.add_argument("-d", "--depth", type=int, default=2, help="directory depth (default 2)")
    p_tree.set_defaults(func=cmd_tree)

    for name, fn, help_ in [("file", cmd_file, "per-file dossier (history, imports, co-change)"),
                            ("why", cmd_why, "why this file matters, with evidence"),
                            ("deps", cmd_deps, "internal dependencies of a file")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("path", help="file path inside the repository")
        p.add_argument("repo", nargs="?", default=".", help="repository root (default: .)")
        p.set_defaults(func=fn)

    p_hist = sub.add_parser("history", help="evolution of a file or a keyword/module")
    p_hist.add_argument("target", help="file path, or a module/keyword such as 'tokenizer'")
    p_hist.add_argument("repo", nargs="?", default=".")
    p_hist.set_defaults(func=cmd_history)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
