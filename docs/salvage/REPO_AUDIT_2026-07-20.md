# Repo Audit — 2026-07-20

Full-repo scan: structure, bloat, bottlenecks, and Rust-conversion assessment.
Run on the Windows clone (`Desktop/floww`), branch `chore/round10-repo-audit` off `fix/skylit-panel-bugs` @ `ca25557`.
Method: three parallel read-only sweeps (backend map, frontend + repo-wide, hot-paths) with every load-bearing
claim re-verified by direct file read before landing here.

---

## 1. Headline numbers

| Metric | Value |
|---|---|
| Tracked files | 3,434 |
| Tracked bytes | ~275 MB |
| `.git` pack size | 150.87 MiB |
| Backend (non-test) | 232 `.py` files / 61,510 LOC |
| Backend tests | 175 files / 36,498 LOC |
| HTTP endpoints | 276 across 46 routers + `server.py` inline |
| Frontend | 210 files / ~17.3k LOC (React 19, CRA + craco, no react-router) |
| Bloat share | **~75% of tracked bytes is non-source artifacts** |

## 2. Bloat inventory

| Item | Size | Status |
|---|---|---|
| `data/github-repos/` (24 vendored clones + duplicated `extracted-code/`) | **206 MB** | ignored at `.gitignore:96-97` but committed before the rule; incl. 34 MB `wordpress.sql`, 28 MB GIFs, ~12 academic PDFs |
| `models/` (top-level, 71 files) | 9.4 MB | ignored at `.gitignore:104` but tracked |
| `data/research_kg.duckdb` + `backend/data/gflows.duckdb` | 24 MB | databases committed to git |
| `data/cached_features/*.csv` | ~9 MB | training feature dumps |
| `reports/training_*.json` (28 files) | small | ignored at `.gitignore:105` but tracked |
| `backend/models/` (222 files, 26 MB) | — | **production model artifacts — FROZEN, stays tracked** |

Root-level sprawl: 42 planning/prompt `.md` files (~13.6k LOC), stale `round9_followup*/` + `round9_agents/` dirs, one 507 KB PDF at root. All-repo markdown: 810 files / 47.8k LOC.

## 3. Dead code

**Confirmed dead — zero references anywhere in app, scripts, or other modules (own tests excepted):**
`services/causal_inference.py` (665), `services/semantic_search.py` (516), `services/runbook_executor.py` (395),
`services/alert_tuner.py` (312), `services/greek_aggregator.py` (298), `services/anomaly_explainer.py` (284),
`services/order_router.py` (226), root `ml_pipeline.py` (258), `ml_advanced.py` (272), `memory_integration.py` (87),
`_check_features2.py` (23). ≈ 3.3k LOC.

**Likely dead / tested-but-unwired (no import path from `server.py`):** ~22 modules ≈ 4k LOC, incl. `audit_trail`,
`cache_router`, `data_quality`, `execution_doctrine`, `fill_monitor`, `signal_translator`, `staleness_alerts`,
`request_deduplicator`, `causal/*`, `rl/trading_env`, `strategies/friday_pin`, `kanban/{multi_repo,rebalancer,throughput_model}`,
`memory/{federation,code_embeddings,chart_embeddings,voice_embeddings}`, `ml/gex_inference`. Quarantine list — owner call.

**Duplication clusters:** paper trading ×5 implementations, morning-briefing ×5, schwab ×4, dead root ML modules
shadowing `services/ml/`; helpers like `_safe_float` ×9, `walk_forward_cv` ×5 defined in multiple files.

**Unused dependencies:** backend 10 of 39 (`boto3`, `requests-oauthlib`, `cryptography`, `python-jose`, `pyjwt`,
`bcrypt`, `passlib`, `jq`, `typer`, `emergentintegrations` — zero imports each; the auth stack is entirely unused).
Frontend: `react-router-dom`, `recharts`, `zod`, `@hookform/resolvers`, `date-fns` unused; 41 of 46 shadcn `ui/`
components never imported (+6 deps only referenced by those dead wrappers). `frontend/package.json` is frozen —
parked for owner approval.

**God files:** `server.py` 3,014 LOC · `services/dash_ui.py` 1,612 (frozen) · `App.js` 1,093 (frozen) ·
`services/heatseeker.py` 1,051 · `services/ml/features.py` 1,001.

## 4. Bottlenecks

Workload is **IO/network-bound** (yfinance, Schwab WS, Mongo), not CPU-bound. CPU-hot paths (greeks/VPIN/Hawkes)
are already numba-JIT'd; `docs/ARCHITECTURE_DEEP.md` records p99 ≈ 179 ms vs a 200 ms budget.

1. `routes/ml_predict_api.py:108-109` & `:335` — `joblib.load` of model + scaler **per request inside the async
   handler** (event-loop stall + disk churn). The file's own 60 s prediction cache (`:41-53`) is defined but never called.
