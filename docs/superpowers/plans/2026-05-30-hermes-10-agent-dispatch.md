# Hermes 10-Agent Parallel Dispatch — floww Round 12 (2026-05-30)

> **For the operator (Nav):** Launch 10 Hermes agents. Give EACH agent the shared
> **PREAMBLE** (section A) + its single **LANE** (H1…H10). One agent per lane. The
> lanes touch **disjoint files** and each commits to its **own branch** — so they
> cannot collide. The architect merges the branches afterward (section C).

---

## A. SHARED PREAMBLE — paste this into EVERY agent, above its lane

```
You are an autonomous coding agent in /Users/nav/Documents/GitHub/floww — the ONLY
floww clone; never create/use another. You are ONE of 10 parallel agents. Stay 100%
inside your LANE's file list; touching another lane's files corrupts the run.

ISOLATION (critical — this is why you won't collide with the other 9):
1. At start: git fetch origin && git checkout -B <your branch name> origin/main
2. Work ONLY on your branch. Commit there. Push there: git push -u origin <branch>.
3. NEVER push, rebase, or commit to `main`. The architect merges branches later.
4. Commit with PATHSPEC only: git commit -m "..." -- <your files>. NEVER git add -A/-a.

ENV & TESTS:
- Python: backend/.venv/bin/python3 . Run: cd backend && .venv/bin/python3 -m pytest
  <your test paths> -q -p no:cacheprovider . NEVER run tests/chaos or tests/e2e.
- Your OWNED source files must end the run ruff-clean: cd backend && .venv/bin/ruff
  check <your files> → 0 errors.

HONESTY (non-negotiable):
- NEVER claim a test passes / ruff is clean / a grep holds without pasting the REAL
  output line. Fabricating completion is the worst outcome and is caught instantly.
- If a fix needs a file outside your lane, a FORBIDDEN file, or a judgment call
  (risk thresholds, model promotion, business behavior) — STOP that item, note it in
  one line, move on. Do not guess, do not reach into another lane.

FORBIDDEN for everyone (escalate to Nav, don't touch):
  backend/services/ml/inference.py, backend/services/dash_ui.py, MODEL_REGISTRY,
  any backend/models/* artifact, backend/tests/conftest.py, services/risk/gate.py +
  tests/services/risk/test_gate.py (architect already did these), frontend/.env,
  frontend/package.json.

LOOP per item: edit → run YOUR tests (paste output) → ruff YOUR files → pathspec
commit to YOUR branch → push branch → next. At the end, append a short honest status
(branch name, commits, real pytest line) to docs/ROUND12_HERMES_STATUS.md on your
branch (the architect will reconcile the file on merge).
```

> **Note for the operator:** main may be mid-flight from DeepSeek. Before launching,
> confirm it at least collects: `cd backend && .venv/bin/python3 -m pytest --co -q 2>&1 | tail -1`.
> If it errors, ping the architect to stabilize main first — branches inherit its state.

---

## B. THE 10 LANES (disjoint file ownership)

### H1 — App core & lifespan  ·  branch `agent/h1-server`
**Owns:** `backend/server.py`, `backend/routes/admin.py`, `backend/tests/routes/test_admin_auth_extra.py`, `backend/tests/routes/test_analytics_validation.py`
**Goal:** (1) Migrate the deprecated `@app.on_event("startup"/"shutdown")` handlers (~6) to a single FastAPI `lifespan` async context manager. (2) Fix `validation_exception_handler` to return the standard `{"detail":[{"loc",...}]}` shape so `test_analytics_validation` finds the field name. (3) Make `test_admin_auth_extra` pass (correct path to `/api/performance/stats`, set the admin key in the test or assert the documented 503). 
**DoD:** full suite still COLLECTS (you own server.py — if it breaks, everything breaks; verify `pytest --co -q`), those 2 test files pass, server.py ruff-clean.

