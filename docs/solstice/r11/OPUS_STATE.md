# OPUS_STATE — Solstice / R11 (sole harness)

Original checkpoint: 2026-09-29 (session 1). Resumed 2026-09-30 by GPT-6.1-Sol in Zed (not Claude Opus), sole lane —
no Spark/Hermes process is running in this checkout; lane separation is kept
in commits (backend vs frontend), not by leases to other agents.

## Identity

| Item | Value | How verified |
| --- | --- | --- |
| git root | `/Users/nav/Documents/GitHub/floww-2` | `git rev-parse --show-toplevel` |
| remote main | `5312fe569f876be5ad05920218742424348234ce` | `git ls-remote origin refs/heads/main` |
| local main | same SHA, `[origin/main]`, 0 ahead | `git branch -vv` |
| work branch | `solstice/r11-opus` (from `5312fe56`) | `git switch -c` |
| pre-existing dirty | `kanban/BOTTLENECK_ALERTS.md` (M) — NOT mine, untouched | `git status --short` |
| worktrees | `~/.cline/audit-fixes` (`fix/audit-2026-09`), `~/.worktrees/cmd-c0-…` (`cmd/recovery-c0-…`) — untouched | `git worktree list` |
| CI pins | Python 3.12 (`ci.yml:48`), Node 20 (`ci.yml:125`); ruff 0.15.22 | grep of `ci.yml` |
| local interp | `backend/.venv/bin/python` 3.14.6 (newer than ship pin) | CLAUDE.md + venv |
| DuckDB in tests | `DUCKDB_PATH` unset in `backend/.env` → `:memory:` | `duckdb_engine._open_shared_db` |
| credentials | `backend/.env` has a Public key set (value not printed); no AI provider key found | `grep -c` only |
| browser | Playwright chromium-1223 cache present in `~/Library/Caches/ms-playwright` (usable for isolated capture later; not yet used) | `ls` |

Stale machine facts corrected (not obeyed): CLAUDE.md canonical-path section
names the Windows clone; `.planning/STATE.md` still cites `.venv313/Scripts`
and "target py313" (live pyproject says py311). Recorded here, not edited
(out of lane for this slice).

## "Seven unpushed local commits" — disposition

Local `main` has **0** unpushed commits. The unpushed work lives on side
branches. `git cherry origin/main <branch>` classification:

