# U16 — evidence/omission map (OpenCode takeover, 2026-10-08)

Method: every unified task mapped to preserved behavior, material delta,
exact evidence, and holder. The old 53-ledger + later rows are REFERENCES
(statuses never transferred to this wave). No tracked category is silently
omitted — each line below says done, blocked-with-reason, or held.

## Task map

| ID | State | Evidence / holder |
|---|---|---|
| U01 census/retention | Done, Cline ACCEPT | `U01/RETENTION-MAP.md` + hashes |
| U02 null-date | Done, Cline ACCEPT | review + 238-run + producer note |
| U03 old-desk review | Done, Cline ACCEPT (review complete) | dossier; proposal merged via PR115 fast-lane (`f1e76e82`), mount recorded |
| U04 neutral theme | Done, Cline ACCEPT (structure) | review; visual sign-off → U17 |
| U05 PNG background | Done, Cline ACCEPT (code+unit) | review + real-browser PNG receipt |
| U06 related | Cline verified-no-repair (WIP, no verdict yet); my probes complement | Cline verdict pending |
| U07 scanner | Same as U06 | Cline verdict pending |
| U08 history | Same as U06 | Cline verdict pending |
| U09 context/matrix | Done, Cline ACCEPT | review + 7-test matrix + STOCK-quirk handoff |
| U10 legacy export | Cline slice; my REPAIR_REQUIRED (2 minor doc/fidelity items) | Cline fix pending |
| U11 storage | Done, my ACCEPT | review; 5/5 re-run |
| U12 trinity | Done, my ACCEPT (slice) | review; 4/4 re-run + ruff |
| U13 budget/range | Done both sides (slice ACCEPT + sweep verified) | reviews; redeploy still needs human sign-off (`:8002` serves pre-slice code) |
| U14 controller | My dossier done; Cline verdict pending | `U14/REVIEW-NOTE.md`, 51/51 suite |
| U15 boundary | My dossier done (takeover) | 5-test contract, HOLD list inside |
| U16 | This record | — |
| U17 visual | BLOCKED: U06–U08 lack Cline verdicts | prep banked (routes, browser 11/11, interaction 6/6, Related/saved/history 130) |
| U18 gates | BLOCKED: on U10–U17 | prep banked (full frontend 2022 green; merged-head 2018 + flakes-resolved) |
| C17 exposure metric | OPEN, optional P2 | no admitted per-strike exposure series exists server-side (see below) |

## Omissions swept (finite)

Related/saved/history features, legacy recovery, friend immutability (77/77),
route identity (8), final-gate prep, commissioning separation — all mapped
above. No category uncovered. Historical REPAIR_REQUIRED items were
reproduced on current snapshots where in scope (U02/U04/U05/U09 parents,
T03 trio); unrelated peer heads unlocked nothing.

## C17 concrete gap (for whoever builds it)

An admitted per-strike exposure series (measured-vs-unknown basis flags)
does not exist in any backend envelope or endpoint at `8194eca4`; the
chain serves one canonical gex + basis per row (U12 established ADV-class
metrics refuse rather than invent). Closure path: version a measured series
into the envelope (producer-side, Cline-shaped work) OR explicitly defer
with reason. Frontend must not invent it. Unchanged by this record.

## Holds (all named, none absorbed)

H-PUBLICATION (no commits/pushes/merges/deploys without human word),
H-ORIGINAL-STOP (8000/8001 + user jobs intact), H-CAPTURE, H-EXECUTION,
H-CLINE-BINDING (Cline halted mid-U15; its lane preserved, unmerged),
H-TRIAD-PROMOTION (now a merged fact for this branch — recorded, not
waived), plus the 7 historical NAV holds.


## Current reconciliation supersedes historical table (2026-10-08)

Local composition now includes both the unified C17 lineage and main's
Triad desk: merge `26ae49cc` has exact parents `ea276b1b` and `2a293b6e`.
The neutral theme, friend-authored current stock tools, data repairs and
Triad mount are retained. C17 now has a backend series and a same-snapshot
consumer repair under review; the original packet still has 55 engineering
obligations (54 historically accepted, C17 pending) and seven external IDs.
No status is silently transferred to this candidate. Six commissioning
categories remain plus the separate NAV-PAPER-EXEMPT policy decision.
U17/U18 need frozen-source checks and independent acceptance; legacy recovery
still needs a real-store completeness receipt. Current host processes are
idle/aborted; no controller or coding model was launched by this audit.

