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
- Next: checkpoint frontend recovery with exact paths, merge #89 under authorized reviewed merge, integrate origin/main without stashing kanban, test combined tree, then layout/profile/Triad slices.
