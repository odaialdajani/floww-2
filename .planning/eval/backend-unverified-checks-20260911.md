# Backend checks not verified by the final full run

Reviewed 2026-09-11 against the reported final source 45e104e4 and current test files. Read-only investigation: no source changes, dependency installation, provider/model calls, orders, or new full test execution. Performed guarded collection only.

## Exact accounting

The final log `TEMP/floww-backend-final-2214.log` records 5486 passed, 70 skipped, 9 deselected, zero errors, 136 warnings, 425.57 seconds, coverage 67.52%. Command selected `tests/ -v --tb=short --cov=. -m "not flaky_env" -p tests.offline_network`. Its source/run metadata is `.planning/eval/backend-suite-20260911-2222.json`.

There are **66 skipped test nodes plus four collection-level module skips**, giving the reported 70. The collection skips suppress entire modules; 70 is not the number of individual unchecked assertions. Current guarded collection (`TEMP/floww-unverified-collection.log`) confirms the same four module reasons and 5561 collected nodes. Inverse-marker collection (`TEMP/floww-unverified-deselected.log`) pins the exact nine excluded nodes below. Skips and deselections are not passes. There was no pre-merge baseline execution in this review, so no finding is labeled preexisting or merge-caused without evidence.

## Skipped-node groups: 66

| Count | Tests | Cause and classification | Concrete next action |
|---:|---|---|---|
| 22 | services/ml/test_ship_models.py | SHIP-specific model/manifest glob finds no QQQ/TLT/DIA/IWM artifacts in backend/models. Verified no matching SHIP files in either backend/models or root models. Genuine missing approved-artifact evidence; not a Python/Torch import failure. | Locate authoritative released model/manifest pairs and their provenance. If none were approved, retain unavailable status; do not rename another model or manufacture a SHIP verdict just to run these tests. |
| 3 | services/test_ml_pipeline.py | Missing root models/SPY_meta_v2.0-regime.json; tests label this “meta quarantined by truth audit (feature/sample ratio).” Model/scaler loading tests passed, but metadata/prediction compatibility did not run. Quarantine rationale is a test assertion, not proof this exact metadata was correctly quarantined. | Reconcile actual model/scaler/metadata provenance and approved compatibility. Preserve quarantine until validated; do not copy unrelated metadata. |
| 11 | services/test_yoptions_fetcher.py | HAS_YOPTIONS false; yoptions absent. All tests already mock the network, but entire module is skipif-disabled. Production loader also disables this optional legacy fetch path on missing import. | Decide whether legacy fetcher is still supported; install the intended optional package or inject a scoped complete fake dependency for unit tests, then run all 11 with network guard. Do not route Public-only production to this feed to satisfy tests. |
| 4 | e2e/test_dashboard_visual.py | Python playwright and pixelmatch both absent; first dependency check skips before server launch. This is a desktop Dash dashboard check, not mobile. | Provide browser-test dependencies and Chromium in an isolated test environment, then audit child-server storage/network isolation before running. The guard in the pytest parent does not automatically protect a spawned server. Verify current /dashboard target and baseline validity before claiming relevant UI coverage. |
| 4 | services/research/test_clone_and_extract.py | Unconditional “Requires network access to GitHub for license check” skips. At least write_queue is entirely local. Other tests can replace license/size reads with fixed inputs. Fixable test coverage gap; contains concrete stale expectation below. | Remove unjustified skips with proper license/size boundary mocks and preserve approval-refusal checks. Update expectations only to the intended current queue contract. |
| 4 | test_analytics_vex_dex_vega.py | Missing data/github-repos/cloned/FlashAlpha-lab_gex-explained/data/sample_chain.csv. Synthetic calculator checks in same file passed, but external sample compatibility did not run. | Restore a licensed pinned source sample or provide an explicitly separate fixture test. Do not call a substitute fixture the original sample verification. |
| 8 | test_api.py | Unconditional integration-only skips on health, heatmap/modes/DTE, checklist, trinity, spot, multiple tickers. Reasons refer to live Mongo/yfinance/Polygon; several comments no longer describe the current Public-first implementation. | Add local boundary fixtures for shape/selection behavior and separate bounded real-provider acceptance. Preserve original per-endpoint assertions; live integration is not established by other unit passes. |
| 5 | test_heatseeker.py | Unconditional integration-only skips for SPY/QQQ/SPX heatmaps, trinity, movers. | Same approach: fixed provider/history/store inputs for route behavior; separate actual authorized data capture. Existing V2 route tests overlap but do not prove every skipped assertion. |
| 5 | test_kelly_replay.py | Hardcoded /Users/nav/dvt_backtest_v2.json absent; each case expects an actual 21-record historical run. Genuine missing original-data blocker compounded by machine-specific path. | Locate/version the authentic run and make its path portable. Keep synthetic unit arithmetic distinct; do not invent 21 historical results. |

