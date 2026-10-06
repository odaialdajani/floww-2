# SPARK R15 — Outcome census re-run (2 Oct 2026, read-only)

Base `1530ccd7`, lane head `solstice/spark-floww-backend`. No writes, no
activation, no live calls. All flags unset in this shell (`DUCKDB_PATH`,
`FLOWW_PRICE_PATH_PRODUCER`, `FLOWW_ENABLE_LIVE_PUBLIC`,
`SOLSTICE_OUTCOME_WORKER`, `FLOWW_RECORDER_WORKER` all empty).

## Configured-store health (actual, not test-DB proof)

- `DUCKDB_PATH` unset → `_open_shared_db` returns `:memory:`.
- `recorder_status` on the live singleton reports `durable:false/mode:memory`.
- `GET /api/solstice/price-paths/status` (test process) reports
  `worker_enabled:false`, `worker_state:absent|wired_off`, `durable:false`.
- Conclusion: missing durable configuration produces a clear refusal (memory
  mode, never claims durable). An in-memory test DB is NOT presented as
  production proof.

## Tracked-DB census (read-only opens)

| Store | Tables | Solstice tables/rows |
|---|---|---|
| `backend/data/gflows.duckdb` | 1 | 0 |
| `data/research_kg.duckdb` | 29 | 0 |

Snapshots / decisions / outcomes / price-paths in durable stores: **0**.

## Missing / censored accounting

- Fixture `r14/evidence/vertical-fixture.json` self-declares synthetic (not a
  market/participant/outcome observation).
- `NEED_EPISODE`, `simultaneous_unknown`, `OBSERVATION_GAP`,
  `TOUCH_NO_BARRIER` semantics preserved in code (`solstice_labels.py`,
  `heatmap_history.outcome_close_tick`); censored stays censored, never a win
  or a zero loss.
- 30–60 sessions remains a COLLECTION MILESTONE with zero sessions collected.

## Verdict

**INSUFFICIENT EVIDENCE** for any session-level, costed, comparative, edge, or
profitability claim. Unchanged from the R14 closeout census. Production
readiness additionally needs admitted records from the actual configured store
after commissioned activation — explicitly out of scope for this lane.
