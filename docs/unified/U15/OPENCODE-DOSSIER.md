# U15 — execution default-deny dossier (OpenCode takeover, 2026-10-08)

Lane: `work/host-opencode` (baseline `8194eca4` + own probes only).
New: `backend/tests/unified/test_execution_boundary_opencode_probes.py`
(5 tests, green). No source edits. No live flag set anywhere in this work.

## Verified boundary facts (current snapshot)

- Kill-switch: `POST /api/public/order` with a fully valid body and LIVE
  unset → **403 `live_trading_disabled`**, zero broker placements — even
  with no broker configured (refusal precedes existence checks).
- Cancel: `POST /api/public/order/{id}/cancel` with app key → 200 CANCELED
  while entries disarmed; without key → 401/403. Exits never pause with
  entries. Fake broker counts prove placement/cancel separation.
- Privileged admission router (`/admission/*`, incl. policy/approval/
  operator/risk endpoints) is UNMOUNTED in the production app (runtime
  route census, not source grep). Test-local mounts don't count.
- `submit(armed=False)` refuses `DISARMED` before any broker access
  (service default; production callers must opt into arming explicitly).

## HOLD dossier (all with Nav — none faked)

Actual account policy selection, live-gate change, `/admission` mount,
broker/API connection, paper/live orders, native workflow registration,
per-operator credentials. Service-only tests prove refusal posture, never
commissioning. H-EXECUTION and NAV-ACCOUNT/CAPTURE/MODEL/NATIVE/RELEASE
stand exactly as scoped.
