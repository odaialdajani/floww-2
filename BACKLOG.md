# BACKLOG.md — Confluence Decoder

> Synced with reality 2026-08-31 (post Phase 3/5 close + test fixes). Completed items
> moved to Done; resolved Discovered Issues annotated with their fix commits where known.
> Authoritative phase tracking now lives in `.planning/ROADMAP.md` (GSD).
> **Note:** This file is legacy. For exact test counts, run
> `cd backend && ./.venv313/Scripts/python.exe -m pytest -q` (backend — needs MongoDB on
> :27017) and `cd frontend && CI=true npx craco test --watchAll=false` (frontend).
> `backend/.venv313` (Python 3.13) is the only working backend interpreter on this box.
> GSD plan is `.planning/ROADMAP.md`; GSD state is `.planning/STATE.md`.

## Active Phase: A — Data Layer ✅ COMPLETE (2026-08-31)

- [x] Data layer schema and migrations (`ad77c90` — versioned DuckDB migrations)
- [x] Repository pattern for MongoDB access (`d54395c`, `280890f`)
- [x] Data collection service with proper error handling (`640773c`)
- [x] Data quality checks and validation (`a34980f` — /api/data-quality/{ticker})

## Pending (promote to numbered phases via ROADMAP.md Phase 6)

### B — Quant analytics ⚠️ PARTIALLY BUILT

Much of the quant infrastructure already exists — this phase is mostly consolidation + exposure.

**Already in codebase:**
- `services/signal_translator.py` — Hermes signals → trade intent
- `services/flow_alerts.py` + `services/flow_quality.py` — institutional alert tiering
- `services/trading_signals.py` — VPIN_HFT signal generator (BUY/SELL)
- `services/hmm_regime.py` — Gaussian HMM regime detection
- `services/volume_clock.py` — volume clock analytics
- `services/composite_flow_score.py` — composite flow scoring
- `flashalpha_client.py` — FlashAlpha sentiment API client
- `scripts/backtest_regime_filtered.py` — regime-filtered signal backtest

**Still needed:**
- [ ] Central quant registry — single entry point for all signal producers
- [x] Signal catalog endpoint — `/api/quant/signals` (`quant_signal_catalog()` in
      `routes/quant.py`) and `/api/quant/full` (`quant_full()` in
      `routes/quant_full.py`), both mounted in `backend/server.py`. Caveat: neither
      returns a per-signal health/status/active field — a producer that raises is
      logged at debug and silently dropped from the list (ROADMAP 6.4)
- [ ] Factor/z-score normalization layer across signal types
- [ ] Signal backtest reports per signal type (Sharpe, hit rate, max-DD)

### C — ML pipeline ✅ MOSTLY BUILT

The ML pipeline is already operational. This phase is about hardening + exposing.

**Already in codebase:**
- `services/ml/` — full pipeline: inference.py (frozen), features.py, gate.py, backtest.py,
  health_monitor.py, registry.py, retrain.py, dashboard.py, gex_inference.py, outcomes.py, quality.py
- `scripts/train_*.py` — multiple training scripts (v2.0, v5, regime-enhanced, balanced ensemble, etc.)
- `scripts/backtest_model.py` + `scripts/walkforward_backtest_spy.py` — walk-forward backtest
- 5 production GBM models (SPY/QQQ/DIA/IWM/TLT) in `models/`
- ADR-0001 model promotion policy enforced

**Still needed:**
- [ ] OOS-locked backtest harness (`scripts/backtest_oos.py` — referenced but not verified present)
- [ ] Rolling OOS validation automation (daily retrain already exists)
- [ ] Model performance dashboard endpoint (ML dashboard UI exists but API exposure TBD)

### D — Backtester ⚠️ PARTIALLY BUILT

Backtest engine exists but needs completion + integration with alerts/ML gating.

**Already in codebase:**
- `services/backtest/engine.py` — event-driven backtest engine (double-slippage bug **FIXED** in `be3b7f8` 2026-08-31; net_pnl now correctly includes slippage costs)
- `services/backtest/report.py`, `signals.py`, `retail_flow_signal.py`
- `scripts/backtest_model.py`, `scripts/walkforward_backtest_spy.py`, `scripts/backtest_regime_filtered.py`
- `scripts/kelly_sizing_replay.py` — sizing policy comparison
- `reports/backtest_2024.md`, `reports/backtest_retail_20260523.md`, `reports/kelly_calibration_report.md`

