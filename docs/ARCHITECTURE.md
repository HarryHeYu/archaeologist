# Architecture

## Layers

```text
cli.py                 argument parsing, command dispatch, logging
  └─ analysis.py? (currently build_analysis in cli.py)
       ├─ gitcmd.py        thin `git` subprocess wrapper (GitRepo, GitError, Commit)
       ├─ walker.py        file walk, ignore rules, binary sniffing, language table
       ├─ loc_counter.py   per-language LOC counting (code/comment/blank)
       ├─ analyzers/       pure analysis functions: models in → models out
       │    ├─ overview.py      repository identity & git facts
       │    ├─ structure.py     language stats, directory roles, entrypoints
       │    └─ history.py       hot files, recent changes, contributors (git)
       ├─ models.py        dataclasses shared across analyzers
       ├─ render.py        terminal output (bars, sections)
       └─ report.py        Markdown report generation
```

## Key decisions

- **Analyzers are pure functions** from inputs (paths, git output) to
  dataclasses in `models.py`. Rendering is a separate layer. This makes
  analyzers unit-testable without terminals and lets the future `arch report`,
  `arch why`, JSON output etc. reuse them unchanged.
- **One git log pass per question, not per file.** Hot files / contributors /
  recent changes each parse a single `git log --numstat` stream instead of
  spawning per-file `git log` processes. This is the single biggest performance
  lever on large repositories.
- **Tracked-file awareness.** In git repositories we walk `git ls-files`
  output instead of the filesystem, so `.gitignore` is respected for free.
  Non-git repos fall back to `os.walk` with the built-in ignore list.
- **LOC heuristic** mirrors cloc/tokei's simple mode: line-based, block-comment
  aware, no tokenization. Trailing comments count as code (documented).
- **History cap.** Git history passes are capped at 10,000 commits
  (`MAX_HISTORY_COMMITS`) so monorepos/kernels don't hang; a note explains the
  approximation.
- **Recent-window fallback.** If the last 30 days have no commits, the window
  widens to 365 days so the section never shows an empty shell.

## Extending

Add a command = add an analyzer function (models → models), a renderer, and a
subparser in `cli.py`. v0.2 plans `arch tree`, `arch file`, `arch history`,
`arch why`, `arch deps` on top of the same primitives.
