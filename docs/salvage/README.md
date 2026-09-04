# Salvage — retired `Desktop/floww` clone (2026-09-04)

The old clone at `C:\Users\DARK HERO\Desktop\floww` is **retired**. It shared history
with this repo up to `ca25557` (2026-06-14) and then diverged; this repo is 1,015
commits ahead. Before that folder is deleted, everything in it that existed
**nowhere else** was copied here.

Nothing in this folder is wired into the app. It is a holding pen so the work is
recoverable, not discarded. Tracking entries live in `BACKLOG.md` → "Phase K".

## What was rescued and why

| File | What it is | Why it was perishable |
|---|---|---|
| `2026-09-04-old-clone-perf-fixes.patch` | Three uncommitted latency fixes | Never committed anywhere |
| `test_ml_predict_cache.py` | Test pinning the prediction-cache contract | Untracked in the old clone |
| `test_ml_ensemble_labels.py` | Test pinning ensemble label ordering | Untracked in the old clone |
| `REPO_AUDIT_2026-07-20.md` | Repo audit from the old clone | Untracked in the old clone |
| `SPY_meta_v2.0-regime.quarantined.json` | SPY regime meta, quarantined by the truth audit (feature/sample ratio) | Deliberately not shipped here; kept for the record |
| `../../project_oracle/models/*.pt` | 3 trained torch artifacts (anomaly detector, meta-anomaly, PatchTST VPIN) | `.gitignore` line 118 keeps them out of git — the old clone held the only local copies |

`meta_anomaly_v1.pt` in the old clone was **retrained** (newer mtime than its
siblings, 1,221,689 bytes vs the committed-era 1,222,057). The copy now sitting in
`project_oracle/models/` is that retrained version. `services/meta_observability.py`
loads it from there and silently retrains from scratch when it is absent — so before
this rescue, the anomaly detector on this machine was starting cold every boot.

## The three perf fixes in the patch

All three are absent from this repo and all three are real event-loop wins:

1. **`routes/ml_predict_api.py`** — mtime-keyed cache for `joblib.load` of the model
   and scaler, plus per-`model_type` prediction caching. Today every
   `/api/predict/{ticker}` call re-reads both artifacts from disk.
2. **`routes/heatseeker_snapshots_api.py`** — wraps three DuckDB calls
   (`get_top_movers_from_db`, `get_history`, `get_latest_snapshot`) in
   `asyncio.to_thread`. They currently block the event loop during pandas
   materialization.
3. **`services/replay_engine.py`** — two `self.db.query(...)` → `await
   self.db.query_async(...)`. `query_async` already exists in this repo at
   `services/duckdb_engine.py:500`, so this one is nearly free.

The patch was generated against the old clone's tree at its `ab01eea` HEAD. Files
have drifted since, so apply with `git apply --3way` and expect to resolve context.

## Restoring the deliberately-removed features

Everything torn out in the AlphaPod cleanup is still in **this repo's own history** —
no copy was needed. Recover any file with `git show <commit>^:<path>`:

- AlphaPod SPA pages (Alpha Flow, Daily Report, Earnings, Ticker Analysis, SPX GEX,
  Capture, Heatmaps, placeholders) — removed in `3f339d5` / `d63560a`
- PaperTrade, MLPredictionsPanel, RateLimitDashboard, VelocityGauge, NodesTable,
  FlowCarousel, DTEFilter, ExpiryFilter, SignInPage, `hooks/useMLPredictions.js`,
  and the shadcn `components/ui` library — removed in `04615cc`
- SwarmFrame, TurboQuantPanel — removed in `489593b`
- `services/graph_updater.py`, `services/position_reconciler.py` — removed in `6f83026`

Verified 2026-09-04: every path above resolves from history.
