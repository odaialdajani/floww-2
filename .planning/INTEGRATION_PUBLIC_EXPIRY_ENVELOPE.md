# Handoff: cost-envelope drift in `8a3dbe3f` (foreign commit, not modified)

**Status: reported, not fixed. The commit is not mine and I did not alter it.**

## What landed

Two commits appeared on `spark/s0-s9-backend-completion` after my last commit
(`cdcbee46`, 15:08), from a concurrent session working in this checkout:

- `8a3dbe3f` 17:10 `fix(public): a 1-expiry request must not be spent on an expired expiry`
- `3ee53fb8` 17:25 `test(public): clear FLOWW_PUBLIC_UNIVERSE so the catalog path is actually exercised`

All commits carry the same local git identity, so authorship does not
disambiguate; the timestamps relative to my last commit do.

## The fix itself is correct and well evidenced

`8a3dbe3f` replaces `for exp in expiries[:max_expiries]` with a walk that
stops once `max_expiries` expiries are *accepted*. The old slice ran before
the per-contract expiry filter, so a vendor list led by an expired expiry
spent the whole 1-expiry window on a dead expiry and returned `None` — a real
503 from `/api/spot/{ticker}`. The commit carries a live before/after probe
and a route-level 503 → 200. That reasoning is sound and the bug was real.

## The defect it introduces: the cost envelope is no longer honest

`backend/services/public_api_adapter.py`

- line 438 pre-debits a **fixed** envelope: `acquire_n(2 + max_expiries, "api.public.com")`
- line 566 walks **unboundedly** over the vendor list:
  `for exp in expiries: if len(exp_dates) >= max_expiries: break`

`max_expiries` now bounds accepted expiries, not expiries *attempted*, and
nothing caps the attempts. So whenever the leading vendor expiries yield no
accepted contracts, actual provider calls exceed the debited amount. The
pre-debit becomes an under-count, which is the exact failure mode the
shared-quota contract forbids ("no exception may create unlimited budget").

This is not hypothetical: the commit's own live observation is that the
vendor returns 33 expiries led by an already-expired `2026-09-29`. Under
that observed condition, a `max_expiries=1` request makes
1 expirations + 1 dead chain + 1 live chain + 1 quote = **4** calls against a
3-call debit, every time.

## Reproduction (local, no credentials, no network)

```
$ cd backend && .venv/bin/python -m pytest tests/services/test_provider_cost_h2.py -q
FAILED tests/services/test_provider_cost_h2.py::test_4_then_8_total_is_16_on_distinct_keys
AssertionError: expected 16 cold calls ((2+4)+(2+8)), got 18
```

- 4 passed / 1 failed on the current branch; **5 passed** at `origin/main`
  (verified in a detached worktree with a copy of this venv, with and
  without `backend/.env`).
- Reverting every one of my own production changes in place still fails it,
  so the branch's Spark work is exonerated. `git log
  origin/main..HEAD -- backend/services/public_api_adapter.py` names
  `8a3dbe3f` as the only commit touching it.

## Options, in the order I would pick them

1. **Bound the attempts, keep the fix.** Walk at most
   `min(len(expiries), max_expiries + MAX_EXPIRY_SKIPS)` with
   `MAX_EXPIRY_SKIPS` a small declared constant (2 or 3). This preserves the
   503 fix, keeps the envelope a function of `max_expiries`, and makes the
   worst case explicit.
2. **Debit for the walk.** Enlarge the pre-debit to cover the worst case and
   release the unused remainder. Honest, but it taxes every request for a
   condition that is rare.
3. **Filter expired expiries before the fan-out.** Cheapest and most
   precise: the vendor list can be filtered by date against `now_utc` before
   any `get_option_chain_parsed` call, so dead expiries cost nothing. This is
   closest to the root cause the commit identified.
4. **Do nothing**, if the shared budget is known to be advisory. Then the
   `16` in that test should stop being described as an envelope, because it
   no longer is one.

Whatever is chosen, the test's expected number has to change from a constant
`2 + N` to something derived, because after any of these fixes the naive
constant is again wrong — in the other direction.

## Why I did not just fix it

The operating contract says to preserve foreign WIP and inspect it read-only
rather than stashing or reverting another session's work. `8a3dbe3f` fixes a
real production 503 with a live reproduction; rewriting it unilaterally would
destroy that evidence and could re-introduce the 503. This is an owner
decision, so it is handed over with the reproduction and the options.