## Four collection-level skips

| Module | Observed reason | Scope hidden / next action |
|---|---|---|
| services/test_agentfield_hub.py | agentfield package missing | 41 test function definitions hidden (not a pytest-expanded count). Tests use fake Agent/Router classes but deliberately import the real package to reuse its __path__ for submodule resolution. Install the intended optional package or make the fake package complete and scoped; removing importorskip alone will fail the later import. Existing global sys.modules/module binding replacement also needs restoration to avoid test pollution. |
| services/test_microstructure_property.py | hypothesis missing | Eight property-test functions hidden. Add the test dependency and execute guarded deterministic property tests; this does not require live data. |
| stateful/test_ingestion_state_machine.py | hypothesis missing | Generated state-machine case hidden. Even after installation, module has unconditional skip for “Async timing issues with mock db.” Fix async test coordination and exercise state transitions; dependency installation alone is insufficient. |
| test_dvt_backtest_byte_compat.py | machine-local dvt_backtest.py absent | Ten function definitions hidden (parameter expansion unknown). Imports depend on /Users/nav plus a machine-specific checkout. Need authentic reference implementation and portable import; canonical size-unit tests do not prove byte compatibility with absent code. |

Installed-package probes in the actual Python 3.11 environment confirm playwright, pixelmatch, hypothesis, agentfield and yoptions are all absent. These are observations, not authorization to install anything.

## Exact nine deselections

| Node | Assessment / next action |
|---|---|
| tests/routes/test_health.py::test_all_healthy | Already mocks Public key, DuckDB and websocket but not every status contributor. Freeze remaining breaker/health state, then remove environmental marker if deterministic. No provider request is needed for presence/status contract. |
| tests/routes/test_llm_endpoints.py::test_llm_analyze_trade_returns_200_or_503 | Real model endpoint is unmocked; accepts 200,422,503. Keep real model calls separately budgeted; add strict local success and unavailable/invalid-input cases with mocked model boundary. |
| tests/routes/test_llm_endpoints.py::test_llm_generate_briefing_returns_200_or_503 | Same; accepting 422 does not prove generation succeeded, and accepting 503 does not prove model wiring. |
| tests/services/test_flow_alerts.py::test_biz_dte_same_day_is_zero_and_skips_weekends | Uses date.today() and computed future expiry; fixable clock/calendar unit test. Pin dates including weekend/holiday and remove marker after guarded success. |
| tests/services/test_flow_desk.py::test_prior_alert_days_counts_distinct_prior_sessions | Uses date.today(), generated alerts and local fresh store; no live market prerequisite. Pin date and eligible alert inputs, verify expected prior-session counting, then remove marker. |
| tests/test_heatseeker_v2.py::test_heatmap_spy_day_grid | Excluded by inherited flaky_env marker despite newly deterministic offline inputs. It passed in the earlier six-file guarded run (113 total); not part of this final full-run pass count. Remove stale marker after confirming fixture scope. |
| tests/test_heatseeker_v2.py::test_heatmap_qqq_grid | Same existing separately verified fixture coverage. |
| tests/test_heatseeker_v2.py::test_trinity_day_all_populated | Same existing separately verified fixture coverage. |
| tests/test_heatseeker_v2.py::test_contract_drilldown_spy | Same existing separately verified fixture coverage. |

## Errors which weak assertions or skips could conceal

