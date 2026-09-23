# Solstice REPLAY_PROTOCOL (T09)

1. Recorder writes fresh builds only (never stale-serves) to DuckDB v2 tables
   with received_at + calculated_at + oi_effective_date preserved.
2. Deduplicate by snapshot digest; corrections append revisions linked to the
   original; session rollover resets cumulative-volume baselines.
3. Replay endpoint `/api/solstice/replay/{id}` returns ONLY rows with that
   snapshot_id (available-at join). Tomorrow's OI never informs yesterday.
4. Manifest `/api/solstice/manifest/{ticker}?day=` reports snapshots + gaps.
   Gaps are missing capture, not missing market.
5. Outcomes labeled per horizon (60/180/300/900s) with first-passage rules;
   simultaneous-barrier observations are unknown-order, never assumed profitable.
6. Research retention is immutable; display cache stays 50/ticker in Mongo
   with typed `ts` + `ts_iso` compat.
