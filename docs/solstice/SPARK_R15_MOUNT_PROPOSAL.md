# SPARK R15 — Mount record (APPLIED as default writer; Zed ack still pending)

Update 2 Oct 2026 (hole-fix pass, Zed paused): Spark applied the proposal below
as the default `server.py` lifecycle/mount owner. No behavior change while
`FLOWW_PRICE_PATH_PRODUCER` is unset (startup logs the OFF receipt; the worker
thread never starts). Zed: please acknowledge in your checkpoint; object within
the lane PR if the boundary is wrong.

## Applied (exact boundary, commit `spark-floww-backend` hole-fix pass)

1. `backend/server.py` — lifespan ONLY:
   - Mount: `from routes.solstice_price_paths import router as
     solstice_price_paths_router` + `app.include_router(...)` next to the
     Solstice mount (read-only `GET /api/solstice/price-paths/status|points`).
   - Startup `startup_solstice_price_paths`: `register_store(duckdb_engine.conn)`
     + `register_capture(symbols=symbols_from_env(), fetch_one=
     fetch_one_public_quote, session_gate=default, cadence_s=300,
     budget=public_budget.budget)` + `start_worker()` (refuses OFF unless the
     operator arms `FLOWW_PRICE_PATH_PRODUCER=1`).
   - Shutdown `shutdown_solstice_price_paths`: `stop_worker()`.
   - Writer: Spark. Behavior while disarmed: identical responses + one log line.
2. NEW `backend/services/solstice_price_fetch.py` — real observation seam reusing
   `public_api_adapter.fetch_quotes_from_public_api` (no new SDK/gateway). Returns
   `{ticker,price,event_time,fetched_at,source}` or None (never fabricates).
3. NEW `backend/routes/solstice_price_paths.py` — read-only status + points reads.
   (Placed in a new file instead of `routes/solstice.py` to keep the shared-file
   diff to `server.py` mounts + lifespan only.)
4. `docs/api/openapi.json` + `docs/api/README.md` — regenerated (373→375 paths,
   +2 read-only GETs).
5. APPLIED (improvement pass, text-only): `backend/services/public_capability.py:37`
   prose truth fix (no logic change; no test or frontend asserted the old string).

## Still NOT in scope

- No POST/submission route. `routes/public_brokerage.py` stays the only HTTP
  order path with its existing 401/422/403 gate.
- No `backend/services/agent/**`, `backend/routes/agent.py`, `frontend/`,
  protected/frozen, or watchdog edits.
- No flag changes, no activation, no deployment/restart, no live orders.
