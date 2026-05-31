# Hermes 10-Agent Parallel Dispatch v2 — floww Round 12 (BIGGER)

> v2 = same isolation model (disjoint files + branch-per-agent) but each lane is now a
> multi-hour WORKSTREAM (4-7 concrete tasks), not a single fix. Give each agent the
> PREAMBLE + its lane. Architect merges branches (H1 first). Operator: Nav.

---

## A. SHARED PREAMBLE — paste above EVERY agent's lane

```
You are 1 of 10 parallel autonomous coding agents in /Users/nav/Documents/GitHub/floww
(the ONLY clone — never make another). Stay 100% inside your LANE's file list.

ISOLATION (why you won't collide with the other 9):
- Start: git fetch origin && git checkout -B <your-branch> origin/main
- Work ONLY on your branch; push only it: git push -u origin <your-branch>. NEVER touch main.
- PATHSPEC commits only: git commit -m "..." -- <your files>. NEVER git add -A / -a.
- Commit after EVERY task (small commits). Push your branch after each.

ENV/TESTS: backend/.venv/bin/python3 only. cd backend && .venv/bin/python3 -m pytest
<paths> -q -p no:cacheprovider. NEVER run tests/chaos or tests/e2e. Mongo is up.
Your owned files must end ruff-clean: .venv/bin/ruff check <files> -> 0.

HONESTY (the only metric): never claim a test passes / ruff clean / grep holds without
pasting the REAL output line. Fabrication is the worst outcome — instantly caught by
re-running. If something needs a file outside your lane, a FORBIDDEN file, or a judgment
call (risk thresholds, model promotion, business behavior): STOP it, note one line, move on.

FORBIDDEN (everyone): services/ml/inference.py, services/dash_ui.py, MODEL_REGISTRY,
backend/models/*, tests/conftest.py, services/risk/gate.py + its test, frontend/.env,
frontend/package.json. Don't `git push origin main` ever.

PACING: you have hours. Do EVERY task in your lane, top to bottom. If you finish, do the
STRETCH item. Append honest per-task status (real pytest lines) to a file named
ROUND12_STATUS_<your-branch>.md on your branch.
```

---

## B. LANES (disjoint files; each a full workstream)

### H1 — App core & lifespan · `agent/h1-server`
Files: `backend/server.py`, `routes/admin.py`, `tests/routes/test_admin_auth_extra.py`, `tests/routes/test_analytics_validation.py`, new `tests/test_server_lifespan.py`
1. Replace ALL `@app.on_event("startup"/"shutdown")` (~6) with one `@asynccontextmanager async def lifespan(app)` passed to `FastAPI(lifespan=...)`. Preserve every startup/shutdown action (DuckDB, schedulers, streamer, task cancellation).
2. `pytest --co -q` MUST still collect (you own server.py — a break here breaks all 10 lanes). Paste it.
3. Fix `validation_exception_handler` to return standard `{"detail":[{"loc",...,"msg","type"}]}` so field names surface; make `test_analytics_validation` pass.
4. Fix `test_admin_auth_extra` (correct `/api/performance/stats` path + set admin key in-test, or assert the documented 503).
5. Write `test_server_lifespan.py` asserting the app starts/stops cleanly via TestClient context.
6. ruff-clean server.py + admin.py.
STRETCH: add a `/api/health/ready` + `/api/health/live` split. DoD: collection clean, 3 test files green, server ruff-clean.

### H2 — Analytics degraded contract · `agent/h2-analytics`
Files: `routes/analytics.py`, `services/cache_router.py`, `services/fetch_coordinator.py`, `tests/routes/test_fallback_responses.py`, new `tests/routes/test_analytics_degraded_contract.py`
1. Make `degraded_response` a SUPERSET: `{status:"degraded", reason, stale:True, retry_after, asof, ...existing}`. Unify the 4 impls (cache_router + fetch_coordinator) to one canonical helper.
2. Ensure `/movers`,`/history` degraded paths add `results:[]` / `snapshots:[],count:0`.
3. Fix stale `/api/analytics/...` -> `/api/...` paths in `test_fallback_responses`; make all 4 pass.
4. Write `test_analytics_degraded_contract.py` pinning the canonical shape for every analytics route (loop the routes, force the error, assert the 5 keys).
5. Verify `pytest tests/test_api.py -q` still green (shared routes). ruff-clean the 3 files.
STRETCH: add a `retry_after` backoff that grows with consecutive failures. DoD: fallback 4 + new contract tests green.