**Still needed:**
- [ ] Event-driven backtest with realistic slippage/commission for alert gating
- [ ] `/api/backtest/*` result-retrieval route — PARTIAL. `routes/backtest.py` exposes
      POST `/run`, `/is-oos`, `/walk-forward`, `/monte-carlo` (mounted in
      `backend/server.py` as `backtest_router`); there is no
      `/api/backtest/report/{ticker}` to read a stored report back
- [ ] Per-alert backtest reports (every alert in `alerts/definitions/` gets a Sharpe/hit-rate/DD report)

### E — Alert DSL ⚠️ PARTIALLY BUILT

Alert system is largely built — YAML definitions + dispatcher + tuner + API routes exist.

**Already in codebase:**
- `alerts/definitions/gex_alerts.yaml` — alert rule definitions
- `routes/alerts_api.py` + `routes/alerts.py` — alert CRUD + status endpoints
- `services/alert_dispatcher.py` — severity/timing dispatch
- `services/alert_tuner.py` — configurable FPR tuner
- `services/flow_alerts.py` — GEX flow alert evaluation
- `server.py` — `_alert_rules` + `_alert_history` in-memory stores + CRUD routes

**Still needed:**
- [ ] Persist alert rules to MongoDB (currently in-memory — lost on restart)
- [ ] Alert DSL as a proper config format (YAML is good; need validation + schema)
- [ ] Backtest gating: every alert needs a backtest report before "live" status
- [ ] Alert quality dashboard (`/api/alert-quality` or similar)

### F — Trading execution ⚠️ BUILT (paper trading)

Paper trading is operational. Live execution is out of scope pending ADR.

**Already in codebase:**
- `paper_trading.py` — $100K paper trading engine
- `services/flow_trade_bridge.py` — alert → trade bridge
- `services/paper_trade_engine.py` — paper trade execution
- `services/execution_engine.py` — order execution
- `scripts/build_order_from_signal.py` — signal → order

**Still needed:**
- [ ] Live execution ADR (separate future decision — paper trading only for now)
- [ ] Trade journal / P&L tracking (overlaps with Phase G)

### G — Portfolio & P&L ❌ NOT STARTED

**Still needed:**
- [ ] Portfolio state service (positions, P&L, exposure)
- [ ] `/api/portfolio/*` routes
- [ ] P&L attribution (by ticker, by signal, by strategy)
- [ ] Equity curve + drawdown tracking

### H — Frontend architecture ⚠️ PARTIALLY BUILT

Frontend is functional (280/280 tests passing). Architecture improvements are incremental.

**Already done:**
- 280 frontend tests across 44 suites, all passing — verified 2026-09-04 via
  `cd frontend && CI=true npx craco test --watchAll=false`
- Dead code removed: FlowseekerPro.jsx (482-line orphan) + FilterBar.jsx (imported only by dead file) deleted (`fe0e9ef`)
- DTE/time-frame filter chips added to Tidehunter Pro flow feed (`fe0e9ef`)
- FlowTicker console.error removed — SSR-safe (`b24fa7a`)

**Still needed:**
- [ ] App.js decomposition (1128 lines — needs architect sign-off)
- [ ] TanStack Query / server-state library (open since ROUND10)
- [ ] Frontend test coverage expansion (currently 280 across 44 suites — goal TBD)

### I — Observability & ops ⚠️ `/metrics` SHIPPED, coverage incomplete

The `/metrics` route exists in code. Remaining gaps are additional metric types, not
the endpoint itself.

**Already in codebase:**
- `prometheus_client` in requirements (installed)
- `services/ml/health_monitor.py` — model health monitoring (PSI drift, etc.)
- structlog JSON logging in production
- `/health` + `/api/health` endpoints
- `/metrics` route — `prometheus_metrics()` in `backend/server.py`
  (`@app.get("/metrics")`), returning `get_metrics_bytes()` from
  `services/observability.py`. Rendering that registry offline gives 34 metric
  families / 92 exposition lines at import time; a live scrape was not possible in
  this session (nothing listening on :8000, `curl` returned HTTP 000), so no
  live line count is claimed.
