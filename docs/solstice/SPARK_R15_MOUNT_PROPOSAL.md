# SPARK R15 — Mount proposal (NOT applied; Zed final review required)

Spark is the default writer for `server.py` mounts, but this increment makes
ZERO shared-file edits to avoid mid-lane conflicts. The following patch is
PROPOSED for Zed's combined-candidate review only. Do not apply until R15-6
gates are green and Zed acknowledges in their checkpoint.

## Proposed (exact boundary)

1. `backend/server.py` — lifespan startup/shutdown ONLY (no new routes):
   - `from services.solstice_price_producer import register_store, register_capture, start_worker, stop_worker`
   - On startup (after `duckdb_engine.db` init): `register_store(duckdb_engine.db.conn)`
     + `register_capture(symbols=<operator-config>, fetch_one=<public-quotes-seam>,
     session_gate=default_session_gate, cadence_s=300)` + `start_worker()`
     (returns `{"started": False, reason: "FLOWW_PRICE_PATH_PRODUCER!=1"}` while
     disarmed — the expected OFF receipt).
   - On shutdown: `stop_worker()`.
   - Writer: Spark. Zed ack required before apply.
2. `backend/routes/solstice.py` — read-only status ONLY (no submission path):
   - `GET /api/solstice/price_paths/status` → `PricePathProducer.health()` shape
     (`version/cadence_s/symbols/generation/captures/gaps/errors/duplicates/
     out_of_order/closed_skips/budget_refusals/last_tick_at/last_latency_ms/
     durable/policy/resolution`) + existing `recorder_health` store block.
   - Writer: Spark. Zed ack required before apply.
3. `backend/services/public_capability.py:37` — one-line prose fix:
   `"PublicBroker.place_order (UNGATED LIVE — disarmed, no route)"` →
   `"PublicBroker.place_order (gated LIVE — POST /api/public/order, FLOWW_ENABLE_LIVE_PUBLIC==1)"`.
   Writer: Spark. Zed ack (doc-only, no behavior change).

## Explicitly NOT proposed

- No new POST/submission route. `routes/public_brokerage.py` stays the only
  HTTP order path with its existing 401/422/403 gate.
- No `backend/services/agent/**`, `backend/routes/agent.py`, `frontend/`,
  protected/frozen, or watchdog edits.
- No flag changes, no activation, no deployment/restart by this lane.
