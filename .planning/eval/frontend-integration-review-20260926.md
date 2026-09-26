# Frontend integration review - 2026-09-26

Read-only reviewer; root owns merge and production changes. Compared common 7685a44b, local dba50893 and incoming 79b28ec2 using immutable git blobs. Scope: App, Skylit dashboard/grid/sidebar, shell and shared research context. No provider/model/broker calls, production edits, reset/revert, mobile work or commits.

## Conclusion

Use the incoming Solstice layout/control additions as the larger dashboard base, then explicitly integrate local exact-displayed-map selection/publication and ticker scoping. Neither complete side is safe to accept wholesale. App requires a combined fetch model. AppShell needs no functional conflict decision: both sides repaired the malformed AgentProvider import; the local extra change is a corrupted comment character.

At 19:30 UTC the root's active merge reports frontend conflicts in App.js, SkylitDashboard.jsx and SkylitMetricsSidebar.test.jsx. Auto-merged grid/sidebar code also needs semantic review below.

## Concrete hazards and combined result

### 1. Incoming App manual refresh disables subsequent polling updates

Incoming App captures `myGen = ++fetchGen.current` once when the polling effect mounts. Its interval keeps comparing that fixed generation. Manual fetch increments the same counter. Every later poll is therefore ignored until an effect dependency changes. Polling also shares one abort controller across its lifetime and lacks the local single-flight guard. This is established from the two immutable source blocks, not an executed App reproduction.

Keep local `useScopedReading` for data/errors/spot/advanced/ensemble: it clears the old scope synchronously and rejects old setter closures. Retain local single-flight polling and clear-on-spot-failure behavior. If incorporating incoming abort/latest-request protection, use per-request ownership with one consistent manual/poll arbitration; do not carry the incoming lifetime generation unchanged. Test manual refresh followed by a later successful interval, reverse-order manual/poll responses, ticker switch with old slow response, and failed new ticker.

### 2. Research context must follow the actual visible surface

Local dashboard publishes mapQuery, mapVersion, shown strikes/expiries and exact selected cell to the shared research provider; AgentProvider deep-copies that context at question submission. Incoming dashboard adds replay, expanded scope, delta/activity overlays and GEX/VEX compare panes but has no shared context publisher. Replacing the local dashboard outright would silently lose this contract.

Resolve one visible surface using: replay versus live; expanded versus inline; active compare pane versus single view; raw versus delta/activity; the surface's own axes; recorded spot in replay; exact snapshot version/query. Use that same result for rows, readout and published selection. Local shownMapStrikes currently reads the main grid axes; incoming overlays may carry separate axes, so merely retaining that helper unchanged can publish different rows than the rendered table. Keep local removal of vanished/off-window selected cells; retain the incoming wall identity separately so WALL_GONE can explain a missing wall rather than replacing it with a nearby one.

Research for a replay/overlay must be bound to its stored identity and supported backend surface. If the backend cannot resolve that exact saved surface, publish an explicit unsupported/unavailable state rather than letting a live base-map lookup stand in for it. Root/backend owner must confirm this cross-boundary support; this frontend review does not claim it exists.

### 3. Confirmed missing-overlay readout reports raw data

Incoming SelectedCellReadout uses overlay.grid when present, otherwise falls back to the raw main surface even when an activity/delta overlay is selected. The grid itself correctly renders unavailable. Reproduced by extracting the exact incoming component, compiling JSX in memory and rendering it with React server rendering: activity overlay absent, raw cell 123 produced `500 · 2026-10-16 · 123.0`. This is a confirmed disagreement, not a hypothetical merge conflict.

Use the shared active-surface resolver with no raw fallback for absent requested overlays. Test unavailable overlay + existing raw cell, genuine zero, missing selected cell, VEX/Charm and both compare panes.

### 4. Incoming selection source and expanded readout disagree

Incoming handleCellClick always chooses overlayData, while the inline selected readout always receives displayData. During expansion the displayed grid may be expData but readout resolves base data. The local visibleData distinction solves that for one surface; extend it to compare/replay/overlays. Incoming handleCellClick also reads followWall/followWallId but omits them from its dependency list: toggling follow without another data dependency changing leaves the old callback. Include all selection dependencies or resolve from current state without stale closure.

Incoming follow-wall state is not explicitly cleared on ticker/scope change despite its comment. The disappearance effect may clear it later if the new wall list proves absence, but missing data or coincident IDs can retain it. Reset on incompatible ticker/query scope; keep explicit retention only across compatible refreshes.

### 5. Missing historical fields must not inherit live values

Incoming displaySpot is `recordedSpot ?? liveSpot` in replay, and both metrics sidebars still receive the live regime prop. A recorded snapshot with unknown spot can therefore show the current spot; historical sidebar regime can disagree with its recorded snapshot. Use recorded spot or unknown in replay and derive the displayed regime from the recorded snapshot or explicit unknown. Keep the local sidebar's “Gamma reading unavailable” instead of default neutral.

Incoming strike clicks still call the parent callback in replay, although cell clicks are guarded and Trade is disabled. That callback opens trade selection in App. Ensure every path from historical/study surfaces remains research-only; test strike rail as well as cells and the Trade button. StudyMode currently has no production import/route outside its tests at incoming79b28ec2: retain the component, but do not claim a reachable study workflow solely from component tests.

### 6. Source-time language must survive the merge

