# Repo Archaeologist (`arch`)

> 🧰 **Use it from your coding agent**: packaged as the `repo-archaeology` skill in [skills-arsenal](https://github.com/HarryHeYu/skills-arsenal) — ask *"what does this repo do?"* in ZCode / Claude Code.

> Understand an unfamiliar repository in seconds — not minutes.

`arch` answers "what is this repo, where is the important code, and how did it
get here?" by combining **git archaeology** (real git history) with **static
analysis** (languages, structure, entrypoints). No AI, no API keys, no network
access required.

```text
arch scan <repo>
```

```text
Repository      Office-PowerPoint-MCP-Server
Path            E:\code\Office-PowerPoint-MCP-Server
Git             yes (branch: main, HEAD: 3631ba2)
Commits         41   contributors: 11
...
Hot Files
  1. ppt_mcp_server.py
     commits: 12   contributors: 5   lines changed: 6,366   score: 60.8
...
```

## Install

Requirements: Python ≥ 3.10, `git` on PATH. Zero third-party runtime dependencies.

```bash
git clone <this repo> && cd archaeologist
pip install .
# optional: symbol extraction via tree-sitter (`arch symbol`, symbols in `arch file`)
pip install .[symbols]
```

**Windows note:** the `arch.exe` launcher is installed into your user
`...\Python\Python3x\Scripts` directory. If `arch` is not found (or resolves to
Git Bash's coreutils `arch`), either add that directory to `PATH` or use:

```bash
python -m archaeologist scan .
```

## Commands

| Command | What it does |
|---|---|
| `arch scan <repo>` | Full overview: git facts, languages, structure, entrypoints, hot files, recent changes, contributors |
| `arch scan <repo> -o report.md` | Also writes a standalone Markdown report |
| `arch tree <repo>` | Pruned, annotated tree with inferred directory roles |
| `arch file <path> <repo>` | Per-file dossier: LOC, created/last-modified, commits, contributors, imports, co-change partners, notable events |
| `arch history <path\|keyword> <repo>` | Evolution timeline of a file (creation, rewrites, renames, yearly activity) or of a module keyword (related paths + matching commits by year) |
| `arch why <path> <repo>` | Importance verdict (HIGH/MEDIUM/LOW) with all the evidence that produced it |
| `arch deps <path> <repo>` | Internal include/import dependencies and reverse importers (Python/C/C++/TS/JS/Rust/Go/Java, best effort) |
| `arch hot <repo>` | Standalone hot-files ranking |
| `arch recent <repo>` (`--days N`) | Standalone recent-change summary |
| `arch contributors <repo>` | Standalone contributor analysis |
| `arch search <query> <repo>` | Search paths, commit messages, and contributors (substring, case-insensitive) |
| `arch symbol <name> <repo>` | Find a function/class/struct by name with location, members, and text-level referencing files (needs extras) |
| `arch timeline <repo>` | Year-by-year evolution: commits, change magnitude, when each area first appeared, largest change per year |

Note the argument order: file-scoped commands take the path first, the
repository root second (`arch file src/main.cpp .`). Both relative and
absolute paths work; Unicode and space-containing paths are supported.

Useful flags: `arch tree -d N` (depth, default 2), `arch hot -n N`,
`arch contributors -n N`, `arch search -n N` (result count), `arch recent
--days N` (default 30, widens to 365 automatically when the default window is
empty), and global `-v` for debug logging.

Non-git directories work fine — git-derived sections degrade gracefully to
"unavailable" instead of failing.

## Design principles

1. **Git + static analysis first.** Every number comes from real `git`
   commands or real file reads. Nothing is guessed.
2. **Zero runtime dependencies.** Standard library only.
3. **Graceful degradation.** Non-git, empty, shallow, and detached-HEAD
   repositories all produce useful output.
4. **Interpretation over numbers.** Directory roles (`tests/ → tests`,
   `docs/ → documentation`) and evidence lines are shown, not raw counts
   alone. When a heuristic is unsure, it says "(purpose not obvious from
   name)" rather than inventing a role.
5. **Cross-platform.** Windows / Linux / macOS; Unicode, Chinese, and
   space-containing paths are tested.

## How hot files are scored

`score = 40·commits + 25·lines_changed + 20·recent_activity + 15·contributors`
(each term normalized against the repository's own maximum). Scores are only
comparable within one repository. A file with 1 huge commit is not hot; a file
many people keep touching is.

For very large histories (10,000+ commits) only the most recent 10,000 commits
are analyzed — scores are then biased toward recent activity, and this is a
documented approximation.

## Configuration

Create a `.archignore` file in the repository root (same syntax idea as
`.gitignore`, one pattern per line; `dir/` marks a directory):

```text
# .archignore
generated/
*.pb.go
```

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — module layout and data flow
- [docs/ROADMAP.md](docs/ROADMAP.md) — the long-term plan (v0.2 …)
- [docs/DECISIONS.md](docs/DECISIONS.md) — why things are the way they are

## Development

```bash
pip install -e .[dev]
python -m pytest
```

## License

MIT — see [LICENSE](LICENSE).