1. **Concrete stale queue expectation:** test_write_queue_payload_shape expects exactly generated_at/to_clone/skip_already/skip_unparseable/counts. Current pure local scripts/clone_and_extract.py::write_queue also emits skip_license and skip_size. The unconditional “network” skip masks this contract disagreement. Source inspection proves the mismatch; this review did not execute the skipped test or decide which behavior should change.
2. **Model smoke tests accept non-success:** two excluded LLM tests accept 422/503 and assert no successful answer shape or exact model call. A green smoke result would still not establish working analysis/generation. Add separate strict successes and intended error assertions.
3. **Probability check may do no check:** test_ship_models.py::test_prediction_proba_valid asserts probability shape only inside hasattr(model, "predict_proba"). If capability is required, assert it before calling; otherwise explicitly label unsupported case. Current artifacts are absent, so this is a latent weakness, not a witnessed incorrect model result.
4. **Browser startup failure is skipped:** desktop visual fixture catches all readiness errors, terminates its own child, then pytest.skip after timeout. Once dependencies exist, an actual broken server/import could still be counted as a skip. Expected setup should fail with captured child output; baseline creation also skips and must not be counted as visual validation.
5. **Degradation-conditioned assertions:** risk-neutral-density tests can skip when PDF/CDF/summary is empty; stochastic tests can skip when simulated samples are insufficient. None of these contributed to the observed 70 skips, so do not blame them for this run. They remain places where future numerical regressions could look unavailable unless valid-input tests require nonempty successful output.
6. **Guard limitation:** final successful session guard proves no intercepted external attempts in that test process. It does not prove real provider integration, protect all future subprocesses, or turn degraded responses into success. Earlier swallowed provider errors were surfaced by this guard and repaired; those already completed fixture repairs are not reopened here.

## Closure priorities

First close deterministic gaps: clone queue tests, mocked AgentField unit setup, Hypothesis/property+state-machine timing, calendar/health state, and stale V2 markers. Next restore authentic missing fixtures/model metadata only with provenance. Then run isolated desktop visual acceptance and separately authorized real-provider/model integration. The historical reference engine/data and approved SHIP models are genuine missing-evidence blockers if no authoritative copy is available. No additional paid model allowance can repair those omissions.

## Exact 66 skipped nodes from the final log