| Branch | ahead | unique | patch-equiv | Disposition |
| --- | --- | --- | --- | --- |
| `fix/audit-2026-09` (worktree `~/.cline/audit-fixes`, remote gone) | 43 | 23 | 20 | **unique, unmerged** — Play Walls / where×how (`wall_response.py`, `PlayWalls.jsx`), `gex_series.py`, session VWAP, OI/DUO/DVO surfaces, Schwab removal tail, 13 dead-module deletion. NOT merged wholesale here (conflicts with #88 surfaces, deletes files). Design intent (raw=where, adj=how) is re-implemented on main's canonical surfaces; see Slice T. |
| `cmd/recovery-c0-…` (worktree) | 20 | 20 | 0 | unique; recovery ledger + C1–C4 tests; ahead 20 / behind 84. Untouched. |
| `feat/h3-missing-input-neutrality` | 39 | 39 | 0 | older H3 scanner definition (superseded by main's `solstice_rank`, per #88 receipt). Untouched. |
| `backup/audit-2026-09-pre-rebase` | 5 | 5 | 0 | backup of the audit branch. Untouched. |
| `verify83`, `fix/health-endpoint-500`, `fix/rerunfailures-missing`, `docs/status-refresh-*`, `docs/model-audit-2026-09` | 1–5 | 1–4 | 0–1 | small unique doc/test commits; untouched. |
| `docs/closeout-h2-h6`, `docs/ledger-79`, `docs/no-self-referential-sha`, `docs/record-pr73-merge`, `docs/status-final-sha`, `docs/status-pr-reconciliation`, `fix/alert-bool-momentum`, `fix/claude-md-venv-regression`, `fix/ignore-sqlite-runtime-stores`, `fix/truth-audit-subject-only`, `test/bar-guard-coverage` | 1–2 | 0 | all | **equivalent** (already in main) |

No branch named in a "seven commits" receipt could be matched to exactly
seven; the count is **unavailable-to-inspect** as stated. The only local
branch tracking `origin/main` with commits ahead is `cmd/recovery-c0-…`
(20). Nothing was cherry-picked or rebased.

## Protected boundary

- Manifest: `docs/solstice/r11/PROTECTED_MANIFEST.txt` — 71 git blob hashes
  at `5312fe56` (Flowseeker/Tidehunter frontend dir, flowseeker route/service
  + tests, blademap tests, tidehunter plist).
- `MarketCoverage.jsx` blob `eeccaa3d…` includes upstream `828c3bbb`
  (provider-release-check fix). **Preserved, flagged, not reverted.**
- Check command: `git diff --stat 5312fe56 -- $(awk '{print $2}' docs/solstice/r11/PROTECTED_MANIFEST.txt)` must be empty.

## Backend → mounted-UI coverage map (at 5312fe56)

| Capability | Producer | Route / field path | Mounted consumer | State |
| --- | --- | --- | --- | --- |
| Raw OI GEX grid | `gex_core.compute_gex_grid_vendor` | `/api/heatmap` → `grid.grid` | Solstice grid, Triad raw pane | already mounted |
| Δ-weighted OI grid | `compute_gex_grid_delta_weighted` | `metrics.grids.delta` | Solstice basis "Δ-wtd", Triad adj pane | already mounted |
| Session volume Σc·u·V | `compute_gex_grid_volume_vendor` | `metrics.grids.activity` | Solstice "Activity", Triad **mislabelled "Session vol × Δ"** (R11-01) | mounted, mislabelled |
| Session volume×|Δ| Σc·u·V·|δ| | `compute_gex_grid_session_delta_volume` | `metrics.grids.session_delta_volume` | **none** (0 refs in `frontend/src`) | backend-only |
| Window Δvolume×|Δ| | `solstice_window` + `window_contract_activity` | `metrics.window_*`, `metrics.wall_window` | inspector row; **reads `window_daddex_reason`, backend writes `window_dadgex_reason`** | mounted, reason key broken |
| VEX | `compute_vex_grid_local` | `grid.vex_grid`, `grid.vex_meta` | Solstice VEX, compare pane | already mounted |
| Charm | `compute_charm_grid_local` | `grid.charm_grid`, `grid.charm_meta` | Solstice Charm | already mounted |
| DUO / DVO | `domain.second_order_exposure` | none | none | helper-only (not promoted) |
| Per-surface counts | domain `ExposureResult` | `metrics.*_usable/_missing/_invalid`; grids have **no usable count, no per-cell coverage** | inspector (dadgex only) | partial |
| Walls | `wall_structure.discover_walls` | `metrics.walls` | status strip, sidebar, inspector | already mounted |
| Wall-local Δ / volume | `wall_metric_breakdown` | `metrics.wall_metrics[id]` (`volume_*` is Σc·u·V but row says `basis: OI_DELTA_WEIGHTED`; **no per-wall session Δ-volume**) | inspector compare table | mounted, incomplete |
| Exact contract | `contract_identity.resolve_contract` | `GET /api/solstice/{t}/contract` | **none** — UI uses legacy `/api/contract/{t}/{strike}/{exp}` | backend-only |
| Solstice scan/rank | `solstice_scan.run_scan`, `solstice_rank` | **no route** | leaderboard reads `/api/flowseeker/universe/*` | helper-only |
| Movers | `/api/movers` (`movers.v2`) | route | `Movers.jsx` | already mounted |
| Recorder / replay | `heatmap_history` | `/api/solstice/*` replay routes | `ReplayStrip` | already mounted |
| Lodestar | `services/agent/*`, `solstice_evidence.py` | `/api/agent/*`; `contracts.py:108` blocks non-raw/replay | `AgentProvider` (closed by default); Solstice publishes context; **Triad publishes none** | mounted (raw live only) |
| Offline guard | `tests/offline_network.py` | opt-in fixture | — | exists, opt-in |
| Capture worker | `recorder_health.start_worker` | disabled by default | — | awaiting activation |
| SPX entitlement | capability matrix | `/api/solstice/capability` | — | awaiting entitlement |

## Leases (self)

- Backend: `backend/services/gex_core.py`, `backend/domain/exposure_metrics.py`,
  `backend/services/solstice_enrichment.py`, `backend/server.py` (metrics block
  + route registration only), `backend/routes/solstice*.py`, new
  `backend/tests/solstice/test_r11_*.py`.
- Frontend: `frontend/src/components/heatseeker/*` (Solstice), 
  `frontend/src/components/TrinityView.jsx`, `frontend/src/lib/*` (new
  helpers), `frontend/src/App.css` (Solstice/Triad sections),
  `frontend/src/App.js` (surgical callback memoisation only).
- Never: anything in `PROTECTED_MANIFEST.txt`, `inference.py`, `dash_ui.py`,
  `conftest.py`, model artifacts, `frontend/package.json`, `craco.config.js`,
  `frontend/.env`, `kanban/BOTTLENECK_ALERTS.md`.

## Queue (in order)

1. **H01** metric contract: per-surface + per-cell coverage, window kernel
   typed-input defects, per-wall session Δ-volume, window reason alias,
   R11-01 route reproduction (100k/10k/5k), schema note.
2. **F01** activity consumer: Triad/Solstice labels bound to the registry;
   inspector rows; window reason key.
3. **PERF/F06** re-render + resize stability (App inline props, playback
   timer, fitRows drift, strike-click trade gate).
4. **F03/F04/F05** toolbar consolidation, layout menu (Focus / Matrix+Profile /
   Multi-map / Calendar), aligned signed profile.
5. **H02/F02** exact-contract drawer against `/api/solstice/{t}/contract`
   with generation guards.
6. **H04/F08** Solstice-owned scan route + leaderboard wrapper.
7. **H05/F09** Lodestar context v2 + Triad publishing.
8. **F07** Triad raw-wall-first review desk.
9. **H06** offline gate; **P6** gates + receipt.

## False leads / corrections

- Agent map claimed Solstice still had a permanent Raw/Delta/Activity tab row:
  **false** — Solstice already uses a GEX basis `<select>`; the permanent row
  exists only in Triad (`TrinityView.jsx:250-265`).
- `test_wall_strength_policy.py` touches no provider seam (imports only
  `domain.wall_strength`); the teardown error attributed to it is the
  session-scoped offline guard firing late (#88 receipt names
  `test_agentfield_hub.py` as origin). To be reproduced in H06 before any fix.

## Commands run (this checkpoint)

```
git rev-parse --show-toplevel; git log -1; git status --short --branch
git ls-remote https://github.com/odaialdajani/floww-2.git refs/heads/main
git cherry origin/main <branch>   (all local branches)
git ls-tree -r origin/main -- <protected paths> > PROTECTED_MANIFEST.txt
git switch -c solstice/r11-opus
```

## Next action

Resume checkpoint 2026-09-30T12:17:32Z: preserve the actual frontend recovery files, integrate reviewed PR #89, then finish mounted layouts/Triad. H01 is committed at `95b16a619d267d6079cd68f751a0c0aa93c1a3aa`, not pending.

## Recovery intake (2026-09-30)

- Actual base/main: `5312fe569f876be5ad05920218742424348234ce`; local HEAD: `95b16a619d267d6079cd68f751a0c0aa93c1a3aa` on `solstice/r11-opus`.
- User explicitly authorizes reviewed integration/merge/publish, but no deploy/restart, force, capture, retrain or order wiring. Surgical App.js composition/callback changes are in the requested scope.
- PR #89 is OPEN, not merged, at `ed107cc11accf22aa8a0cb8779325ae55cdf2464`. Retrieved with `gh pr view 89 --json state,headRefOid,statusCheckRollup,mergeable,mergeStateStatus`: backend-tests, frontend-build and ruff SUCCESS; docker-build SKIPPED. Mergeable/CLEAN. Those are #89's checks, not the later candidate's checks.
- Reviewed its 15-file diff. It overlaps local H01 (wall/session counts and typed window inputs) and ControlBar. Preserve both contributions; consolidate compatible field aliases and the duplicate display-metadata modules after integration.
- `python3` manifest comparison of all 71 protected blobs against #89 head: no changes. Upstream MarketCoverage retained.
- Local unfinished frontend files match the pasted handoff. Ran `CI=true npx craco test --watchAll=false --runInBand src/lib/solsticeMetrics.test.js src/components/heatseeker/SkylitHeatmapGrid.test.jsx src/components/heatseeker/SkylitHeatmapGrid.r11.test.jsx src/components/heatseeker/SkylitControlBar.test.jsx`: 4 suites / 40 tests PASS. The handoff's larger remembered totals are not this result.
- No actual 23-commit Opus stack exists on this branch. `fix/audit-2026-09` remains separate unique work described above; do not merge its deletions/alternative metric engine wholesale.
- Named Recovery-Harness/Audit/ZIP files were not attached as readable artifacts and path search found none. Repository #89 recovery receipt is available via its branch.
- GSD builder invocation ends at dirty-tree guard (changes on non-gsd branch); no queue claim/stash/reset. Discovery inputs already specify the product choices; no new speculative discovery map or recurring task created.
- Unrelated kanban file and two other worktrees untouched. No additional agents created. No preview or market/AI network call made.
- Recovery commit `812ea89d`, explicit local integration merge `438727b1`.
- #89 actually merged to `origin/main@ca3dd8b5ccad5668cf433e8383d2f84e68b269ed`; verified by fetch + log. This was an explicitly authorized, reviewed merge, not a deployment.
- Resolved four conflicts without dropping either suite: one wall calculation, compatible short/full aliases, typed window validation/counts, governed window surface, compact labels. Combined backend `pytest tests/solstice/`: 474 passed / 24 warnings; scoped Ruff PASS. Combined focused frontend: 73 PASS.

### Working slice F03/F04/F06/F07/H02 (2026-09-30T12:50Z)

Owned additions/edits: SkylitDashboard/Grid, gexBases compatibility adapter, solsticeMetrics, TrinityView, ExactContractReview, shared signed profile, SolsticeWorkspace.css, stable Solstice review callbacks, surgical App.js callback wiring, mounted regression tests. No protected path edited.

- Four same-observation layouts: Focus, Matrix+Profile, four-metric Multi-map (not cross-symbol fetching), Calendar. Profile sums exact loaded dates, zero axis and selection align; source metadata stays visible without Lodestar. Basis availability from backend contract. Replay panel opens on request. Manual scroll pauses spot-follow. Existing compare/review testids retained.
- Triad: top signed profile, raw-left/adjusted-right, one adjustment selector, shared raw wall, conditional readiness from wall-local supplied values + measured interaction + quality. No model/order/target/stop. True dte=0 / <=7 scopes; Next listed remains explicitly disabled pending a proven scope route. Replay handoff uses existing stored projection and never fresh price path.
- Exact contract drawer now lists supplied shortlist and resolves explicit OSI/tuple+snapshot, never midpoint/first-expiry guess. Abort/generation guards retain late error/success ownership. Also composed into Solstice drawer.
- Stable callbacks remove two blocking legacy contract fetches and avoid callback-identity churn on spot polling; unknown OI/delta/quotes remain null. Existing handoff remains research/paper only; no order calls added.
- Red: four Canvas tests missing layout/follow controls. Green: 48 Canvas+Dashboard tests. Red: three Triad mounted tests missing profile/exact-choice/context. Green after implementation. Existing tests adapted only for intentional button-to-selector and listed-candidate behavior.
- `CI=true npx craco test --watchAll=false --runInBand`: 114 suites / 986 tests PASS before latest callback edit. Existing React act warnings observed; not yet a warning-free browser receipt.
- `CI=true npx craco test --watchAll=false --runInBand src/hooks/useSolsticeReviewCallbacks.test.jsx src/App.test.jsx src/App.egress-invariant.test.js`: 2 suites / 6 tests PASS (App.test.jsx not present; only the named existing suites ran). Callback wiring test red before App patch.
- `CI=true npm run build`: compiled successfully. Large-bundle warning remains (main ~273 KB gzip, existing chunk ~1.38 MB); no measured live-performance claim.
- Offline reproduction: `pytest tests/test_wall_strength_policy.py tests/services/test_agentfield_hub.py -p tests.offline_network -q`: 46 passed + 1 teardown error. Guard BLOCKED one api.public.com attempt, originating from `TestTickerNormalization.test_gex_regime_uppercases_ticker`, not wall-strength policy. Fix actual mocked seam next; do not weaken guard.
- New inspected H02 defects: exact snapshot route does not reject cross-ticker snapshot ID; quote_state reports stale=False from quote values with no timestamps when last exists. Add red route/unit regressions before correcting.
- Current reviewed remote base is ca3dd8b5; local current committed head remains 438727b1 plus working slice. No candidate PR yet; no exact-candidate CI claim.
- Next: fix isolated provider seam and exact-contract server identity/age, verify scan coordinator through a Solstice-owned route (not legacy caches), validate v2 context with current raw/replay guard retained, run integrated gates and publish recoverable PR with exact-head evidence.

### Recovery checkpoint 2026-09-30T13:00Z

- Re-fetched origin: main remains ca3dd8b5; local integration HEAD 438727b1, confirmed ancestry. No new lane/agent created.
- Ran 7 current frontend suites (Canvas, Dashboard, Triad, callbacks, RecoveryR12, App egress): 74 passed. React act warnings remain in async owned tests; will fix rather than suppress.
- Protected manifest: 71 files, zero changed blobs. `git diff --check` found one trailing space in the owned toolbar; corrected.
- Checkpointing actual mounted UI/callback work before backend fixes so it can be recovered and published. No claim of current CI or browser acceptance.
- Published workspace checkpoint 122c6b0e to origin/solstice/r11-opus; remote SHA verified. Draft PR #90: https://github.com/odaialdajani/floww-2/pull/90. Main remains ca3dd8b5; #90 is not merged.

### H02/H06 checkpoint 2026-09-30T13:06Z

- Reproduced 46 passed + 1 offline teardown error. Origin: test_gex_regime_uppercases_ticker. Fixed the dead services.heatseeker mock to the actual Public adapter and asserted uppercase call identity. Guard unchanged.
- Six exact-contract regressions red before patch: complete prices without time falsely fresh; OSI ignored conflicting tuple; absent multiplier state; route reported guessed scope; cross-ticker snapshot accepted; exact decimal request rounded to listed strike.
- Green: `.venv/bin/python -m pytest tests/solstice/ tests/test_wall_strength_policy.py tests/services/test_agentfield_hub.py -p tests.offline_network -q -p no:cacheprovider --tb=short`: 525 passed / 27 warnings; zero external attempts. Scoped Ruff clean.
- Contract route now uses string/Decimal identity, ticker-owned snapshots and actual recorded scope/provenance. Quote freshness remains unknown without a declared source policy; prices alone cannot make it fresh. Multiplier value and source status explicit; older recorder rows lack multiplier source, so provenance stays unknown.
- Known storage limit: old contract observation strike column is DOUBLE. Exact transport is now preserved and no near-strike substitution occurs; migration for source decimal strings remains required for precision beyond stored DOUBLE. Normal listed fractional strikes covered. No production store/config change.
