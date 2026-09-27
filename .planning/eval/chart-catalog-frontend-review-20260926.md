# Chart/catalog frontend independent review - 2026-09-26

Scope: actual root integration after the concurrent catalog/history handoff. Read .planning/MARKET_COVERAGE_HISTORY_API_CHECKPOINT.md through20:29 and output/market-coverage-check/VERIFICATION.md, then reviewed current production source and tests. Source edits remain root-owned. All subprocesses were launched from node_repl with explicit argument arrays and windowsHide:true. No visible app/browser, real network/provider/model/order call, or production/test-source edit by reviewer. Scratch fixtures and logs are under output/chart-catalog-review-20260926.

## Confirmed finding - historical chart does not isolate research context

Severity: high for answer truth, no broker-write exposure reproduced. PriceNodeHistory is mounted above the main Solstice map and manages open/position/playing locally. It does not notify SkylitDashboard or publish an unsupported historical display. SkylitDashboard continues publishing the live raw map. AgentProvider freezes that shared context when a question is asked, so the existing backend replay/overlay refusal does not protect this separate chart.

Reproduction: the actual shared useScreenContext starts on tickerSPY/displayMode=live/mapVersion=LIVE-MAP. Mount real PriceNodeHistory, load three mocked historical candles, scrub to the first frame, then an AskProbe reads the same context as AgentProvider. It still receives displayMode=live and the live map identity. The expected non-live identity assertion FAILS. Exact probe: output/chart-catalog-review-20260926/independent-history.test.jsx; log independent-history.log. The second test, playback advance and stop on collapse, PASSES. No real model question was sent.

### Minimal owner correction points

- PriceNodeHistory opening event must notify parent that this historical chart owns or blocks research immediately, including its loading/error/empty state. Closing/unmount must release that ownership. Keep the chart read-only and do not pass trade callbacks.
- SkylitDashboard must incorporate this active state into its existing shared-context publication. While history is open, mark a distinct unsupported price-history display and remove live selected-cell/map identity; do not fabricate historical map binding. A later live-map refresh must not overwrite that guard.
- backend/services/agent/contracts.py request_spec must refuse this unsupported price-history display as it already does replay/activity/delta, before live raw tools run. Broader historical-AI interpretation remains separate work; refusal is not implementation of it.
- On collapse/close or ticker-key remount, recompute the newest actual main surface context. Do not restore a captured older context. If main Solstice replay is active then, restore replay refusal rather than live. Test opening before response, loaded/scrubbed, late live refresh while open, closing after a newer main map, and ticker switch.

## Verified behavior

1. Seven relevant existing suites passed independently:65tests, exit0. StockDirectory, PriceNodeHistory, priceNodeTraces, tickerUniverse, SkylitTickerBar.paging, MarketCoverage and SkylitDashboard. Log focused-tests.log. Existing async React act warnings remain. CI=true wrapper and runInBand/forceExit completed the owned process normally.
2. Two new scratch mounted tests passed against actual dashboards: actual Solstice contains both directory/history and selectingZZZ forwards onTickerChange; actual active Tidehunter contains directory/coverage and selectingZZZ updates its focused ticker while closing the dialog. Axios/fetch responses are fully mocked; Plotly is replaced by a test element. Log actual-mounts.log. This validates actual mounting/selection, not live provider data.
3. Independent history playback test passed: Play from the final position restarts at first frame, advances one shown candle after250ms, and collapsing removes the chart/stops playback. Existing ticker-change test confirms old chart clears while new request waits. Existing trace tests cover no overnight bridge, hourly node freshness cut-off, and fresh five-minute spans.
4. Catalog paging successfully handles13,135 names above the old12,000cap and returns explicit completion. StockDirectory separately displays incomplete/stale provider catalog warnings and exposes retry. The App caller currently discards fetchFullUniverse.complete when filling its button/search list: partial-list provenance is not shown there, although the separate full-directory dialog remains available and no total-market scan claim is inferred from that list. This is a remaining disclosure limitation, not the confirmed historical-context defect.
5. MarketCoverage distinguishes available universe/fresh/waiting/failed, custom/saved/unavailable catalog, expiry limit and per-stock row cap. Text says snapshot activity is not a live feed of every trade. Its release check refreshes five minutes and checks its timestamp before claiming current.

## Tested source SHA256