- Request latency histogram + error-rate counter — `metrics_middleware()` in
  `backend/server.py` records `floww_api_request_duration_seconds`
  (route/method/status) and `http_requests_total` (method/endpoint/status) for every
  route except `/metrics` itself.
- Provider counters — `floww_provider_calls_total` (success / failure / rate_limited)
  and `floww_yfinance_calls_total`, incremented in `backend/data_providers.py`.

**Still needed:**
- [ ] Provider counters for Public API and cvserver — `services/public_api.py` and
      `services/cvserver_client.py` import nothing from `services/observability.py`;
      `databento_provider.py` only publishes `floww_circuit_breaker_state`
- [ ] Explicit data-source fallback counter (today fallback must be inferred from
      `floww_provider_calls_total` by provider label)
- [ ] MongoDB connection pool metrics — no mongo/pool metric is defined at all
- [ ] Live scrape verification against a running backend

### J — Quality processes & ADRs ✅ MOSTLY DONE

**Already done:**
- ADR-0001 (model promotion policy) + ADR index at `docs/adr/`
- PR template at `.github/pull_request_template.md`
- Conventional commits documented in CLAUDE.md
- `.planning/codebase/` — 7 GSD codebase intel docs
- `.planning/LEARNINGS.md` — session learnings

**Still needed:**
- [ ] More ADRs (model quarantine, data source policy, deployment, etc.)
- [ ] Automated conventional commit enforcement (currently manual)
- [ ] Pre-commit hooks (ruff, mypy on non-frozen files)

### K — Wanted, not discarded (from the 2026-09-04 old-clone comparison)

The retired clone at `Desktop/floww` was compared against this repo. **No backend
function, class, or method was lost** and only one endpoint changed
(`/api/llm/generate-briefing` → `/api/llm/generate`, clean rename, test updated).
Everything below is either stranded work or a feature that was removed on purpose.
**All of it is wanted — none of it is discarded.** Artifacts and restore
instructions: `docs/salvage/README.md`.

**K1 — Stranded perf fixes ✅ LANDED (`a2f0532`, 2026-09-04)**
- [x] `routes/ml_predict_api.py` — mtime-keyed model/scaler cache + per-`model_type`
      prediction cache + legacy-binary ensemble branch + `n_hold` in the response
- [x] `routes/heatseeker_snapshots_api.py` — 3 DuckDB calls moved to `asyncio.to_thread`
- [x] `services/replay_engine.py` — 2× `self.db.query()` → `await self.db.query_async()`
- [x] `test_ml_predict_cache.py` + `test_ml_ensemble_labels.py` landed in
      `backend/tests/routes/` — 3 failed before the fix, 7 pass after; 104 passed
      across every test file referencing the three changed modules

