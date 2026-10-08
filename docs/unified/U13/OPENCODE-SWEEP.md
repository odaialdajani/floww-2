# U13 — budget/range sweep record (OpenCode takeover, 2026-10-08)

Lane: `work/host-opencode` (baseline `8194eca4` + own probes only).
No source edits. System interpreter; isolated stores/fakes throughout.

## Receipts (all re-run this pass, current snapshot)

- Read-budget slice: 27/27 (`test_dashboard_read_budget.py`, re-run).
- Budget services (`test_public_budget*`): 21/21 — incl. cold fan-out
  debit, warm zero-spend, concurrent same-key single envelope, and
  cancelled-broker-init slot release.
- Range seams + analytics: 19/19.
- Related suites + cancel/store faults: 52/52.
- Consumer digest identity (`RANGE_IDENTITY_MISMATCH` tamper refusal):
  green inside the 245 frontend run.
- Ruff clean on all four slice files (0.15.22 CI pin).

## Sweep judgment: verified, no repair required

Every U13-listed behavior (refusal/cancellation/error accounting,
per-key reservation, cold/warm fan-out, range grids, query/clock scoping,
digest tamper refusal, dashboard read classification) holds at this
snapshot. No RED counterexample was found across budget, range, related,
cancel-fault, and consumer-tamper surfaces — so no repair was manufactured.
The read-budget slice itself (Cline, reviewed ACCEPT) is the only recent
change in this area and is covered.

## Stated limits (not hidden)

- `tests/agent/test_read_budget.py` does not collect locally (missing
  `mongomock_motor` in this interpreter) — CI-covered; not claimed here.
- Live provider budgets and per-process account caps were not exercised
  with real providers (forbidden in checks); fake-provider accounting only.
- `:8002` preview still serves pre-slice code (429s live) — redeploy needs
  human authorization, unchanged by this record.
