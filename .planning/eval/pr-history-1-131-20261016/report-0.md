# PR #1–#43 audit at `6716946b109e43ced81bec6f2fec9c0c46332f14`

**Read-only engineering audit, not original-owner acceptance or live readiness.**

Records: 43, one per PR. Classification counts: {"confirmed repair needed": 3, "current intent retained": 31, "owner-hold": 4, "superseded/declined": 4, "unverified": 1}.

## Evidence and limits

Every changed-file page was fetched using GitHub pagination and counted against fresh PR detail; all 43 counts match. Issue discussion, reviews and inline comments were fetched to terminal pagination; all returned zero for this range. Empty remote discussion is not approval.
PR #1 and #3 are depth-limited broad history imports. REST and GraphQL both stop at 250 commits although declared totals are 417 and 358; local ancestry inventories are separate evidence and are not substituted as exact PR-specific acceptance. Their broad file inventories were fetched, not exhaustively semantically certified.
Existing deterministic tests: 131 unique functions passed by direct/AST execution, 5 excluded. This is NOT a pytest/full-suite/CI result. One first-run fixture-path error was corrected by backend cwd and rerun successfully. 12 current pure JavaScript helper assertions passed under Node; no Jest/build/browser/live-provider test was run.
No server imported/started, account connected, paid call, capture/trading activation, source edit, commit, push, merge, reset, deletion or original-owner signoff. In-memory DuckDB only. File-backed restart tests were excluded to honor report-only ownership.
Concurrent worktree drift was observed after a clean baseline (backend/server.py and new snapshot-write files); it was preserved. Citations and server AST extraction are fixed to the requested candidate, not the drifting worktree. Audited imported pure modules/tests were not among changed paths.

## Reproduced actionable findings

### SCOUT-BOUNDARY — primary PR #23

Future quote event times are coerced to fresh age zero by _age_s; strict 0DTE scout admits them. Other helper-only malformed fields also pass.

**Impact:** medium: read-only candidate/data-quality integrity, not order execution

**Call path:** GET /api/solstice/scout/{ticker} -> fetch_spot_and_chains_merged -> scout_candidates; _build_heatmap_impl -> scout_candidates -> payload.scout/shortlist -> WallInspector/ContextSections.

**Reproduction:** scout_boundary_probe in this JSON: strict now_s=2030-01-02T14:00Z, session_date=2030-01-02, otherwise valid same-day PUT. Bid/ask both 2030-01-03T14:00Z return n_eligible=1,rejected={}; control current quote also returns 1.

**Safe failing-test proposal (not installed):** In test_r5_d_red.py (proposal only, not written), parametrize future_bid, future_ask and unequal_future_timestamps. Freeze now_s and use same-day expiry; assert n_eligible==0 with explicit invalid/future-clock reason. Positive control with measured current quote remains eligible. Calculate raw event-time skew before clamping or reject future times outside an explicit documented clock tolerance; do not invent now for missing time.

**Limits:** No vendor payload, account, live service, trade route or order invoked; no claim actual observed future quotes. Safe repair must preserve original owner control and adapter sanitation. Tests not added in repository.

- https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/contract_scout.py#L34
- https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/contract_scout.py#L167
- https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/contract_scout.py#L175
- https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L173
- https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1998

### ABLATION-LOCAL — primary PR #27

L2 promotes missing wall-local delta support from scope ratio; L3 calls zero-volume-change row positive local activity.

**Impact:** medium for research validity; no current production caller found

**Call path:** run_ladder(snapshot) engineering/offline research helper. Pinned git grep across backend/services, backend/routes, backend/server.py finds only its definition (no product caller). Existing slice2 and P10 tests call it; frozen protocol names it.

**Reproduction:** ablation_boundary_probe in this JSON: one near-spot wall, scope ratio 0.9, wall_delta_share={}, matching strike delta_volume=0. Returns L2 signal wall_local=false and L3 signal with abstentions=0.

**Safe failing-test proposal (not installed):** Extend test_r4_p10_red.py (proposal only) with missing_selected_wall_share + high_scope_ratio expecting L2 abstention/DELTA_UNKNOWN, and separately valid local share + zero/negative/nonfinite delta_volume expecting L3 abstention/NO_WINDOW_ACTIVITY. Positive finite local delta-volume control must still promote. Keep frozen thresholds, cost assumptions and outcome labels unchanged; do not retune research parameters.

**Limits:** A research smoke helper, not a mounted trading signal or evidence of loss/profit; existing tests cover low explicit local share and wrong strike but omit absent local share and zero delta. No collected outcomes, historical user records or capture touched.

- https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_ablation.py#L70
- https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_ablation.py#L92
- https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r4_p10_red.py#L43

## Per-PR records

### PR #1 — sync: merge verified floww main into floww-2

**Classification:** unverified

