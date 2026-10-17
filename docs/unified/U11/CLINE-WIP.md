# U11 — Cline: store isolation/restart integrity; one narrow repair

Owner: Cline. Baseline `8194eca4`. New: `backend/tests/unified/test_storage_restart_integrity.py`
(5 tests, green — `../evidence/u11.log`) + one-line repair in
`backend/services/related_price_series.py` (U06/U08 write path).

Fresh counterexample found and repaired (failed-first):
- A corrupt/torn SQLite file raised an UNCUGHT `sqlite3.DatabaseError`
  instead of the typed `cache_storage_unavailable` the reader advertises
  (only OperationalError was caught). Widened the catch to `sqlite3.Error`;
  corrupt copies now disclose unavailability, never fabricate rows.

Verified without repair:
- Dated Related series and scan observations survive close/reopen with
  clocks and contents intact (read-only reopen path exercised).
- Digest-tampered payloads are dropped, never served (symbol degrades to its
  attempt record with empty bars — disclosed, not silent).
- Missing store file = cold cache (`None`), not a crash-safe claim.
- Full unified suite still green after the repair: 68/68 (`../evidence/u-all.log`).

Inventory note (config paths not secrets): DuckDB research store via
`services/duckdb_engine.py`, Mongo agent-history via
`services/agent/repository.py`, scanner/Related SQLite default paths as in
the respective services; memory fallbacks disclose `live=false`/
`trade_eligible=false` — per acceptance, no claims of crash-safety for them.
Originals and user Mongo untouched.
