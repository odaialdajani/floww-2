# INTEGRATION LEDGER — H0–H7 (Hermes, integration owner)

Single shared coordination file. Each agent maintains its OWN receipt and does
not edit this file except to read it. Hermes is the only writer.

Last updated: 2026-09-28 · coordinator: Hermes · base: `d905c9d2`

## 0. Source of truth — measured, not asserted

| Fact | Value | How verified |
|---|---|---|
| Canonical repo | `/Users/nav/Documents/GitHub/floww-2` | `git worktree list`; serving PIDs resolved by `lsof` |
| Actual main HEAD | `d905c9d2` | `git rev-parse` on `origin/main` after fetch |
| CI on that exact head | success (all 3 jobs) | `gh run list --commit d905c9d2` |
| PR #67 | MERGED, `.gitignore` only | `gh pr view 67`; ignore rules confirmed live via `git check-ignore` |
| Open PRs | 0 | `gh pr list` |
| Working tree | clean except `kanban/BOTTLENECK_ALERTS.md` | `git status --short` |
| SIDE_BRANCH_SWEEP | COMPLETE | `.planning/SIDE_BRANCH_SWEEP.md` |

**Correction to the planning packet.** The packet's stated main `69d73c95` is
four merges stale. Work actually landed after it: `29bddf85` (#68), `70265385`
(#70), `5dcb8774` (#69), `d905c9d2` (#71/#72). All three agents must read
`d905c9d2` as the base, not `69d73c95`.

**Correction to the packet's H2/H3 file references.** `rank-and-scan.py` does
not exist in this repository. The real modules are
`backend/services/public_scanner.py` and `backend/services/universe_scan.py`,
with ranking in `backend/services/conviction_rank.py` and the only production
caller at `backend/routes/flowseeker.py`.

## 1. Ownership — no overlapping edits

| Track | Agent | Owns |
|---|---|---|
| Visual UI | OpenCode | Solstice/Triad React components, scoped styling, browser tests |
| Canonical math/data | Command Code | Greek/metric definitions, pure canonical Triad projection, schema/fixtures, oracle tests |
| Scanner/persistence | Hermes | scanner/ranker, persistence+history wiring, route/service entry points, combined acceptance, this ledger |

Shared files needing an **exclusive lease + handback SHA**:
`frontend/src/App.js`, `backend/server.py`, route registries, lockfiles.

`backend/services/conviction_rank.py` — **leased to Hermes, no active
contention.** OpenCode and Command Code must not edit it while this entry stands.

## 2. Frozen-file constraints (from `.planning/AGENT_CONTRACT.md`)

Architect-frozen, ask Nav first: `backend/services/ml/inference.py`,
`backend/services/dash_ui.py`, model artifacts under `backend/models/`,
`frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`,
`frontend/src/App.js` (surgical edits only, explicit approval).
`backend/tests/conftest.py` freeze is WAIVED per current CLAUDE.md.

Forbidden git ops: `push --force`, `commit --amend` on others' commits,
`rebase -i`, `reset --hard`, `checkout .`, `restore .`, `clean -fd`.
**In this shared checkout: never a broad reset.** It previously destroyed the
other agent's unstaged `kanban/BOTTLENECK_ALERTS.md`. Targeted path stash only.

`kanban/BOTTLENECK_ALERTS.md` belongs to another agent — never stage, reset or
discard it. It is currently modified and must be left that way.

## 3. Per-agent receipts

| Agent | Receipt | Branch | Head | Status |
|---|---|---|---|---|
| Hermes | `kanban/cards/agent_HERMES_INTEGRATION_status.md` | `feat/h3-missing-input-neutrality` | `5cba1d9d` | H3 slice complete, PR pending |
| OpenCode | *(its own receipt — not yet received)* | — | — | not started |
| Command Code | *(its own receipt — not yet received)* | — | — | branch not handed over |

Existing `kanban/cards/agent_*_status.md` cards are all from May 2026 and are
stale. No live claim exists on the ranking/persistence lane.

## 4. Worktree / port / database isolation

Each agent uses an isolated worktree off the canonical repository, a distinct
port and a distinct test database. Do not reuse another agent's port. The
current runtime holds `:8000` (backend, PID 46355) and `:3000` (frontend static,
PID 47226) — **both belong to the existing Hermes-managed Meridian stack; do not
restart or kill them without asking.**

The frontend static server serves a **stale production build**
(`main.a56d9c23.js`, built 17.4h before the latest frontend merges), so the
running UI does not reflect current `frontend/src`.

## 5. Findings log

### H3 — ranking semantics (COMPLETE, `5cba1d9d`)

The packet described the defect as "fuses a score once, then passes the fused
score as the flow input into rank_many, which fuses it again. Reproduced
73 -> 67.05." **That description does not match the code.** The caller at
`flowseeker.py:2684` passes the fused blob as the `conviction` PAYLOAD FIELD;
it never passes a fused score as `flow`. The real defects were different and
are now fixed:

1. **Absent scored as neutral.** `_norm_conf` and `_norm_ml` returned `0.5` for
   missing input while `_norm_flow` and `_norm_opp` returned `0.0`. An entirely
   empty setup scored **17.5** and outranked real-but-weak evidence. The
   module's own `*_status` fields said "missing" while the component said
   0.5. Fixed to `0.0`.

2. **Direction leaked into quality.** `_norm_ml` mapped DOWN→0.0, UP→1.0 and
   applied confidence around 0.5, so a bullish label at 0.8 confidence became
   0.95 while the identical bearish mirror became 0.05. Measured on one full
   evidence set: **85.75 bullish vs 60.25 bearish**. Both now score 74.25.
   `_norm_conf` had the same shape: `(v+100)/200` made 0 mean 0.5. Both
   normalizers now scale symmetrically around a neutral midpoint.

3. **Fused blob re-read as raw input.** `rank_many` sniffed dict keys, so a
   blob carrying `label` matched the ML branch and one carrying `total` matched
   the confluence branch — a fused row silently gained components it never had.
   Now gated on fused-output markers.

Tier thresholds unchanged; `test_rank_one_fuses_and_degrades` updated to the
corrected 74.25/MED with a symmetry assertion added inline. No test skipped,
xfailed, or loosened.

All four mutations caught. MUT4 initially survived (the components dict has no
scorer-shaped keys, so no key-only assertion could see it); two tests were added
to pin the fused-marker guard, after which it is killed.

Gates: `tests/services tests/routes` → **4546 passed, 33 skipped**; ruff clean.

**Still unaddressed in H3** (not yet started, and not claimed as done):
- The route supplies `confluence=None, ml=None` at `flowseeker.py:2614` and
  `:2684` despite the four-scorer description. Either connect real causal
  producers or label those dimensions unavailable. Not yet decided.
- `^SPX`/entitlement handling and 0DTE-vs-expiry-count separation (H2).
- Recency/invalidation: a stale high-conviction alert is not a current
  observation.
- Cross-batch leaderboard rank recomputation over one eligible population.

## 6. Binding product decision (from Nav)

Solstice is visually quiet: only **GEX / VEX / Charm** as permanent metric tabs.
Raw/adjusted/activity comparison, scenario review, review queue and journal move
into **Triad**. Raw walls locate the level; adjusted/activity context interprets
a possible reaction; price confirmation is required. **A model or sign alone is
not an automatic trading instruction.**

## 7. Next actions

| # | Action | Owner | Blocked on |
|---|---|---|---|
| 1 | Open PR for `5cba1d9d`; verify CI on exact head | Hermes | — |
| 2 | Hand over `WallDeskSnapshot.v1` frozen fixture | Command Code | definitions |
| 3 | Decide confluence/ml: connect causal producers vs label unavailable | Hermes | — |
| 4 | Confirm scope: H2 scanner cursor + budget, H4 persistence, H5/H6/H7 | Nav | — |

## 8. Actions explicitly NOT taken

No remote merge, no deploy, no service restart, no persistent-service
activation, no broker orders, no credential changes, no external support
messages, no model retraining/promotion/deletion. No test skipped to make a
suite green. No profitability or predictive claim made: the fusion is a
deterministic sort over recorded evidence, **not** a calibrated win probability.