## Slice-4 lane disposition (Spark, 2026-10-09, successor `fix/floww-finish-20261008`)

Source: Hermes `LANE-INTEGRATION.json` (53 non-ancestor commits; 27
patch-equivalent + 1 identical already included) + OpenCode worksheet
`FLOWW-Lane-Disposition-Worksheet.md`. Every held item below was re-checked
against the live successor tree (not just subjects/ancestry). No blanket
cherry-pick; no history removed. User decides DEFER rows explicitly.

### INCLUDED (adopted onto successor with failing-first regressions)

| Lane commit | What | Evidence |
|---|---|---|
| `155edea` ADJ == RAW x \|delta\| | Adopted by `01c1a6ab` as new `test_oi_duo_dvo_surfaces.py` (6 tests incl. hostile missing/invalid/unknown-type/mult/netting classes) | 6/6 pass |
| `c3bdf4c` greeks plain float | Worksheet guessed DROP (no numpy import) — **wrong**: scipy returns np.float64, proven live. Adopted: `float()` on all 11 success returns in `bs_greeks.py` + new `test_greek_plain_float.py`. Values unchanged | 237 pass across 7 greek suites (canonical, oracle, masking, scalers, convention) |
| `9c5734c` #57 record + `3ed61b5` round-2 Triad record | Adopted as labeled historical appendix in `docs/audit/CLAIMS-VERIFIED.md` (history, not live claims) | File review; no protected paths touched |

### SUPERSEDED (present by construction, with evidence pointer — not a claim)

| Lane commit | Evidence |
|---|---|
| `85c32d7` DUO-106x | Candidate never had the bug: `domain/second_order_exposure.py` carries the correct product-rule `C*(S^2*g''+4*S*g'+2*g)`, pinned by `test_second_order_exposure_oracle.py` |
| `85c32d7` VWAP dead wire | Same bug class guarded: `session_levels_source.py` + `test_session_levels_source.py` assert the bad symbol does not exist; 23 pass with OSI suite |
| `85c32d7` GexChart sign | Component absent; sign discipline lives in shared palette, 35 `SkylitHeatmapGrid*` tests pass (incl. r11) |
| `a40b295` ADJ history | Live path computes `delta_grid` with population counters (`server.py:1516`); history persists all grids generically (`heatmap_history.py:435-451`); math pinned by adopted `155edea` tests |
| `f39f839` Charm/VEX dead rows | VEX row present (`WallInspector.jsx:143-155`); `test_charm_grid_surface.py` passes |
| `d70a7ee` signal channel + `9e65b05` parser/channel | `alerts.py:92-131` already carries sync broadcaster + normalized frames + logged-only fallback (successor `95a17b47`); 15 channel/OSI tests pass. Lane-tip `databento_provider.py`/`test_osi_parse_regression.py`/`MultiTimeframeGEXPanel.jsx` byte-match candidate = already included |
| `29a53e0` + `5e04201` OI/DUO/DVO surfaces | Ship via `heatmap_snapshot.py`; 51 pass across snapshot/charm/OI-DUO-DVO/oracle/registry suites |
| `de3a320` tab-set doctrine | Implemented as TriadDesk + Raw+Δ compare (`SkylitDashboard.jsx`) + admitted exposure endpoint (live 200, 11/11 C17 tests) |
| `1a7ff03` C17 slice | Candidate carries the newer reviewed C17; lane version must not regress it |
| `de9b136`/`f95aeb7` Workspace.jsx | 7-line diff: lane uses local `cellPalette` normalization; candidate uses reviewed shared `signedCellPalette` + hatching. Adopting the lane file would REGRESS PR117 grids — do not. 103 `RangeAnalytics*` tests pass |
| `958bfc6` DUO/VEX distinction | Already in candidate docs (`second_order_exposure.py` VEX-non-equivalence section, `METRIC_CONTRACT.md` convention column) |

### CONFLICT / DEFER — preserved as history, not adopted

