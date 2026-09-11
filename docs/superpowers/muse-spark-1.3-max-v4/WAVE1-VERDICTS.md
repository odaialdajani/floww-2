# Agent-1 review receipts — Wave 1, 2026-09-10 UTC

Exact-head verdicts. A head move voids the verdict for that PR.

## PR57 (agent2/wave1 @ 0b05229) — REWORK

Production delta in-lease and sound: momentum/volume inputs forwarded to
detectors (alert_engine.py +4/-4 param, routes/alerts.py strike-map and
momentum coercion). No threshold or scoring change.

Blocker is test isolation, not product behavior:

- CI full-suite: TestAlertsSummaryEmptyState::test_empty_state_returns_zeros
  fails, assert 17 == 0 (run 34429114597; 1 failed / 5064 passed).
- Local repro at detached 0b05229: the plumbing file plus the summary file
  together -> 1 failed, 10 passed; each file alone passes.
- Root cause: test_alert_plumbing.py is new in this PR and uses a
  module-scoped TestClient against the process-global engine; posted
  snapshots persist into the pre-existing empty-state test.

Repair condition: isolate the plumbing tests (function-scoped client with
engine reset, or unique tickers plus cleanup) so the pair passes; then
green CI at the new head. Verdict posted on the PR. Never weaken the
empty-state test.

## PR58 — APPROVED at a3fe6db (was: withheld), queued behind PR60

- Full payload reviewed: eventual reconciler (fail-open, journal close only
  on filled + positive price, key-gated POST /reconcile-close) plus
  read-only drift check (GET /position-journal-drift/{symbol}, never raises,
  never mutates). Matches EXEC-RECON-1 contract.
- Backend rerun at a3fe6db PASSED (11m41s) — flake classification confirmed;
  frontend + Ruff pass. Needs main-update + CI at merged head, then merge.
- The Agent-1 rerun of the stale head is void and recorded as such.

- At 1c5f886: backend red on
  test_anomaly_training.py::TestTraining::test_overfit_small_dataset
  (loss=0.0105). Local: passes 3/3 in isolation and 24/24 with the PR's own
  reconcile tests. Payload (routes/alpaca.py + reconcile test) cannot
  plausibly move ML overfit loss. Classified environmental flake.
- Owning lane pushed a3fe6db (drift-check endpoint + test, +177 lines) while
  Agent-1 was reproducing. Stale-run rerun by Agent-1 targets the old head
  and is meaningless for the gate; the lane's own run plus an Agent-1
  rerun of 34430761740 (accepted, pending at a3fe6db) will decide the new
  head. No merge until green CI exists at the current head.

## PR59 (agent2/data-contract @ 1c8a827) — APPROVED, integrating

Additive-only: event_envelope.py (123) + test (100), zero deletions. No
secrets, live orders, vendor SDK, or licensed rows (synthetic fixtures).
Exact-head CI green (backend 11m48s, frontend, Ruff). Branch updated to
main via a364128 (5 PR55 frontend files only, zero payload drift); CI
re-running. Merge iff green at a364128.

## PR59 (agent2/data-contract) — DONE, merged via 43fa666

## PR60 (agent2/eval-harness) — DONE, merged via 2c33de0

## PR61 (agent2/vex-parity @ dc01004) — APPROVED (payload), queued

Docstring-only production delta (bs_greeks.py +6, gex_vex_calculator.py +5)
documenting the GEX-parity display scale vs per-unit-sigma scale, plus a
64-line parity test. No behavior change; dual-scale convention preserved.
Exact-head CI green (backend 11m34s, frontend, Ruff). Needs main-update +
CI, then merge. Queued behind PR60.

## PR62 (agent2/composite-truth @ db77e38) — APPROVED, queued

4-line docstring correction (formula already 5-component in code at base
in both mirrored modules — verified) + 40-line parity guard. No behavior
change. Exact-head CI green (backend 12m37s, frontend, Ruff). Needs
main-update + CI, then merge. Queued behind PR61.

## PR63 — APPROVED at 2c63666 (was: withheld), queued last

Additive-only (2 new files, +187/-0). Backend rerun PASSED (12m42s) —
latency-budget flake classification confirmed; frontend + Ruff pass.
Needs main-update + CI at merged head, then merge.

## Integration order (disjoint payloads, branch protection needs fresh base)

## Integration order (disjoint payloads, branch protection needs fresh base)

PR57 already GC'd before this receipt landed; Agent 2 must publish the
main-merged head first. PR58 (withdrawn by tool state) is behind. PR59
merged via 43fa666, PR60 merged via 2c33de0. PR61/62/63 remote heads
already main-merged (verified hashes below); pushing them myself risks a
second-thread race with owning worktrees.

Next: publish the 57 main-merge outbound, then merge 57, 58, 61, 62, 63
in that order as each reaches clean exact-head CI.