**K2 — Removed UI we still want (all recoverable from this repo's git history)**
- [ ] Alpha Flow feed page (`3f339d5`) — backend `/api/alpha-flow` + `/api/alpha-flow/dates` are LIVE with no UI
- [ ] Daily Report page (`3f339d5`) — backend `/api/flow-digest` is LIVE with no UI
- [ ] Earnings page (`3f339d5`) — backend `/api/earnings`, `/api/earnings/week`, `/api/earnings/ticker/{t}/detail` are LIVE with no UI
- [ ] Ticker Analysis / deep-dive page (`3f339d5`) — backend `/api/deep-dive/{ticker}` is LIVE with no UI
- [ ] SPX GEX page (`3f339d5`) — backend `/api/gex/spx` is LIVE with no UI
- [ ] PaperTrade panel (`04615cc`) — `paper_trading.py` engine still live in backend
- [ ] MLPredictionsPanel + `hooks/useMLPredictions.js` (`04615cc`)
- [ ] RateLimitDashboard (`04615cc`)
- [ ] DTEFilter / ExpiryFilter (`04615cc`) — partly superseded by the Tidehunter DTE chips (`fe0e9ef`); reconcile before rebuilding
- [ ] VelocityGauge, NodesTable, FlowCarousel (`04615cc`) — VelocityGauge and NodesTable were re-inlined into App.js; FlowCarousel is not
- [ ] SwarmFrame + TurboQuantPanel (`489593b`) — TurboQuant backend routes are LIVE (`/api/turboquant/*`)
- [ ] `services/graph_updater.py`, `services/position_reconciler.py` (`6f83026`)

**K3 — Built but unreachable in the current UI**
- [ ] Steal Three preview — the one genuine orphan. Imported at `App.js:48` and rendered
      on `page === "steal-three"` (`App.js:1086-1087`), backend `routes/steal_three.py`
      is live, but there is no nav entry and the `?page=` whitelist in `App.js` (~line 506)
      lists only heatseeker / trinity / skylit / flowseeker-pro / journal / portfolio.
- [ ] `ticker-analysis` — no page exists at all. `App.js` mentions it once, in the
      ticker-strip visibility condition (`App.js:208`); there is no render block and no
      component. Rebuilding it means writing the page, not wiring one up.
- [ ] `flow-alerts` — no render block either. `App.js:191` sets `isLive = page === "flow-alerts"`,
      and `FlowAlertsPage` is defined at `App.js:327` but never mounted (nothing renders
      `<FlowAlertsPage />`; the only other reference is a source-grep assertion in
      `App.egress-invariant.test.js`). Dead component, not a routing gap.

**K5 — Found while clearing K1/K4 (2026-09-04)**
- [ ] `services/vpin_toxicity.py` — the label at the exact 0.30 boundary is
      numpy-version dependent. Same input (10 buckets of 130/70) returns
      LOW_TOXICITY on numpy 2.4.6 and MODERATE_TOXICITY on 2.5.2, with both
      reporting vpin == 0.3. The `flaky_env` marker on
      `test_label_thresholds_match_specification` is therefore **correct** — do
      not remove it (tried and reverted). Real fix: compare with a tolerance
      instead of a bare `>=` at each threshold.
- [ ] `server.py` — 4 unused imports (`provider_last_success_seconds_ago`,
      `provider_calls_total`, `get_metrics_bytes` at 1988-1990) + 1 unsorted
      import block at 2660. These are the only ruff findings left; the CI ruff
      gate cannot pass until they clear. Left alone — file is open in a
      concurrent session.
- [ ] `backend/.venv313` has drifted to fastapi 0.137.2 vs the pinned 0.110.1.
      `app.routes` returns `_IncludedRouter` wrappers there, which makes
      `test_steal_three_routes.py` report 4 false failures. Verify against
      `backend/.venv` (Python 3.11.15 + fastapi 0.110.1), which matches
      `requirements.txt` and `python:3.11-slim`. Consider deleting `.venv313`.
- [ ] `services/finnhub_api.py` + `finnhub_client.py` — both fail to import:
      `ModuleNotFoundError: No module named 'finnhub'`. The package is not in
      `requirements.txt`. Either add it or delete the two modules.
- [ ] **GitHub Actions has never run on this repo — 0 runs, ever.** It is a
      fork, and GitHub keeps workflows disabled on forks until enabled once in
      the Actions tab. Every gate discussed here is inert until Nav clicks it.

**K4 — Regressions to decide on**
- [ ] Sign-in gate removed with the AlphaPod teardown (`3f339d5`). `isAuthenticated`
      is destructured in `App.js:502` and never used, yet the header still renders
      email, tier badge and sign-out. Either restore the gate or strip the chrome.
      Backend still key-protects mutating methods (the `X-API-Key` auth middleware in
      `server.py`, "Auth middleware — checks X-API-Key header for mutating routes");
      reads are open.
- [x] DONE — the frontend `continue-on-error: true` mask is gone from
      `.github/workflows/ci.yml`. The "Tests" step under the frontend job now runs
      `npm test -- --watchAll=false` with `CI: true` and no `continue-on-error`, so the
      suite gates CI again; the only remaining occurrence of the phrase in that file is
      inside the comment explaining the removal. Verified 2026-09-04 in the working tree
      with `grep -n "continue-on-error" .github/workflows/ci.yml` (single hit, a comment
      line). Note: this change is uncommitted in the working tree, not yet on `main`.
- [ ] Backend CI runs `-m "not flaky_env"`, excluding 10 tests (health, LLM
      endpoints, flow alerts, flow desk, heatseeker v2). Fix or re-include.
- [ ] 48 unused npm dependencies still in `frontend/package.json` (full Radix set,
      lucide-react, react-hook-form, zod, date-fns, cmdk, embla, vaul, sonner…).
      Main chunk is 1.38 MB gzipped. **`package.json` is architect-frozen — needs Nav's approval.**
- [ ] `models/SPY_meta_v2.0-regime.json` stays quarantined by the truth audit
      (feature/sample ratio); `test_ml_pipeline.py::test_meta_file_exists` skips on it.
      Copy kept at `docs/salvage/` for the record.

## Done

- [x] Initial project setup
- [x] Security audit and fixes
- [x] ML training pipeline
- [x] Cron jobs for data collection
- [x] WebSocket improvements
- [x] Paper trading module
- [x] Morning briefing email system
- [x] Round 10 P0 tickets (conftest, fetch_spot_and_chains, STALE_IMPORT)
- [x] KillSwitch wired into auto-trade pipeline (`c5fe895`)
- [x] Columnar DuckDB bulk insert — ingestion 65x faster (`6648006`)
- [x] Rust decoder-core GEX path + volume-grid fallback (`98c8fd7`, `69691e4`)
- [x] Phase 3 — Public API Data Layer (94c3c89)
- [x] Phase 5 — Frontend Public API Wiring (c5e3b18, a1e69bc, dd14e32)
- [x] 3 pre-existing test failures resolved (caa3e77)

## Discovered Issues — status as of 2026-08-31

| Issue | Status |
|---|---|
| `iron_condible` typo in paper_trading.py | ✅ Fixed (comment at line 42 documents it) |
| App.js needs decomposition | Open — 1128 lines; Phase H |
| No server-state library (TanStack Query) | Open — Phase H |
|| No frontend tests | ✅ Resolved — 280 tests across 44 suites, all passing (verified 2026-09-04); dead FlowseekerPro.jsx + FilterBar.jsx removed |
| portfolio.py floats vs Decimal | Deferred — upstream prices are floats |
| Alert engine hardcodes alert types | ✅ Fixed (`beb02cc` — ALERT_TYPE_CATALOG) |
| No structured logging | ✅ Resolved — structlog JSON in prod |
|| No Prometheus metrics | ✅ Resolved — `/metrics` route shipped (`prometheus_metrics()` in `backend/server.py`); remaining gaps are additional metric types, not the endpoint (see Phase I) |
| No ADRs | ✅ ADR-0001 + index shipped (`docs/adr/`) |
| No PR template | ✅ Shipped (`900130f`) |
| No conventional commits enforcement | Partially — documented in CLAUDE.md |
|| BACKLOG.md stale (Phase A "Active" when complete) | ✅ Resolved in this sync (2026-08-31) |
|| Double-slippage in backtest engine | ✅ Fixed (`be3b7f8` 2026-08-31 — net_pnl now includes slippage) |

## Notes

- Deployment target: Oracle Always Free ARM. Runbook: `deploy/free/README.md`.
- Test posture: backend collects clean with 0 collection errors (verified 2026-09-04 via
  `cd backend && ./.venv313/Scripts/python.exe -m pytest --collect-only -q`). The total is
  a moving number — the same command returned 4581 and then 4608 inside one session while
  other work landed a new test file and edited `backend/pytest.ini`, so run the command
  instead of quoting a figure. Pass/skip/xfail counts need MongoDB on :27017 — run
  `cd backend && ./.venv313/Scripts/python.exe -m pytest -q` for them.
  Frontend 280 passed / 280 total across 44 suites (verified 2026-09-04).
- Backend health: `/health` + `/api/health` green on localhost:8000 (smoke-tested 2026-08-31).
- Local backend running: MongoDB + uvicorn on :8000 (launch via `scripts/launch_decoder.sh`).