| Lane commit | Disposition |
|---|---|
| `4f5fd42`, `f531617`, `c33e635` (`wall_response.py`, `PlayWalls.jsx`) | DECLINED (acting owner, 2026-10-09) with safety rationale, not merely deferred: the modules encode dealer-intent / front-running instructions that convert exposure data into attributed dealer positioning — the exact sign-only-trading harm class the R11 guardrail exists to prevent. The safe subset already ships (king-by-construction at `gex_core.py:606`, TriadDesk same-rail doctrine, conditional-watch wording). Rebuilding the doctrine as conditional watches remains possible only as a fresh design with its own review, never a wholesale lane merge. History preserved untouched. |
| `161384c` camera | DECIDED (acting owner, 2026-10-09): split verdict. Price-chart PNG export is PRESENT and tested (`RecordedPriceChart.jsx` downloadChart + failure-state tests, zero deps — the user-visible save-a-chart capability exists). A heatmap-grid snapshot button is DECLINED until a dependency install is safe: `npm install` fails in this checkout (node_modules symlinks to another worktree's install + ERESOLVE conflicts; package.json/lock protected), and the lane's button without a rasteriser is a control that only reports failure. Revisit with a real node_modules + lockfile update + full build proof. |
| `b0de55c` recorded multi-resolution GEX curve | SPECIFIED (acting owner, 2026-10-09): bounded build spec at `docs/unified/RECORDED-CURVE-SPEC.md` (aggregate-only table, rollup-not-refetch, 30-day TTL + 50k cap, default OFF, activation checklist). NOT built, NOT activated: recording writes production records and stays under H-CAPTURE until the checklist is explicitly approved. |

### N/A or DROP (verified, not assumed)

| Lane commit | Reason |
|---|---|
| `3b2f3d4` ladder legs, `50119c1` vwap rename, `bacc9fa` mobile tabs | Target components/files absent (`PriceLadder`, `session_vwap.py`, `SurfaceTabs`/`.surface-tab` all missing) — the defects cannot exist; ruff-clean covers style |
| `88b98fc` import sort | Trivial; ruff clean on touched files |
| Composition docs (`de9b136`/`f95aeb7` CLINE-VERDICT/WIP + unified docs) | Preserved in lane checkouts as history; not adopted as live docs |

### Still open after this slice

Nothing engineering-actionable remains open. Prior gaps closed by owner
decision (2026-10-09): R11 wall modules DECLINED with safety rationale (not
deferred); camera split-decided (price-chart export present, grid snapshot
blocked on dependency-install safety); recorded curve SPECIFIED with
activation checklist (not built/activated, H-CAPTURE). (INCOME-04 producer
`fillna(0)` closed after this record was first written: NaN→None loader +
`iv_unknown`/`volume_unknown` flags, 7 backend + 2 frontend tests; see
`HEATMAP-SUCCESSOR-MAP.md` item 16.) What remains needs a human, not code:
six commissioning holds, visual acceptance, release, PR-merge approval.

## Test-hygiene appendix (Spark, 2026-10-09 — zero product changes)

- **Session-poison kill:** `test_toxicity_ensemble_contract.py` installed a
  spec-less torch stub into `sys.modules` at collection time. scipy's
  array-api dispatch probes `sys.modules["torch"].Tensor`, so the stub
  turned every later `scipy.stats` call session-wide into AttributeError —
  deterministically killing the ml_realtime kurtosis cross-check in full
  runs while green in isolation (bisected file-by-file to prove it). The
  stub served nothing (ml_ensemble is natively torch-optional; the file uses
  no torch names), so it was removed with the mechanism documented
  in-file — not worked around.
- **Optional-dep guards:** 25 agent/snapshot files (`mongomock_motor`), 2
  dash files (`plotly`), 2 hypothesis files, 1 tenacity file, 3 torch
  files, plus `skipif(torch)` on 2 detector-shape tests and local
  `importorskip` in 1 admission test — all following the repo's existing
  `importorskip("duckdb")` idiom. Missing deps now skip visibly with
  reasons instead of erroring; hosted CI (which has them) still runs all.
- **Result:** full backend suite `7530 passed, 62 skipped, 0 failed,
  0 errors` (e2e/perf excluded as before). Ruff clean on every touched
  file. The kurtosis oracle, all greek suites, and the ML-scale guards are
  in the green set.
- **Beyond the default collection:** `tests/perf/test_p99_latency.py` 9/9
  and `test_bars_audit.py` + `test_feed_economics.py` 8/8 pass when run
  explicitly (perf dir is excluded from the default suite). Remaining
  exclusions are tool-blocked, not code-blocked: `tests/e2e`
  (needs playwright+chromium+pixelmatch) and the Storybook vitest browser
  suite (needs the Playwright bundled headless shell; the config's
  `FLOWW_BROWSER_CHANNEL=chrome` escape is ignored by this toolchain
  version). Neither touches code changed on this branch.
