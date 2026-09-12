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
from .render import render_scan
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
