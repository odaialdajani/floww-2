# Command Code C0–C6 recovery ledger

Session label: Command Code session pasted 2026-09-28.
Runtime: this response was produced by the tool runtime backing this session. I do not have a separate authenticated model/version string in local context, so I record session/branch/SHA evidence rather than asserting Muse Spark 1.3 from the requested name.

## C0 source preservation

- Private original branch intact: `fix/audit-2026-09`
  - HEAD: `bacc9fabb68c464ab1b7a037af5f6d3945b82ec9`
  - Dirty path preserved: `M kanban/BOTTLENECK_ALERTS.md`
  - Dirty blob: `a01f44629be3aefae22e18df8ed98ee7c15be228`
  - Diff is timestamp-only bottleneck metadata.
  - Rollback refs preserved:
    - `pre-rebase-2026-09 = 2750548046c53075b9f31c787062aaeb9623d452`
    - `backup/audit-2026-09-pre-rebase = 2750548046c53075b9f31c787062aaeb9623d452`
- Current origin/main verified without switching another checkout:
  - `origin/main = d905c9d238cc958eefdbb495c0831f723ca29de4`
  - Message: `docs(solstice): stop pinning a SHA the documents own merge invalidates (#72)`
- Observed but not switched/reset:
  - `/Users/nav/Documents/GitHub/floww-2`: `feat/h3-missing-input-neutrality`, `d905c9d2`, dirty bottleneck file
  - `/Users/nav/.opencode/floww2-solstice-ui`: `feat/solstice-ui-cleanup`, `d905c9d2`
- Recovery worktree only:
  - `/Users/nav/.worktrees/cmd-c0-20260928070352`
  - Branch: `cmd/recovery-c0-20260928070352`
  - HEAD: `d905c9d238cc958eefdbb495c0831f723ca29de4`
  - Clean at creation.

## Recomputed relationships

- Prompt SHAs `f77b87dd97cf3a87c3e7c12ed16087ebd079b3ed` and `69d73c958d40a245a9fe89ca816b9ee9e5500bd2` are both ancestors of current `origin/main`.
- Current main is newer: `d905c9d238cc958eefdbb495c0831f723ca29de4`, including #68-#72 lineage.
- `origin/main...fix/audit-2026-09`: `878 43`.
- Merge base: `89fb61b0d8aed1eda879870bcc8c7d8e180604b1`.
- Ancestry/counts are not feature equivalence; main has selective recovery/history-only merges.

## 43-commit classification

Method: `git cherry origin/main fix/audit-2026-09 -v`, commit bodies, patch file lists, production-caller/main-equivalent checks. Classifications only; no ports completed here.