Keep local Research/Stream connected labels and explicit quote/source observation limits. Incoming heatLive uses data.asof (snapshot build timestamp) plus spot to label liveness, not necessarily source observation time, and memoization alone does not age it without another render. Do not replace local truthful unknown-source wording with an unverified live claim. New Solstice quality/status controls can coexist, subject to their supplied source fields.

## Verification and relevant checks

An attempted five-suite local run overlapped the root's merge. AgentProvider, AgentPanelAnswer and useScopedReading passed: **3 suites / 21 tests**. Dashboard and sidebar suites could not parse active merge markers: **2 suites not executed**. These are merge-in-progress syntax failures, not evidence of application regressions. The command used CI=true, explicit runTestsByPath, --watch=false --runInBand --forceExit. No combined passing claim is made.

The isolated immutable incoming SelectedCellReadout render above completed and confirmed the raw-fallback defect without editing files or calling a server.

After resolution, run the union of local and incoming tests: SkylitDashboard, SkylitHeatmapGrid, SkylitMetricsSidebar, SolsticeSlice2, SolsticeStudyMode, solsticeSelection, solsticeReplay, heatmapQuery, AgentProvider, AgentPanelAnswer, useScopedReading and useWebSocketGex. Preserve tests from both parents rather than picking one conflicted file. Add targeted cases for manual refresh then poll; frozen research in replay and expanded compare; absent overlay raw-fallback refusal; unknown recorded spot/regime; follow toggle/scope changes; historical strike click guard. Final build and a desktop sequence remain root-owned.

## Limits

This is a bounded source integration review, not full release acceptance or a replay-data audit. Existing memory only identified the prior handoff and authorization boundaries; every code finding above was rechecked against current immutable refs. No prior test totals were treated as current evidence.

## Combined-source follow-up - 19:41 UTC

Root resolved the frontend conflicts and requested read-only refutation. No production/test files were changed by this reviewer. Current source has per-request polling generation, retained useScopedReading/single-flight behavior, shared active mapSurface/axes, separate selectedReading versus retained wall identity, replay-only recorded spot/unknown regime, guarded replay strike callback and complete follow dependencies/reset.

Independent executable probes, all without server calls or file writes:

- Extracted the actual current App fetchData and polling effect blocks into an isolated JavaScript function with deferred mocked axios responses and a captured interval. Manual response superseded an older poll; a subsequent interval still updated data; a newer poll superseded a slower manual response. All three assertions passed. This validates the reviewed blocks, not the complete App mount/effect dependency lifecycle.
- Executed actual current mapSurface/shownMapStrikes with main axis100/MAIN and activity axes210,200/OVERLAY. The helper returned exactly overlay rows and expiry; absent overlay returned an empty matrix despite populated raw cells. Assertions passed.
- Transpiled the actual current Dashboard in memory for React server rendering, supplying a frozen replay snapshot as its initial replay state and mocked child components. Recorded spot=null with live spot999/live positive regime passed null to both grid/sidebar, sidebar regime stayed null, and invoking the grid strike callback produced zero parent trade callbacks. Assertions passed. Server rendering does not test post-mount effects, request cancellation or user event sequences.

No additional definite defect was reproduced in these targeted cases. Tiny recommended durable coverage: App deferred response/interval regression for the three orderings above; a mounted replay test asserting null recorded spot + no strike trade call; a selected overlay with axes distinct from raw asserting rendered and published axes agree. Existing dashboard test mocks should expose grid spot/strike callbacks and control metric callbacks for those checks. Root remains owner of any added tests, final build and desktop verification. This follow-up is bounded evidence, not full acceptance.

## Final hidden read-only refutation - 20:07 UTC

All subprocesses used Node execFile/spawn with argument arrays and windowsHide:true through node_repl. No browser, application window, provider/model/order call or unrelated StockDirectory/PriceNodeHistory file was opened or changed.

Current-source extracted App blocks passed deferred-response checks for stale poll error suppression, polling after manual refresh, a newer poll failure surviving an older manual success, and loading clearing. This extends the earlier success-only ordering probe; it does not mount the entire App.

An in-memory render of the actual current Dashboard with a frozen replay missing its spot and live props spot999/change50/changePct9/isLive=true confirmed: header spot/change/changePct remain null, live badge false, refresh callback absent, grid spot null, and historical strike callback never calls the parent trade handler. Current activity map helper again returned its own axes rather than raw axes. These are controlled component/projection probes, not desktop acceptance.

Backend request_spec refusal test executed with --noconftest and tests.offline_network: 3 passed, 7 deselected, one Hypothesis collection warning. Replay, activity and delta cannot fall back to live raw research.

Focused current frontend run reported 4 suites / 50 tests passed (SkylitDashboard, SkylitHeatmapGrid, SkylitMetricsSidebar, useScopedReading), with existing asynchronous React act warnings. The craco process did not exit after reporting, so only owned hidden test tree PID9848 and its children56060/53192 were terminated after recording results. A prior attempt timed out at the tool boundary and has no claimed result; a subsequent exact process query found no remaining matching process from that attempt. This is a passed test-result report with a runner-shutdown limitation, not a clean process-exit claim.

No additional definite source defect was reproduced in this bounded pass. Durable App mounted timing coverage remains recommended; broader desktop/release acceptance remains root-owned. No production or test edits by reviewer.
