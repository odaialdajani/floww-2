# Spark / Muse Spark 1.3 — S0–S9 feature matrix and receipt

Branch `spark/s0-s9-backend-completion`, based on `origin/main` `605aca8a`
(tree `5ea6a8de…`). Head: `49ef7012`, tree `fa1f38fc8968288710b6739b75a5e2f64997e64a`.
Ten commits; the authoritative list is `git log origin/main..HEAD`, and the
durable facts in this document are the dispositions below rather than any
prose about counts.

Every row states producer → canonical computation → route → storage →
consumer, with the exact commit. Status vocabulary is deliberately narrow:
**live**, **source-ready** (wired to a caller path, tests pass, not mounted
behind a route), **test-only**, **deferred** (with the reason), **external**
(not decidable in this repo).

## Reconciliation of the Rev-10 findings

| ID | Disposition | Where |
| --- | --- | --- |
| R10-01 | **Fixed.** `session_delta_volume_gamma_v1` (Σ c·u·V·|δ|) registered as a distinct metric with its own grid twin; `volume_gamma_v1` untouched. Server emits additive keys, no field replacement. The UI label ("Session vol × Δ" over the VOLUME grid) is still wrong and is **deferred UI work**, explicitly not certified here. | `ba5ff9cc` |
| R10-02 | **Fixed.** `resolve_multiplier()` returns `(value, reason)`. Explicit invalid → rejected; absent key → documented `DEFAULT_STANDARD`; present-`None` → unknown; alias disagreement → `MULTIPLIER_ALIAS_DISAGREE`. `gex_core` grid twins share the same kernel. | `ba5ff9cc` |
| R10-03 | **Fixed on the Solstice boundary; legacy path untouched and pinned as still-defective.** `rank_rows` preserves an already-fused row. The legacy `rank_many` re-fusion is asserted in a test as *current Tide behavior* so a future fix is visible rather than silent. | `8e3c5d2c` |
| R10-04 | **Fixed on the Solstice boundary.** NaN/inf/bool → `invalid`; missing → absent; measured zero → zero; ML confidence 0 stays 0; bull/bear symmetry preserved. | `8e3c5d2c` |
| R10-05 | **Fixed for the Solstice path.** Cache identity carries universe + tickers + dte/max_expiries/mode/scalp + provider + formula. The legacy global cache is unchanged and remains a known defect. | `8e3c5d2c`, `ff8cf7ba` |
| R10-06 | **Fixed.** `wall_desk_snapshot` no longer imports `tests.fixtures`; missing spot → unavailable; identity derived from input; empty population is legitimate. | `9646bb2f` |
| R10-07 | **Fixed.** `solstice_window.window_activity_surface` is the governed window path with a comparability gate; the legacy helper refuses instead of zero-filling. | `c94af993` |
| R10-08 | **Fixed.** Exact `Decimal` strike keys; integral strikes keep the legacy key form. | `5cedd6ba` |
| R10-09 | **Fixed.** Two honestly named modes: `session_bar_vwap_for_ticker` (intraday, genuinely volume-weighted) and `session_daily_typical_price_for_ticker`. The legacy name is a documented alias. | `36fea14f` |
| R10-10 | **Not mine.** Pre-existing, reproducible with or without my changes (see below). Hermes's test-isolation lane. |
| R10-11 | **Fixed.** `eastern_at_safe` / `eastern_now_safe` return aware datetimes whose UTC timestamp equals the input. `server._eastern_now` uses it; wall-hour gates unchanged. | `5cedd6ba` |
| R10-12 | **Backend capability only.** The four surfaces now exist server-side. Periodic refresh, `dte=0` requests and the label migration are **deferred UI** work. |
| R10-13 | **Deferred UI.** Backend exact-identity support landed (`5cedd6ba`); the unguarded detail request is a frontend correctness migration. |
| R10-14 | **Ledger below.** Helpers are classified, not wired to make an inventory green. |

## Feature matrix