2. `services/ml/inference.py` — full 1-year `yf.download` on every `predict()` (`:158`, offloaded to thread but
   re-downloaded per call); `_feature_cache` (`:400`) + `FEATURE_CACHE_TTL_SEC` (`:97`) declared, never read.
   **Frozen file — fix needs owner approval.**
3. `services/ml/inference.py:345` — fresh sync `MongoClient` per GEX cache-miss (minor; 120 s TTL above it).
4. `services/duckdb_engine.py:358` — sync `query()` (`fetchdf`) footgun; used by `services/replay_engine.py:95,145`;
   `services/heatseeker_snapshots.py:419/449/493/528` call raw `.fetchdf()` directly.
5. `services/schwab_streamer.py:190` — per-message O(n) rebuild of `_message_timestamps` (minor CPU wart at RTH rates).

### Correctness bug found during audit

`routes/ml_predict_api.py:205` — `/api/ml/ensemble` maps the inference engine's 3-class output
(DOWN=0 / HOLD=1 / UP=2) with binary logic `"UP" if pred.prediction == 1 else "DOWN"`:
**a true UP (2) is labeled "DOWN"; a HOLD (1) is labeled "UP"**; `probabilities[1]` (`:208-210`) reports HOLD mass
as "up". The ensemble BULLISH/BEARISH verdict is built from these wrong labels. Fixed in this round (TDD).

## 5. Rust conversion assessment

**Full rewrite: NO-GO.**
- The app's latency is dominated by network waits, and the stated p99 budget is already met — Rust's raw-CPU win
  has almost nothing to bite on; the genuinely hot math already runs at ~C speed under numba.
- Port surface: ~51.8k LOC / 277 handlers.
- Two hard walls: sklearn `.joblib` inference has **no native Rust load path** (would require ONNX export via
  skl2onnx → `ort`/`tract`, a Python sidecar, or retraining in smartcore/linfa — GBM support is weak), and
  `dash_ui.py` (1,612 LOC, frozen) is Python-only and cannot be ported.
- Clean-mapping parts if ever needed: FastAPI→axum, Motor→`mongodb` crate, DuckDB→`duckdb-rs`,
  websockets→`tokio-tungstenite`, pandas→polars (pandas is concentrated in ML/backtest/offline code;
  the realtime heatseeker/flowseeker engines are pure-Python dict math).

**If Rust is still wanted, the right-sized pilot:** port `heatseeker.py` + `flowseeker.py` engines (pure functions,
no pandas/IO) as a PyO3 extension crate (maturin build), behind an adapter that falls back to the Python
implementation when the wheel is absent; golden-vector parity tests against the existing suite; ~1–2 weeks;
hard gate = measured speedup before any further Rust spend. Second candidate (only after the pilot proves out):
standalone Rust streamer+ingestion service. Not worth doing: numba→Rust (no headroom).

## 6. Remediation executed this round (branch `chore/round10-repo-audit`)

- **Phase 1** — untrack bloat, no history rewrite: `git rm -r --cached` on `data/github-repos/`, `models/`,
  `data/cached_features/`, both `.duckdb` files, `reports/training_*.json`; `.gitignore` extended. Files stay on
  disk; `backend/models/` (222 artifacts) untouched. `.git` history unchanged (rewrite = separate owner decision).
- **Phase 2** — TDD fixes in non-frozen files: ensemble 3-class label bug; wire the dead prediction cache; cache
  `joblib.load` keyed `(ticker, mtime)`; async-safe DuckDB reads on async paths.
- **Phase 3** — delete tier-0 dead files (`_check_features2.py`, `ml_pipeline.py`, `ml_advanced.py`).
- **Phase 4** — drop the 10 unused backend deps, verified in a fresh venv.

## 7. Parked — owner sign-off required

1. `.git` history rewrite (filter-repo + force-push — forbidden by default) to reclaim the ~150 MiB pack.
2. Tier-1/2 dead-module deletions (each carries tests) + the ~22-module quarantine list.
3. Duplicate-cluster consolidation (paper trading / briefing / schwab) — behavior-affecting.
4. Frozen-file fixes: enable `inference.py` feature cache (biggest remaining latency win), frontend
   `package.json` + shadcn prune, `App.js` split, `server.py` decomposition.
5. Rust pilot go/no-go.

## 8. Baseline (this machine, recorded during audit)

- Machine had no venv / no `node_modules` — backend venv rebuilt at `backend/.venv` (Python 3.13.13).
- Pytest baseline: see Phase commit bodies for the exact pass/fail/error counts captured before and after each change.
- Frontend untouched this round; jest not run on this machine (no `node_modules`; no frontend files modified).
