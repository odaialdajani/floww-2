# Handoff: cost-envelope drift in the public-expiry fix — RESOLVED by Hermes

**Status: closed. Hermes resolved it while I was investigating. Nothing of
theirs was modified by me; this file records the diagnosis and the closure so
the claim is not re-litigated.**

## What landed

Two commits appeared on `spark/s0-s9-backend-completion` after my last commit
(`cdcbee46`, 15:08), from the concurrent Hermes session working in this
checkout:

- `8a3dbe3f` 17:10 `fix(public): a 1-expiry request must not be spent on an expired expiry`
- `3ee53fb8` 17:25 `test(public): clear FLOWW_PUBLIC_UNIVERSE so the catalog path is actually exercised`

All commits carry the same local git identity, so authorship does not
disambiguate; the timestamps relative to my last commit do. Hermes confirmed
these as theirs.

## The fix itself was correct and well evidenced

`8a3dbe3f` replaced `for exp in expiries[:max_expiries]` with a walk that
stops once `max_expiries` expiries are *accepted*. The old slice ran before
the per-contract expiry filter, so a vendor list led by an expired expiry
spent the whole 1-expiry window on a dead expiry and returned `None` — a real
503 from `/api/spot/{ticker}`. The commit carried a live before/after probe
and a route-level 503 → 200.

## The defect it briefly introduced: the cost envelope was no longer honest

`backend/services/public_api_adapter.py`

- line 438 pre-debits a **fixed** envelope: `acquire_n(2 + max_expiries, …)`
- the walk over the vendor list became **unbounded**

`max_expiries` then bounded accepted expiries rather than expiries
*attempted*, and nothing capped the attempts, so whenever leading vendor
expiries yielded no accepted contracts the actual provider calls exceeded the
debited amount — the pre-debit became an under-count, which is the failure
mode the shared-quota contract forbids.

Not hypothetical: that commit's own live observation was a vendor list led by
an already-expired expiry, exactly the condition that overruns the envelope.

### Reproduction (local, no credentials, no network)

```
$ cd backend && .venv/bin/python -m pytest tests/services/test_provider_cost_h2.py -q
FAILED …::test_4_then_8_total_is_16_on_distinct_keys
AssertionError: expected 16 cold calls ((2+4)+(2+8)), got 18
```

The 2 extra calls were exactly the 2 expired-expiry skips. Measured directly
against the existing fixture (8 vendor expiries, only 6 still live):

```
N=4: calls=8 declared=6  (2 skips to collect 4 accepted)
N=8: calls=10 declared=10
```

- 5 passed at `origin/main` in a detached worktree, with and without
  `backend/.env`.
- Reverting every Spark production change in place still failed, and
  `git log origin/main..HEAD -- backend/services/public_api_adapter.py`
  named `8a3dbe3f` as the only commit touching it. The Spark work was
  exonerated before anything was concluded.

## Resolution

Hermes fixed it in the working tree while I was diagnosing: a declared
`MAX_EXPIRY_SKIPS = 3` with `max_attempts = min(len(expiries),
max_expiries + MAX_EXPIRY_SKIPS)` and the walk sliced to
`expiries[:max_attempts]`. Verified:

- `test_provider_cost_h2.py` → 5 passed
- `test_provider_cost_h2.py + test_public_expiry_coverage.py + test_public_advantage.py` → 61 passed
- `ruff check services/public_api_adapter.py` → clean
- Direct probe: with 1 / 3 / 10 / 25 dead leading expiries and
  `max_expiries=1`, chain calls are 2 / 4 / 4 / 4 — capped at
  `1 + MAX_EXPIRY_SKIPS`, never unbounded.

So the envelope is now a bounded, declared function of `max_expiries`:
`2 + max_expiries` contracted, at most `+ MAX_EXPIRY_SKIPS` when skipping
dead expiries. The 503 fix survives (a 1-expiry request still returns the
next live expiry) and the shared quota can no longer be overrun silently.

I had not yet made any edit to those files when this was resolved; the
diagnosis, the reproduction and the mechanism are what this file preserves.

