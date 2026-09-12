# Decisions

Append-only log. Newest first.

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
