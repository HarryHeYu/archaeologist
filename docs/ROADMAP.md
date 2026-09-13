# Roadmap

Long-term vision lives in the project brief; this file tracks the executable plan.

## v0.1 — `arch scan` that is genuinely useful ✅
- [x] repository overview (git facts, graceful non-git degradation)
- [x] language statistics with code/comment/blank split
- [x] structure classification with directory roles
- [x] entrypoint detection (filename + content heuristics)
- [x] hot files (heuristic score, evidence shown)
- [x] recent changes (areas, new/deleted files, largest commits, window fallback)
- [x] contributors (name-aggregated, main areas, no quality judgement)
- [x] Markdown report (`arch scan <repo> -o report.md`)
- [x] `.archignore` configuration
- [x] test suite + real-repo validation (Python / TS / C / huge tree)

## v0.2 — per-file and relational analysis
- [x] `arch tree` — meaningful pruned tree, not a dump
- [x] `arch file <path>` — per-file dossier (history, contributors, related files)
- [x] `arch history <path|keyword>` — file/module evolution timeline
- [x] `arch why <path>` — importance verdict with evidence
- [x] `arch deps <path>` — include/import graph (file→file, simple regex level)
- [x] `arch contributors`, `arch recent`, `arch hot` as standalone commands
- [x] `arch search` (paths / commit subjects / contributors)
- [ ] incremental cache (`.archaeologist/`) keyed on HEAD commit (deferred: current scans are fast enough at tested scales)

## v0.3 — symbols (Tree-sitter, optional dependency)
- [x] unified Symbol model; `arch symbol <name>` (Python/C/C++/Rust/JS/Go)
- [x] definitions extraction feeding `arch file` (Symbols section)
- [ ] import/call edges between symbols; symbol refs feeding `arch why`

## v0.4 — evolution
- [ ] `arch timeline`, module evolution, `arch compare <a> <b>`

## v0.5 — optional AI layer (never required)
- [ ] `arch explain` / `arch ask` over structured analysis results only
