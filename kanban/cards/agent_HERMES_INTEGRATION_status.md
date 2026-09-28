[2026-09-28T00:00:00Z] HERMES_INTEGRATION :: H3 continued :: branch=feat/h3-missing-input-neutrality :: HEAD=32d1d6a3 (docs) / b51ee581 (code) :: base=d905c9d2
PR: #73 OPEN, mergeable, NOT merged (no in-session authorization to merge)

slice 1 -- absent evidence scored as neutral (5cba1d9d) + absent flow as measured zero (df3ddc10):
  _norm_conf/_norm_ml returned 0.5 for missing input while _norm_flow/_norm_opp returned 0.0,
  so an empty setup scored 17.5 (0.2*0.5+0.15*0.5) and outranked real-but-weak evidence.
  direction leaked into quality: identical evidence scored 85.75 bullish vs 60.25 bearish.
  Both now 74.25. flowseeker seeded flow={"conviction":0} so an absent feed reported ok.

slice 2 -- availability boundary unified across all scorers (b51ee581):
  _norm_flow({})                   was 0.0/"ok"       -> now 0.0/"missing"
  _norm_flow({'conviction':None})  0.0/"invalid"     -> 0.0/"missing"
  _norm_conf({'total':None})       0.0/"invalid"     -> 0.0/"missing"
  _norm_ml({}) / {'prediction':None} 0.0/"invalid"    -> 0.0/"missing"
  malformed payloads still "invalid"; real 0.0 still "ok" with 0.0 component.
  real producer: services.agent.confluence.score returns total=None +
  direction="insufficient_evidence" when uncovered -- an ABSENCE, which the
  ranker was reporting as "invalid" (i.e. producer emitted garbage).
  self-correction: I wrongly "simplified" all three empty-dict clauses as
  redundant; confluence's IS load-bearing because .get("total",0) defaults to
  0. Suite caught it, reverted, now commented. _norm_flow's clause IS redundant
  -- MUT7 survived its removal, so it was deleted rather than left untested.

scope: backend/services/conviction_rank.py (_norm_flow, _norm_conf, _norm_ml, rank_many blob guard)
       backend/routes/flowseeker.py (_universe_scan_conviction flow=None)
tests: backend/tests/services/test_conviction_missing_inputs.py (NEW, 19 tests, red-first)
       backend/tests/services/test_universe_scan_conviction.py (expectation 74.25/MED + symmetry assertion)
gates: tests/services+tests/routes 4555 passed / 33 skipped / 0 failed; ruff clean
       CI 36414866514 on b3874cc9: backend 6511 passed / 0 failed, frontend 918 passed, ruff pass
mutations: MUT1-MUT6, MUT8, MUT9 killed. MUT7 SURVIVED -> clause deleted.
live proof: real /api/heatseeker/node-confluence SPY (136 strikes considered)
       rows[0].confluence total=None direction=insufficient_evidence
       -> ranker now "missing" (was "invalid")

H2 refuted: advance_cursor rotates over the full universe; batches disjoint;
       n=0 and slice>n guarded. No code change made. Recorded so it is not
       re-audited as broken.

slice 3 -- recency surfaced, score deliberately unchanged (f76a5cee):
  asof was recorded and never evaluated, so a 6-month-old alert scored
  identically to a fresh one (both 31.5). Evidence now carries asof_status in
  {fresh,stale,future,unknown,unparseable} + asof_age_seconds; 7-day window
  matches the alert feed. SCORE UNCHANGED on purpose -- a decay curve is an
  unvalidated model of signal decay, the exact invented arithmetic this work
  removes. Test pins the diagnostic as inert.

slice 4 -- ^SPX classification corrected (13b952bc), DOCUMENTATION-ONLY:
  NON_OPTIONABLE had ^VIX/^SPX, asserting no options contract exists. Both are
  listed on Cboe and this deployment serves ^SPX: HTTP 200, spot 7743.41, 80
  strike rows. Split into NON_OPTIONABLE (BTC,ETH) + ENTITLEMENT_UNVERIFIED
  (^VIX,^SPX), sets asserted disjoint.
  SCOPE CORRECTION: neither symbol is in POPULAR_UNIVERSE (75 symbols, 0
  excluded in a real prefilter) so NO live behavior moved and exposure was
  always zero. Not the user-visible defect the packet implied. Recorded so it
  is not over-claimed.
  test_prefilter_orders_and_excludes used ^VIX as its NON_OPTIONABLE exemplar
  and asserted that reason -- it encoded the error. Exemplar now BTC; the
  behavior actually pinned (excluded stays excluded) unchanged and asserted.

slice 5 -- dte was folded into an expiry COUNT (91881cc2):
  max_expiries is a COUNT. build_heatmap also takes dte as a separate axis.
  scan_batch forwarded only the count, so NO tenor filter was ever applied and
  0DTE entered every row's metrics on an expiry day -- today 2026-09-28 is the
  chain's FIRST expiry. Live proof the axes are independent:
    dte=0&expiries=2 -> expiries_used=['2026-09-28']
    dte=1&expiries=3 -> expiries_used=['2026-09-28','2026-09-29']
  dte is now a scan_batch param + /universe/scan query param, defaulting to
  None (no filter = exactly current behavior). API docs regenerated (370 paths).
  This one DID affect every scan, unlike slice 4.
  a stub in test_scan_batch_builds_with_injected_fns needed the new signature
  (it did not accept dte, so scanned fell to 0); assertion unchanged.

gates: local tests/services+tests/routes 4564 passed / 33 skipped / 0 failed
       ruff clean; API docs check passes (370 paths)
mutations: MUT1-MUT6, MUT8, MUT9, MUT13, MUT14, MUT15 killed. MUT7 SURVIVED
       -> clause deleted rather than left untested.
live proof: /api/heatmap/%5ESPX -> HTTP 200, 124144 bytes, spot 7743.41, 80 rows
       /api/flowseeker/universe/scan pre-fix row: score 23.62 with
       confluence=0.5, ml=0.5 from no evidence -> same row fixed = 6.12
       (exactly the 17.5 phantom points removed)

STILL OPEN -- not claimed done:
  confluence/ml not yet wired into the route. Producer proven COMPATIBLE:
  node_confluence rows[].confluence = {total, direction, dimensions,
  coverage_weight, missing_input_policy, weights_version}, directly consumable
  by _norm_conf. Wiring is mechanical but is a behavior change to a live route
  and is NOT done.
  cross-batch leaderboard rank recomputation over one eligible population.
  H4-H7 untouched (persistence/events/history, Muse packet, H5-H7 evidence).
  OpenCode and Command Code have handed over nothing; three-track integration
  has NOT happened. No WallDeskSnapshot.v1 fixture exchanged yet.

preserved: kanban/BOTTLENECK_ALERTS.md unstaged/untouched (other agent).
live backend PID 46355 NOT restarted -- it still runs pre-fix code.
no-merge/no-deploy/no-restart/no-orders/no-credential-change: honored
