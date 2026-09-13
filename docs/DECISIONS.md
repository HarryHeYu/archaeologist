# Decisions

Append-only log. Newest first.

## 2026-09-13 — multi-agent review round (v0.4.1)
- **Review process**: a docs-consistency subagent audited README/docs/CLI; when
  the code-review and QA subagents kept failing on infra errors, destructive
  QA (13 synthetic fixtures: empty dirs/repos, detached HEAD, renames, merge
  commits, 3MB files, CRLF+BOM, Chinese/space paths, CLI misuse) and the code
  review were done in the main session instead.
- **Fixes from the round**: all git invocations now run with
  `-c core.quotepath=off` (non-ASCII paths never octal-escaped); numstat
  rename spellings (`a => b`, `a{x => y}b`) normalize to the new path so
  renames count toward the surviving file; `search ""` is an error instead of
  matching everything; `recent --days N` is respected verbatim (365-day
  fallback now applies only to the default 30-day window); `scan`/git commands
  reject file paths with "not a directory"; report stamp uses the real package
  version; package version bumped 0.1.0 → 0.4.0 to match the roadmap.
- Known accepted limitations: `history` on a pure-rename commit shows 0-line
  events (git gives no numstat lines for pure renames); empty git repos render
  "(no git history or no matching files)" which is accurate but terse.

## 2026-09-13 — v0.4 (timeline)
- **`arch timeline` describes, it never interprets**: per-year commit counts,
  change magnitude, first-appearance of top-level areas, and the largest commit.
  Statements like "new areas: `cuda/`" are directly verifiable in the diffs.
- Timeline paths are filtered through the same ignore list as the walker and
  rename artifacts (`=>` forms) are skipped, so IDE dirs and vendor trees
  don't show up as "new areas".

## 2026-09-13 — v0.3 (tree-sitter symbols, optional)
- **Tree-sitter is an optional extra** (`pip install .[symbols]`): the core
  tool keeps zero dependencies and every non-symbol command works without it.
  Symbol features print an actionable install hint when the extras are absent.
- **Symbols are name+kind+line-range only** (no name resolution, no call
  graph) per the "best effort, confidence-explicit" principle. C function
  names are dug out of `declarator` nodes; `Referenced by` is explicitly
  labeled text-level in the output.
- **`arch file` shows static info even for non-git repos**: imports and
  symbols now render before the git-history section instead of being skipped
  by the early return.

## 2026-09-13 — v0.2.1 (standalone commands + search)
- **`hot` / `recent` / `contributors` skip the filesystem walk entirely**
  (they only need git + `ls-files`), so they answer in well under a second
  even on repos where `scan` takes longer.
- **Hot-file candidates are filtered to recognized source/metadata files** and
  paths touching ignore-list dirs (vendor, `Dependencies/`, dotfiles) are
  dropped — a vendored `glfw3.h` with one giant import commit must not top the
  churn ranking. Trade-off: `.github/` workflow churn is not shown; acceptable.
- **`search` is plain case-insensitive substring matching** with a filename >
  directory ranking bias. No index yet; if repos feel slow, add a persisted
  path/subject index alongside the planned cache.

## 2026-09-13 — v0.2 (file/relational layer)
- **File-scoped commands take `path` before `repo`** (`arch file src/x.cpp .`),
  so they work naturally from inside a repo (`arch file src/x.cpp` with the
  default `.`).
- **Dependency resolution is root-relative and regex-level.** Python relative
  imports (`.store`, `..pkg.mod`, bare `from . import`) are resolved by dot
  counting; C headers resolve relative to the includer first, then repo-wide
  (unique basename match only, else "external/unresolved"). No parser, no
  symbol table — documented as best effort.
- **`arch why` never gives a bare verdict**: HIGH/MEDIUM/LOW is always printed
  with the git/structural/change evidence that produced it, plus the raw score.
- **`arch history <keyword>` is deliberately non-semantic** (filenames, paths,
  commit subjects, diff sizes only). Real commit-interpretation waits for the
  optional AI layer.
- **Deferred the incremental cache**: the 10k-commit cap and parallel LOC fast
  path made tested scales (including a 96k-file kernel tree, ~2.5 min) fast
  enough; a cache adds invalidation complexity before it buys real time.

## 2026-09-13 — project bootstrap
- **Language: Python 3.10+, standard library only.** The tool's value is
  orchestration and presentation, not performance-critical computation; Python
  gives fast iteration and trivial cross-platform behavior. `subprocess` wraps
  the real `git` binary — reimplementing git in-process (pygit2/GitPython) was
  rejected as an added dependency with no user-visible gain for v0.1.
- **CLI: argparse, not click/typer.** One less dependency for ~6 commands.
- **Repo layout: src/ layout + pyproject.toml.** Standard, pip-installable,
  `arch` console script plus `python -m archaeologist` fallback.
- **`arch` name collision on Windows:** Git Bash ships coreutils `arch.exe`
  earlier on PATH; we keep the name, document `python -m archaeologist` as the
  portable invocation, and don't fight the user's PATH.
- **Hot score is relative, not absolute** (normalized against the repo's own
  maxima). Absolute scores would be meaningless across repo sizes.
- **Contributors aggregated by display name**, not email: the common annoyance
  is one person appearing N times due to email changes. (Known trade-off:
  two people sharing a display name merge; rare enough for v0.1.)
- **Recent window falls back 30d → 365d** so quiet repos still show something
  informative instead of "No commits."
- **LOC fast path above 4,000 source files:** count lines only (no
  comment/blank split) with chunked reads; keeps kernel-scale trees tolerable.
- **History capped at 10k commits** for hot/recent/contributor passes;
  documented approximation for huge repos.
