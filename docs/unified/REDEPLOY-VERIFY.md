# Redeploy + live verification (2026-10-08, architect-authorized)

- PR116 merged to main as `2a293b6e` (4/4 hosted gates green before merge).
- Preview backend `:8002` restarted via `work/start_backend.py` (same safe
  flags: local deployment, captures/trading OFF, broker keys stripped).
  Old pid retired cleanly; originals 8000/8001 untouched. New pid serves
  the composed tree — `/api/version` reports `"sha":"97e16bbe"`,
  `/api/health` healthy.
- Previously-429 reads now 200 (`/api/related/SPY`,
  `/api/solstice/scan/leaderboard`, `/api/version`).
- Browser battery re-run on the redeployed preview: **11/11 checks**,
  zero runtime errors, zero order POSTs, **zero failedReads** (the 429
  class is gone live — read-budget fix verified end to end).