### H2 — Analytics degraded contract  ·  branch `agent/h2-analytics`
**Owns:** `backend/routes/analytics.py`, `backend/services/cache_router.py`, `backend/services/fetch_coordinator.py`, `backend/tests/routes/test_fallback_responses.py`
**Goal:** Unify `degraded_response` (cache_router.py:121) to a SUPERSET dict incl. `status:"degraded", reason, stale:True, retry_after, asof` plus existing keys; ensure `/movers` & `/history` degraded paths include `results:[]` / `snapshots:[],count:0`. Fix the stale `/api/analytics/...` paths in the test to `/api/...`.
**DoD:** `test_fallback_responses` 4 pass; `pytest tests/test_api.py -q` still green; these files ruff-clean.

### H3 — ML trainers & leakage  ·  branch `agent/h3-ml-train`
**Owns:** ALL `backend/scripts/train_*.py`, `backend/scripts/setup_gflows_data.py`, `backend/scripts/upsert_features_to_mongo.py`, new `backend/tests/services/ml/test_no_preprocessing_leakage.py`
**Goal:** In `train_real_data_ml.py` + `train_gex_models.py`, fit `StandardScaler` + feature-selection INSIDE each walk-forward fold (train-only), not on full X. Replace the fake `acc/(1-acc)` "sharpe" with real `services.ml.gate.compute_trading_sharpe` or raw fold OOS accuracy. Add a leakage-guard test. Finish the F841 lint in these scripts and FIX any syntax errors left from prior edits (verify every file imports: `.venv/bin/python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('backend/scripts/train_*.py')]"`).
**DoD:** grep shows scaler.fit only inside the fold loop (paste it); no `acc / (1` proxy; leakage test passes; all train_*.py parse + ruff-clean. **Commit NO models, do NOT touch MODEL_REGISTRY.**

### H4 — ML services (non-frozen)  ·  branch `agent/h4-ml-svc`
**Owns:** `backend/services/ml_ensemble.py`, `ml_realtime_features.py`, `services/ml/registry.py`, `services/ml/gate.py`, `services/ml/health_monitor.py`, `services/gex_inference.py`, `backend/routes/ml_outcome_api.py`, `backend/routes/ml_api.py`, `backend/routes/ml_dashboard.py`, `backend/routes/ml_predict_api.py` + their tests under `tests/services/ml/` and `tests/routes/test_ml*`
**Goal:** Fix the `np.exp` overflow in `ml_ensemble.py:46,65` (clip the exponent). Add the `logger.warning` to the silent `except Exception: pass` in `ml_outcome_api.py:~296`. Collapse the duplicate `/api/ml/*` routes (ml_dashboard shadowed by ml_api/ml_predict_api) to one owner. Add type hints + coverage.
**DoD:** ml tests pass, no overflow warning, one owner per `/api/ml/*` path, files ruff-clean. (inference.py stays FROZEN.)

### H5 — Microstructure & options math  ·  branch `agent/h5-micro`
**Owns:** `backend/services/node_lifecycle.py`, `microstructure_math.py`, `hawkes_process.py`, `gex_aggregator.py`, `greek_aggregator.py`, `iv_skew_analyzer.py`, `oi_change_detector.py`, `numba_greeks.py`, `bs_calculator.py`, `cpr_calculator.py`, `gex_history.py` + their tests
**Goal:** Full type hints on greek_aggregator/iv_skew_analyzer/oi_change_detector (run `mypy` on them, exit 0; install mypy in venv if needed). Raise coverage for node lifecycle + microstructure math. Fix any failing tests in this set.
**DoD:** mypy clean on the 3 named modules, owned tests green, files ruff-clean.

### H6 — Data providers & resilience  ·  branch `agent/h6-data`
**Owns:** `backend/services/data_providers.py`, `data_fallback.py`, `alpha_vantage_client.py`, `request_deduplicator.py`, `rate_limit_tracker.py`, `circuit_breaker.py`, `duckdb_engine.py`, `databento_oi.py`, `yfinance_fetcher.py`, `yoptions_fetcher.py`, `backend/routes/data_providers.py` + their tests
**Goal:** Raise coverage on the resilience primitives (circuit breaker states, dedup, retry/timeout, fallback chain). Verify the AlphaVantage circuit breaker is actually wired into the provider. Finish F841 lint in these files.
**DoD:** owned tests green, resilience paths covered, files ruff-clean.

