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

## Verification (this session)
- F02 reproduction: grid ignores supplied gamma (3,810,251 both runs) vs panel 100,000/9,900,000 — confirmed before fix; vendor engine now changes output (new tests).
- `python3 qc/audit/check_silent_excepts.py` → OK (258 files).
- New tests: `backend/tests/solstice/test_solstice_foundation.py` (14 checks: metric invariants, put-sign trap, exact clock, timestamp preservation, vendor-gamma sensitivity, unknown states, gross ratio, order contracts).
- Targeted suites: 91 passed (`test_heatseeker_routes velocity`, `test_heatseeker`, `test_gex_dual`, `test_public_api_integration`, `test_public_api_partial_data`, solstice foundation).
- Frontend heatseeker: 23 suites / 87 tests passed (incl. updated scope-preservation test).
- Inherited failures (present on main, unchanged by this branch): `/api/public/order` route exists (data-router order test), ChainCache + bars/technical fixtures with stale hardcoded dates/symbols, dash_ui plotly collection errors. Documented, not silenced.

## Next
- T04–T07: wire vendor engine into build_heatmap behind flag + wall registry integration + full snapshot route; replay recorder (T09) start capture.
- Rerun full backend pytest + frontend jest + CI at this head before merge; reconcile with origin/main drift.
- No merges, deploys, credential changes, or live trades performed.
