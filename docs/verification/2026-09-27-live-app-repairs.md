# Real-app repair verification — 2026-09-27

User request: fix the failures detected by operating the actual application, and remember the working computer-control method.

## Resolved software faults

- SPY and QQQ rejected wide books caused the Public-only chain/spot views to fail. Strict book rejection remains. An exactly matched rejected quote can use the provider's daily regular-session close only outside the open session, after a 15-minute settling period, with exact symbol, session date, timestamp, finite OHLC and range validation. Wrong-symbol, absent-quote, active-session, future-bar and bad-price cases remain unavailable. This is a provider daily close, not proof of a final auction print. Cache and coalescing are bounded by symbol/session and broker identity.
- Both options-chain routes now apply one shared set of display calculations. Provider time-to-expiry is retained; missing inputs remain missing, finite supplied vanna/charm remain intact, and actual zero remains zero. Filtering the direct route no longer mutates the shared cached chain.
- The live connection now carries price source, observation time and status separately from response/calculation time and the chain observation time. The screen says Price observed and includes the date.
- Fractional strikes remain visible in bars, options table and summary levels. Small vanna/charm values no longer round to misleading whole-number zeroes.
- Installed the already-declared pandas-market-calendars 4.6.1 package into the active project environment. Movers can now resolve the last two completed sessions. Movers waits briefly for busy admission slots without bypassing provider limits; its total compute deadline remains 25 seconds. Overlapping callers share success or failure, disconnected callers do not cancel siblings, result limits are applied per caller, and stale-response annotations cannot mutate saved data. Partial coverage has its own screen label.

## Validation

- 115 affected backend tests pass after final changes. New cases reproduce the original missing price/reading faults and exercise session boundaries, corrupt/future bars, expiry inputs, route parity, timestamp separation, concurrent admission, unavailable results and disconnects.
- Entire frontend test suite: 918 tests pass across 105 suites. Production build succeeds. Existing notices remain about bundle size and test handle cleanup.
- Ruff passes for affected Python files. Bandit medium-or-higher scan passes for affected production Python files. Eight changed production Python files parse at the Python 3.11 syntax floor. Local execution is Python 3.13; this does not claim a Python 3.12 deployment run or a full backend-suite pass.
- Independent adversarial review reproduced and closed the lock contention, future-bar, supplied-Greek and overlapping-failure cases. Final six mover failure/concurrency checks passed independently.
- Actual app: React on localhost:3000, backend on localhost:8000, existing Mongo retained. Operated through connected Chrome MCP using fresh accessibility state and screenshots, not a fixture screen. SPY grid and options table, QQQ grid/history, and IWM bars/decimal strike were visibly inspected. No broker action was taken.
- Final backend real responses: SPY 771.35 and QQQ 744.50, both marked stale Public session close observed 2026-09-25 20:00 UTC; IWM 282.22995, marked stale Public midpoint observed 2026-09-25 23:57:28 UTC. All three spot routes return 200.
- Movers visibly reached 75/75 after warmup before the final restart. The final cold concurrent check returned 69/75 within 25.036 seconds; both callers shared the identical computed time and received their own 1-row/12-row limit. The six missing stocks were explicitly reported as a compute timeout. Full coverage is not guaranteed under every load.
- QQQ history loaded 395 actual price candles and zero aligned saved historical nodes. Old nodes were never recorded for those candles; they remain unavailable. Current observations are not backfilled into historical candles. Missing source inputs and optional disabled integrations are not represented as working feeds.

## Integration and evidence

Colleague changes through 69d73c95 were fast-forwarded first: documentation fixes and SQLite ignore rules, with no source conflict. Local runtime stores remain local.

Detailed command outputs and live response receipts are in output/live-app-fixes-20260927 (ignored local evidence). The user-requested future test preference was saved through the supported memory-extension note, including exact app startup, hidden Windows background commands, Chrome MCP discovery, real-data checks, and leaving the app open.

Provider contract references: https://public.com/api/docs/resources/market-data/get-bars-v2-with-aggregation and https://public.com/api/docs/resources/market-data/get-quotes . These explain regular-session bars and separate trade/book times; no claim of auction finality is made.
