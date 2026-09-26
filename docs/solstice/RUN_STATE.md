# R8 RUN_STATE (continued from R7; same branch `solstice/r7`)

Model: Muse Spark (muse-spark-1.3-contributor-free). Base `7fed6012` (post-#47).
Head `21c52325` (R8 commit on top of R7 `046a1357`): **11 commits ahead** of
`origin/main` (10 R7 + 1 R8; receipt "ten vs nine" resolved from Git).
Packet: R8-00–07, NO merges authorized.
Env: macOS, python 3.14.6, node v24.14.1. Formula `gex.v2`.
Dirty (preserved, in progress): heatmap_history.py (reviews DDL move +
state_filter/review_state), test_r8_04_review_journal.py, App.css
(follow/review styles), SkylitDashboard.jsx + test (follow re-resolve,
review fetch), untracked test_r8_05_outcome_attach.py.
Unrelated preserved: kanban/BOTTLENECK_ALERTS.md (dirty, untouched);
PRs #3/#4/#5/#12 outside scope.

## Package ledger

- R8-00 reconciliation: acceptance-tested. Branch/head/base/ahead verified
  from Git (not prose). 3 solstice failures from repo root are CWD path
  artifacts — 207/207 pass from backend/. Dashboard 21/21, ruff + silent
  gate clean after 2-line fixes (I001 blank line, _parse_features debug log).
- R7 rows: reported → re-verified where R8 touches them; retained unchanged.

## Package ledger (implemented / integrated / acceptance-tested / blocked)

- R7-00 reconciliation: acceptance-tested. Head `16d3d714` on `solstice/r7`,
  9 commits ahead of `origin/main` `7fed6012`. Tree clean. Env ok.
- R7-01 Top Movers: acceptance-tested. `movers.v2` route (Public bars v2,
  completed-session percent, rank-then-limit, explicit loading/empty/partial/
  stale/error states) + App.js UI states + route→component test. Verified
  pct semantics, session dates, ranking, zero/missing denominator, provider
  failure, last-good cache, holiday/incomplete-session fixture.
- R7-02 delta/VEX contract: acceptance-tested. Canonical vex_net/gross_1volpt
  producers (local-bs-vanna.v1, signed vanna, coverage) wired into every
  display path as `data.grid.vex_grid` + `vex_meta`; grid vex view renders
  explicit unavailable (no blank-as-zero). Unknown option type rejected in
  all gex_core aggregations (registry already strict) with invalid_type
  accounting on grid dicts; adjusted quarantine unified. .99 helper fixed
  to ×0.01 with version note; tautological test rewritten as finite-difference
  oracle. Finite-difference VEX tests pass.
- R7-03 display/replay/readout: acceptance-tested. Recorded projection now
  persists full metrics (wall_window, nearest) + context
  (session/scout/regime/patterns/vanna/moneyness); replay restores them
  with dual snapshot_id/snapshotId spelling + complete/partial projection
  status (legacy records explicit, never reconstructed). Readout resolves
  the active viewMode+metric surface (missing = unavailable, never stale
  click value or GEX-under-VEX). Replay clicks cannot reach the live Trade
  handler (call boundary + armed-disarm on entering replay + disabled
  button); false eligibility with empty reasons shows a generic blocker.
  Also fixed a pre-existing broken replay-adapter test (stale fixture
  shape + assertion on an unused path).
- R7-04 compare workspace: acceptance-tested. Single (default, unchanged) /
  GEX+VEX toggle in the existing bar; two REAL grids over one
  snapshot/request (GEX left, VEX right; stacked <900px). Shared
  ticker/spot/scope/selection/live-replay; scroll synced by identity with
  loop guard; independent per-pane scales with a joint lock (cleared on
  scope change); VEX pane ignores weighting controls; missing VEX is
  explicit. Active pane owns the readout; inspector stays raw-anchored.
  Same desk inline and expanded.
- R7-05 review workflow: acceptance-tested. Inspector comparison string
  replaced by a small table (raw/Δ/VEX/session/window + basis/coverage);
  standalone window row removed (was duplicated). Observed interaction
  timeline + deterministic readiness (Observe/Wait/Confirmed for
  review/Invalidated) from the interaction record. Shortlist rows (3/side:
  OSI/expiry/delta/bid×ask/spread/ages) tagged in/out of the selected wall;
  no-candidate explains with reject counts. Advanced shows real per-expiry
  vanna + moneyness distributions (contract-vanna units labeled, no "view
  present"). Backend attaches shortlist rows; tick size honestly null.
- R7-06 series clocks + capability: acceptance-tested. last_trading_utc is
  now calendar-bound (clock.v2): expiry-day close (16:00/13:00 half-day),
  closed expiries fall back to last open close, AM SPX monthly uses the
  preceding open session 17:00 ET (settlement 09:30 never a deadline).
  resolve_series derives SPX/SPXW/EQUITY from root+expiry (third-Friday);
  adapter passes series into the clock and stores it on contracts.
  /capability gains a per-symbol matrix from recorded observations only
  (entitlement unobserved-by-default, no ticker substitution).
- R7-07 episode policy/pending-final: acceptance-tested. label_touch
  no_touch now requires gap-free coverage (pre-encounter gap > max_gap_s
  censors as OBSERVATION_GAP instead of confident no_touch). close_episodes
  re-processes censored/indeterminate outcomes when a longer path is
  supplied (path_end_t dedup); terminal target_hit/stop_hit stay idempotent.
  New episode_policy.py: research_barriers.v1 default symmetric barriers
  d=max(zone_half_width, 2*underlying_tick) with policy_unavailable when
  zone/tick unknown; setup_review.v1 read-only structural preview (no
  invented target/stop); episode_status_from_outcome maps labels to
  final_observed/pending lifecycle. Pending→final lifecycle tests pass;
  no-touch gap censored instead of confident.
- R7-08 study/visual acceptance: acceptance-tested. Visual design preserved
  (dark terminal, palette, density, typography, strike rail, expiry columns,
  zoom, scrolling — no redesign, no restored bands). Study/comprehension
  infrastructure repaired: 5 pre-existing test files had `backend/` path
  assumptions that break when pytest runs from `backend/`; fixed
  test_r5_e_red.py, test_r5_holes2_red.py, test_r4_p11_red.py,
  test_r6_5_red.py. Installed pandas-market-calendars to fix
  test_hole_gap_unknown_time_and_dst (calendar returned CALENDAR_UNKNOWN
  without the package). Frozen comprehension fixtures (comprehension_v1.json)
  now load cleanly; scorer rejects reversed/wrong-direction/"trade immediately"
  answers and reads both canonical + snake_quality formats. Interactive study
  script (scripts/solstice_comprehension.py) imports cleanly; participant run
  is external (human).
- R7-09 final gates/handoff: pending. Remaining: RUN_STATE brought current
  to match landed reality; final sweep (194/194 solstice tests pass, ruff
  clean); evidence-backed per-package status; concrete disabled commissioning
  package for R7-07 recorder (injected clock/provider, durable progress,
  catch-up, gaps, restart — code + synthetic tests done, activation external);
  limitations explicit.

## Before-fixtures (all reproduced 25 Sep 2026, main@7fed6012)

- VEX: `dollar_vex_per_1pct_vol_change(.2,100,100)` = 198000.0 (expect 2000.0).
  Fixed: now returns 2000.0 (×0.01, not ×0.99).
- Movers: `App.js` read `r.change`, route sent `pct`; `data[:limit]` unsorted;
  catch-noop + `…` forever. Fixed: route sends pct (correct), UI reads pct,
  rank-then-limit, states wired.
- `_display_surfaces` returned GEX surfaces only; grid `vex` view read
  `data.grid.vex_grid` (absent). Fixed: vex_grid produced + wired.

## Final verification

```
$ cd backend && .venv/bin/python -m pytest tests/solstice/ -q --tb=no -p no:cacheprovider
194 passed, 20 warnings in 4.40s

$ cd .. && python3 -m ruff check backend/ 2>&1 | tail -1
All checks passed!
```

## External blockers (do NOT block R7-00–08 engineering)

- SPX entitlement: code/schema/fixture support complete; empirical validation
  needs account access.
- Participant study: study infrastructure ready (scorer + frozen fixtures);
  interactive run (`scripts/solstice_comprehension.py`) requires human.
- Commissioning: R7-07 recorder code + synthetic tests done; activation
  external (auth, broker, persistent service).
- Browser pixels: mounted DOM/SSR + mocked HTTP used; pixel receipts external.
- Live sessions: code/engineering complete; empirical validation external.

## Changed files (R7 total, 9 commits on solstice/r7)

```
backend/routes/solstice.py                   (movers, capability symbols, replay)
backend/services/episode_policy.py           (R7-07 policy interface)
backend/services/public_api_adapter.py       (R7-01 bars, R7-06 series plumbing)
backend/services/public_capability.py        (R7-06 capability matrix)
backend/services/solstice_labels.py          (R7-07 lifecycle)
backend/services/solstice_time.py            (R7-06 clocks)
backend/services/gex_core.py                 (R7-02 VEX surface, population)
backend/tests/solstice/test_r4_p11_red.py    (R7-08 path fix)
backend/tests/solstice/test_r5_e_red.py      (R7-08 path fix)
backend/tests/solstice/test_r5_holes2_red.py (R7-08 path fix)
backend/tests/solstice/test_r6_5_red.py      (R7-08 path fix)
backend/tests/solstice/test_r7_6_red.py      (R7-06 clock tests)
backend/tests/solstice/test_r7_7_red.py      (R7-07 lifecycle tests)
frontend/src/components/heatseeker/          (R7-03/04/05 UI)
frontend/src/App.js                           (R7-01 movers wiring)
docs/solstice/RUN_STATE.md                   (this file)
kanban/BOTTLENECK_ALERTS.md                  (R7-07 status)
```

## Handoff (R7, superseded by R8 ledger below)

All R7-00–08 packages are implemented, integrated, and acceptance-tested against
the actual mounted path (backend calculators/DuckDB + React SSR/jsdom + mocked
HTTP). R7-09 closes by bringing this RUN_STATE current and recording the final
evidence above. No merges, deployments, credential changes, vendor messages,
or trades authorized. External validation items (SPX, participant study,
commissioning, browser pixels, live sessions) are explicit blockers, not
claiming failure.

## R8 ledger (branch solstice/r7, base 7fed6012, head 36872db7 + deltas)

R8-00 reconciliation: pass. 12 commits ahead of origin/main (10 R7 + R8
review-journal + this batch counted at commit). Earlier "ten vs nine"
resolved from Git; a parallel session landed 36872db7 mid-run — overlapping
areas verified identical-or-superset, no reverts, remaining deltas below
are unique (checked per file vs HEAD).
- Accepted repairs retained: R7 movers/delta/VEX/replay/compare/inspector/
  clocks/outcomes all present at HEAD; dirty tree matched HEAD on overlap.
- Test env note: 3 solstice failures from repo root are CWD path artifacts;
  207/207 pass from backend/ (also true at HEAD).

R8-01 analytical path: pass with 3 repairs. (a) market_bars→Public bars
seam was broken (wrong kwargs + wrong row shape — live movers 0/75 valid);
fixed + live-verified (full universe: 64/75 valid in 8s, abs-ranked TWLO
-7.96 first; 11 PROVIDER_UNAVAILABLE incl. one 401 — honest partial) +
regression test. Movers concurrency 8→4 (documented 10/s ceiling headroom). (b) Vendor
Greek timestamps don't exist → _display_quality reports GREEK_TIME_UNKNOWN
on the vendor path (eligibility unchanged) + unit test. (c) Movers declares
price_basis vendor-close-as-returned-unadjusted (splits unadjusted, honest).
Metric switch verified fetch-free (local state); delta grids in payload;
replay gen guards + compare observation times verified in Slice2 tests.

R8-02/R8-04 review loop: pass. Save review UI (Reviewed/Waiting/Skipped +
reason + frozen wall/metric/mode note) POSTs to the journal and refetches;
Next-to-review queue (unreviewed, newest-first, cap 5) jumps to replay via
a generation-guarded openRequest prop. Route rejects unknown states (422).
Alerts: engine alerts carry timestamps — strip now suppresses >24h
(withheld count shown) matching the backend's own window; missing
timestamps stay visible. Two real bugs fixed en route: review routes
registered AFTER include_router (never mounted — 404) and list_decisions
never selected r.state.

R8-03 compare gaps: pass. Manifest/compare/last-two requests carry the
same generation guards as snapshot opens; compare result names both
observation times (13:00→14:00 style receipt).

R8-05 worker/policy keys: pass. close_episodes expands list horizons and
keys idempotency on (decision, horizon, policy, label version); terminal =
any non-censored label (fixes duplicate-row rewrite); record_outcome +
attach handle policy versions and nested results. price_paths_v1 store +
outcome_close_tick worker (pure, restart-safe, synthetic-tested:
pending→final, policy rerun, duplicates, multi-horizon). Scheduler hook
exists but default-disabled (SOLSTICE_OUTCOME_WORKER=1); env default off
verified by test.

R8-06 browser + study: PARTIAL pass. Real Chromium capture works
(end-to-end recipe in docs/solstice/capture-solstice.mjs): single,
inspector, compare, narrow shots in docs/solstice/r8-shots/SHOTS.md
(live data = layout receipts). Two genuine product fixes from the
attempt: kill-switch SW reloaded 127.0.0.1 dev sessions in a loop
(loopback exclusion added), Movers used REACT_APP_API_URL instead of the
app config (now imports API). Study rubric hardened: gibberish/negated/
wrong-direction answers fail, stale fixture quality propagates unlaundered,
confidence recorded (6/6 study tests). Movers-populated shot added after
the bars-seam fix (MSFT +3.66%, 2/75 partial honest). Compute timeout
added (25s, keeps completed rows, COMPUTE_TIMEOUT reason) so throttled
cold scans answer partial fast; fanout 8→4 under the 10/s ceiling. No
before/after pair (no pre-R8 baseline shots exist).

Remaining external: SPX entitlement, participant study run, commissioning
activation, empirical live sessions. No merges performed.