- `tests/e2e/test_dashboard_visual.py::TestDashboardVisual::test_heatseeker_tab_loads`
- `tests/e2e/test_dashboard_visual.py::TestDashboardVisual::test_heatseeker_tag_overlays_render`
- `tests/e2e/test_dashboard_visual.py::TestDashboardVisual::test_visual_regression_heatseeker`
- `tests/e2e/test_dashboard_visual.py::TestDashboardVisual::test_screenshot_determinism`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_model_loads[QQQ]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_model_loads[TLT]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_model_loads[DIA]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_model_loads[IWM]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_manifest_valid[QQQ]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_manifest_valid[TLT]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_manifest_valid[DIA]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_manifest_valid[IWM]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_prediction_shape[QQQ]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_prediction_shape[TLT]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_prediction_shape[DIA]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_prediction_shape[IWM]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_prediction_proba_valid[QQQ]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_prediction_proba_valid[TLT]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_prediction_proba_valid[DIA]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_prediction_proba_valid[IWM]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_dummy_input_deterministic[QQQ]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_dummy_input_deterministic[TLT]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_dummy_input_deterministic[DIA]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_dummy_input_deterministic[IWM]`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_qqq_rf_primary_ship`
- `tests/services/ml/test_ship_models.py::TestShipModelLoading::test_tlt_gbm_ship_quality`
- `tests/services/research/test_clone_and_extract.py::test_plan_clones_buckets`
- `tests/services/research/test_clone_and_extract.py::test_write_queue_payload_shape`
- `tests/services/research/test_clone_and_extract.py::test_main_dry_run_writes_queue_and_returns_zero`
- `tests/services/research/test_clone_and_extract.py::test_main_execute_without_yes_returns_3`
- `tests/services/test_ml_pipeline.py::TestModelArtifacts::test_meta_file_exists`
- `tests/services/test_ml_pipeline.py::TestModelArtifacts::test_meta_valid_json`
- `tests/services/test_ml_pipeline.py::TestModelArtifacts::test_model_predicts_valid_output`
- `tests/services/test_yoptions_fetcher.py::TestFetchOptionsChain::test_fetch_calls_returns_normalized_df`
- `tests/services/test_yoptions_fetcher.py::TestFetchOptionsChain::test_fetch_both_types`
- `tests/services/test_yoptions_fetcher.py::TestFetchOptionsChain::test_fetch_returns_empty_on_failure`
- `tests/services/test_yoptions_fetcher.py::TestFetchOptionsChain::test_fetch_saves_raw_json`
- `tests/services/test_yoptions_fetcher.py::TestFetchOptionsChain::test_greeks_present_in_result`
- `tests/services/test_yoptions_fetcher.py::TestFetchOptionsChain::test_all_tickers_configured`
- `tests/services/test_yoptions_fetcher.py::TestFetchOptionsChain::test_handles_yoptions_error_string`
- `tests/services/test_yoptions_fetcher.py::TestFetchAllChains::test_fetch_all_combines_results`
- `tests/services/test_yoptions_fetcher.py::TestFetchAllChains::test_fetch_all_returns_empty_on_total_failure`
- `tests/services/test_yoptions_fetcher.py::TestRetryLogic::test_retry_on_connection_error`
- `tests/services/test_yoptions_fetcher.py::TestRetryLogic::test_retry_exhaustion_returns_empty`
- `tests/test_analytics_vex_dex_vega.py::TestCalcVex::test_with_sample_chain`
- `tests/test_analytics_vex_dex_vega.py::TestSampleChainShape::test_vex_sample_chain`
- `tests/test_analytics_vex_dex_vega.py::TestSampleChainShape::test_dex_sample_chain`
- `tests/test_analytics_vex_dex_vega.py::TestSampleChainShape::test_vega_sample_chain`
- `tests/test_api.py::test_health`
- `tests/test_api.py::test_heatmap_spy`
- `tests/test_api.py::test_heatmap_modes`
- `tests/test_api.py::test_heatmap_dte_filter`
- `tests/test_api.py::test_daily_checklist_endpoint`
- `tests/test_api.py::test_trinity`
- `tests/test_api.py::test_spot_spy`
- `tests/test_api.py::test_multiple_tickers`
- `tests/test_heatseeker.py::test_heatmap_spy`
- `tests/test_heatseeker.py::test_heatmap_qqq`
- `tests/test_heatseeker.py::test_heatmap_spx`
- `tests/test_heatseeker.py::test_trinity`
- `tests/test_heatseeker.py::test_movers`
- `tests/test_kelly_replay.py::TestReplayAllStructure::test_real_dvt_backtest_v2_loads_cleanly`
- `tests/test_kelly_replay.py::TestReplayAllConsistency::test_full_kelly_filter_count_matches_per_record_filter`
- `tests/test_kelly_replay.py::TestReplayAllConsistency::test_avoided_loss_pnl_sums_correctly`
- `tests/test_kelly_replay.py::TestReplayAllConsistency::test_naive_2pct_aggregate_equals_sum_of_records`
- `tests/test_kelly_replay.py::TestReplayAllConsistency::test_scaling_factor_matches_baseline`

## Bounded repairs after the inventory (22:40 UTC)

The inventory above preserves the final2214 historical result; these subsequent changes have separate evidence and are not retroactively added to its pass count.

- Queue mismatch reproduced after removing only its false skip: TEMP/floww-clone-queue-red.log, 1 failed / 30 deselected. Repaired current seven-field/count expectations; all four clone-related skips removed, license/size reads mocked, actual route through plan/main retained, dry-run and missing-confirmation paths assert execute_plan not called.
- AgentField unit tests now load a private source copy while a temporary fake dependency exists only inside patch.dict; original dependency and production module identities are asserted restored immediately. No real package installation or lasting module/class rebinding. All 41 functions execute.
- Authorized test dependency installed via uv into backend/.venv Python 3.11: hypothesis 6.168.0 and its new dependency sortedcontainers 2.4.0, no unrelated upgrades. Both pinned in requirements-test.txt; existing CI test install line includes that file. The original missing-package observations above describe the prior run, not the current environment.
- Replaced the skipped state-machine test with 200 examples x 20 transitions over actual enqueue, oldest-drop, drain, start and stop. Private asyncio.Runner prevents async errors being swallowed. Mock storage records actual converted rows, including unique arrival IDs; invariants compare write order, queue bounds, enqueue/dequeue/drop/insert counts and error count. Removed fake token/connectivity actions that never affected the production component; those features are not claimed covered here.
- Eight existing microstructure property tests pass after installing Hypothesis. Removed silent import skip now that the dependency is declared. Strengthened GEX scaling test: unequal call/put OI ensures positive nonzero baseline, so the ratio assertion cannot be bypassed by exact cancellation.
- Guarded four-module verification without conftest: **81 passed, zero skipped, 1 warning, 3.31s**, TEMP/floww-unverified-restored-final.log. With normal conftest: **81 passed, zero skipped, 21 warnings, 4.80s**, TEMP/floww-unverified-restored-conftest.log. Both completed the offline guard with no blocked attempts. Ruff and diff whitespace checks passed. This is bounded verification, not a new full suite result.

