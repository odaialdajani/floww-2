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

**Second gap, found by mutation testing after this ledger was written.** The
restart tests above bind their own `duckdb.connect` to a temp file, so they
exercise the *store* — not the engine production actually uses. Replacing

```python
path = os.environ.get("DUCKDB_PATH", ":memory:") or ":memory:"
```

in `services/duckdb_engine.py::_open_shared_db` with `path = ":memory:"`, so the
configured path is ignored and every save silently becomes non-durable, left the
**full** backend suite green (5467 passed, 68 skipped). Nothing guarded the one
switch that decides whether a saved review survives a restart, which is exactly
the property this row claims.

Closed by `backend/tests/services/test_duckdb_engine_durability.py` (9 tests),
asserted behaviorally because `DuckDBEngine` exposes no `path` attribute — a
file on disk after `CHECKPOINT` is the only observable proof a path was honored.
9 pass unmutated; 4 fail with `DUCKDB_PATH` ignored. The unusable-path branch
also asserts the fallback is **logged**, because a silent durability downgrade is
the failure mode this release exists to prevent.

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
3. ~~`API_SECRET_KEY` unset locally blocks the in-browser Save~~ — RESOLVED
   2026-09-27. A real browser click on `skylit-review-save-waiting` was driven
   against a keyed, **file-backed** instance
   (`DUCKDB_PATH=…/r8-restart-proof.duckdb API_SECRET_KEY=… uvicorn :8012`),
   with only the review POST proxied to it. The app built the correct payload
   itself:

   ```
   POST /api/solstice/SPY/decisions/dec_ddfdbbf38732/review
   body {"state":"waiting","reason":"CONFIRMED_SETUP",
         "note":"wall w_a527fe306350 … metric raw view gex mode live"}
   -> 200 {"state":"waiting","durability":"durable"}
   ```

   The process was then **killed and restarted** against the same file, and the
   row read back by a separate process:

   ```
   REVIEWS SURVIVING THE RESTART: 1
   id=dec_ddfdbbf38732 state=waiting reason=CONFIRMED_SETUP
   reviewed_at=2026-09-27T06:44:31.262665+00:00
   ```

   This is the R8-04 acceptance clause satisfied over the real mounted path, not
   only in a unit test. Screenshot: `r8-shots/r8-03-review-roundtrip.png`.

   Two corrections to the earlier draft of this section, both now fixed:
   - The first keyed probe reported `durability: durable` from an instance with
     **no `DUCKDB_PATH`**, i.e. `:memory:`. That proved the auth gate and the
     request path, but NOT durability. Re-run with a real file.
   - `DUCKDB_PATH` defaults to `:memory:`, so a "durable" response from a
     default-configured instance is not evidence. Check the env before trusting
     the flag.

   Remaining local-config note, not a defect: the running `:8000` has no
   `API_SECRET_KEY`, so mutating routes there are deliberately disabled (503) and
   the frontend `.catch()` swallows it without claiming success. That is the
   auth design working.

## Post-audit corrections — 2026-09-27, head `bc47b8d5`

This ledger was written against `main@71f83625`. Three later defects were found
and fixed on `feat/node-confluence-overlay`. None of them touch the R8 rows
above, but they change what "verified" means for this branch, so they are
recorded here rather than left implicit.

**R8 rows are unaffected.** Re-verified on `bc47b8d5`:
`tests/solstice/` = 222 passed, `test_r8_04_restart_durability.py` = 5 passed.
The only frontend change since `71f83625` is `NodeConfluencePanel`, which none
of the screenshots capture. No re-capture required.

**Three WebSocket defects were live and green.** All shipped in this branch and
all had passing tests at the time:

1. `6aaa7dea` — `broadcast_signal` emitted `alert.to_dict()`, whose
   `type: "GAMMA_FLIP"` frame `AlertOverlay.js` discards. Six tests asserted a
   frame reached `send_json`; none checked the consumer.
2. `1c471b20` — `routes/alerts.py` uses `APIRouter(prefix="/api/alerts")`, so
   `@router.websocket("/ws/signals")` registered at `/api/alerts/ws/signals`,
   a path no client opens. The client's `/ws/signals` matched `server.py`'s
   greedy `/ws/{topic}` and landed in `websocket_streamer`. The channel had
   never delivered anything. Every test mounted `A.router` on a bare FastAPI
   app, which never includes `server.py`, so the prefix and ordering were
   invisible to all of them.
3. `bc47b8d5` — `websocket_gex`'s error branch sent its payload on a socket
   that had just failed, raising `LocalProtocolError` and logging every routine
   browser disconnect as a FATAL error.

**Method note.** The common cause is that a test on an isolated router cannot
see a defect that exists only on the assembled app, and an assertion on the
socket cannot see a defect in the consumer. Both blind spots produced green
suites. Assert route identity on the real `app`, and assert the consumer's
filter against a real frame.

**CI on `bc47b8d5`: success.** lint ✓, frontend-build ✓ (2m5s),
backend-tests ✓ (8m28s) — `5469 passed, 74 skipped, 9 deselected`. The six new
regression tests above are all confirmed PASSED in that run by name.

**Still not claimed.** PR #56 is open, not merged. `Empirically validated`
remains `not_required` on every row: these are behavioral and durability
results, never profitability.
