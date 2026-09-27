# R8 Acceptance Ledger

Single source of truth for the R8 release claim. Generated from the evidence
recorded here, not from prose. Every row names the head it was verified at.

**Verified at:** `main @ 71f83625` (Merge PR #53 `fix/v3-budget-honesty`)
**Ledger written:** 2026-09-27
**Verifier:** Hermes, cold check against the local branch and the live app.

## Why this file exists

Revision 8 received a receipt that was self-contradictory: it described nine
commits while listing ten, named an endpoint (`16d3d714`) older than its own
head (`046a1357`), and shipped prose claiming completion next to a checklist
leaving `R7-06..09` open. Two artifacts made the claim unusable:

1. No single ledger. The completion claim and the checklist were generated
   separately and disagreed.
2. Screenshots pinned to a stale head. The previous `SHOTS.md` recorded head
   `36872db7`; at the time of writing the tree was 16 commits ahead of it.
   Screenshots from another head are not evidence of the current build.

This ledger is generated from one pass so those two failure modes cannot recur.

## Correction to the Revision 8 review

The Revision 8 review reported that `046a1357` was absent locally and that
`main` was `7fed6012`. Both were true *of the reviewer's checkout* and are
now false *of this tree*. R7 is merged: `046a1357` is an ancestor of `main`,
and R8 work has since landed across eleven R8-labeled commits, the last five
arriving via PRs #50, #51 and #52. R8 was therefore built on a real R7 base,
not on a hypothetical one.

## Evidence states

`pass` — the required evidence exists and was reproduced by the verifier.
`not_required` — the facet cannot apply to this row.
`pending` — the facet is applicable and has not been produced.
`blocked` — applicable, but an external precondition is missing.
`fail` — attempted and did not hold.

| # | Requirement | Implemented | Integrated | Acceptance-tested | Visually checked | Commissioned | Empirically validated |
|---|---|---|---|---|---|---|---|
| R8-01 | Frozen-fixture journey to a saved review | pass | pass | pass | not_required | not_required | not_required |
| R8-02 | Selected-wall brief (where / changed / price / watch / blocker) | pass | pass | pass | pass | not_required | not_required |
| R8-03 | Two-grid compare, coordinate-synced readout | pass | pass | pass | pass | not_required | not_required |
| R8-04 | Journal save survives restart, evidence-linked | pass | pass | pass | pass | not_required | not_required |
| R8-05 | Outcome lifecycle producer -> store -> closure -> consumer | pass | pass | pass | not_required | pass | not_required |
| R8-06 | Screenshots at current head | pass | pass | pass | pass | not_required | not_required |
| R8-07 | This receipt | pass | pass | pass | not_required | not_required | not_required |

`Empirically validated` is `not_required` for every row. No held-out real
session supports any R8 claim, and this release does not assert one. Synthetic
fixtures test behaviour, never profitability.

## Row detail

### R8-01 — frozen-fixture journey
Implemented and integrated: `backend/tests/solstice/test_r8_01_e2e_frozen_fixture.py`
drives the analytical path to a saved review from a frozen fixture.
Acceptance-tested: passes in the `backend/tests/solstice/` run (222 passed).

### R8-02 — selected-wall brief
`WallInspector.jsx` answers all five questions, confirmed by reading the
mounted DOM after a real cell click at `main@71f83625`:

- where — zone, gross/net, distance (`780–780 · gross $565.0M · net $533.8M`, `DISTANCE 8.65 (1.12%)`)
- changed — `CHANGED: first sighting of this wall` (honest, not fabricated)
- what price did — `INTERACTION: no interaction observed`, `TOUCHES: none`
- what to watch — `CONFIRM: acceptance above 780.0 fails; return and hold below`
- what blocks it — `DATA: usable, greek timestamp unknown` → `Readiness: Wait — GREEK_TIME_UNKNOWN`

The unknown states are the point. The panel reports a gap rather than filling it.

### R8-03 — compare mode
**Correction to an earlier claim in this session: I first reported compare mode
as absent, because I listed only `frontend/src/components/heatseeker/` and
filtered for a "compare" filename. It exists.** `SkylitDashboard.jsx` renders
the toggle (`skylit-compare-toggle`) and `WallInspector.jsx` renders the
`wall-compare-table` readout. Verified in-browser: after a cell click,
`[data-testid="wall-compare-table"]` count = 1. Both grids carry independent
scale and units labelling, and the readout is keyed on strike/expiry
coordinates rather than array index.

### R8-04 — journal durability
`routes/solstice_review.py` persists through a real DuckDB engine and refuses
to claim durability on the memory path (`transient_memory_fallback_not_allowed`).

**Gap found and closed by this ledger:** every pre-existing R8-04 test opened
`duckdb.connect(":memory:")`. An in-memory database cannot demonstrate
durability — it dies with the handle, so those tests only proved that two
calls in one process agree. The R8 brief requires reproducing a saved review
*after restart*. Added
`backend/tests/solstice/test_r8_04_restart_durability.py` (5 tests) using a real
on-disk file with an explicit `close()` before a fresh `connect()`.

One assertion in the first draft was wrong, not the code: it expected
`list_decisions` to raise on a closed handle. `list_decisions` fails *soft*
(`return []` plus a log line) — correct, since a journal read must never 500
the request path. The test now pins the real contract.

Mounted-path check, against a throwaway instance on `:8010` with
`API_SECRET_KEY` set (the running `:8000` has none):

```
POST /api/solstice/SPY/decisions/NOPE/review  -H 'X-API-Key: …'
  -> {"decision_id":"NOPE","state":"waiting","saved_at":"…","durability":"durable"}
POST … (no key)   -> 401 {"detail":"Invalid or missing API key"}
POST … (no key, :8000, no API_SECRET_KEY configured)
  -> 503 {"detail":"Authentication not configured. Set API_SECRET_KEY."}
```

The save path works and is correctly auth-gated. On the local `:8000` instance
the Save control no-ops, because mutating routes are *deliberately* disabled
when `API_SECRET_KEY` is unset, and the frontend `.catch()` swallows the 503
without claiming success. That is a local configuration gap, not a code defect.
Configured, the endpoint answers `"durability": "durable"`.

### R8-05 — outcome lifecycle
`test_r8_05_outcome_worker.py` and `test_r8_05_outcome_attach.py` pass. The
worker is **default-disabled** at the scheduler and stays that way; the brief
allows pending -> final to be tested with synthetic data and forbids shipping
a live background poller by default. Replay does not write. Restart catch-up
is covered.

### R8-06 — screenshots
**The previous shots were stale and have been recaptured.** `SHOTS.md` pinned
head `36872db7`, 16 commits behind. Recaptured at `main@71f83625` against the
running app via real Chromium (`playwright-core` 1.59.1, local Chrome binary),
headless, 1600x900 and 390x844.

Recaptured: `compare-desktop.png`, `inspector-desktop.png`, `single-narrow.png`,
plus two new ones — `r8-01-selected-wall.png` (the inspector element captured at
its natural 1089px height, so the `DATA` section is not cut off by a 900px fold)
and `r8-02-review-saved.png`.

Verified non-blank by unique-colour count (2,580–10,678; a reload loop or error
page yields near-uniform images) and by direct inspection. Dark styling, single
grid, palette, density, strike rail, expiry columns and controls are unchanged,
as the brief requires.

Note: five older captures (`solstice-desktop.png`, `prod-gex.png`,
`prod-vex.png`, `movers-populated.png`, `blend-inspector.png`) were moved to
`docs/solstice/r8-shots/older-heads/` on 2026-09-27. They are NOT evidence for
this head and must not be cited for any acceptance claim. They were kept rather
than deleted because `RECONCILIATION.md` cites `prod-gex`/`prod-vex` as the
live-pixel verification for PR #50.

## What this release does not claim

- No claim of predictive or economic value. No held-out real-session evidence
  backs any R8 row. `Empirically validated` is `not_required` throughout.
- A passing linter and green backend totals do not establish mounted behaviour.
  They are recorded, and they are not the argument.
- The 194-test figure from the R7 receipt was not independently certified and
  is not used here. Current measured count: 222 in `backend/tests/solstice/`.
- Live sessions are still needed before any outcome-rate or hit-rate claim.

## Reproduce

```
cd backend && .venv/bin/python -m pytest tests/solstice/ -q -m "not flaky_env"
cd backend && python3 -m ruff check .
cd docs/solstice  # SHOTS.md names the head
node capture-solstice.mjs   # needs playwright-core + a local Chrome binary
```

## Open items

1. ~~`SHOTS.md` cites a stale head and a nonexistent `RUN_STATE`~~ — RESOLVED
   2026-09-27: `r8-shots/SHOTS.md` rewritten to name `main@71f83625`, point at
   this ledger, and point at the capture command. The dangling `RUN_STATE`
   reference is gone.
2. ~~Older captures could be read as current~~ — RESOLVED 2026-09-27: moved to
   `r8-shots/older-heads/` with a README stating they are not evidence for this
   head. Re-shooting them remains optional.
3. `API_SECRET_KEY` is unset locally, so the in-browser Save control cannot
   round-trip until a key is configured for the local stack. Verified working
   with a key; not verified in the running `:8000` UI, which has none.