### Newly reproduced production gap: failed batch loses accounting

A separate local probe constructed IngestionPipeline with Mock storage whose execute_write_bulk raises RuntimeError("controlled storage failure"), enqueued one SPY tick, then awaited _drain_and_flush. Actual metrics: enqueued=1, dequeued=1, dropped=0, ticks_inserted=0, errors=1, queue_size=0. The tick is neither queued, inserted nor counted as dropped. Current drain removes messages before the write and catches the exception without restoring/counting the failed batch. This probe used no external storage, provider, model or order calls.

The successful-storage state machine does not certify preservation under failed writes. Parent was notified for coordinated production repair. Choice between explicit lost-row accounting and retaining/retrying requires care for partial multi-table writes; do not requeue already-successful inserts or silently duplicate rows. No production change was made by this subtask. This remains an open correctness issue at this handoff.

## Coordinated ingestion repair (22:46 UTC; awaiting independent review)

Parent authorized bounded production repair after the failed-write reproduction. New targeted tests first produced 11 failures and 1 pass (TEMP/floww-ingestion-failure-red.log), including failure-before-write, exception-after-recorded-write, cancellation during active write and duplicate start.

`unconfirmed_write_rows` now counts each batch whose storage call raised. Such rows are neither definitely dropped nor confirmed inserted; no automatic retry is attempted because the write may already have committed. Each of ticks/chains/lob/lob_depth is attempted independently, so an earlier failure does not suppress later types. Overflow retains the existing known-drop counter.

Stop now signals a wake event, waits for the active periodic write to finish and be accounted, then performs a serialized final drain. It no longer cancels an in-flight to_thread storage call. Lifecycle locking prevents duplicate start tasks; a flush lock prevents overlap between manual/final and periodic drains. Idle shutdown wakes promptly rather than waiting for the configured interval.

Tests exercise all four failure positions before and after a simulated recorded write, all-table failure, exact successful/overflow counts, no retry, continuation of later batches, stop during a blocked storage write followed by release/new arrival, duplicate start and idle-stop latency. Full bounded ingestion regression: **34 passed, zero skipped, 1 warning, 6.59s**, TEMP/floww-ingestion-regression-final.log; offline guard completed without blocked attempts. Ruff and diff whitespace checks passed after a style-only timeout-suppression adjustment. No full suite or real external data/storage calls were made. Source and focused tests were sent to parent for fresh independent review before final acceptance.

Limit: unconfirmed row counts intentionally do not determine whether the database committed; recovery/reconciliation is outside this bounded repair. Callers should stop producers before stopping ingestion; ongoing enqueue after shutdown remains outside the shutdown contract. External cancellation of internal private tasks is not a supported stop mechanism.

## Nine environmental exclusions restored (22:50 UTC)

Removed all nine flaky_env markers in the five assigned files. Health tests now isolate the retired breaker and institutional summary dependencies; timeout simulation raises an actual TimeoutError instead of creating an unawaited coroutine. Business-day counting uses four explicit dates across same-day/weekday/weekend boundaries. Prior-alert-day counting persists explicit valid alerts independently of score generation, with two rules per day, repeated upserts, current-day and outside-lookback rows; a fixed module clock proves exactly two prior distinct dates.

LLM route smoke tests were replaced with strict mocked contracts: exact successful response and forwarded arguments for analysis/generation, exact provider listing, import-unavailable 503, invalid-input 422 with no model calls, and service-value-error 400. The first restored run had three failed assertions because the new tests initially expected FastAPI's default detail body, while this application deliberately wraps HTTP errors as error/status_code/path. The corrected tests pin that existing exact application error contract; no production error behavior changed.

