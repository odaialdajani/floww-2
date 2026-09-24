# Solstice Durable-Capture Commissioning Package (R5-F, DRAFT — not approved)

Status: **prepared, NOT commissioned**. Persistent service activation requires
a separate final authorization. This document is the reviewable change + rollback
plan for that approval request. No service, cron, launchd entry, credential or
deployment change has been made.

## 1. Exact configuration

| Item | Value |
|---|---|
| Storage path | `$DUCKDB_PATH` (unset → `:memory:`, non-durable by design) |
| Proposed durable path | `~/floww-data/solstice.duckdb` (local research only; backup below) |
| Schema version | `heatmap_history.SCHEMA_VERSION = "2"` (additive migrations only) |
| Capture cadence | Structural chain builds as today; session manifest `cadence_s=300` default |
| Request budget | Shared `public_budget` singleton; 10 req/s/account baseline with headroom |
| Health endpoint | `GET /api/solstice/recorder_health` (durable flag, tables, latest write) |

## 2. Expected load

One heatmap build fans out to all UI consumers (single-flight per query key).
Recorder writes: 1 snapshot row + N contract rows + capability row per fresh
build (background thread, writer-lock serialized). At a 5-minute structural
cadence for 2 symbols: ~576 snapshot rows/day; contracts dominate volume
(~2,000 max per snapshot, declared truncation). Measure disk growth for one
week before setting retention tiers.

## 3. Health view

- `GET /api/solstice/recorder_health` → `{durable, mode, tables, latest_snapshot, checked_at}`.
- `GET /api/solstice/manifest/{ticker}?cadence_s=300` → snapshots + `gaps` + heartbeat.
- `GET /api/solstice/capability` → registry + measured + persisted observations.
- Alarm conditions: `durable == false` while `DUCKDB_PATH` set (disk failure);
  gap rate rising; `n_observed == 0` over a full session (producer stalled).

## 4. Stop / rollback

1. Unset `DUCKDB_PATH` (or stop the service) → recorder returns to `:memory:`;
   analytics keep running, `recorder_health.durable` reports false.
2. Code rollback: revert to the pre-R5-F merge SHA; schema migrations are
   additive (`ADD COLUMN IF NOT EXISTS`) so old code reads new DBs; new
   columns are ignored by old readers.
3. No data migration is required to roll back; to roll forward again,
   re-merge and restart.

## 5. Restart proof (required before approval)

1. Set `DUCKDB_PATH` to a temporary file; run two fresh builds for one symbol.
2. `GET /api/solstice/manifest/{ticker}` shows 2 snapshots, 0 unexplained gaps.
3. Restart the backend process; `GET /api/solstice/replay/{id}` returns the
   identical strikes/walls/contracts/cells/quality/scenarios recorded before.
4. Record the three outputs in the approval request. Without this proof the
   service must not be called commissioned.

## 6. What commissioning does NOT grant

Live trading, credential changes, vendor messages, multi-user data
redistribution (Individual API is personal-use), or any predictive-performance
claim. Thirty to sixty sessions is a collection target, not a passing grade.