- `c8287907` CI lint/API docs: needs port after current-main gate diff; do not cherry-pick generated docs blindly.
- `ba5be87b` deterministic API-docs gate: needs port after current-main gate diff.
- `9e65b053` OI parser/Net Gamma/signal channel: likely partly already present; minimal behavior diff only.
- `ccb862c2` venv/doc correction: likely obsolete/superseded.
- `0acb3799` delete 13 dead frontend modules: incompatible as whole-commit port; OpenCode/UI-owned.
- `ec1c2aaa` audit claims record: port only missing rows.
- `92b9e4ec` ML schema guard: Hermes/ML lease required.
- `c7d696fb` observability compose fix: check current compose diff.
- `bd5326c7` unwatched alert: check current alert diff.
- `5d9663d2` stop Schwab-as-source docs: doc-only minimal patch possible.
- `2a869af0` Schwab retirement map: port only missing rows.
- `ef1ee1f5` remove Schwab tree-wide: incompatible as whole commit; Hermes owns routes/integration.
- `7ea33753` Schwab tail: incompatible as whole commit.
- `eaf6e2ef` Schwab fixtures: check current fixtures.
- `6c97bb17` sidebar/App contract: OpenCode/UI-owned.
- `3dd5e187` all-Public data contract: Hermes/data lease required.
- `f6f9fec0` blank Triad columns/stale dep: canonical-projection behavior only; no old UI rewrite.
- `ea8f44a4` doc defects: likely obsolete.
- `09963ac6` memory durability pin: Hermes persistence lease required.
- `f39f839a` Charm/WallInspector VEX: trace current wiring; Hermes owns server/routes.
- `8eac5381` fan-out audit docs: likely obsolete.
- `a618813b` warn off metrics.grids.raw fix: port only if guard missing.
- `5156da67` source-inspection flake: likely obsolete.
- `29a53e0a` OI/DUO/DVO surfaces: current main has no DUO/DVO/OI-grid math; minimal canonical port required; C1/C2 gate.
- `de3a3208` eight-surface Triad tabs: old UI absent from main; joint packet only.
- `88b98fc7` import sort: obsolete standalone.
- `3ed61b5d` round-2 Triad docs: likely obsolete.
- `5e042019` Solstice OI/DUO/DVO grid: Hermes/OpenCode coordination required.
- `d70a7ee5` signal-channel fix: check current alerts diff.
- `9c5734c0` #57 docs: obsolete/superseded.
- `c33e635f` where/how wall read: current main has no wall_response module; minimal conditional behavior only; C1.4 gate.
- `f5316174` Play Walls panel: incompatible as UI port; OpenCode owns visuals.
- `b0de55c6` GEX series: current main lacks gex_series; Hermes schema lease required; C1.5/C5 gate.
- `161384cc` ladder/VWAP/chart/camera/mobile: current main lacks session_vwap; UI belongs to OpenCode; C1.2/C1.3 gate.
- `50119c10` VWAP rename: obsolete standalone.
- `85c32d71` DUO/VWAP/chart correctness: DUO math required; VWAP/chart need current-contract adaptation.
- `958bfc68` DUO vs VEX convention: versioned registry only; C2 gate.
- `4f5fd422` one strong wall + rank: deterministic tie policy only; C1.4 gate.
- `3b2f3d42` ladder magnitude: geometry expectations to OpenCode.
- `a40b2958` ADJ/VOL history: Hermes lease required; C1.5/C5 gate.
- `c3bdf4c1` plain-float Greeks: boundary policy; preserve frozen ML; C1.6 gate.
- `155edeac` ADJ = RAW x |delta| pin: canonical registry already has it; port only missing oracle coverage.
- `bacc9fab` mobile tab CSS: OpenCode visual cleanup.

## C1 status

All six remain claims until current code and independent tests establish them. Old frontend/backend counts are stale without collected node IDs, markers, environment accounting, and same-ignore reconciliation.

## C2 VEX distinction

Current main already distinguishes canonical `VEX_1VOLPT`, display/UI dual scale, and frozen ML single-spot scale. Old factor-15 language is separate history and must not silently rescale current data. Use versioned registry IDs/units and schema migration.

## C3 Triad projection

Current TrinityView has GEX/VEX modes, not old private SurfaceTabs/PlayWalls/PriceLadder/GexChart/heatmapSurfaces files. Define WallDeskSnapshot.v1 jointly. Backend owns aggregation/computation; OpenCode owns rendering/selection. No polarity-by-spot-division, inferred zero-gamma root, fake expiry/zero/stale/ticker defaults, or incompatible-population comparisons.

## C4 metric family

Canonical registry already has raw, delta-weighted, session-volume, and window delta-volume metrics with missing-as-unavailable semantics. Do not relabel session volume gamma as volume-delta-adjusted. Window activity needs comparable cumulative observations, reset/retraction exclusion, and visible interval.

## C5/C6 handoff

Fixture and WallDeskSnapshot.v1 packet are not yet published from this slice. Needed: oracle/serialization/route-projection/history tests that fail on old behavior, fixture hashes, exact commands/results, compatibility effects, source-linked limits. Shared route/server mutations remain under Hermes lease. No merge/deploy/trade, broad rebase, force-push, reset, branch deletion authorized or performed.

## Next command

```sh
git -C /Users/nav/.worktrees/cmd-c0-20260928070352 status --porcelain=v1
git -C /Users/nav/.cline/audit-fixes rev-parse fix/audit-2026-09 origin/main
git -C /Users/nav/.cline/audit-fixes rev-list --left-right --count origin/main...fix/audit-2026-09
```

## Slice status (updated as work landed)

Candidate branch `cmd/recovery-c0-20260928070352`, base `d905c9d2`. Eighteen
commits so far. "Verified" below means a test exists that fails on the old
behavior; it does not mean the item is closed against Nav's review.