All five files together with normal conftest and offline guard: **74 passed, zero skipped, zero deselected, 21 warnings, 12.38s**, TEMP/floww-nine-exclusions-final.log. Ruff and diff checks passed. The four previously separately verified V2 cases now participate normally. This result supersedes the exclusion status of those nine cases for this bounded check only; the historical final2214 aggregate remains unchanged until a new full run.

## Eleven optional-feed unit skips restored (22:52 UTC)

Removing only the yoptions skip first reproduced the missing mock target (None.get_chain_greeks), TEMP/floww-yoptions-restored-red.log. Test-only repair now imports a private copy of the fetch module under a temporary fake optional dependency and immediately restores dependency/production-module identities. No retired provider was installed or enabled, and Public-only application policy is unchanged.

All 11 cases execute. Assertions now include exact call/put counts and forwarded arguments, output tickers across all configured symbols, actual saved raw-JSON values, retry attempt count and scheduled waits of 1/2 seconds (waiting mocked only). Real local fetch/conversion/retry code is exercised. Normal conftest with offline guard: **11 passed, zero skipped, 21 warnings, 0.57s**, TEMP/floww-yoptions-restored-final.log. Ruff and diff checks passed; no production failure was exposed by these cases.

## Thirteen legacy route skips restored - 23:14 UTC

Owned changes are limited to tests/test_api.py and tests/test_heatseeker.py. Removed all eight plus five unconditional skip decorators. Actual local heatmap/trinity/spot/checklist/movers routes now execute using the existing offline market fixture, isolated save/history boundaries and controlled health inputs. No real provider was installed or enabled; TestClient does not enter server lifespan. Mocked source data is explicitly local route-contract evidence, not real-provider acceptance.

The first restored two-file run reproduced three failures with36 passes: old health key dependencies versus current checks; an incomplete velocity fixture; and the actual missing richer daily-checklist response. Repaired the first two test issues without relaxing health: now checks exact healthy dependency set, Public key-presence result, retired-provider marker and zero connections. Movers uses six explicit rows and asserts exact first-five response plus one source call, replacing the old possibly-vacuous empty-list test. Trinity verifies all three requested tickers, exact controlled spots and nonempty calculations. Spot verifies exact source/value/time/status. DTE verifies a too-short window stays empty and a wider window includes exactly the nearest expiry. The first strengthened DTE assertion incorrectly expected an expiries member inside the deliberately empty grid; corrected to exact grid={} and expiries_used=[] after reproducing it. No original product assertion was deleted to hide that issue.

Final normal-conftest command used isolated test_floww_route_contracts_20260911 and tests.offline_network: **38 passed, 1 failed, zero skipped, zero deselected, 21 warnings, 17.14 seconds**, TEMP/floww-route13-final-2314.log. Guard completed with zero external attempts. Ruff and diff whitespace checks passed. Source is frozen; no full suite or production edit was performed by this subtask.

### Confirmed unresolved daily-checklist gap

The retained original test asserts regime, key_levels, strategy, risk_management, hedging_flow and strategy.recommended_strategies. Actual routes/analytics.py daily_checklist returns only ticker, spot, asof and regime with gex_regime/market_regime/iv_rank/skew. The original missing-field assertions remain unchanged and failing, with no skip or expected-failure marker.

Both parents of integration merge9d5e500a contain this same shortened route body, so this is pre-existing missing behavior, not an integration-conflict deletion. Actual retained desktop consumers establish the richer intent: frontend/src/components/MorningBriefing.jsx reads levels, recommendations and risk levels; PositionSizing.jsx reads distance-to-flip/walls; TradeEntry.jsx fills its form from walls.

Existing server.py _get_strategy_recommendation and _get_risk_levels helpers could supply legacy suggestions and projected stop/support/resistance values, and advanced_analytics.calc_gamma_flip_levels already produces hedging_flow. Wiring these would re-expose concrete premium-selling/long-volatility/account-risk suggestions. Parent explicitly declined that wider change during this bounded review. Therefore the failing contract remains visible; richer checklist behavior requires a separately chosen truthful implementation rather than placeholder objects or weakened tests.
