# PROPOSAL (apply-blind): B1 snapshot cadence job

Status: PROPOSAL-ONLY. Owner lane: architect/backend.

## 0. Verify first
1. Confirm Mongo 50-cap enforcement location (PLAN asserts a 50/ticker
   snapshot cap — grep `limit(50)` / sort+slice in snapshot write paths).
2. Confirm `DuckDBEngine(db_path)` file-backed mode works outside
   `:memory:` (constructor default `services/duckdb_engine.py:125`).

## 1. Design
- Job: `asyncio.create_task(_logged_task(...))` precedent
  (`server.py:920,1180,1833,1852`). New `_snapshot_cadence_loop()` in
  `server.py` near the other background tasks: every 60s, market-hours
  only (skip 09:30–16:00 ET check → sleep), tickers = cached Triad +
  active pulse tickers (bounded list, never open-ended).
- Write path: existing `bulk_insert(conn, batch)` (`server.py:1765`,
  `routes/heatseeker_snapshots_api.py:205`) via
  `contracts_to_recordbatch` — reuse, don't rebuild.
- Idempotency: upsert key (ticker, expiry, strike, type, ts_minute);
  re-runs overwrite, never duplicate.
- Retry/backoff: existing `retry_on_failure` (`duckdb_engine.py:32`).
- Mongo: raise/segment the 50-cap (separate capped collection per
  ticker or TTL index) OR roll intraday to file-backed DuckDB and keep
  Mongo for daily closes only — decide at implement time, keep the
  read path (`get_history`, `heatseeker_snapshots.py:427`) unchanged.
- Stale markers: cadence status row `{last_run, tickers_ok, tickers_failed,
  next_run}` for the status endpoint; chain payloads keep existing
  `stale` flags.
- RVOL/intraday baselines: add date-partitioned rollup view
  (day premium vs trailing-20d same-time mean) once the job is green —
  frontend shows "baseline building n/20" until then (already shipped).

## 2. Fixture (pytest sketch)
- Fake chain (10 contracts) → run job body twice → assert row counts
  identical (idempotent), second run overwrites.
- Kill upstream (raise in fetcher) → assert stale status row +
  degraded 200s, no exception escapes the loop (loop survives).
- Market-closed timestamp → assert no fetch attempted.

## 3. OpenAPI sketch
- `GET /api/snapshots/cadence/status` → `{last_run, tickers_ok,
  tickers_failed, next_run, store: "duckdb-file"|"memory"}`.

## 4. Acceptance
24h paper run: no gaps >3 min in market hours; duplicate-count query
returns 0; memory flat (no unbounded maps — prune with buffer pattern).
