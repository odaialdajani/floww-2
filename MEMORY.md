# MEMORY.md — Project Oracle (floww)

**CANONICAL FLOWW = /Users/nav/Documents/GitHub/floww**
See [CONSOLIDATION_REPORT.md](CONSOLIDATION_REPORT.md) for the full consolidation record.

This file is the canonical memory index for the floww project.
It is synced bidirectionally with mem0 and Obsidian.

## Project Tag
All entries in this project are tagged `project:floww`.

## Active Memory

<!-- These seven entries used to be links to project_*.md / reference_*.md.
     Those files were never committed: `git log --all -- project_oracle.md`
     (and the other six) returns nothing for every branch. A link to a file
     that is not in the tree sends the reader nowhere and gives no signal
     about whether they are on the wrong branch or the doc was never written.
     The one-line descriptions below are kept, with the dead target removed
     and its location stated honestly. If a target lives outside the repo,
     say so here rather than emitting an unresolvable relative link. -->

- **Project Oracle directive** — May 2026 master directive; supersedes CLAUDE_REVIEW_PROMPT.md. _Not present in this repository._
- **Master plan operating laws** — no synthetic data, baseline-first, OOS-locked. _Not present in this repository._
- **Skylit feature parity** — commercial target; gap list in SKYLIT_FEATURES.md (in `docs/`). _Source doc not present in this repository._
- **Research pipeline** — arxiv discovery → URL extraction → clone → extract patterns. _Not present in this repository._
- **Herder swarm regime** — skill arsenal and dispatch patterns. _Not present in this repository._
- **Truth-audit** — `qc/audit/truth_audit.sh` runs every session start. _Source doc not present; the script itself is in the repo._
- **Tool boundaries** — CLI/Bash/Python/git only; Nav drives IDEs. _Not present in this repository._

## Cross-Project Memory

To query across all projects:
  ask-hermes --all-projects "query here"

To query floww only (default for trading queries):
  ask-hermes "query here"

## Memory System

- **Backend:** mem0 Platform (agent mode)
- **User ID:** user_c778280e23af
- **Agent caller:** hermes
- **Consolidation:** scripts/consolidate_memory_daily.py (daily @ 4am)
- **Pruning:** scripts/prune_memory.py (nightly, session entries > 30d)
- **Auto-tagging:** scripts/auto_tag_memory.py (on insert)
- **CLI:** scripts/ask_hermes.py (semantic search + git + kanban)
