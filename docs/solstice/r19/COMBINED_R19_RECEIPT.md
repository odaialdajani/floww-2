# Round-19 combined candidate — status receipt (2026-10-05)

Coordinator: Hermes (GLM5.3) executing both lanes' completion under the
user's explicit takeover authorization ("check opencode work and if it not
working take over for both"). OpenCode lane idle since 06:37 EDT (d24fedce);
Cline session stalled 2026-10-04 — both lanes' obligations completed and
reviewed here.

## Composition (branch solstice/combined-r19-20261010 → PR107)

- `cda68973` merge: Cline r18 analytical lane (PR106 all-green at c39752bc)
- `73483f8e` merge: Spark r18 execution lane (S01–S14 ACCEPTED by independent
  Cline-lane review at 1f3b4258/a7609446/d24fedce; probes in packet references/)
- `2afa846a` backend I03: agent read-side digest → rga-content.v3
- `a55bd9ad` frontend I03: rangeReplay gate v3 + regenerated transport fixture
  + chronological-contract test fixes

The prior r19-integration branch carried STALE pre-C11/pre-S-series copies of
both producer domains; this candidate is composed at the CURRENT lane heads.

## Local verification on the combined tree

- Full backend: **7410 passed, 37 skipped, 0 failed** (7m09s)
- Full frontend: **130 suites / 1369 tests, 0 failed**
- ruff backend clean; silent-excepts OK (362); docs --check current 383 paths
  (admission router UNMOUNTED — no new live surface)
- protected71: **71/71** via git hash-object
- Executor files byte-identical to spark-r17 head; producer files byte-identical
  to cline lane head (structural diff verified)

## Hosted gates

At `a55bd9ad` (recorded as observed; single checks, no polling loops):
- frontend-build **PASS** 2m58s (failed at the pre-fix head with the v2 pin —
  the fix is verified hosted-green now)
- backend-tests / ruff / docker: pending at receipt time; the identical backend
  content already passed 20m18s at `2afa846a` (run 37359471322).

## Honest residuals (recorded, unchanged by this candidate)

1. Same-approval replay within ≤24h places a second order (verified probe) —
   single-use/lease→submit wiring stays REVIEW-PENDING (Nav/OpenCode).
2. POST /api/alpaca/order: authenticated (global middleware, verified 401) but
   without the admission stack; PAPER-only; predates the lanes (b1208083).
3. Unmounted /admission/decision accepts client ctx.now — bounded by
   evidence_grade=client-asserted which never admits (mount-note item 5).
4. Six NAV commissioning HOLDs stand. Activation OFF, policy UNSET, capture
   OFF, zero durable admitted records, INSUFFICIENT EVIDENCE.

Merge decision stays Nav's. No merge/deploy/activation performed.