| Feature | Producer → computation | Route | Storage | Consumer | Status |
| --- | --- | --- | --- | --- | --- |
| Raw OI net/gross | `server.py:1440` → `domain.exposure_metrics.compute_raw_oi` | `/api/heatmap` | `heatmap_snapshots_v2` | Solstice grid, wall discovery | **live** |
| Delta-weighted OI | `server.py:1441` → `compute_delta_weighted_oi` | `/api/heatmap` | same | delta grid overlay | **live** |
| Session volume gamma (Σ c·u·V) | `server.py:1442` → `compute_volume_gamma` | `/api/heatmap` | same | `grids.activity` | **live, unchanged** |
| Session volume × delta (Σ c·u·V·|δ|) | `server.py:1446` → `compute_session_delta_volume_gamma` | `/api/heatmap` | same (`metrics_full_json`) | `grids.session_delta_volume` | **live** (label migration deferred) |
| Session delta-volume grid twin | `gex_core.compute_gex_grid_session_delta_volume` | `/api/heatmap` | grid cells | grid overlay | **live** |
| Window delta-volume activity | `solstice_window.window_activity_surface` → live kernel `solstice_enrichment.window_contract_activity` | `/api/heatmap` | prior snapshot | `metrics.window_*` | **live** |
| Wall identity / nearest walls | `services.wall_structure.discover_walls` | `/api/heatmap` | `walls_json` | inspector, Solstice/Triad | **live** |
| Wall-local metric breakdown | `wall_metric_breakdown` | `/api/heatmap` | `metrics_full_json` | inspector | **live** |
| Contract exposure annotation | `services.triad_projection.annotate_contract_exposure` | `/api/public/chain/{ticker}`, `/api/market/...` | — | chain consumers | **live** (caller and missing-vs-zero semantics preserved) |
| Triad chain projection | `project_triad_from_chain` (exact strikes) | none | none | none | **source-ready** — no production caller found; the audit's own note is preserved rather than inventing a route |
| Strict multiplier provenance | `domain.exposure_metrics.resolve_multiplier` | all exposure routes | — | all exposure consumers | **live** |
| Eastern instant-preserving clock | `services.eastern_clock.eastern_*_safe` | n/a (gates) | — | `server._eastern_now` + gates | **live** |
| Session reference (bar VWAP) | `session_levels_source.session_bar_vwap_for_ticker` | none | none | none | **source-ready** — no production caller found; deliberately not mounted because nothing consumes it yet |
| Session reference (daily typical) | `session_daily_typical_price_for_ticker` | none | none | none | **source-ready** |
| Recorder / replay | `heatmap_history.record_snapshot` / `replay_snapshot` | heatmap path | DuckDB `heatmap_snapshots_v2` | replay, compare | **live** |
| Recorder health (store + capture) | `services.recorder_health.recorder_health` | `/api/solstice/recorder_health` | — | operator | **live** |
| Capture worker | `recorder_health.start_worker` | — | — | — | **disabled by default**; no caller, no activation |
| Solstice rank boundary | `services.solstice_rank.rank_rows` | none | — | coordinator | **source-ready** |
| Solstice scan coordinator | `services.solstice_scan.run_scan` | none | — | none | **source-ready** — route registration is a shared-file change under Hermes's lease |
| Decision → outcome | `record_decision` → `close_episodes` → `label_touch` | `/api/solstice/outcomes/close` | `scenario_decisions_v1`, `outcome_labels_v1` | journal, research | **live** |
| DUO / DVO | `domain.second_order_exposure` | none | none | none | **experimental, not wired** — units need dimensional review before adoption (S8) |
| Strongest-wall policy | `domain.wall_strength.assign_strongest_wall` | none | none | none | **test-only**, retained as a policy helper; not wired to make an inventory green |
| Numeric boundary | `domain.numeric_boundary` | none | none | none | **test-only**, retained |
| Vanna-expiry removal view | `services.solstice_vanna.expiry_removal_view` | `/api/solstice` | — | VEX panel | **live** |
| ML unification | — | — | — | — | **deferred** — product/engineering decision, not required by any retained producer |

## Known failures, honestly

1. **Full-suite: 6711 passed, 37 skipped, 1 error.** The error is
   `tests/test_wall_strength_policy.py::test_unknown_values_are_unavailable_not_zero`
   at *teardown*, raised by the session `deny_external_network` fixture after
   `tests/services/test_agentfield_hub.py::TestTickerNormalization::test_gex_regime_uppercases_ticker`
   attempted a real `api.public.com` connection. That test patches
   `services.heatseeker`, which the reasoner no longer calls.
   **Reproduced on the unmodified base files** (checked out `origin/main`
   versions of `gex_core.py`, `exposure_metrics.py`, `server.py`: 42 passed
   in isolation, identical either way), and the file passes in isolation on
   both trees. It is a full-run ordering/isolation defect = R10-10, owned by
   Hermes. It is not a result of this work and was not worked around.
2. Bandit is not in the venv by default; installed for the gate. Exit 0.
3. `frontend/` was not touched (deferred by the packet). No frontend suite
   was run, and none of the UI is certified by any backend commit here.

## CI-equivalent local gates (at head)

- `qc/audit/truth_audit.sh` → 227 passed, 0 failed
- `ruff check .` (0.15.22) → All checks passed
- `bandit -r . --severity-level medium …` → exit 0
- `pytest tests/ -m "not flaky_env" --cov=.` → 6711 passed, 37 skipped, 1 error
  (pre-existing), coverage **68.03%** (gate 60%)
- `py_compile` on every changed backend module (3.12-syntax check)

## Deferred, with reasons

- UI label migration for the activity surface (R10-01) — frontend deferred.
- Mounting `solstice_scan` / `solstice_rank` / the session references behind
  routes — shared route/server registry, Hermes's lease.
- Triad periodic refresh, true `dte=0` request, contract-detail generation
  guard — frontend correctness migration.
- DUO/DVO unit reconciliation (`D''(S)` vs ½·D''·move² with dollar spot
  increments) — the registry's "USD/(1% move)²" wording needs a dimensional
  decision before any consumer.
- Capture-worker activation — requires explicit operator authorization and a
  rollout receipt; activation is not implied by this code.
- SPX entitlement, participant comprehension, research validation — cannot be
  produced by any test in this repo.