History-preserving sync is an ancestor of the candidate and both historical heads are available locally. Current Lodestar agent layer, server heatmap path and AppShell survive, but the 394-file historical import is not feature-by-feature acceptance. Python 3.11 language ceiling was explicitly superseded by current Python 3.12 ship pins; historical red silent-except and omitted full-suite run are not current defects without reproduction.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/1 · [head](https://github.com/odaialdajani/floww-2/commit/1b7ddf6a5cec8e9d1794201c2b822867d854f6e3) · [merge](https://github.com/odaialdajani/floww-2/commit/8748cf4002c6cb37459adf0b69bc1acac0a5152a); merge ancestor of candidate: True. Changed files 394 in 4 pages, declared 394. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** All four changed-file pages (394 entries), and discussion/reviews/review-comments (empty) fetched and changed_files matched live PR metadata. REST and GraphQL commit traversal stop at 250 despite declared 417; local base..head has 417 commits and is recorded as ancestry evidence, not individual feature review. Representative paths/ship pin inspected, NOT all 394 files or historical commits. No runtime/full-suite proof.

**Current definitions / callers / tests:**
- `backend/server.py:1221` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1221
- `frontend/src/shell/AppShell.jsx:77` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/shell/AppShell.jsx#L77
- `Dockerfile.backend:1` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/Dockerfile.backend#L1
- `backend/services/agent/loop.py:8` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/agent/loop.py#L8

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #2 — chore(floww-2): declare floww-2 canonical

**Classification:** current intent retained

All five historical pointer changes still name odaialdajani/floww-2 or floww-2 checkout. Bootstrap clone commands consume these constants; launcher remains a macOS-specific script. No service or deployment script was executed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/2 · [head](https://github.com/odaialdajani/floww-2/commit/040c06496dc6a804df98ef78016f8359e3517729) · [merge](https://github.com/odaialdajani/floww-2/commit/aae421cf432083196e13594318ab6fa64d39b1ef); merge ancestor of candidate: True. Changed files 5 in 1 pages, declared 5. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete small historical patch and current pointer/caller reads; host aliases, external cron and launchd state excluded.

**Current definitions / callers / tests:**
- `scripts/launch_decoder.sh:17` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/scripts/launch_decoder.sh#L17
- `deploy/free/oracle-setup.sh:15` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/deploy/free/oracle-setup.sh#L15
- `deploy/free/server-setup.sh:8` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/deploy/free/server-setup.sh#L8
- `scripts/gsd-loop-build-pass.sh:56` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/scripts/gsd-loop-build-pass.sh#L56
- `scripts/gsd-loop-review-pass.sh:54` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/scripts/gsd-loop-review-pass.sh#L54

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #3 — fix(frontend): Skylit panel bugs — AlphaPod no-cors, nav a11y, lint cleanup

**Classification:** superseded/declined

The advertised AlphaPod iframe/no-cors integration was replaced by native application surfaces: no AlphaPodCapturePage remains in current tracked frontend; App routes to native Skylit/Tidehunter, Sidebar retains aria-current on the active native item. Do not resurrect localhost:3456 or missing old page paths as a defect. PR API diff is anomalously broad (1,152 files) because of ancestry; only advertised ca255571 patch and current shell/navigation were semantically reviewed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/3 · [head](https://github.com/odaialdajani/floww-2/commit/ca255571c3e2dae059567fba3f74d180750b1e38) · [merge](https://github.com/odaialdajani/floww-2/commit/2ec7fa740c8ae48ca8fe410548325872dca48084); merge ancestor of candidate: True. Changed files 1152 in 12 pages, declared 1152. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** All changed-file pages fetched (1,152 entries) and matched live PR count. Advertised ca255571 head patch and current native shell/navigation inspected. REST and GraphQL both terminate at 250 despite declared 358 PR commits; local base..head returns 579 ancestry commits (distinct set, not substituted). PR-specific exhaustive commit reconciliation and broad 1,152-file review remain unverified; no mounted native-UI run.

**Current definitions / callers / tests:**
- `frontend/src/App.js:877` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/App.js#L877
- `frontend/src/shell/Sidebar.jsx:199` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/shell/Sidebar.jsx#L199
- `frontend/src/shell/navConfig.js:1` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/shell/navConfig.js#L1

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #4 — propagate fetched_at through options data pipeline (source → heatmap)

**Classification:** current intent retained

Fetch receipt is propagated from Public adapter into heatmap without synthesizing source age. Later work correctly removed the PR fallback-to-now in server.py: fetched_at remains raw.get(fetched_at), while asof is compute time. Snapshot clock adapter keeps receivedAt and sourceMin/Max separate. eval_harness remains an opt-in point-in-time scorer, not a claim all legacy evaluation paths are filtered.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/4 · [head](https://github.com/odaialdajani/floww-2/commit/008e31b95f7076e1fe1da143055918ecc854b658) · [merge](https://github.com/odaialdajani/floww-2/commit/2ec7fa740c8ae48ca8fe410548325872dca48084); merge ancestor of candidate: True. Changed files 3 in 1 pages, declared 3. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete three-file historical patch; current producer/build/snapshot/scorer source traced. No live provider call or full downstream endpoint census.

**Current definitions / callers / tests:**
- `backend/services/public_api_adapter.py:311` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/public_api_adapter.py#L311
- `backend/server.py:1675` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1675
- `backend/services/heatmap_snapshot.py:144` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_snapshot.py#L144
- `backend/services/eval_harness.py:105` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/eval_harness.py#L105

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #5 — fix(frontend): X4 stale-data indicator — lift STALE_MS + isStale exports, unblock tests

**Classification:** superseded/declined

The old inline manual-refresh state and accidental plus-prefixed historical lines are not present in the current rewrite. STALE_MS=60000 and isStale(lastRefreshAt, now) are exported and used by current scan-age handling; elapsed scan freshness uses producer metadata and a 1s clock rerender. This supersedes the old component-local shadowed helper rather than requiring restoration.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/5 · [head](https://github.com/odaialdajani/floww-2/commit/7d3d75c58c9baa254922770177fdf27c88e23aee) · [merge](https://github.com/odaialdajani/floww-2/commit/1eefd864221ac64cba8f41009556e54ac82d2ed1); merge ancestor of candidate: True. Changed files 2 in 1 pages, declared 2. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete two-file historical patch; current exported helper, producer-aged scan caller and clock teardown inspected. Historical helper-specific assertions no longer appear under the same test file; current broader scan tests are not asserted to cover that pure threshold. No mounted fake-timer/browser run.

**Current definitions / callers / tests:**
- `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx:56` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/flowseeker/FlowseekerProBlademap.jsx#L56
- `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx:859` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/flowseeker/FlowseekerProBlademap.jsx#L859

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #6 — docs: record floww-to-floww-2 migration and floww freeze

**Classification:** current intent retained

FLOWW_MIGRATION.md retains branch/tag/PR map, source-repository freeze and canonical destination. This is a retained historical record, not proof local hooks, archives under old temporary paths, shell aliases or every remote branch still exist.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/6 · [head](https://github.com/odaialdajani/floww-2/commit/f9965cb96f626e37e8cc1e546bdc6786a55f457d) · [merge](https://github.com/odaialdajani/floww-2/commit/cdcf4964f195b6beb7657b535833231fe9c1907d); merge ancestor of candidate: True. Changed files 1 in 1 pages, declared 1. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete historical and current document read; no external archive/hook/credential or legacy checkout read.

**Current definitions / callers / tests:**
- `FLOWW_MIGRATION.md:1` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/FLOWW_MIGRATION.md#L1
- `FLOWW_MIGRATION.md:27` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/FLOWW_MIGRATION.md#L27

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #7 — docs: park ex-floww issue 8 spec until floww-2 Issues enabled

**Classification:** owner-hold

Parked X chatter specification remains explicitly preserved in FLOWW_MIGRATION.md. It requests paid X credits and owner enablement of Issues; a parked doc-only PR is not a promise of a mounted X card. No implementation gap is inferred and no paid call was made.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/7 · [head](https://github.com/odaialdajani/floww-2/commit/415ce5c88cc0f0d4d1bc3c22e8eafdc243478579) · [merge](https://github.com/odaialdajani/floww-2/commit/7685a44b5e28c9d488642ff945393cc83a248899); merge ancestor of candidate: True. Changed files 1 in 1 pages, declared 1. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete added specification inspected against candidate document; no X account, credits, remote settings write or external owner action.

**Current definitions / callers / tests:**
- `FLOWW_MIGRATION.md:45` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/FLOWW_MIGRATION.md#L45

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** Original owner decides Issues enablement and X credit spend; no authorization inferred from merged documentation.

### PR #8 — fix(frontend): remove stray < breaking AppShell.jsx compile

**Classification:** current intent retained

The malformed <import line is absent. Current AppShell has a valid AgentProvider named/default import and mounts AgentProvider around the application. Later shell expansion does not reintroduce the one-character syntax defect.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/8 · [head](https://github.com/odaialdajani/floww-2/commit/c0fee43baf1bfd8189dfdc8a3d9aee7aad1c7e69) · [merge](https://github.com/odaialdajani/floww-2/commit/c0fee43baf1bfd8189dfdc8a3d9aee7aad1c7e69); merge ancestor of candidate: True. Changed files 1 in 1 pages, declared 1. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete one-character historical patch; current import/mount/caller read. No CRA build or live HTTP claim.

**Current definitions / callers / tests:**
- `frontend/src/shell/AppShell.jsx:5` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/shell/AppShell.jsx#L5
- `frontend/src/shell/AppShell.jsx:79` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/shell/AppShell.jsx#L79
- `frontend/src/App.js:62` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/App.js#L62

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #9 — fix(tickers): restore endless ticker universe

**Classification:** superseded/declined

Finnhub directory restoration was superseded by Public EQUITY catalog. GET /tickers/all now calls market_catalog.get_catalog and pages the provider-backed instruments, retaining stale/incomplete flags instead of claiming fixed 31k coverage. Finnhub-specific deleted paths or historic count are not repair work.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/9 · [head](https://github.com/odaialdajani/floww-2/commit/3179874c9dac5371c57799aaecf994716bab9776) · [merge](https://github.com/odaialdajani/floww-2/commit/283394f8e9007fcd6b4d92533af929f664efcba5); merge ancestor of candidate: True. Changed files 5 in 1 pages, declared 5. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Substantive original route/client/test patch read; current route/catalog/provider caller and replacement tests inspected. No account entitlement/live catalog count verified.

**Current definitions / callers / tests:**
- `backend/routes/market_data.py:95` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/market_data.py#L95
- `backend/services/market_catalog.py:75` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/market_catalog.py#L75
- `backend/services/market_catalog.py:67` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/market_catalog.py#L67
- `backend/tests/routes/test_tickers_all.py:44` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/routes/test_tickers_all.py#L44

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #10 — fix(scroller): endless ticker universe, kill 1/10 counter

**Classification:** current intent retained

App passes the full tickers object to both SkylitDashboard mounts; control arrows use buildTickerUniverse and stepIndex, with no x/N position counter. MultiTickerHeatmap still limits featured overview requests rather than turning the directory into thousands of concurrent chain fetches. Current picker redesign supersedes button-bar presentation only.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/10 · [head](https://github.com/odaialdajani/floww-2/commit/56502f5f026d873ec3729df11913ea8dc99c4b94) · [merge](https://github.com/odaialdajani/floww-2/commit/61d17917276b92913ff64339f9824b8a19d9b36a); merge ancestor of candidate: True. Changed files 5 in 1 pages, declared 5. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete five-file historical patch excluding no source; current parent/child universe plumbing and stepping inspected. Component tests read, not run; no browser reachability assertion.

**Current definitions / callers / tests:**
- `frontend/src/App.js:121` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/App.js#L121
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:875` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L875
- `frontend/src/components/heatseeker/SkylitControlBar.jsx:81` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitControlBar.jsx#L81
- `frontend/src/components/MultiTickerHeatmap.jsx:69` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/MultiTickerHeatmap.jsx#L69

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #11 — fix(frontend): 404 no-options stops auto-retry with honest message

**Classification:** current intent retained

ErrorState normalizes numeric/string status into codeStr; 404 suppresses automatic RetryButton while retaining manual retry and honest no-options text. 429/500 preserve auto-retry. Current consumer error-state call path and timer tests remain.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/11 · [head](https://github.com/odaialdajani/floww-2/commit/5db4971a297164023547911991c9984ed5193ef2) · [merge](https://github.com/odaialdajani/floww-2/commit/5db4971a297164023547911991c9984ed5193ef2); merge ancestor of candidate: True. Changed files 2 in 1 pages, declared 2. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete historical patch; current component branching and existing timer tests inspected, not executed. No claim a live 404 occurred.

**Current definitions / callers / tests:**
- `frontend/src/components/RetryButton.js:214` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/RetryButton.js#L214
- `frontend/src/components/RetryButton.js:239` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/RetryButton.js#L239
- `frontend/src/components/RetryButton.test.jsx:16` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/RetryButton.test.jsx#L16
- `frontend/src/components/CharmChart.jsx:144` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/CharmChart.jsx#L144
- `frontend/src/components/VannaChart.jsx:153` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/VannaChart.jsx#L153

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #12 — feat(frontend): paged A-Z ticker scroller with active-follow

**Classification:** superseded/declined

The 500-button active-follow A–Z strip was intentionally replaced by a compact shared TickerPicker. Current bar delegates full-list search/browsing to a 30-result paged combobox with favorites; global picker additionally queries filtered provider pages. Full-universe stepping remains in ControlBar. Missing old page-next IDs are obsolete-test contracts, not proof browsing is absent.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/12 · [head](https://github.com/odaialdajani/floww-2/commit/2f7013f13cb862df0a0729e0b5eb1597dfcb2d7a) · [merge](https://github.com/odaialdajani/floww-2/commit/1a368183903737a8a1caba6f7f8a8064bd59330c); merge ancestor of candidate: True. Changed files 5 in 1 pages, declared 5. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete substantive ticker patch and current replacement definitions/callers inspected; yarn.lock dependency churn not semantically audited. No mounted end-to-end picker test.

**Current definitions / callers / tests:**
- `frontend/src/components/heatseeker/SkylitTickerBar.jsx:14` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitTickerBar.jsx#L14
- `frontend/src/components/heatseeker/TickerPicker.jsx:12` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/TickerPicker.jsx#L12
- `frontend/src/components/heatseeker/TickerPicker.jsx:224` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/TickerPicker.jsx#L224
- `frontend/src/components/heatseeker/SkylitControlBar.jsx:81` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitControlBar.jsx#L81

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #13 — Solstice heatmap upgrade (Rev-3 T00–T29, read-only)

**Classification:** owner-hold

The core read-only desk remains mounted: vendor-gamma/actual-365 clock, separate metric grids, walls, inspector/scenarios, recorder and evidence paths exist in current server/UI. Subsequent R4–R14 work replaces many original implementations; e.g. SPX AM deadline is now preceding-session rather than the original settlement-day 09:30 rule. Offline foundation/canary fixtures exercised selected formula, clock and unknown-data invariants. This is NOT whole T00–T29 acceptance: vendor entitlement, durable capture, study participants and multi-session after-cost validation remain external gates.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/13 · [head](https://github.com/odaialdajani/floww-2/commit/158629439342bc7cc00fa011260fdf66d6ffb84f) · [merge](https://github.com/odaialdajani/floww-2/commit/eb478417eba4b45b6bb1be49c79afb4c658c01df); merge ancestor of candidate: True. Changed files 81 in 1 pages, declared 81. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** All 81 file rows and 8 commits fetched; selected core historical vendor/clock/broker serializer patches inspected. Current core definitions/callers and 42 selected foundation/canary/slice2 test functions directly exercised across the broader lineage. Not exhaustive 81-file Rust/AI/broker feature acceptance; Rust/Jest/live/browser/commissioning excluded.

**Current definitions / callers / tests:**
- `backend/server.py:1221` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1221
- `backend/services/gex_core.py:1045` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/gex_core.py#L1045
- `backend/services/solstice_time.py:88` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_time.py#L88
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:226` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L226
- `docs/solstice/COMMISSIONING_PACKAGE.md:14` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/COMMISSIONING_PACKAGE.md#L14

**Executed existing test functions touching PR file scope:** {'passed': 42}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_solstice_canaries.py`
- `backend/tests/solstice/test_solstice_foundation.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** SPX entitlement, production capture authorization, original-owner UI/study acceptance and independent costed multi-session validation remain unsatisfied by this audit.

### PR #14 — Solstice sweep-5: grid depth, capture scheduler, sources, reconciliation

**Classification:** current intent retained

Capture remains explicit opt-in with six-symbol cap and 60s floor; its loop calls fresh build implementation, not cached serve. Current hours policy is delegated to calendar-aware capture policy (superseding broad 09:00–16:30 historical guard). Strike concentration rail, expiry-day context and 0DTE shares remain; later labels correctly disclose sum of absolute signed cells is not raw gross.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/14 · [head](https://github.com/odaialdajani/floww-2/commit/87800f47c843bcddfedecf527c893d1f6ca83a33) · [merge](https://github.com/odaialdajani/floww-2/commit/54e4b5663c89afe271fdc151d8e5f2533b8b780b); merge ancestor of candidate: True. Changed files 8 in 1 pages, declared 8. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical scheduler/grid patches and current config/loop/grid labels inspected. No scheduler activation, environment discovery, current capture readiness or browser test. Sources-register completeness is documentation-only, not vendor proof.

**Current definitions / callers / tests:**
- `backend/server.py:4177` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L4177
- `backend/server.py:4190` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L4190
- `frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx:425` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx#L425
- `frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx:637` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx#L637

**Executed existing test functions touching PR file scope:** {'passed': 13}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_solstice_canaries.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #15 — Solstice sweep-6: envelope zone bug, volume windows, compare UI, vanna check

**Classification:** current intent retained

normalize_event now selects the first successful parsed alternate timestamp rather than truthy parse tuple; mixed naive/aware delay uses explicit assumed-UTC flags. Recorded comparison includes volume rebase quarantine; ReplayStrip owns comparison controls. The vanna-vs-vega derivative canary remains and passed in direct isolated execution. Later governed window comparability supersedes the original coarse comparison for admissibility.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/15 · [head](https://github.com/odaialdajani/floww-2/commit/cb1cba76dda15d817cab26254c2c66158ae013c5) · [merge](https://github.com/odaialdajani/floww-2/commit/ae2548548857a24d9245ed4c9f51d1e3337843e7); merge ancestor of candidate: True. Changed files 8 in 1 pages, declared 8. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Full historical envelope/comparison changes and current definitions read; derivative canary and recorded-history slice executed in memory. EventEnvelope original class suite not run via pytest; no time-zone/provider commissioning.

**Current definitions / callers / tests:**
- `backend/services/event_envelope.py:66` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/event_envelope.py#L66
- `backend/services/event_envelope.py:106` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/event_envelope.py#L106
- `backend/services/heatmap_history.py:953` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L953
- `frontend/src/components/heatseeker/ReplayStrip.jsx:117` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/ReplayStrip.jsx#L117
- `backend/tests/solstice/test_solstice_canaries.py:183` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_solstice_canaries.py#L183

**Executed existing test functions touching PR file scope:** {'passed': 32}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_solstice_canaries.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #16 — Solstice sweep-7: display-scale lock + exact-spot rail chip

**Classification:** current intent retained

Grid still exposes a zero-anchored locked/fixed/relative scale and exact-spot rail title. Dashboard controls scale lock and clears it on query-scope changes; later compare mode uses distinct locks. Nothing in current source requires restoring the earlier markup.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/16 · [head](https://github.com/odaialdajani/floww-2/commit/f75e7170faaff0c1072d937d5b417bd5e65da042) · [merge](https://github.com/odaialdajani/floww-2/commit/c351cc759c601c61f43a1671d62f919f79d3628f); merge ancestor of candidate: True. Changed files 4 in 1 pages, declared 4. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical frontend patch and current controls/clear branches/grid consumer inspected. SolsticeSlice2 assertions read; no mounted/browser lock/spot precision acceptance.

**Current definitions / callers / tests:**
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:295` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L295
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:454` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L454
- `frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx:321` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx#L321
- `frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx:150` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx#L150

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #17 — Solstice sweep-8: OI findings, comprehension harness, ablation ladder, SPX draft

**Classification:** owner-hold

OI_EFFECTIVE_UNKNOWN and GREEK_TIME_UNKNOWN vocabulary, frozen comprehension fixtures/scoring and abl.v1 ladder survive. Dated measured provider receipts remain explicitly historical. Current comprehension scoring has later anti-rushed/reversed-answer checks; scripted answer-key success is not human comprehension or strategy validation. SPX follow-up draft explicitly remains an unsent owner/vendor dependency. Research-ladder gaps are separately reproduced in #27.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/17 · [head](https://github.com/odaialdajani/floww-2/commit/b05559a2c17ef35a07baecdbca703a8ea24fa48f) · [merge](https://github.com/odaialdajani/floww-2/commit/05ca4dc4b251b63e45704b58e241a636b33dfe59); merge ancestor of candidate: True. Changed files 8 in 1 pages, declared 8. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical findings/ladder/harness patches and current definitions/hold docs inspected. Current scorer negative controls and selected ladder fixture passed; no participant response, fresh OI timestamp probe or vendor message.

**Current definitions / callers / tests:**
- `backend/services/capability_manifest.py:18` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/capability_manifest.py#L18
- `scripts/solstice_comprehension.py:90` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/scripts/solstice_comprehension.py#L90
- `backend/services/solstice_ablation.py:33` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_ablation.py#L33
- `docs/solstice/SPX_FOLLOWUP.md:15` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/SPX_FOLLOWUP.md#L15
- `docs/solstice/FROZEN_PROTOCOL.md:39` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/FROZEN_PROTOCOL.md#L39

**Executed existing test functions touching PR file scope:** {'passed': 19}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** Vendor/account SPX entitlement; owner-approved capture; consenting participant study; independent costed validation.

**Related finding(s):** ABLATION-LOCAL

### PR #18 — Solstice sweep-9: payload interactions, file-backed DuckDB, reconciliation + frozen protocol

**Classification:** current intent retained

Server attaches scoped interactions and scenarios to one heatmap payload; current inspector reads those same fields. Shared DuckDB can use DUCKDB_PATH, with unusable file-path fallback to memory. Durable status later moved to actual connection backing (#43); merely having file-support code is not proof current research history persists. Frozen protocol remains collection-phase, no edge claim.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/18 · [head](https://github.com/odaialdajani/floww-2/commit/ccfca76b63524daa053cb4ade969a9fad17f7561) · [merge](https://github.com/odaialdajani/floww-2/commit/5f325e10f40b7c23a5b75627eb4ad4933641d02c); merge ancestor of candidate: True. Changed files 10 in 1 pages, declared 10. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical attachment/persistence patch, current producer/consumer and frozen protocol inspected. In-memory recorder tests passed; file-backed restart and service lifecycle excluded to honor only-two-files/read-only scope.

**Current definitions / callers / tests:**
- `backend/server.py:1961` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1961
- `backend/services/duckdb_engine.py:549` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/duckdb_engine.py#L549
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:87` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L87
- `docs/solstice/FROZEN_PROTOCOL.md:39` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/FROZEN_PROTOCOL.md#L39

**Executed existing test functions touching PR file scope:** {'passed': 19}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #19 — R4 P01+P02: audit reconciliation, immutable snapshots, typed quality, strict evidence

**Classification:** current intent retained

Snapshot deep-copies payload, hashes content+observation, and normalizes quality unknown-first; evidence binds typed facts/scope to snapshot and rejects unsupported citations/numerics/tools. Later #31 fixes canonical normalization/observation identity and #35 strengthens prose binding. Current P02 tests all passed under direct isolated execution. Reconciliation text is historical finding bookkeeping, not proof remaining original-owner obligations closed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/19 · [head](https://github.com/odaialdajani/floww-2/commit/2f4e2dedc31b9461594980f437497dfa203fa2df) · [merge](https://github.com/odaialdajani/floww-2/commit/f51d3f88f4053ee82374a7fe9f2c7bd81c10125b); merge ancestor of candidate: True. Changed files 10 in 1 pages, declared 10. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** All 10 file rows/3 commits fetched; P02 substantive commit plus current snapshot/evidence definitions/callers/tests inspected. No actual LLM, broad model security certification or endpoint process imported. Eight P02 tests directly passed.

**Current definitions / callers / tests:**
- `backend/services/heatmap_snapshot.py:115` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_snapshot.py#L115
- `backend/services/heatmap_snapshot.py:56` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_snapshot.py#L56
- `backend/services/solstice_evidence.py:267` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_evidence.py#L267
- `backend/routes/solstice.py:36` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L36
- `backend/tests/solstice/test_r4_p02_red.py:26` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r4_p02_red.py#L26

**Executed existing test functions touching PR file scope:** {'passed': 27}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #20 — fix(r4-p03): raw walls, dated OI, window activity, grid unavailable, regime/research

**Classification:** current intent retained

P03 side-specific wall lookup, zero-mass/gap breaks, dated OI comparisons, window rebase rejection and multiplier-aware regime remain. Current window code additionally uses validated domain measurements and explicit exclusions; original unknown baseline and delta-missing tests still pass. Raw/delta unavailability is explicit rather than silently falling back to another basis.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/20 · [head](https://github.com/odaialdajani/floww-2/commit/659c00b596a027468663505b9bcf52f60f00be0e) · [merge](https://github.com/odaialdajani/floww-2/commit/2e716b7092b5e864389cac6cf1e7e088417aa3ed); merge ancestor of candidate: True. Changed files 16 in 1 pages, declared 16. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Substantive head-delta excerpts and all nine current P03 tests read/executed; current server metrics caller traced. No live full-chain correctness, vendor methodology or profitability acceptance.

**Current definitions / callers / tests:**
- `backend/services/wall_structure.py:160` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/wall_structure.py#L160
- `backend/services/solstice_enrichment.py:47` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_enrichment.py#L47
- `backend/services/solstice_enrichment.py:105` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_enrichment.py#L105
- `backend/services/solstice_regime.py:140` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_regime.py#L140
- `backend/server.py:1554` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1554

**Executed existing test functions touching PR file scope:** {'passed': 36}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #21 — fix(r4-p04): interaction continuity, dwell clocks, scoped history

**Classification:** current intent retained

Wall history is joined by ticker/scope/wall, not restarted unobserved at each build. transition separates approach side from wall position, uses continuous inside/beyond clocks, and resets continuity after gaps. Current server prefers newest DB/full state and stores dwell fields; durable is checked separately. All five P04 regressions directly passed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/21 · [head](https://github.com/odaialdajani/floww-2/commit/edc2a3ea15dad5e9257ad005d542acb5ec8d43f3) · [merge](https://github.com/odaialdajani/floww-2/commit/edc2a3ea15dad5e9257ad005d542acb5ec8d43f3); merge ancestor of candidate: True. Changed files 19 in 1 pages, declared 19. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical state/history/server excerpts, current transition/state join/callers and P04 tests inspected. No live long-session or restart/durable-store exercise.

**Current definitions / callers / tests:**
- `backend/services/wall_interaction.py:115` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/wall_interaction.py#L115
- `backend/services/wall_interaction.py:47` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/wall_interaction.py#L47
- `backend/server.py:1878` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1878
- `backend/server.py:1884` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1884
- `backend/services/heatmap_history.py:621` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L621

**Executed existing test functions touching PR file scope:** {'passed': 41}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #22 — fix(r4-p05): identity selection, scoped scenarios, honest labels

**Classification:** current intent retained

resolveSelectedWall retains by wall ID using current snapshot values, clears cross-symbol, explains WALL_GONE and does not replace missing wall with nearest. Dashboard uses the resolver and Inspector explicitly labels scope-wide delta ratio and signed-cell expiry mass honestly. Direct Node probes verified identity retention, cross-symbol, gone, scenario filtering and unclassified selection.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/22 · [head](https://github.com/odaialdajani/floww-2/commit/4ba436e27ab5d4097afa59f83952f2c456bf4db4) · [merge](https://github.com/odaialdajani/floww-2/commit/4ba436e27ab5d4097afa59f83952f2c456bf4db4); merge ancestor of candidate: True. Changed files 24 in 1 pages, declared 24. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical selection/UI excerpts and current helper/callers/tests read. Five selection-related in-memory Node assertions passed; no Jest or actual mounted click flow.

**Current definitions / callers / tests:**
- `frontend/src/lib/solsticeSelection.js:14` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/lib/solsticeSelection.js#L14
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:73` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L73
- `frontend/src/components/heatseeker/WallInspector.jsx:127` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/WallInspector.jsx#L127
- `frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx:637` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx#L637

**Executed existing test functions touching PR file scope:** {'passed': 41}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #23 — fix(r4-p06): 0DTE eligibility, weekend and quality gates

**Classification:** confirmed repair needed

Most P06 protections survive and all five existing tests passed. Reproduced current gap SCOUT-BOUNDARY: _age_s clamps a quote timestamp one day in the future to age zero, so strict session_date + now_s accepts the candidate with n_eligible=1. Bid/ask skew derived from clamped ages is also lost for future readings. Current route and server both call the helper; source adapter preserves event timestamps, so this must not be called fresh. See finding for safe failing-test proposal; no broker action occurred.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/23 · [head](https://github.com/odaialdajani/floww-2/commit/e9709d8ac5809775a871a9b362f458ee41cb5e82) · [merge](https://github.com/odaialdajani/floww-2/commit/e9709d8ac5809775a871a9b362f458ee41cb5e82); merge ancestor of candidate: True. Changed files 27 in 1 pages, declared 27. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical P06 patch, full current scout/session definitions and production call paths inspected; existing tests passed plus an isolated synthetic boundary reproduction. No claim vendor actually emitted a future timestamp; boundary defect is reproducible.

**Current definitions / callers / tests:**
- `backend/services/contract_scout.py:24` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/contract_scout.py#L24
- `backend/services/contract_scout.py:117` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/contract_scout.py#L117
- `backend/routes/solstice.py:173` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L173
- `backend/server.py:1998` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1998

**Executed existing test functions touching PR file scope:** {'passed': 46}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_r4_p06_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

**Related finding(s):** SCOUT-BOUNDARY

### PR #24 — fix(r4-p07): atomic capture, gaps, capability writer

**Classification:** current intent retained

record_snapshot now uses connection-wide lock plus transaction and returns None on failed commit; missing-contract retry rewrites incomplete capture, full grids/quality/scenarios persist. Server production writer emits explicit coverage and capability record. Gap/heartbeat manifest receipts remain, while actual file backing is later checked by #43. All five P07 memory-store regressions directly passed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/24 · [head](https://github.com/odaialdajani/floww-2/commit/2f4f4d2710965ffbe1f3721c0fcb9f979668034c) · [merge](https://github.com/odaialdajani/floww-2/commit/2f4f4d2710965ffbe1f3721c0fcb9f979668034c); merge ancestor of candidate: True. Changed files 28 in 1 pages, declared 28. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical atomic/capability excerpts, current transaction/dedup/coverage and server writer inspected. In-memory retry/coverage/gap tests executed; no real WAL, crash or active store inspected.

**Current definitions / callers / tests:**
- `backend/services/heatmap_history.py:363` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L363
- `backend/services/heatmap_history.py:272` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L272
- `backend/services/heatmap_history.py:1044` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L1044
- `backend/server.py:2100` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L2100

**Executed existing test functions touching PR file scope:** {'passed': 51}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_r4_p06_red.py`
- `backend/tests/solstice/test_r4_p07_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #25 — fix(r4-p08): tool boundary, scope-aligned evidence routes

**Classification:** current intent retained

Validator rejects tool_requests/tool_calls/order/actions and incorrect setup promotion; fallback mode is explicitly model_evaluated=False. walls/patterns share scope parameters and query-key layout with snapshot/evidence paths. Current replay evidence rejects ticker/wall mismatch. Pure validator/outage/injection checks passed; route signature/source inspected without importing server.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/25 · [head](https://github.com/odaialdajani/floww-2/commit/fb8704f1b5bec74e06148c94bb2eba6f35145de1) · [merge](https://github.com/odaialdajani/floww-2/commit/fb8704f1b5bec74e06148c94bb2eba6f35145de1); merge ancestor of candidate: True. Changed files 29 in 1 pages, declared 29. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical tool/scope patch excerpts; current validator/corpus/route definitions inspected. Three P08 pure tests directly passed; route-source inspection test excluded because it imports routes/server; no LLM or HTTP route execution.

**Current definitions / callers / tests:**
- `backend/services/solstice_evidence.py:277` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_evidence.py#L277
- `backend/services/solstice_ai_eval.py:45` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_ai_eval.py#L45
- `backend/routes/solstice.py:109` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L109
- `backend/routes/solstice.py:142` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L142

**Executed existing test functions touching PR file scope:** {'passed': 54, 'excluded': 1}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_r4_p06_red.py`
- `backend/tests/solstice/test_r4_p07_red.py`
- `backend/tests/solstice/test_r4_p08_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #26 — fix(r4-p09): actual guided replay in mounted grid

**Classification:** current intent retained

Stored replay replaces the same dashboard grid/inspector via replaySnap rather than showing counts. Current hydration reads stored grids/quality/context and refuses missing identity or cross-symbol data; stepping stops at record boundaries. ReplayStrip generation+abort guards were added later. Direct Node probes verified recorded cells, missing context, ticker mismatch and stepping bounds.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/26 · [head](https://github.com/odaialdajani/floww-2/commit/63c6b7dfc0cca55d35beb99b4284c8d1b6821f8c) · [merge](https://github.com/odaialdajani/floww-2/commit/63c6b7dfc0cca55d35beb99b4284c8d1b6821f8c); merge ancestor of candidate: True. Changed files 32 in 1 pages, declared 32. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical replay implementation excerpts; full current adapter, request guards and dashboard merge/selection branches inspected; seven replay-related Node assertions passed. No real stored user records, browser or backend process used.

**Current definitions / callers / tests:**
- `frontend/src/components/heatseeker/ReplayStrip.jsx:148` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/ReplayStrip.jsx#L148
- `frontend/src/lib/solsticeReplay.js:62` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/lib/solsticeReplay.js#L62
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:360` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L360

**Executed existing test functions touching PR file scope:** {'passed': 54, 'excluded': 1}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_r4_p06_red.py`
- `backend/tests/solstice/test_r4_p07_red.py`
- `backend/tests/solstice/test_r4_p08_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #27 — fix(r4-p10): encounter-first labels, wall-local ablation

**Classification:** confirmed repair needed

Encounter-first/censored label semantics remain and five existing P10 tests passed. Reproduced ABLATION-LOCAL: run_ladder still substitutes the scope-wide delta ratio when the selected wall has no local share, emitting L2 with wall_local=False; L3 admits a matching strike whose delta_volume is zero because it checks only strike-set intersection. This contradicts wall-local/nonzero activity intent. The helper has no production caller in the scoped current call census and remains an engineering research smoke tool, so this is not a live trading bug.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/27 · [head](https://github.com/odaialdajani/floww-2/commit/64d1ffd601b832e06649c6199f536d36a1e89b92) · [merge](https://github.com/odaialdajani/floww-2/commit/64d1ffd601b832e06649c6199f536d36a1e89b92); merge ancestor of candidate: True. Changed files 35 in 1 pages, declared 35. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical ladder/label excerpts; full current ladder/label definitions and tests inspected, plus isolated synthetic reproduction. Production absence is limited to current backend services/routes/server caller search; empirical held-out validation not run.

**Current definitions / callers / tests:**
- `backend/services/solstice_ablation.py:70` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_ablation.py#L70
- `backend/services/solstice_ablation.py:92` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_ablation.py#L92
- `backend/services/solstice_labels.py:20` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_labels.py#L20
- `backend/tests/solstice/test_r4_p10_red.py:43` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r4_p10_red.py#L43

**Executed existing test functions touching PR file scope:** {'passed': 59, 'excluded': 1}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_r4_p06_red.py`
- `backend/tests/solstice/test_r4_p07_red.py`
- `backend/tests/solstice/test_r4_p08_red.py`
- `backend/tests/solstice/test_r4_p10_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

**Related finding(s):** ABLATION-LOCAL

### PR #28 — fix(r4-p11): capability classification, disarmed boundary

**Classification:** current intent retained

Registry retains 27 operations classified separately by test, entitlement and observation axes, rather than calling wrapper existence live capability. Shared PublicBudget singleton is retained. Solstice execution disarm must be scoped separately from public_brokerage: it is not a claim every broker route is unreachable. Registry and singleton regressions directly passed; execution-boundary test was only read because it reads source via path and this review does not invoke orders.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/28 · [head](https://github.com/odaialdajani/floww-2/commit/41b2c42a8e53ffe607dba7795a95a8e1f53679a8) · [merge](https://github.com/odaialdajani/floww-2/commit/41b2c42a8e53ffe607dba7795a95a8e1f53679a8); merge ancestor of candidate: True. Changed files 37 in 1 pages, declared 37. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete small registry head patch/current registry/budget definitions inspected; two pure tests executed. No broker method invoked, account entitlement tested, key read or global execution safety signed.

**Current definitions / callers / tests:**
- `backend/services/public_capability.py:49` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/public_capability.py#L49
- `backend/services/public_capability.py:73` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/public_capability.py#L73
- `backend/services/public_budget.py:275` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/public_budget.py#L275
- `backend/tests/solstice/test_r4_p11_red.py:26` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r4_p11_red.py#L26

**Executed existing test functions touching PR file scope:** {'passed': 61, 'excluded': 2}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_r4_p06_red.py`
- `backend/tests/solstice/test_r4_p07_red.py`
- `backend/tests/solstice/test_r4_p08_red.py`
- `backend/tests/solstice/test_r4_p10_red.py`
- `backend/tests/solstice/test_r4_p11_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #29 — fix(r4-p12): pattern evidence, experimental centroid

**Classification:** current intent retained

Pattern records remain candidates with evidence IDs and coverage guards, not automatic confirmed setups. exposure_centroid remains explicitly experimental and gross-weighted, not a calibrated target/VWAP. Three P12 tests passed. Current server attaches detect_patterns_v1; centroid has no production attachment in the inspected server/routes path, which is consistent with optional research scope rather than a missing mounted feature.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/29 · [head](https://github.com/odaialdajani/floww-2/commit/283f6cfe80bc155e73df94b0a771d57e0a28e9aa) · [merge](https://github.com/odaialdajani/floww-2/commit/283f6cfe80bc155e73df94b0a771d57e0a28e9aa); merge ancestor of candidate: True. Changed files 40 in 1 pages, declared 40. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical centroid/pattern excerpts and current definitions/caller/tests inspected; P12 pure tests passed. No empirical significance, full pattern lifecycle, participant comprehension or live centroid plot claimed.

**Current definitions / callers / tests:**
- `backend/services/solstice_patterns.py:41` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_patterns.py#L41
- `backend/services/solstice_centroid.py:31` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_centroid.py#L31
- `backend/server.py:1972` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1972
- `backend/services/solstice_research.py:22` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_research.py#L22

**Executed existing test functions touching PR file scope:** {'passed': 64, 'excluded': 2}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_r4_p06_red.py`
- `backend/tests/solstice/test_r4_p07_red.py`
- `backend/tests/solstice/test_r4_p08_red.py`
- `backend/tests/solstice/test_r4_p10_red.py`
- `backend/tests/solstice/test_r4_p11_red.py`
- `backend/tests/solstice/test_r4_p12_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #30 — fix(r4-p13): resweep — CI justifications, full scope/payload, live window

**Classification:** current intent retained

Recorder includes quality/scenarios/interactions and metric-grid metadata; current replay restores full cells and context. Original latest-ticker/UTC-day window lookup has been superseded by full request identity + governed recorded_window_activity with source-clock/NY-session comparability. Dashboard scope clearing and heatmapQuery tests preserve dte/scalp alignment. Current P13 recorder preservation test directly passed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/30 · [head](https://github.com/odaialdajani/floww-2/commit/f3ce1f09afa6dae29b4e194ed276e35664611133) · [merge](https://github.com/odaialdajani/floww-2/commit/0340de86789694e69d8cc28de8d85ffd42976013); merge ancestor of candidate: True. Changed files 42 in 1 pages, declared 42. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical recorder/window/scope excerpts and current server baseline caller/replay payload inspected. One P13 in-memory test passed; frontend parity assertions read, not executed; no source clock or capture activation proof.

**Current definitions / callers / tests:**
- `backend/services/heatmap_history.py:206` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L206
- `backend/server.py:1648` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1648
- `backend/server.py:1661` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1661
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:263` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L263
- `frontend/src/lib/heatmapQuery.test.js:3` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/lib/heatmapQuery.test.js#L3

**Executed existing test functions touching PR file scope:** {'passed': 65, 'excluded': 2}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p02_red.py`
- `backend/tests/solstice/test_r4_p03_red.py`
- `backend/tests/solstice/test_r4_p04_red.py`
- `backend/tests/solstice/test_r4_p06_red.py`
- `backend/tests/solstice/test_r4_p07_red.py`
- `backend/tests/solstice/test_r4_p08_red.py`
- `backend/tests/solstice/test_r4_p10_red.py`
- `backend/tests/solstice/test_r4_p11_red.py`
- `backend/tests/solstice/test_r4_p12_red.py`
- `backend/tests/solstice/test_r4_p13_red.py`
- `backend/tests/solstice/test_solstice_slice2.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #31 — fix(r5-a): mounted observation contract

**Classification:** current intent retained

Canonical camelCase quality normalization is idempotent for setup eligibility; source clocks stay null when unknown. Observation ID binds content/asof/ticker and recorder accepts issued snapshot ID so volume-only observations remain separate despite same exposure digest. Server emits snapshotId before wall-event writes and passes it to capture. All four current R5-A regressions passed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/31 · [head](https://github.com/odaialdajani/floww-2/commit/31cb0016e2c90c6aae8044b0413d11cc26815bd0) · [merge](https://github.com/odaialdajani/floww-2/commit/58f2e478ce16e0da14b93fe94959919df84fd991); merge ancestor of candidate: True. Changed files 6 in 1 pages, declared 6. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical R5-A delta excerpts, current canonical adapter/ID functions/server linking and tests inspected; four tests directly executed. No live event journal or every quality capability spelling certified.

**Current definitions / callers / tests:**
- `backend/services/heatmap_snapshot.py:92` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_snapshot.py#L92
- `backend/services/heatmap_history.py:92` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L92
- `backend/server.py:1826` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1826
- `backend/server.py:2145` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L2145

**Executed existing test functions touching PR file scope:** {'passed': 4}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_a_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #32 — fix(r5-b): complete recording, truthful transactions, replay isolation

**Classification:** current intent retained

Current recorder stores versioned cell maps/axes and normalizes DB contract identity; connection guards enclose transactions and commit failures return None. Replay hydrates stored context and refuses cross-symbol identity rather than mixing live data. Three R5-B in-memory tests passed and direct Node helper probes passed. File-backed restart fixture is present but excluded under only-two-report-files scope.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/32 · [head](https://github.com/odaialdajani/floww-2/commit/d9de2b4ce7c104f43da35845f52d4f9359ae2655) · [merge](https://github.com/odaialdajani/floww-2/commit/a660180d7a271330c81f91018c511d58e26ec9e1); merge ancestor of candidate: True. Changed files 8 in 1 pages, declared 8. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical R5-B storage/scope/replay excerpts; current transactions/hydration/request guards and tests inspected. Three existing memory-store tests executed; no actual restart, file DB, mounted async race or complete frontend suite.

**Current definitions / callers / tests:**
- `backend/services/heatmap_history.py:56` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L56
- `backend/services/heatmap_history.py:533` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L533
- `backend/services/heatmap_history.py:419` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L419
- `frontend/src/lib/solsticeReplay.js:62` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/lib/solsticeReplay.js#L62
- `frontend/src/components/heatseeker/ReplayStrip.jsx:99` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/ReplayStrip.jsx#L99

**Executed existing test functions touching PR file scope:** {'passed': 3, 'excluded': 1}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_b_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #33 — fix(r5-c): causal wall lifecycle

**Classification:** current intent retained

Current transition preserves adverse-side direction, clears inside dwell when leaving, handles acceptance/retest/invalidation and source/session gaps. scope_id_for binds DTE/mode/scalp/expiry dimensions; server newest-wins join no longer overwrites newer memory dwell with old DB event. The historical opt-in mock feed was subsequently removed: current startup_ingestion starts storage only and awaits verified producers. Six R5-C tests passed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/33 · [head](https://github.com/odaialdajani/floww-2/commit/c8a7131b5365eb90aa2e4b8d3299c73c97e40b57) · [merge](https://github.com/odaialdajani/floww-2/commit/fc58edbf7d0d7bfb42ac8a6b5aad4ca5d547754c); merge ancestor of candidate: True. Changed files 5 in 1 pages, declared 5. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical causal-state/scope/server excerpts and current transition/join inspected; six deterministic state-path tests executed. No live session rollover, actual service ingestion or persisted restart continuity proof.

**Current definitions / callers / tests:**
- `backend/services/wall_interaction.py:38` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/wall_interaction.py#L38
- `backend/services/wall_interaction.py:47` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/wall_interaction.py#L47
- `backend/services/wall_interaction.py:361` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/wall_interaction.py#L361
- `backend/server.py:1895` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1895
- `backend/server.py:4141` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L4141

**Executed existing test functions touching PR file scope:** {'passed': 6}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_c_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #34 — fix(r5-d): strict 0DTE production context

**Classification:** confirmed repair needed

Production scout callers do pass now_s and session_date; missing quote times, preopen and explicit ineligible quality are blocked. Existing strict-context tests pass. However SCOUT-BOUNDARY remains: future bid/ask times become age zero, and helper also admits NaN volume/T and infinite T through only <=0 checks. Public adapter sanitizes nonfinite volume and constructs T, reducing malformed-number reachability on that producer; future timestamps are preserved. Same repair cluster as #23, not a second independent defect count.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/34 · [head](https://github.com/odaialdajani/floww-2/commit/abb124c882e380fcf9c9f890fe5f0f38b9f93d71) · [merge](https://github.com/odaialdajani/floww-2/commit/6b94c3aaa113d93949725a822c53a3f7b3093120); merge ancestor of candidate: True. Changed files 5 in 1 pages, declared 5. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical strict-context delta and current scout/session/callers/producer sanitation inspected. Two pure R5-D tests passed; source-import caller test excluded and replaced by pinned source call-path inspection. Synthetic strict-context boundary probe reproduced; no bad live provider reading asserted.

**Current definitions / callers / tests:**
- `backend/routes/solstice.py:183` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L183
- `backend/server.py:1999` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1999
- `backend/services/contract_scout.py:167` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/contract_scout.py#L167
- `backend/services/contract_scout.py:175` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/contract_scout.py#L175
- `backend/services/public_api_adapter.py:739` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/public_api_adapter.py#L739

**Executed existing test functions touching PR file scope:** {'passed': 2, 'excluded': 1}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_d_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

**Related finding(s):** SCOUT-BOUNDARY

### PR #35 — fix(r5-e): evidence-bound explanation and study scoring

**Classification:** current intent retained

Current evidence packets include selected-wall interaction/scenario/quality facts; route refuses recorded ticker/wall mismatch. Validator checks numeric free prose and later template/suffix constraints, not only typed values array. Comprehension scorer rejects reversed wall answers, direction errors and immediate-action false confidence; participant CLI records latency separately. All three R5-E tests passed after correcting test cwd to backend (first root-cwd fixture read failure was audit harness setup, not product defect).

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/35 · [head](https://github.com/odaialdajani/floww-2/commit/7a177392b2764b69088e37c2511f0375caea32bb) · [merge](https://github.com/odaialdajani/floww-2/commit/72e067729d37d110d9c613cb665c71076955b049); merge ancestor of candidate: True. Changed files 4 in 1 pages, declared 4. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical packet/route/validator excerpts and current definitions/callers/negative-control tests inspected; three existing tests directly passed from correct cwd. No real LLM, participant response, timing validity or clinical-style study acceptance.

**Current definitions / callers / tests:**
- `backend/services/solstice_evidence.py:205` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_evidence.py#L205
- `backend/services/solstice_evidence.py:331` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_evidence.py#L331
- `backend/routes/solstice.py:67` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L67
- `scripts/solstice_comprehension.py:90` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/scripts/solstice_comprehension.py#L90

**Executed existing test functions touching PR file scope:** {'passed': 3}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_e_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #36 — fix(r5-f): encounter horizons, linked producers, readiness package

**Classification:** owner-hold

Encounter-anchored horizon/censoring, linked decision/outcome producers, explicit manifest cadence and actual recorder health remain in current code. Later close_episodes uses versioned episode/barrier policy and worker opt-in; current decision producer retains abstentions and candidate quote evidence. Four R5-F tests passed in memory. Readiness package remains DRAFT; participant runs, durable service activation, SPX entitlement and empirical validation cannot be self-signed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/36 · [head](https://github.com/odaialdajani/floww-2/commit/1f26e99601235928f82d4f1f3ce5e816a5466aa2) · [merge](https://github.com/odaialdajani/floww-2/commit/25cb1f72ba42335ddad88e04be0765356fc7d99b); merge ancestor of candidate: True. Changed files 8 in 1 pages, declared 8. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical producer/readiness excerpts and current label/decision/manifest/health definitions inspected; four deterministic in-memory tests passed. Original capture inventory and readiness receipts are historical, not renewed commissioning.

**Current definitions / callers / tests:**
- `backend/services/solstice_labels.py:20` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_labels.py#L20
- `backend/services/solstice_labels.py:140` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_labels.py#L140
- `backend/server.py:2015` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L2015
- `backend/routes/solstice.py:266` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L266
- `docs/solstice/COMMISSIONING_PACKAGE.md:1` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/COMMISSIONING_PACKAGE.md#L1

**Executed existing test functions touching PR file scope:** {'passed': 9}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r4_p10_red.py`
- `backend/tests/solstice/test_r5_f_red.py`

**Original-owner / external gates:** Original owner approves durable capture/service configuration and study participants; account owner resolves SPX entitlement; independent multi-session after-cost validation required.

### PR #37 — fix(r5-followup): replay-spot scope, restart parity, suite evidence

**Classification:** current intent retained

Current displaySpot is recorded spot (or null) during replay and exactly caller-provided live spot otherwise; the old replay fallback to live spot was further removed. Scope-wide ratio label remains honest. Added file-backed restart parity test exists but was deliberately not run because creating DB files would exceed ownership scope; memory replay tests and helper probes passed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/37 · [head](https://github.com/odaialdajani/floww-2/commit/713844ec5ec82b617132f0061a9e46880df7fe0e) · [merge](https://github.com/odaialdajani/floww-2/commit/49ec78749b32d75f87d3d4576288b857df309878); merge ancestor of candidate: True. Changed files 3 in 1 pages, declared 3. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Complete small spot-label head patch plus added restart fixture inspected; current producer/consumer spot flow read. No file-backed process restart or mounted Spot UI run. Historical full-frontend counts not reused as proof.

**Current definitions / callers / tests:**
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:367` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L367
- `frontend/src/components/heatseeker/WallInspector.jsx:127` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/WallInspector.jsx#L127
- `backend/tests/solstice/test_r5_b_red.py:83` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r5_b_red.py#L83

**Executed existing test functions touching PR file scope:** {'passed': 3, 'excluded': 1}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_b_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #38 — fix(r5-gaps2): replay endpoint tests, expand-close clearing, live-spot scope

**Classification:** current intent retained

Closing expand clears expData; reopening without new data reports loading scope rather than old expanded pixels. Current click/display selection uses the active displayed generation. Evidence route retains ticker/wall refusal tests and current source branches. This is engineering source retention, not a fresh mounted overlay or HTTP proof.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/38 · [head](https://github.com/odaialdajani/floww-2/commit/ce6c2e3d3289a337fcde192b72d2b4fbca90a42a) · [merge](https://github.com/odaialdajani/floww-2/commit/c65ccab7cb883f8832a36523d37af9f5ccbd947c); merge ancestor of candidate: True. Changed files 4 in 1 pages, declared 4. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical overlay/test patch and current clear/loading/caller plus route tests inspected. No Jest, server import, live HTTP or true browser stale-response execution; route acceptance remains static in this audit.

**Current definitions / callers / tests:**
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:450` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L450
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:594` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L594
- `frontend/src/components/heatseeker/SkylitDashboard.test.jsx:507` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.test.jsx#L507
- `backend/tests/solstice/test_solstice_routes.py:151` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_solstice_routes.py#L151

**Executed existing test functions touching PR file scope:** {}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.


**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #39 — fix(r5-holes): canonical keys, scout strictness, wall staleness, contract matrix

**Classification:** current intent retained

Unknown scenario_side and adjusted/nonstandard scout inputs are rejected; DB/JSON strike identity normalizes 500 and 500.0; explainer refuses mismatched wall ID. Five current holes tests passed, including end-to-end in-memory recorded-baseline joining and broken-storage behavior. Unknown CONTRACT type is a different helper boundary (currently treated as put), documented in SCOUT-BOUNDARY probe rather than falsely claiming this PR already handled it.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/39 · [head](https://github.com/odaialdajani/floww-2/commit/38a30331db74921eacda9c16d3ac13d53ee37cfe) · [merge](https://github.com/odaialdajani/floww-2/commit/30491b945a2352a78e65440d9d687d96299a9c4f); merge ancestor of candidate: True. Changed files 7 in 1 pages, declared 7. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical scout/identity/evidence excerpts and current full functions/callers/tests inspected; five tests directly passed. Contract-matrix documentation is a contract map, not account entitlement/production coverage evidence. Related boundary repair is tracked once under #23/#34.

**Current definitions / callers / tests:**
- `backend/services/contract_scout.py:71` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/contract_scout.py#L71
- `backend/services/solstice_enrichment.py:90` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_enrichment.py#L90
- `backend/services/solstice_evidence.py:292` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_evidence.py#L292
- `backend/tests/solstice/test_r5_holes_red.py:59` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r5_holes_red.py#L59

**Executed existing test functions touching PR file scope:** {'passed': 5}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_holes_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

**Related finding(s):** SCOUT-BOUNDARY

### PR #40 — fix(r5-holes2): per-wall OI dates, study coverage, sighting honesty

**Classification:** current intent retained

Vendor strike rows collect supplied OI dates; discover_walls unions member dates and Inspector shows dates or explicit unavailable. Persistent sightings are distinguished from first_seen and memory/durable flags. Canonical and snake-case comprehension quality both accepted by scorer. Three holes2 tests passed. No missing effective date was backfilled from request time.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/40 · [head](https://github.com/odaialdajani/floww-2/commit/a39a12fda91e869bfd40eaa4d58904426d0eea56) · [merge](https://github.com/odaialdajani/floww-2/commit/93fcd4b7705299575ad252de8f3e7880c5d6fafa); merge ancestor of candidate: True. Changed files 8 in 1 pages, declared 8. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical OI propagation/label excerpts; current source→row→wall→inspector path and scorer fixture inspected. Three pure tests executed; no fresh vendor OI-date availability claim, participant study or UI screenshot acceptance.

**Current definitions / callers / tests:**
- `backend/services/gex_core.py:1086` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/gex_core.py#L1086
- `backend/services/wall_structure.py:125` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/wall_structure.py#L125
- `frontend/src/components/heatseeker/WallInspector.jsx:130` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/WallInspector.jsx#L130
- `scripts/solstice_comprehension.py:63` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/scripts/solstice_comprehension.py#L63

**Executed existing test functions touching PR file scope:** {'passed': 3}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_holes2_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #41 — fix(r6-1): canonical display contract, stable grid, replay hydration

**Classification:** current intent retained

_display_surfaces still selects supplied-Greek rows/grid together with explicit local-BS/volume fallback provenance; later VEX/Charm surfaces have separate metadata. Recorder full-grid projection keeps axes/cells; current SelectedCellReadout resolves current pane/basis value, not stale click value. Four non-server R6-1 tests passed; three server-function tests also passed after extracting only pure _display_surfaces AST (no server import/startup).

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/41 · [head](https://github.com/odaialdajani/floww-2/commit/f3224033887553abbbae05888bafd91a48b6043a) · [merge](https://github.com/odaialdajani/floww-2/commit/f24d050dd45474a43f894a9762e441d41a149a40); merge ancestor of candidate: True. Changed files 12 in 1 pages, declared 12. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical canonical-surface/grid excerpts, current selected definition/callers/hydration/selection tests inspected. Seven R6-1 tests passed via memory-only direct/AST execution; this does not prove all React layout or actual API response behavior. No frontend bundle/browser/source runtime identity check.

**Current definitions / callers / tests:**
- `backend/server.py:1102` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1102
- `backend/server.py:1102` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1102
- `backend/services/heatmap_history.py:533` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L533
- `frontend/src/components/heatseeker/SkylitDashboard.jsx:49` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L49
- `frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx:277` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx#L277

**Executed existing test functions touching PR file scope:** {'passed': 10, 'excluded': 1}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_b_red.py`
- `backend/tests/solstice/test_r6_1_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #42 — fix(r6-2): wall-local comparison, true local window, location chips

**Classification:** current intent retained

Current wall_metric_breakdown aggregates only member contracts with missing/invalid delta counts, and aggregate_window_by_wall joins only matching member strikes with explicit coverage. Server attaches wall_metrics/wall_window; Inspector reads those by selected wall_id, while scope ratio is labeled separate. Status strip location chips use side-specific walls. All three R6-2 tests passed.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/42 · [head](https://github.com/odaialdajani/floww-2/commit/d75c41cbcb87579fe7847b50331a14ec4828398a) · [merge](https://github.com/odaialdajani/floww-2/commit/d4939e8a29fd636d4f595fecc27bdc5643413266); merge ancestor of candidate: True. Changed files 18 in 1 pages, declared 18. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical per-wall/window excerpts; current domain→server→inspector/status data flow inspected and three pure tests executed. No real account chain/window coverage or mounted selected-wall comparison verified.

**Current definitions / callers / tests:**
- `backend/domain/exposure_metrics.py:425` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/domain/exposure_metrics.py#L425
- `backend/services/solstice_enrichment.py:217` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_enrichment.py#L217
- `backend/server.py:1696` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1696
- `frontend/src/components/heatseeker/WallInspector.jsx:149` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/WallInspector.jsx#L149
- `frontend/src/components/heatseeker/SolsticeStatusStrip.jsx:10` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SolsticeStatusStrip.jsx#L10

**Executed existing test functions touching PR file scope:** {'passed': 13, 'excluded': 1}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_b_red.py`
- `backend/tests/solstice/test_r6_1_red.py`
- `backend/tests/solstice/test_r6_2_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

### PR #43 — fix(r6-3): calendar sessions, actual health, visible context

**Classification:** current intent retained

XNYS calendar supplies real holiday/half-day session hours and fails closed when unavailable; session_state uses it for entry while preserving management. recorder_status reads PRAGMA database_list rather than trusting a path string; writes use connection guards. ReplayStrip renders actual health and Inspector renders scout/pattern/regime context. Three R6-3 in-memory/calendar tests passed including Thanksgiving closure/13:00 half-day and false file-looking path. Actual file-backed durability fixture remains excluded.

**Remote evidence:** https://github.com/odaialdajani/floww-2/pull/43 · [head](https://github.com/odaialdajani/floww-2/commit/9147d1c59dbc5774e5e810accd870af9f45f9c44) · [merge](https://github.com/odaialdajani/floww-2/commit/d314572645d68f89c968f216c089e37cab992e39); merge ancestor of candidate: True. Changed files 23 in 1 pages, declared 23. Discussion/reviews/inline: 0/0/0 (terminal pagination).

**Depth / limits:** Historical actual-backing/calendar/UI excerpts, current functions and data consumers inspected; three existing tests directly passed. File-backed test, real service health, writer concurrency under load and mounted UI contexts not executed; dependency acceptance is the installed local environment, not shipped-container proof.

**Current definitions / callers / tests:**
- `backend/services/solstice_calendar.py:36` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_calendar.py#L36
- `backend/services/solstice_session.py:50` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_session.py#L50
- `backend/services/heatmap_history.py:236` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L236
- `backend/services/connection_guard.py:26` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/connection_guard.py#L26
- `frontend/src/components/heatseeker/ReplayStrip.jsx:297` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/ReplayStrip.jsx#L297
- `frontend/src/components/heatseeker/WallInspector.jsx:410` — https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/WallInspector.jsx#L410

**Executed existing test functions touching PR file scope:** {'passed': 16, 'excluded': 2}. Accumulated-stack scope may include tests introduced under earlier PRs; this is not a distinct per-PR test total.

- `backend/tests/solstice/test_r5_b_red.py`
- `backend/tests/solstice/test_r6_1_red.py`
- `backend/tests/solstice/test_r6_2_red.py`
- `backend/tests/solstice/test_r6_3_red.py`

**Original-owner / external gates:** No original-owner visual, live-provider, commissioning or trading acceptance is signed by this engineering audit.