- frontend/src/components/heatseeker/StockDirectory.jsx = 57b6b42c5bd7383a67fbb056f6936664e2b76bcc5f9788fc743b64ed5e9a2bfb
- frontend/src/components/heatseeker/PriceNodeHistory.jsx = 4354f5829a7d5ee771fe1d60b4ebcd2da812e7a99632d0b7124a4d0a0ada3063
- frontend/src/components/heatseeker/priceNodeTraces.js = 68ab428bbf8ae9243036bce4821415d5c9b4e03a5fab67ca3bba12f71860b8f7
- frontend/src/components/heatseeker/tickerUniverse.js = 044a3ba8079638f0abb0bab5f0f1b7ed6b0c0eb00cc0f34b39f9f805ad23749b
- frontend/src/components/flowseeker/MarketCoverage.jsx = 663fc4e7cca99d6f590283bf5b5d3cb52218d6da6164c0df7c62f7d646691074
- frontend/src/components/heatseeker/SkylitDashboard.jsx = 31a1c372748b2914ae6b8ad9d623af77ee3510f8a694da5187ce0407f9016515
- frontend/src/components/flowseeker/FlowseekerProBlademap.jsx = 4495638e2ed9281a176d1e3e830f1fc8b719f4a9692f4e3be89da9d711c86918

At report write, unchanged versus captured hashes: {"frontend/src/components/heatseeker/StockDirectory.jsx":true,"frontend/src/components/heatseeker/PriceNodeHistory.jsx":true,"frontend/src/components/heatseeker/priceNodeTraces.js":true,"frontend/src/components/heatseeker/tickerUniverse.js":true,"frontend/src/components/flowseeker/MarketCoverage.jsx":true,"frontend/src/components/heatseeker/SkylitDashboard.jsx":true,"frontend/src/components/flowseeker/FlowseekerProBlademap.jsx":true}. Hash manifest: output/chart-catalog-review-20260926/source-hashes.json. Future root corrections need new evidence/hash entries rather than inheriting this result.

## Limits

No full818-test or production-build rerun by this reviewer; concurrent task counts were read but not used as independent proof. No headless visual run was necessary for the reproduced state/context defect. Backend candle timing, available-at joining and recorder durability remain with root/backend review. No claim of all-market freshness, past-node reconstruction, historical-AI answers or full acceptance. One confirmed finding remains for root correction.

## Independent verification of the repair - 21:19 UTC

Root implemented parent-controlled PriceNodeHistory open state and an unsupported price-history research context. This supersedes the initial confirmed finding for the tested states. Independent scratch test guarded-history.test.jsx mounts the actual Dashboard and actual historical component with mocked axios/Plotly, and all3 cases PASS (exit0):

- Opening before the response immediately clears live map identity; loaded/scrubbed history remains guarded; a newer live map cannot overwrite that guard; closing restores the newest actual main map.
- Main Solstice replay can already be active; opening history changes the research guard to price-history, and closing restores replay with its recorded snapshot/version, never live.
- Switching ticker while history is open keeps the guard and the new ticker; a late old-ticker response cannot render; closing restores the new ticker map. Unmounting with another response pending and mounting a new supported map leaves the new context intact when the old response arrives.

Exact tests/log: output/chart-catalog-review-20260926/guarded-history.test.jsx and guarded-history.log. The earlier independent-history.test.jsx remains the archived pre-fix standalone reproduction; current integration is verified through the actual parent-controlled mount, not the unconnected standalone component.

Backend: existing unsupported-surface parameterized checks3PASS/7deselected with offline guard. A separate direct request_spec probe additionally verified price-history, replay and unknown future non-live display all raise the display refusal before live research; log history-refusal.log. This blocks unsupported historical interpretation; it does not implement historical AI.

Repaired SHA256 snapshot:
- frontend/src/components/heatseeker/PriceNodeHistory.jsx = 817508a76469b6d5b6b78261adf900c6f416d09b97fc580c0420a5e350c8fd74
- frontend/src/components/heatseeker/SkylitDashboard.jsx = 65298a8fb6b03ff713069f52a4502ceb41cb173e4ca6c27af84f788d47eb668d
- frontend/src/agent/useScreenContext.js = cf13ac826a05a552022ed22602eedebf9eff080fbdbef77cda4b0971284313f2
- backend/services/agent/contracts.py = cd85b26269b3e230a641334608db43f970aa5e3decd592d9ae7aeaabdccf464d
Manifest guarded-source-hashes.json is beside the logs. No additional defect reproduced in these requested state transitions. App partial-directory work was not edited or retested here. All child processes were hidden and exited; no provider/model/order call, source/test-production edit, app window or full acceptance claim.