### H3 — ML trainers & leakage · `agent/h3-ml-train`
Files: ALL `backend/scripts/train_*.py`, `scripts/setup_gflows_data.py`, `scripts/upsert_features_to_mongo.py`, new `tests/services/ml/test_no_preprocessing_leakage.py`
1. FIRST: verify every script parses — `.venv/bin/python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('backend/scripts/*.py')]"` — fix any SyntaxError from prior edits. Paste it clean.
2. In `train_real_data_ml.py` + `train_gex_models.py`: fit StandardScaler + feature-selection INSIDE each walk-forward fold (train-only), not on full X.
3. Grep-prove it: scaler `.fit`/`.fit_transform` only inside the fold loop. Paste the grep.
4. Replace `acc/(1-acc)` "sharpe" with real `services.ml.gate.compute_trading_sharpe` or raw fold OOS accuracy; grep shows no `/ (1` proxy left.
5. Write `test_no_preprocessing_leakage.py`: fails on full-series fit, passes on per-fold.
6. Finish F841/F541 in all scripts; ruff-clean.
**Commit NO models; do NOT touch MODEL_REGISTRY.** STRETCH: add a `--dry-run` that prints fold OOS accuracy without writing artifacts. DoD: all scripts parse + ruff-clean, leakage test green, greps pasted.

### H4 — ML services & ml routes · `agent/h4-ml-svc`
Files: `services/ml_ensemble.py`, `ml_realtime_features.py`, `services/ml/registry.py`, `services/ml/gate.py`, `services/ml/health_monitor.py`, `services/gex_inference.py`, `routes/ml_api.py`, `routes/ml_dashboard.py`, `routes/ml_predict_api.py`, `routes/ml_outcome_api.py`, tests under `tests/services/ml/` + `tests/routes/test_ml*`
1. Clip the `np.exp` overflow in `ml_ensemble.py:46,65` (e.g. `np.clip(z,-500,500)`); add a test feeding extreme scores.
2. Collapse duplicate `/api/ml/*` routes — `ml_dashboard` is fully shadowed by `ml_api`+`ml_predict_api`. Keep one owner per path; delete dead duplicates; verify each path 200s.
3. Add `logger.warning` to silent `except Exception: pass` in `ml_outcome_api.py:~296`.
4. Type-hint `ml_realtime_features.py` + `registry.py`; mypy them to 0.
5. Coverage for gate.py thresholds + registry load/save. ruff-clean.
STRETCH: a `/api/ml/health` aggregating per-ticker model status. DoD: ml tests green, one owner per ml path, no overflow.

### H5 — Microstructure & options math · `agent/h5-micro`
Files: `services/node_lifecycle.py`, `microstructure_math.py`, `hawkes_process.py`, `gex_aggregator.py`, `greek_aggregator.py`, `iv_skew_analyzer.py`, `oi_change_detector.py`, `numba_greeks.py`, `bs_calculator.py`, `cpr_calculator.py`, `gex_history.py` + their tests
1. Full type hints on greek_aggregator, iv_skew_analyzer, oi_change_detector; `mypy` them to 0 (install mypy in venv if needed).
2. Add edge-case tests for node lifecycle transitions (formed→active→tapped→expired) + Hawkes intensity at boundaries.
3. Property test: put-delta < 0 < call-delta across a strike grid (guards the bug architect just fixed).
4. Coverage for gex_aggregator + cpr_calculator. Finish F841 here; ruff-clean.
STRETCH: vectorize any per-row python loop you find in numba_greeks callers. DoD: mypy clean on 3 modules, owned tests green.

### H6 — Data providers & resilience · `agent/h6-data`
Files: `services/data_providers.py`, `data_fallback.py`, `alpha_vantage_client.py`, `request_deduplicator.py`, `rate_limit_tracker.py`, `circuit_breaker.py`, `duckdb_engine.py`, `databento_oi.py`, `yfinance_fetcher.py`, `yoptions_fetcher.py`, `routes/data_providers.py` + tests
1. Verify the AlphaVantage circuit breaker is actually wired into the provider call path (grep + test that N failures opens it).
2. Tests: dedup collapses N concurrent identical calls to 1; retry/timeout on duckdb writes; fallback chain order (AV→Polygon→Finnhub→yfinance).
3. Add a degraded path to `/api/data/{ticker}` mirroring H2's contract (coordinate shape only, don't edit analytics).
4. Type-hint rate_limit_tracker; mypy to 0. Finish F841; ruff-clean.
STRETCH: a `/api/data/providers/health` matrix. DoD: resilience tests green, files ruff-clean.

