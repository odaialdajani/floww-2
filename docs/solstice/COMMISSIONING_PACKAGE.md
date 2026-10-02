# Solstice Durable-Capture Commissioning Package (R5-F, DRAFT — not approved)

Status: **prepared, NOT commissioned**. Persistent service activation requires
a separate final authorization. This document is the reviewable change + rollback
plan for that approval request. No service, cron, launchd entry, credential or
deployment change has been made.

## R14 readiness / activation boundary (1 Oct 2026)

- Offline engineering acceptance is separate from activation: source event/fetched/available clocks, complete/partial/missing/stale records, exact listed identity, comparable window baseline and registered replay envelopes are required. Older incomplete records stay refused; no live substitutes or invented baseline/outcome.
- The historical table below describes build-time recording, not a new default-on scheduled service. `SOLSTICE_OUTCOME_WORKER` remains explicit opt-in (`1`); default-disabled lifecycle test passes. This task changes no environment, path, worker registration, service or deployment.
- Recorder restart durability, review journal, episode lineage and outcome worker/attachment fixtures are checked separately. Missing episode/barriers/price path stays pending; incomplete coverage stays censored; same-bar dual barrier stays `simultaneous_unknown`. Review is not calibration or an outcome claim.
- Participant preparation: use existing `scripts/solstice_comprehension.py --selftest` for answer-key plumbing only. An actual participant run must separately identify source/fixture, tasks, responses, confidence and consent; do not count scripted answers/native Chromium zoom as human comprehension. No study participant or live session has been commissioned here.
- External acceptance remains SPX entitlement, durable capture/service authorization, participant study and empirical multi-session validation. Obtain data rights and commissioning approval before activation; this document is preparation, not authorization.

## 1. Exact configuration

| Item | Value |
|---|---|
| Storage path | `$DUCKDB_PATH` (unset → `:memory:`, non-durable by design) |
| Proposed durable path | `~/floww-data/solstice.duckdb` (local research only; backup below) |
| Schema version | `heatmap_history.SCHEMA_VERSION = "2"` (additive migrations only) |
| Capture cadence | Structural chain builds as today; session manifest `cadence_s=300` default |
| Enable flag | None yet — capture runs wherever the backend runs; persistent activation = setting `DUCKDB_PATH` to the durable path + long-lived process (launchd/service file to be proposed in the approval request, not before) |
| Request budget | Shared `public_budget` singleton; 10 req/s/account baseline with headroom |
| Health endpoint | `GET /api/solstice/recorder_health` (durable flag, tables, latest write) |

## 2. Expected load

One heatmap build fans out to all UI consumers (single-flight per query key).
Recorder writes: 1 snapshot row + N contract rows + capability row per fresh
build (background thread, writer-lock serialized). At the 5-minute structural
cadence across a regular 6.5-hour session: 6.5 × 60 / 5 = 78 scheduled
snapshots per symbol (≈156 for two symbols) before endpoint/loop effects —
NOT 576/day (that assumed 24 hours). Measure one week of disk growth before
setting retention tiers.

## 3. Health view

- `GET /api/solstice/recorder_health` → `{durable, mode, tables, latest_snapshot, checked_at}`.
- `GET /api/solstice/manifest/{ticker}?cadence_s=300` → snapshots + `gaps` + heartbeat.
- `GET /api/solstice/capability` → registry + measured + persisted observations.
- `POST /api/solstice/outcomes/close` → runs the outcome job over open
  decisions (auth-gated, idempotent); episodeless decisions stay pending
  (`NEED_EPISODE`), never labeled. Price paths are caller-supplied until a
  scheduled price-path recorder is commissioned.
- Alarm conditions: `durable == false` while `DUCKDB_PATH` set (disk failure);
  gap rate rising; `n_observed == 0` over a full session (producer stalled).

## 4. Stop / rollback

1. Unset `DUCKDB_PATH` (or stop the service) → recorder returns to `:memory:`;
   analytics keep running, `recorder_health.durable` reports false.
2. Backup/recovery: copy `~/floww-data/solstice.duckdb` while the writer is
   stopped (single-writer lock, §writer policy in `heatmap_history`);
   restore = replace file + restart + `manifest` gap check. No WAL replay
   tooling is assumed — a mid-write copy is discarded, never repaired.
3. Code rollback: revert to the pre-R5-F merge SHA; schema migrations are
   additive (`ADD COLUMN IF NOT EXISTS`) so old code reads new DBs; new
   columns are ignored by old readers.
4. No data migration is required to roll back; to roll forward again,
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