### H7 — Alerts, monitoring & observability  ·  branch `agent/h7-alerts`
**Owns:** `backend/services/alert_engine.py`, `alert_dispatcher.py`, `credit_monitor.py`, `meta_observability.py`, `observability.py`, `backend/routes/alerts.py`, `backend/routes/alerts_api.py`, `backend/routes/health.py` + their tests
**Goal:** Raise coverage for alert detection/dispatch + credit monitor. Verify `/api/alerts/*` and `/api/health` contracts. Ensure no duplicate `/api/alerts/status` shadowing.
**DoD:** owned tests green, alerts/health endpoints verified, files ruff-clean.

### H8 — Execution & paper trading  ·  branch `agent/h8-exec`
**Owns:** `backend/services/execution_engine.py`, `paper_broker.py`, `paper_trader.py`, `position_sizing.py`, `order_router.py`, `fill_monitor.py`, `position_reconciler.py`, `live_trading_switch.py`, `replay_engine.py`, `backend/routes/replay.py`, `backend/routes/live_trading.py` + their tests, `backend/tests/perf/test_p99_latency.py`
**Goal:** Make `test_p99_latency::test_fill_monitor_record_latency` robust (p99 over N runs / realistic budget — do NOT skip). Add `logger.warning` to the silent `except` in `replay.py:~65`. Coverage for execution + position sizing. **FORBIDDEN: risk/gate.py (done).**
**DoD:** perf test stable, owned tests green, files ruff-clean.

### H9 — Retail flow, sentiment & semantic  ·  branch `agent/h9-flow`
**Owns:** `backend/services/retail_flow_graph.py`, `retail_flow_score.py`, `retail_flow_signal.py`, `semantic_search.py`, `services/backtest/retail_flow_signal.py`, `vpin_engine.py`, `services/vpin_cdf.py`, `bvc_classification.py`, `flowseeker.py`, `routes/vpin.py`, `routes/flowseeker.py` + their tests
**Goal:** Raise coverage for retail-flow scoring + VPIN + semantic search. Finish F841 lint here. (This is the subsystem the future Reddit-sentiment feed will plug into — leave clean seams.)
**DoD:** owned tests green, files ruff-clean.

### H10 — Docs, dead-code audit & frontend  ·  branch `agent/h10-hygiene`
**Owns:** `docs/ROUND9_FINAL_CLOSURE.md` (+ other `docs/*.md` with broken refs), `frontend/jest.config.js`, `frontend/babel.config.js`, `frontend/src/**` (component leak fixes only) — and a NEW `docs/ROUND12_DEAD_CODE_AUDIT.md`
**Goal:** (1) Fix doc-rot: correct citations to non-existent files in ROUND9_FINAL_CLOSURE (e.g. `backtest_engine.py`→`backtest.py`) by grepping the real symbols. (2) Make `npx jest --no-coverage` run without JSX/ESM errors (touch jest/babel config ONLY — NOT package.json). (3) Dead-code: AUDIT ONLY — for each candidate, grep callers=0, write the report; do NOT delete (architect sign-off required).
**DoD:** cited files exist (ls-verified), jest runs, dead-code report written. No backend code edits.

---

## C. INTEGRATION (architect, after agents finish)
1. For each branch in H1…H10 order: `git checkout main && git merge --no-ff agent/hN`, run the full suite, resolve any conflict (lanes are disjoint so conflicts should be near-zero), push main with the anti-skip gate.
2. Merge H1 (server.py) FIRST — it's the only cross-cutting file; everything else rebases cleanly on top.
3. Reconcile the 10 `ROUND12_HERMES_STATUS.md` fragments into one. Run the full suite once more; record the real pass/fail count.

## Self-review (operator): every lane has a unique branch + a disjoint file list + a pasted-output DoD. No file appears in two lanes. server.py is H1-only.