| C-item | State | Evidence |
|---|---|---|
| C1.1 DUO | math pinned, **displayed value NOT pinned** | `53ea53b6` — oracle vs independent lower-order functions. The −929.33 / −8.77 numbers are still unpinned: the original inputs and the Taylor factor were never recovered, so pinning them would invent a definition. |
| C1.2 VWAP | **verified** | `954604f0` pure math; `a7a6e94a` real async bar path, no nested loop, not labeled market VWAP. 20 tests. |
| C1.3 signed geometry | **verified, handed off** | `9ebf03f9` pure geometry contract + fixtures for OpenCode. Rendering/screenshot side is OpenCode's, not claimed here. |
| C1.4 strongest wall | **verified** | `2e3c9541` deterministic tie policy, no tolerance-ambiguous uniqueness. |
| C1.5 adjusted/activity history | **partially** | `ad56e904` WallDeskSnapshot.v1 round trip preserves missingness. Writer/storage/route wiring is Hermes's lease — not done, not claimed. |
| C1.6 scalar boundary | **verified** | `0ea45dc9` one numeric boundary, missingness preserved end to end. |
| C2 VEX registry | **verified** | `ef4946bf` VEX / DUO / DVO are three distinct rows, with units and basis. No rescale of live data. |
| C3 Triad transform | **verified** | `790257f1` pure projection replaces the inline transform; 6 defects each reproduced by running the OLD code on the same input. |
| C3 real input reaches values | **module verified, route NOT wired** | `04dcf539` + `dca82a7b`. See the route-lease note below — this is the most important open item. |
| C4 one definition per instrument | **verified** | `ed278d04` parity for SPY / QQQ / ^SPX / AAPL; the projection is asserted not to branch on instrument at all. |
| C5 fixture | **published** | `f965064c` frozen WallDeskSnapshot.v1 fixture + pure canonical projection. |

## C3: the public-chain path was still dead, and closing it needs a route line

`/api/public/chain/{ticker}` returns contracts with gamma/delta/oi/volume/
strike/expiry/type/exposure_basis and **no computed `gex`**
(`services/public_api_adapter.py::_fetch_chain_live`). The Triad read `c.gex`,
on the old inline transform and on the new pure projection alike, so real input
yielded zero renderable rows and the view fell through to `/api/data`. The
frontend tests passed because they injected a `gex` the real adapter never
emits. Measured on one fixture: 0 renderable rows before, 3 after.

`backend/services/triad_projection.py` supplies the exposure, deriving each
row's value from the canonical aggregate (`compute_raw_oi([row], spot).net`)
rather than re-deriving the formula, so it cannot drift from the registry.

**Not wired, deliberately.** Attaching it is a shared route/server mutation and
Hermes owns that lease. The one line needed, wherever the chain payload is
assembled for the Triad:

```python
payload["contracts"] = annotate_contract_exposure(payload["contracts"], payload["spot"])
```

Until it lands the Triad still falls through to `/api/data`, which does carry
exposure via `build_heatmap` — so the view is not blank, but it is not this
path either.

An earlier version of that module re-implemented the formula with a hardcoded
multiplier of 100. The canonical resolver honours an explicit per-contract
multiplier and quarantines adjusted/nonstandard contracts, so the hardcoded
version was wrong in all four cases tested (off by the multiplier ratio on
explicit multipliers, and confidently scoring contracts the canonical engine
refuses to score at all). Fixed in `dca82a7b`, with five regression tests.

## Beyond the C0–C6 list

Two gates and two repairs were added that the mission did not name, because the
audit found the same defect class twice more:

- `qc/audit/find_dead_imports.py` (`d9f3ddcf`) — 5 dead imports found and
  repaired. Each sat inside a broad `except` and so degraded to "no data"
  silently. One of them (agentfield `/execute/order`) was deliberately NOT
  wired, because resolving it would create a new broker-reachable path, which
  CLAUDE.md forbids without explicit approval.
- `qc/audit/check_docs.py` (`4cc19c45`) — 8 dead doc links fixed. The
  CONTRACT_MATRIX was checked and is sound: all 28 named producers exist.
