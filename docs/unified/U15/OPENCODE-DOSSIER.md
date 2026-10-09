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


## Independent review correction (2026-10-08)

The five tests above prove only the listed refusal/cancel/mount posture;
they do not close the full U15 execution contract. The policy/store and
immutable-approval paths require `test_public_brokerage_admission.py`,
`test_s18_approval_single_use.py` and `test_s18_mounted_full_stack.py` plus
the remaining S18 authority/effect/retry/risk/protection suites, bound to
the frozen candidate. Fresh receipts are kept in the current coordinator
outputs; historical counts are not promoted here.

The mounted route authenticates a shared API key and accepts the operator
name from the request body; matching it to stored approval does not prove
an authenticated per-operator principal. Actual per-operator credentials,
file-durable authority commissioning, server account/risk/native integration,
verified protection support and production unknown-outcome/restart evidence
remain explicit holds. Fake journal/store failures and mounted fake broker
workflows prove engineering behavior only. No live service, order or cancel
has been commissioned by this work.
