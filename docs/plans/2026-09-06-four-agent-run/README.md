# Floww four-agent execution package — 2026-09-06

> For agentic workers: use `superpowers:subagent-driven-development` for a fresh worker per admitted task, or `superpowers:executing-plans` inside an assigned worker session. The coordinator owns admission and integration. This package is a planning deliverable; it has not started a four-hour run.

**Goal:** four hours of useful work per lane on verified remaining Floww work, with complete backlog accounting, independent review, and resumable evidence.

**Architecture:** one coordinator, four isolated worker roles. One task per worker at a time, whole-file leases, independent task branches, centralized runtime/provider-budget ownership. A passing audit closes a question; it does not require a cosmetic change.

**Stack:** FastAPI, React/CRACO, MongoDB, DuckDB, Public API, pytest, Ruff, GitHub protected-main PRs.

**Sources:** the supplied master plan, current GitHub issues, `INVENTORY.md`, repository contracts, and the source register. This is an execution/discovery queue, not a claim that every candidate already has an implementation-ready product contract.

## Start here

1. Open `COORDINATOR.md` in the architect session. It owns the four-hour clock and task leases.
2. Give each worker its complete `AGENT-1-platform.md`, `AGENT-2-data.md`, `AGENT-3-experience.md`, or `AGENT-4-proof.md` prompt. These reference the common protocol by an absolute local path, so new worktrees do not need to contain this uncommitted package.
3. Coordinator performs admission preflight, including release of overlapping institutional/G1/G3 ownership. Workers can read, reproduce offline, and prepare contracts while a product-file lease is pending.
4. Read `QUEUE.md` for outcomes, paths, proof and dependencies. Use `run-state.json` plus per-lane checkpoints outside git for live progress; only the coordinator writes central state.
5. Finish with reviewed branches/PR evidence and a remaining-work ledger. Nav owns merges under the installed GSD policy. Do not equate a branch commit with a merge or a merge with deployed proof.

## Workspaces actually prepared

All four were created from `5b9d9a96a29951e548e883d108a806b93c2d11a9` (`origin/main`). Upstream tracking was removed so a default push cannot target main through an inherited upstream. Use explicit feature-branch pushes only.

| Role | Worktree | Branch | Runtime reservation |
|---|---|---|---|
| 1 Platform | `/Users/nav/Documents/GitHub/floww-worktrees/run-20260906-platform` | `run/20260906-platform` | 8101, if free |
| 2 Data | `/Users/nav/Documents/GitHub/floww-worktrees/run-20260906-data` | `run/20260906-data` | 8102, if free |
| 3 Experience | `/Users/nav/Documents/GitHub/floww-worktrees/run-20260906-experience` | `run/20260906-experience` | 3103, if free |
| 4 Proof | `/Users/nav/Documents/GitHub/floww-worktrees/run-20260906-proof` | `run/20260906-proof` | 8104/3104, if free |

Reservations are suggestions, not evidence that a port is free. No servers, dependency installs, databases, brokerage calls, bots, or worker loops were started by creating these worktrees. Baseline tests and dependency setup remain launch preflight. Do not use the shared canonical venv for upgrades or share mutable node_modules.

The existing canonical checkout is `phase9/g1-reads-witness`, not main. Existing `floww-g3` and `floww-worktrees/tidehunter` lanes remain intact. The two previous untracked Sept-6 plans and unrelated dirty files were preserved.

## Four-hour operating budget

| Elapsed | Expected work in every lane |
|---|---|
| 0–25 min | Fresh refs, ownership, isolated dependencies, baseline, next task contract |
| 25–90 min | First high-value task; red/green proof or a resolved audit; independent review request |
| 90–165 min | Next independent task or reviewed rework; broaden relevant fault matrix |
| 165–220 min | Remaining eligible task; cross-lane integration/replay/performance evidence |
| 220–240 min | Finish current safe unit, verify final heads, checkpoint, PR/handoff, enumerate blockers |

These are planning estimates, not deadlines for passing tests. Each lane has at least four hours of candidate work, with reserve tasks beyond that budget. Each lane records its own start and deadline at admission; a late-starting Proof lane receives its own four-hour window. On a capacity-limited host this can extend coordinator supervision beyond four hours. At a lane's deadline checkpoint unfinished work; do not force a broken commit, invent defects, or erase findings to meet the clock. Continue only if the session's run budget is extended. Stop immediately on a user stop request. An exhausted or blocked queue is reported honestly, not padded with repeated probes.

## Durable execution limitation

A prompt cannot guarantee wall-clock execution after its host ends a turn or exhausts context. This session has no native recurring-task tool. **No scheduler is installed or running.** Use a persistent supervising Hermes/session with continuation, or a supported native scheduler after its preflight. Do not substitute an unattended shell `while` loop for the installed `gsd-loop-schedule` skill.

The installed GSD builder is one bounded pass and permits only one claiming builder per repository. Four workers must not each invoke its global issue picker. Coordinator-dispatched local tasks use GSD-style contracts; actual GitHub GSD issues require the human `gsd:ready` gate. Issues #17/#18 currently have no labels. Issue #8 has `gsd:ready` but remains credit-blocked. No issues or labels were changed by this planning pass.

If this host offers only four total agent slots including the coordinator, run three workers concurrently and rotate the proof worker into a released slot; do not claim four workers are simultaneously running. Four independent user-launched sessions can use all four prompts with the architect in a separate session.

## Priority and exclusions

Track A integrity/dependency work gets first integration priority. Prepare independent C2 work in parallel. Exposure alerts and the named round11 tests already exist: verify first. Redesign B0, paid Phase 4, Oracle provisioning, live Discord witnesses, credentials/rotation, model retraining, and frozen-file changes remain explicit gates. Azure repair and retired-provider restoration remain excluded.

Nothing here authorizes live orders, account changes, Discord/webhook messages, purchases, model retraining, or restarting another lane's services. Offline paper execution tests are in scope; real paper transactions require the existing genuine-human approval gate.
