# GitHub Pattern Research — Agent 4 (2026-09-03)

**Rules followed:** public repos only · patterns described, NO code copied · license + risk recorded.
Extraction method: prior knowledge of well-known public repos + web index check where noted.
Nothing below was cloned into the repo. Tidehunter must re-implement from the pattern description.

## Target patterns

### 1. React virtualized tables
- Repos: TanStack Virtual (https://github.com/TanStack/virtual, MIT) · react-window
  (https://github.com/bvaughn/react-window, MIT).
- Pattern: windowed row rendering with stable row keys; overscan; memoised row components; scroll-offset
  driven slice. 15s poll updates only the visible slice.
- Application: Pulse tape + Scanner at 10× volume; perf gate per wave.
- Do-not-copy: do not vendor the lib without install approval; do not copy demo code with fake data generators.
- Risk: low (MIT). Bundle-size cost if adopted — ADR first.

### 2. Per-tab config persistence
- Repos: generic pattern (zustand persist middleware https://github.com/pmndrs/zustand, MIT;
  redux-persist https://github.com/rt2zz/redux-persist, MIT).
- Pattern: ONE serialized object per tab {schemaVersion, filters, columns, highlighting, tickerScope,
  resultsCap, sort}; versioned migration for missing fields; localStorage-first, backend promotion later.
- Application: W3 one-substrate requirement (max 10 Live / 5 Scanner tabs).
- Do-not-copy: storage keys/schemas must be ours (match CONTRACTS.md tab-config object).
- Risk: low (MIT). Key-collision risk with concurrent agents — namespace keys `flowseeker.*`.

### 3. Chart modal with synchronized views
- Repos: lightweight-charts (https://github.com/tradingview/lightweight-charts, Apache-2.0).
- Pattern: single time-axis model, multiple series panes synced to one crosshair; lazy-load secondary
  views; explicit empty-state per pane.
- Application: W3 chart modal v1 (contract history + Net Premium); later 5-view expansion.
- Do-not-copy: do not copy example datafeeds; time handling must follow CONTRACTS timezone rules.
- Risk: low (Apache-2.0). License header preserved if vendored.

### 4. Options flow scanners
- Repos: OptionScannerTWS (local dir ~/OptionScannerTWS — check license before reuse),
  awesome-options-analytics (https://github.com/.../awesome-options-analytics — list, mixed licenses).
- Pattern (industry-standard, non-copyable facts): sweep proxy = multi-venue burst within short window;
  unusual = vol/OI + premium thresholds; block = premium size gate. THESE ARE HEURISTICS, not academic rules.
- Application: scanner classification proxy labels; must carry "proxy" copy per copy-checklist.
- Do-not-copy: no venue-data logic may claim true sweeps; no threshold may cite a paper.
- Risk: medium — copying threshold folklore risks re-creating refuted attributions. Re-implement with OUR gates.

### 5. DuckDB analytical query patterns
- Repos: duckdb (https://github.com/duckdb/duckdb, MIT).
- Pattern: in-memory analytical scans over snapshot batches; window functions for rolling baselines
  (RVOL baseline, sigma bands); parametrized queries from Python; file-backed migration path for >memory.
- Application: B1 baseline plumbing (RVOL, volume z-score, quiet-accumulation gate); :memory: pressure
  risk at 10× volume → file-backed plan.
- Do-not-copy: connection/singleton handling must follow backend conventions.
- Risk: low (MIT).

### 6. Mongo time-series snapshots
- Repos: mongodb docs pattern (time-series collections); Motor async driver
  (https://github.com/mongodb/motor, Apache-2.0).
- Pattern: time-series collection per ticker, 50-snapshot cap awareness, TTL/compaction indexes,
  idempotent upserts on (ticker, timestamp), stale markers.
- Application: B1 snapshot cadence; ΔOI from consecutive snapshots.
- Do-not-copy: index/collection names must match backend conventions.
- Risk: low.

### 7. FastAPI cache endpoints
- Repos: fastapi (https://github.com/tiangolo/fastapi, MIT); fastapi-cache pattern.
- Pattern: aggressive Cache-Control + ETag on slow-moving data (earnings calendar, ATS weekly, SHO daily);
  stale-while-revalidate; explicit `as_of` + `stale` fields in every payload (matches CONTRACTS states).
- Application: B2/B3 endpoint proposals.
- Do-not-copy: auth/Public-paths behavior must stay per backend/auth.py (PUBLIC_PATHS rule).
- Risk: low.

### 8. FINRA ATS parsers
- Pattern: weekly ATS text/CSV aggregates → (ticker, venue, week_ending, volume, trade_count); delay stamp;
  NO side field exists — parser must not synthesize one.
- Application: B3 ETL. Data: https://www.finra.org/filing-reporting/otc-transparency.
- Do-not-copy: no third-party parser vendored without license check; write our own against the spec.
- Risk: low if self-written; format drift is the operational risk (pin expected columns + alert on change).

### 9. Reg SHO parsers
- Pattern: daily short-volume files → (ticker, date, short_volume, total_volume, short_ratio); positioning
  context only, never "direction of today's prints".
- Application: B3 ETL + Johnson-So borrow context.
- Do-not-copy: same as ATS.
- Risk: low.

### 10. Finnhub calendar caching
- Pattern: free-tier calendar endpoint + aggressive cache (daily TTL), 1-month history limit honored in UI
  ("no multi-quarter trends" empty state); API key from env only.
- Application: B2 / W2 earnings proximity.
- Do-not-copy: never hardcode keys; never cache-bust in a loop (free-tier limits).
- Risk: low; rate-limit breach is the risk class.

### 11. Backtest harness structure
- Repos: generic event-driven backtest pattern (no single canonical repo endorsed).
- Pattern: signal events → fill assumptions (mid ± slippage, spread-aware) → outcome ledger by rule+band;
  read-only calibration; no auto-threshold changes; fixture-first before Databento live data.
- Application: W5 backtest harness + outcomes module.
- Do-not-copy: no P/L engine copied; fills must be labeled assumptions.
- Risk: medium — survivorship/lookahead bias; evaluator fixtures must include boundary cases.

## General prohibitions

- No private repos, no auth-walled scraping, no copied code files.
- Every adopted pattern gets an ADR/proposal entry with license + source URL.
- If a repo's license is unclear, treat as do-not-touch until clarified.