- `f90aa2ed` — the dead-wire tests themselves had been stubbing
  `sys.modules["services.heatseeker"].compute_gex_profile`, a symbol that does
  not exist. Passing tests against a dead wire is the same illusion the gate
  exists to kill, so those were replaced with tests on the real path.

## The one inherited failure, characterised

`tests/solstice/test_r7_1_red.py::test_upstream_seam_calls_real_adapter_signature_and_shape`
fails with "Expected mock to have been awaited once. Awaited 0 times."

**Pre-existing and order-dependent, not caused by this work.** Verified by
running it in a throwaway worktree at the base commit `d905c9d2`: it fails
identically there when the file runs as a whole, and passes in isolation on
both trees.

Cause: the preceding test, `test_total_provider_failure_is_unavailable_then_stale`,
calls `movers_svc.get_movers(limit=5)`, which runs the real clock and provider
and consumes the shared request budget. `market_bars._budget` IS the
`public_budget.budget` singleton, and `market_bars._reset_state()` clears only
`_CACHE`, `_QUARANTINE` and `_LAST_ERROR` — not the budget. The seam test
therefore short-circuits inside `_get` before ever reaching the broker.

Not fixed here: both candidate repairs (resetting the shared budget in
`_reset_state`, or giving the seam test a `_NullBudget`) touch a shared service
or a test this slice does not own. Left for Nav or Hermes to call.

## C6 test manifest, measured at `223c6fc8`

Run from `./backend` unless stated — that is the `working-directory` CI uses, and
running these from the repo root produces different (misleading) results.

| CI gate | Command | Result |
|---|---|---|
| 1 truth audit | `bash qc/audit/truth_audit.sh` | 229 passed, 0 failed — **PASSED** |
| 2 lint | `ruff check .` | All checks passed! |
| 3 security | `bandit -r . --severity-level medium -q --exclude ./.venv,./tests --skip B101,B108,B301,B310,B313,B314,B324,B604,B608,B614,B615` | exit 0, no findings |
| 4 tests + coverage | `pytest tests/ -m "not flaky_env" --cov=.` | **6533 passed, 1 failed, 37 skipped**; coverage **67.67%** vs `fail_under = 60` — reached |
| 5 frontend tests | `npm test -- --watchAll=false` | 107 suites, 940 tests passed |
| 6 frontend build | `npm run build` | build succeeded |

Two new audit gates, run directly (not part of CI yet):
`python3 qc/audit/find_dead_imports.py` and `python3 qc/audit/check_docs.py` —
both clean.

Coverage of the modules this slice added, measured directly:
`triad_projection.py` 94%, `session_levels_source.py` 96%,
`domain/session_levels.py` 98%.

The single failure in gate 4 is the inherited, order-dependent solstice test
characterised above; it reproduces identically at the base commit.

Two notes on running the gates locally, so the next person is not misled:

- `pytest --cov` needs `pytest-cov`, which is not in the shared working venv. CI
  installs it explicitly. Running it locally means adding it — do **not** install
  into `/Users/nav/Documents/GitHub/floww-2/backend/.venv`, which is shared with
  another checkout. A `pip install --target <dir>` plus `PYTHONPATH=<dir>` gives
  coverage without mutating the shared venv.
- `ruff check .` from the REPO ROOT reports ~456 errors, almost all in vendored
  data under `data/`. None of that is what CI lints. Run it from `./backend`.

## Honest limits

- The agentfield SDK is not installed and not declared in requirements;
  `server.py` documents that hub as optional. Its tests stub the SDK.
- C1.1's displayed DUO values (−929.33 / −8.77) are **unverified by choice**,
  not by omission: the original inputs and Taylor factor were never recovered,
  and pinning the numbers would invent the definition they claim to check.
- C1.5's writer/storage/route half is **not done** — Hermes's lease.
- C3's route wiring is **not done** — Hermes's lease. Until it lands the Triad
  primary path still falls through to `/api/data`.
- The inherited solstice failure is **left failing on purpose**, with both
  candidate fixes named in the ledger. It is not in this slice's lease.
- The 19 commits sit on `cmd/recovery-c0-20260928070352` in a worktree. Nothing
  was merged, pushed, deployed, rebased or force-written. `fix/audit-2026-09`
  remains at `bacc9fab` with its dirty path and both rollback refs intact,
  re-verified after the last commit.


