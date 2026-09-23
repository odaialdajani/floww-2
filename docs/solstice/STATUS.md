# Solstice STATUS — T00 baseline + T01–T03 foundation (living receipt)

Base: local `main` 5db4971a (includes open-PR #11 retry-404 work) stacked on
origin/main 61d17917276b92913ff64339f9824b8a19d9b36a (12 Sep 2026).
Work branch: `solstice/t00-t03-foundation` (from local main; includes #11, avoids duplicating it).
Correction to earlier receipt line: base is NOT bare origin/main — local main already contains #11.
Environment: macOS `/Users/nav/Documents/GitHub/floww-2` (CLAUDE.md Windows canonical path does not apply here; reconciled).

## Branch / PR disposition (rechecked 23 Sep 2026)
- main = 61d1791 (origin/main). Local feat/ticker-az-paging (2f7013f1) stacks #11→#12, ahead of main.
- 262 branches visible locally; 12 PRs on GitHub: 7 merged (#1,#2,#6,#7,#8,#9,#10), 5 open (#3,#4,#5,#11,#12).
- #3 `fix/skylit-panel-bugs`: broad divergent history + conflict — do NOT bulk merge; extract narrow fixes only.
- #4 `fetched_at` propagation: receipt/build time, NOT source freshness — preserve received_at separately, missing source time stays null.
- #5 stale-indicator work: coordinate quality semantics; not Solstice fix evidence.
- #11/#12: 404 NO_OPTIONS vs retry + paged A–Z scroller (stacked) — reuse, avoid duplication.
- `work/reconcile-ai-ui-20260911` (if fetched): selection identity + visible-map scope overlap T06/T21; reuse concepts, not redesign.

## CI baseline
- `lint` workflow on PR #12 head: Ruff F841 + full Ruff PASS; `check_silent_excepts.py` FAILED with 16 unjustified sites (incl. public_api_adapter).
- This branch: silent-except gate now PASSES (258 files) via meaningful logging + unknown-state preservation (no empty justifications).
- Full pytest + frontend suites: not yet rerun at this SHA (T00 blocker carried; targeted solstice tests below pass).

## Foundation delivered (this branch)
- T01: `backend/domain/exposure_metrics.py` (gex.v2 registry: gross/net/delta-weighted/volume) + Decimal identity + invariants.
- T02: Public parser preserves bid/ask/last timestamps + greeks_source + oi_effective_date; OSI supports adjusted roots; `resolve_public_instrument_type` (SPX family); adapter uses exact T clock + explicit chain type + per-contract exposure_basis; missing OI/volume stay unknown.
- T03: `solstice_time.py` exact actual/365 clock (AM/PM aware, floor only while tradable, expired→None); `gex_core` vendor-gamma canonical engine (`compute_gex_*_vendor` — supplied-gamma change MUST change output); max-pain corrected to call/put intrinsic (prior total-OI×distance retained only as compat, never as target).
- F07: scalp mode emits real 2D volume-weighted grid (was empty); payload carries exposure_basis + quality (setup/execution eligibility).
- F04: payload no longer hardcodes data_fallback=False; source_received_at preserved; stale_age_s is build age only.
- F08–F10: lifecycle/velocity unknown-first; tap_prob=None uncalibrated; heatseeker classify_nodes requires observed OI trend.
- F13/F14: dual-GEX no OI→volume substitution; gross denominator + minimum support + unknown states; legacy net/net kept as `activity_ratio_legacy_net`.
- F15–F19: frontend stable zero-anchor scale (locked/fixed/relative label), scope-keyed change badges with reset, largest-cell vs strongest-wall labeling, expand preserves scope + explicit widen + query-keyed guards + snapshot-linked selection.
- F25–F27: cancel→DELETE with empty-body tolerance; multileg placement `type` (preflight keeps `orderType`); Order gains openClose/averagePrice/bracket linkage/legs; added replace/search/v2/strategy-quote wrappers (disarmed, mocked in tests).
- AI harness: `solstice_evidence.py` packet + validator + deterministic fallback; `useSolsticeSnapshot` single-flight hook; WallInspector + ScenarioStrip (deterministic first, AI optional).

## Slice 2 — read-only desk completion (same branch, 23 Sep 2026)
- T04: per-cell delta/activity grids from the same snapshot (`metrics.grids`);
  frontend Raw/Δ-wtd/Activity switch with raw-locked walls, scope-keyed badges.
- T09: DuckDB v2 recorder (7 tables, idempotent digests) + available-at replay
  + session manifest; `save_snapshot` typed `ts` + `ts_iso` compat; velocity
  mixed-type ordering hardened; rolling route requires 2+ full-chain histories.
- T05/T07: wall registry wired into payload (`metrics.walls/nearest_walls`);
  interaction state machine + two-sided scenarios; inspector resolves selection
  by identity from the current snapshot.
- T08: moneyness/OI-change/relative-volume enrichment (no inference).
- T10: scout already side-first; counts attached to payload + `/scout` route.
- T11: first-passage labels, walk-forward splits, baselines registry.
- T12: disarmed exec tests (UUID idempotency, pending≠canceled, bracket
  linkage, data-adapter has no order method). No live calls; still disarmed.
- T13: ROLLOUT.md (shadow/SLO/rollback, read-only first).
- T14: METHODOLOGY.md label→formula map + replay guide; control-bar popover.
- T15: corrected regime/roots contract (sign never permits direction).
- T16: five-pattern numeric library + distant-node relevance (no intent).
- T17: Vanna/Vomma-separated views + expiry-removal scenario.
- T18/T26: 27-operation registry + unknown-first measured manifest.
- T19/T20: session permissions/playbooks + whole-contract sizing/stress.
- T21/T22: evidence packet + 8-case adversarial corpus runner + docs.
- T23: status strip + replay strip + guided manifest.
- T24/T29: ticket harness + longevity/migration/ownership + retention.
- T25: missed-opportunity causal ledger + ≤3-question review.
- T28: Q1/Q2/Q3 frozen protocols + sizing ablation.
- F05/F19: App.js single-flight (generation IDs + abort) + freshness-derived
  `heatLive` replaces `!!livespot` at both Skylit mounts (surgical).
- Routes: `/api/solstice/*` (snapshot, evidence, walls, regime, patterns,
  vanna, scout, capability, replay, manifest) — all read-only, no writes.

## Slice 3 — gap close + full-suite baseline (same branch, 23 Sep 2026)
- F20: gex_aggregator VEX documented as VOMMA with `vomma_surface` alias +
  `weight_basis` tag (short-DTE volume fillna opt-in, never silent); grid VEX
  stays vanna. PLAN.md added (T00–T29 map).
- T02/T09/T27: solstice_provenance.py — Greek pair classification
  (vendor/vendor eligible; mixed/unknown blocked), volume-retraction quarantine
  (1240→1180 = VOLUME_REBASE, never negative flow), sequential change
  attribution (spot→IV/time→OI + residual/tol).
- T27 canaries: 13 mutation tests (put sign, vendor gamma, timestamp
  laundering, volume-as-OI, cross-symbol refusal, missing-source confidence,
  same-observation fill, Decimal/multiplier, distances, float claim).
- F23: full-universe off-screen landmarks (`metrics.offscreen_landmarks`);
  grid cells keyboard-accessible (tabIndex/role/Enter/Space/aria-label).
- Fixture repairs (expired hardcoded dates → future-relative + symbols):
  test_public_advantage, test_public_budget_debit — 5 fixed.
- Full backend suite: 5182+ passed; remaining 40 failed + 27 errors ALL in
  untouched files (verified identical on stashed tree): llm/chart_emb/
  autoformer/patchtst/charm_vec/microstructure/ml_realtime/verify_runner/
  regime_thresholds/sweep_replay-fixture-path/bars/chaincache/order-router/
  dash_ui(plotly missing)/yoptions. No new failures from this branch.
- Full frontend suite: 576 passed / 2 failed; the 2 failures (Sidebar,
  BlademapFlowView, AppShell suites) reproduce on stashed tree — inherited.

## Slice 4 — correctness sweep + parity + full baselines (same branch, 23 Sep 2026)
- Ruff clean on all branch files (E731/E702/B905/F401/F841/I001 fixed; CI pins
  0.15.22, local 0.15.14 — same rule bar). Silent-except gate OK (280 files).
- PARITY FIX: Rust `nodes.rs` max-pain still used old total-OI×distance while
  Python moved to call/put intrinsic → would have diverged wherever the
  extension is installed. Rust ported to intrinsic + `max_pain_basis` key in
  bindings; new Rust unit test + Python canary pin 90.0 (28+1 Rust tests pass
  under py3.12; py3.14 cannot build pyo3 0.22 — local runs use Python fallback
  by design). Vendor-gamma engine stays Python-only (BS-path parity unaffected).
- Recorder now stores strike rows + walls (`strikes_json`/`walls_json` with
  additive migration); replay returns them; new `compare_snapshots` +
  `/api/solstice/attribute/{ticker}` (coarse, history_unavailable <2 snaps).
- Registry alias `window_delta_weighted_volume_v1` (§28.3 name, same state).
- Inspector upgraded (§28.3): units/basis, call/put two-sided note, per-expiry
  contributions from same-snapshot grids, Δ/raw ratio, Δ provenance counts,
  OI-date coverage note.
- Commissioning: `scripts/solstice_commission.py` — 6/6 offline checks pass;
  account probes report BLOCKED (no PUBLIC_API_KEY, no approval) with exact list.
- Full backend suite: 5182+ passed; remaining 40F/27E all in untouched files,
  verified identical on stashed tree. Full frontend: 576/2, both inherited.
- Branch stacks open PR #11 (base local main 5db4971a); PR opened for review,
  NOT merged (needs separate authorization).
- PR #13 (solstice/t00-t03-foundation → main): OPEN, MERGEABLE; CI `ruff`
  check PASSED on the PR head (16s). Live full-suite CI beyond lint not
  inferred — see baselines above.
- Commissioning (COMMISSION.md, 23 Sep 2026, read-only, redacted): SPY path
  commissioned (live quote w/ timestamps, 32 expiries incl. 0DTE, chain shape,
  targeted Greeks, 252 bars, tick metadata); SPX/SPXW chain HTTP 400 on all
  shapes (quote works) → index chain gated; OI cadence/429/history/brackets
  explicitly unprobed with reasons. Live capture: SPY 684 contracts/2 walls,
  QQQ 724/126/4, replay verified, compare honestly unavailable.

## Slice 6 — verification hardening (branch solstice/sweep6-verify, 23 Sep 2026)
- Envelope bug fixed: tuple `or`-chaining always returned the first parse
  (breaking alternate keys); naive timestamps now UTC-normalized with an
  explicit `naive_assumed_utc` flag (mixed naive/aware no longer raises).
- Window Δvolume per strike in compare (rebase-quarantined); ReplayStrip
  "Compare last two" control (session change window; 1m/5m/15m honestly
  unavailable until intraday capture cadence exists).
- Vanna = dVega/dSpot finite-difference cross-check + vomma distinction test.
- Full-suite baselines unchanged (remaining failures verified pre-existing).

## Verification (slice 6)
- Solstice + envelope: 66 passed. Ruff + silent gate clean.
- Frontend heatseeker+slice: 24 suites / 94 passed.

## Slice 5 — missed-items sweep (branch solstice/sweep5-missed-items, 23 Sep 2026)
PR #14 (sweep5 → main): MERGED 23 Sep 2026.
- §8 grid gaps closed: strike-rail gross-concentration bars (no cancellation),
  expiry headers with exact date + days-left + column coverage, 0DTE column
  share of matrix gross. All client-side from the same snapshot.
- Tab-independent recording: opt-in `FLOWW_SOLSTICE_CAPTURE` scheduler
  (default OFF, 6-ticker cap, 60s floor, market-hours guard, paced, tested).
- SOURCES.md adoption register (28 texts + cheat sheet, duplicates noted).
- Registry carries docs base + review date (S12–S27 + pinned SDK).
- Reconciliation test: vendor rows = cells = aggregate net/gross + walls.
- Full-suite baselines unchanged (remaining failures verified pre-existing).

## Verification (slice 5)
- `backend/tests/solstice/`: 54 passed. Silent-except gate OK (280 files).
- Ruff clean on all touched files. Frontend grid/slice/dash: 17 passed.

## Next
- T04–T07: wire vendor engine into build_heatmap behind flag + wall registry integration + full snapshot route; replay recorder (T09) start capture.
- Rerun full backend pytest + frontend jest + CI at this head before merge; reconcile with origin/main drift.
- No merges, deploys, credential changes, or live trades performed.
