# U08 — Cline: recorded-history integrity verified; no repair required

Owner: Cline. Baseline `8194eca4`, lane `work/host-cline`. New:
`backend/tests/unified/test_history_integrity.py` (7 tests: in-memory DuckDB
decision store + pure-function node history; no active store, no provider).
No source edits — all invariants held at this snapshot.

Admitted (green, exit 0 — `../evidence/u08.log`):
- Keyset paging is stable under new inserts: a mid-flight insert does not
  shift the next older page; HMAC-signed cursor with ticker/state/order
  binding — a foreign-ticker cursor refuses; bad state/limit refuse;
  missing storage is typed `DecisionHistoryUnavailable`, never a fake page.
- Unknown/malformed decision clocks are EXCLUDED and counted
  (`excluded_unknown_time`), invalid identities likewise
  (`excluded_invalid_identity`), page status degrades to `partial` —
  gaps stay gaps.
- Node history: a snapshot attaches to a bar only when known at or before
  the bar time; observation age is measured from `asof`, so a late-ARRIVING
  old snapshot can never become fresh; >900s old readings withhold nodes.
- Ambiguous (timezone-naive) bars and invalid OHLC bars are dropped;
  scope/query_key binds snapshot choice; malformed wall levels (0/negative)
  are dropped, never rendered as zero.
