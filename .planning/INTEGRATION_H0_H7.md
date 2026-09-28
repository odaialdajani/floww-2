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

### H2 — scanner cursor: claim REFUTED, no code change

The packet's headline H2 defect — "prefilter truncates to limit, then cursor
advances by that same limit modulo the truncated length. Repeated calls scan
the identical top batch" — **does not exist in this code.**

`backend/services/public_scanner.py:118 advance_cursor` rotates over the FULL
universe size, not the truncated batch:

    first 3 indices per call: [(0,1,2), (10,11,12), (20,21,22), (30,31,32), (40,41,42)]
    cursor after 5 calls: 50
    n=0 -> ([], 0)          # empty universe guarded
    slice>n -> ([0,1,2], 0) # slice larger than universe guarded

Batches are disjoint, so repeated calls do advance. No change made; recording the
refutation so the item is not re-audited as broken. **Not yet checked**: whether
priority changes between calls are honored across the rotation, and the
checkpoint/durability requirement — those remain open.

### H3 — additional: absent flow reported as a measured zero (`df3ddc10`)

`flowseeker.py:_universe_scan_conviction` seeded `flow = {"conviction": 0}`
before attempting the DuckDB read. `_norm_flow` returns `0.0`/"ok" for a dict
holding 0, so a row whose feed was unavailable reported `flow_status: "ok"` —
evidence that was never observed, presented as measured. Now starts at None and
only builds a flow dict when the read returns a real non-None conviction.

Combined with the phantom-0.5 fix, every `/universe/scan` leaderboard row on
main carried **17.5 points of confidence that did not come from evidence.**

The silent-except fallback is preserved exactly: an unavailable feed still
degrades to unranked rather than failing the rank.

### H3 — availability boundary unified across scorers (`b51ee581`)

The three normalizers had drifted, so `*_status` could not be trusted. Three
distinct meanings were being reported through two labels:

| payload | before | now |
|---|---|---|
| `_norm_flow({})` | 0.0 / `ok` | 0.0 / `missing` |
| `_norm_flow({"conviction": None})` | 0.0 / `invalid` | 0.0 / `missing` |
| `_norm_conf({"total": None})` | 0.0 / `invalid` | 0.0 / `missing` |
| `_norm_ml({})` | 0.0 / `invalid` | 0.0 / `missing` |
| `_norm_ml({"prediction": None})` | 0.0 / `invalid` | 0.0 / `missing` |

The confluence case is a **real integration boundary, not hypothetical**:
`services.agent.confluence.score` returns `{"total": None,
"direction": "insufficient_evidence"}` when it has no coverage (verified by
calling it). The producer said "insufficient evidence"; the ranker relabelled
it "invalid" = "emitted garbage".

Genuinely malformed data still reports `invalid`; a real reading of 0.0 still
reports `ok` with a 0.0 component. So "measured and neutral" remains
distinguishable from "never measured" while both contribute nothing.

**Correction to my own work:** I initially "simplified" the empty-dict clauses
in all three normalizers as redundant. That was wrong for confluence —
`conf.get("total", 0)` defaults to 0, not None — and the suite caught it. The
confluence clause is load-bearing and is now commented as such. The `_norm_flow`
clause genuinely IS redundant; MUT7 survived its removal, so it was deleted
rather than left as untested code.

**Confluence producer exists and is compatible.** `node_confluence.node_brief`
calls `services.agent.confluence.score`, which emits exactly the `{"total",
"direction", "dimensions"}` shape `_norm_conf` consumes. The route still passes
`confluence=None` — connecting it is the open decision below, not a blocker.

### Live-data confirmation of the availability fix

Not a synthetic fixture — the running Floww-2 service, `/api/heatseeker/node-confluence?ticker=SPY`
(136 strikes considered), feeding its real `rows[0]["confluence"]` into `rank_one`:

    producer total         : None
    producer direction     : insufficient_evidence
    ranker confluence_status: missing        <- was "invalid"
    ranker component        : 0.0
    conviction              : 0.0 LOW

Before the fix the ranker told consumers this producer emitted garbage. It now
agrees with the producer: nothing was available, so nothing was claimed.

The row shape is `{'total', 'direction', 'dimensions', 'coverage_weight',
'missing_input_policy', 'weights_version'}` — directly consumable by
`_norm_conf`, so wiring it is mechanical rather than a redesign.

### H3 — recency: age now surfaced, score deliberately unchanged (`f76a5cee`)

`asof` was recorded on every row and never evaluated, so a historical alert read
as a current observation:

    6-month-old alert : 31.5 LOW | asof 2026-03-01T00:00:00+00:00
    fresh alert       : 31.5 LOW | asof 2026-09-28T00:00:00+00:00
    identical score? True

Evidence now carries `asof_status` in {fresh, stale, future, unknown,
unparseable} and `asof_age_seconds`. The 7-day staleness window matches the
alert feed window the scan route actually reads.

**The conviction score is unchanged, on purpose.** A decay curve would be a
model of how conviction decays, and there is no evidence for one here.
Applying invented decay to a fusion score is precisely the class of
unvalidated arithmetic this work removes. The module reports age and refuses to
rescale; the consumer decides. A test pins the diagnostic as inert.

Absent and unparseable timestamps are labelled, never guessed.

Mutations: MUT10 threshold widened → 1 failed; MUT11 always-fresh → 1 failed;
MUT12 unparseable-as-fresh → 1 failed. ruff flagged 3 issues on the first draft
(local import placement, timezone alias); fixed before commit, not left to CI.

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
