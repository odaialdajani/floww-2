# U07 — Cline: dated scanner observations verified; no repair required

Owner: Cline. Baseline `8194eca4`, lane `work/host-cline`. New:
`backend/tests/unified/test_saved_scanner_admission.py` (9 tests, tmp SQLite
stores, zero provider calls). No source edits; preserved behavior verified
exactly. 77 friend files untouched (see U01).

Admitted invariants (all green, exit 0 — `../evidence/u07.log`):
- Dated snapshots keep ORIGINAL receipt + source-event clocks; ages reported
  as known/unknown/future — future-dated receipts are excluded from page
  candidates and counted as unknown-clock, never served as current.
- Retention is monotonic: an older receipt never overwrites newer rows
  (`unchanged`), newer replaces older.
- Duplicate contract identity within a snapshot → refused; non-`ok` status or
  malformed clock → refused; >120-row packs → refused, never truncated.
- Missing quote extras / volume source clocks mark `data_status=partial`
  (counted in coverage), never upgrade to complete.
- Failure/deferred/capacity attempts are separate checks with typed states;
  symbol capacity refuses beyond the bound.
- Page filters bounded (offset/limit/age/max_age validated); `live=false`,
  `trade_eligible=false`, `complete_realtime_market=false`,
  `full_contract_chains=false` verified in the returned truth block.
- Legacy example rows are surfaced only as their actual stored rows
  (LEGACY_ROWS_PER_SYMBOL=3 cap present in source; no fabricated history).