### H7 — Alerts, monitoring & observability · `agent/h7-alerts`
Files: `services/alert_engine.py`, `alert_dispatcher.py`, `credit_monitor.py`, `meta_observability.py`, `observability.py`, `routes/alerts.py`, `routes/alerts_api.py`, `routes/health.py` + tests
1. Coverage for every alert type in `detect_alerts` (gamma flip, squeeze, charm pinning, vanna regime, pc-oi, max-pain) — feed snapshot pairs, assert the right Alert.
2. Test alert dispatch dedup + the credit-monitor 429 rolling window.
3. Verify no duplicate `/api/alerts/status` (alerts vs alerts_api); collapse if found.
4. Add Prometheus counters for fired/suppressed alerts in observability. ruff-clean.
STRETCH: an `/api/alerts/history?ticker=` endpoint backed by the dispatcher cache. DoD: alert detection fully covered, endpoints verified.

### H8 — Execution & paper trading · `agent/h8-exec`
Files: `services/execution_engine.py`, `paper_broker.py`, `paper_trader.py`, `position_sizing.py`, `order_router.py`, `fill_monitor.py`, `position_reconciler.py`, `live_trading_switch.py`, `replay_engine.py`, `routes/replay.py`, `routes/live_trading.py`, `tests/perf/test_p99_latency.py` + tests. FORBIDDEN: risk/gate.py.
1. Make `test_p99_latency::test_fill_monitor_record_latency` robust: p99 over ≥100 runs with a realistic budget; do NOT skip.
2. Add `logger.warning` to silent `except` in `replay.py:~65`.
3. Tests: position-sizing math (Kelly/fixed-fractional bounds), order-router routing, paper-broker fill simulation, fill_monitor reconciliation.
4. Coverage for live_trading_switch state machine. ruff-clean.
STRETCH: a deterministic replay→paper_broker integration test. DoD: perf test stable, execution covered.

### H9 — Retail flow, sentiment & semantic · `agent/h9-flow`
Files: `services/retail_flow_graph.py`, `retail_flow_score.py`, `retail_flow_signal.py`, `services/backtest/retail_flow_signal.py`, `semantic_search.py`, `vpin_engine.py`, `services/vpin_cdf.py`, `bvc_classification.py`, `flowseeker.py`, `routes/vpin.py`, `routes/flowseeker.py` + tests
1. Coverage for retail-flow scoring (graph build, score thresholds, signal generation).
2. VPIN: test the CDF + bucket-volume bar construction + toxicity threshold.
3. BVC classification: test buy/sell volume split correctness.
4. Define a clean `SentimentSource` interface in retail_flow_score (a seam for the future Reddit feed) — abstract method + a stub impl; document it. Finish F841; ruff-clean.
STRETCH: a `RedditSentimentSource` skeleton (no network) implementing the interface, behind a feature flag. DoD: flow/VPIN covered, seam documented.

### H10 — Docs, dead-code audit & frontend · `agent/h10-hygiene`
Files: `docs/ROUND9_FINAL_CLOSURE.md` (+ docs with broken refs), `frontend/jest.config.js`, `frontend/babel.config.js`, `frontend/src/**` (leak fixes only), new `docs/ROUND12_DEAD_CODE_AUDIT.md`. NOT frontend/package.json, NOT backend code.
1. Doc-rot: fix every citation in ROUND9_FINAL_CLOSURE to a real file (grep the symbol; e.g. backtest_engine.py→backtest.py). ls-verify each cited path exists.
2. Frontend: make `npx jest --no-coverage` run without JSX/ESM errors (jest/babel config only). Paste the run.
3. Frontend leaks: apply the AbortController cleanup pattern to any `useEffect` fetch lacking cleanup (src components only).
4. Dead-code AUDIT only: for each candidate, grep callers=0, write `ROUND12_DEAD_CODE_AUDIT.md` with verdicts. DO NOT delete (architect sign-off).
STRETCH: a CI doc-link checker script. DoD: cited files exist, jest runs, audit written.

---

## C. INTEGRATION (architect)
Merge order H1→H2→…→H10 (H1's server.py first). `git merge --no-ff agent/hN`, run full suite between each, push main with anti-skip gate. Lanes are disjoint so conflicts ≈ 0. Reconcile the 10 `ROUND12_STATUS_*` files into one. Final: full suite + real pass/fail count.

Self-review: 10 unique branches, 10 disjoint file lists, every task has a pasted-output verification, server.py is H1-only, no file in two lanes.
