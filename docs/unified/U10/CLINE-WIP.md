# U10 — Cline: export/import machinery proven on isolated copies; real-store completeness HELD on NAV-CAPTURE

Owner: Cline. Baseline `8194eca4`, lane `work/host-cline`. New:
`backend/scripts/export_legacy_decisions.py` + `backend/tests/unified/test_legacy_export_completeness.py` (5 tests, all green exit 0 — `../evidence/u10.log`).

Evidence delivered (isolated synthetic DuckDB copies only; originals untouched):
- Digest-verified import: wrong digest refuses before the store is opened;
  conflicting native identity refuses with rollback (zero partial rows);
  duplicate identical input counted not double-imported; malformed/non-200
  source responses refused.
- Round-trip: synthetic stopped copy → export (full uncapped rows, per-table
  presence reported: quotes/reviews present-or-absent honestly) → fresh
  isolated import → independently reopened destination matches identities
  and stored SHA-256 digests exactly.
- Truth preserved: `quote_details_recovered=0` — a summary import can never
  restore quote rows and the receipt says so.

Explicit remaining gap (task stays open for this): exporter proven against
synthetic copies; a completeness receipt for the ORIGINAL research store
requires authorized access to its stopped copy (NAV-CAPTURE hold — original
8000/8001 services and files are untouched by design).
