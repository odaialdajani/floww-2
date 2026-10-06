# Spark / Muse Spark 1.3 — S0–S9 feature matrix and receipt

Branch `spark/s0-s9-backend-completion`, based on `origin/main` `605aca8a`
(tree `5ea6a8de…`). The branch is 23 commits ahead; `origin/main..HEAD` also
contains two commits from the concurrent **Hermes** session (`8a3dbe3f`,
`3ee53fb8` and later work), which are identified in the log by their own
subjects and are not mine. The durable facts in this document are the
dispositions below, not any prose about counts.

Spark commits, in order: `ba5ff9cc` (S1/S2), `9646bb2f` (S3), `5cedd6ba`
(S5), `8e3c5d2c` (S6), `c94af993` (S2 window), `36fea14f` (S5 session),
`2cf4f48b` (S4 lineage), `e87d7a9f` (S4 health + S7), `ff8cf7ba` (S6
coordinator), `c43302bc` (S4 route), `49ef7012` (matrix), `b1276d08`,
`6c062afc` (receipt), `cb06ea0a`, `caa76481`, `1c702016`, `cdcbee46`
(resweep), `17d01bdf` (ImportError fix), `8162d39b` (envelope handoff).

## Second adversarial pass (resweep) — defects in my own new code

Every one of these was found by re-reading this branch's own code rather
than by trusting the first pass, and each is pinned by a test that fails on
the pre-fix code.

| # | Defect | Consequence before the fix |
| --- | --- | --- |
| H1 | Window comparability gate was **fail-open** (`if prev and cur and …` skipped any field missing on one side) | A window with no declared ticker returned `window_net = 500.0` |
| H2 | `KeyedScanCache` unbounded | 500 scopes → 500 entries + 500 locks; expired never reclaimed |
| H3 | A cache hit reported no cache time | A fresh timestamp could be read off a stale payload |
| H4 | A cache hit returned the payload's cursor as the live checkpoint | Two callers could believe they advanced the same slice |
| H5 | US DST rule applied to pre-2007 instants | Silently an hour wrong (`2003-04-05`: 13:00−04:00 vs truth 12:00−05:00) |
| H6 | `wall_metric_breakdown` dropped unreadable strikes with no count | A wall with all-unreadable members looked like a wall with no contracts |
| H7 | Raw and session-volume surfaces published no population | Measured 0.0 was indistinguishable from unavailable |
| H8 | Caller weight override merged blindly | String → TypeError; negative → score outside 0–100; non-unit → silent rescale |
| H10 | Provider failure raised raw out of the coordinator | A route would 500 instead of returning an unavailable sweep |
| H11 | *(introduced by the H10 fix, caught immediately)* failure got cached | One provider blip became a TTL-long outage |

All are closed. `H9` (concurrent single-flight) was probed and found
correct, so no change was made for it.

One regression was mine and is recorded honestly: the H5 hardening narrowed
the missing-tzdata signal to two exact exception class names, which broke
`tests/test_live_window_dst_fallback.py` (9 failures). The existing test was
right; the narrowing was reverted, not the test (`17d01bdf`).

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
| R10-13 | **Backend closed, UI still deferred.** `GET /api/solstice/{ticker}/contract` resolves an explicit identity (OSI, or strike+expiry+type) from a recorded snapshot and refuses a wall midpoint or first expiry with a reason (`d27cbf14`). The unguarded frontend detail request and its generation guard remain a frontend correctness migration. |
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
| Contract detail by exact identity | `services.contract_identity.resolve_contract` | `GET /api/solstice/{ticker}/contract` (new, read-only) | recorded snapshot contracts | review UI (future) | **live**; a wall midpoint or first expiry is refused with a reason, never substituted |
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

1. **The credential-conditional offline-guard error is Hermes's lane
   (R10-10), not this branch.** It surfaces at the *teardown* of whichever
   test happens to be running when the session-scoped `deny_external_network`
   fixture asserts, naming
   `tests/test_wall_desk_strength_policy.py` or
   `tests/services/test_agentfield_hub.py` depending on the run — the
   attribution is unstable, which is itself the point. The originating test
   is `test_agentfield_hub.py::TestTickerNormalization::test_gex_regime_uppercases_ticker`,
   which patches `sys.modules["services.heatseeker"]` while the reasoner calls
   `services.public_api_adapter.fetch_chain_from_public_api`
   (agentfield_hub.py:110-112).

   **Exoneration evidence, because I initially got this wrong on thin
   grounds:**
   - Reverting **all** of this branch's production changes in place still
     produced the error in this checkout.
   - A detached worktree at `origin/main`, with a copy of this venv and a
     copy of the live `backend/data` store, produced **0 errors across four
     runs** of the same subset.
   - The one remaining variable is `backend/.env`: this checkout has
     `PUBLIC_API_KEY` set, the worktree had only `.env.example`.
     `_get_broker()` returns a live broker with a key and `None` without
     one, so with no key the reasoner returns before any request is made.
   - I did **not** reproduce it with the real key, per the packet's
     instruction not to repeat a credential-triggered network attempt.

   CI cannot see this class of defect because CI has no key, so it only
   appears on the operator's machine. Hermes owns the fix.

2. **Hermes's public-expiry commit briefly broke a cost-envelope test.**
   Diagnosed, mechanism proven (unbounded walk over vendor expiries against
   a fixed `2 + N` pre-debit), and **resolved by Hermes** with a bounded
   `MAX_EXPIRY_SKIPS`. Recorded in
   `.planning/INTEGRATION_PUBLIC_EXPIRY_ENVELOPE.md`. I modified none of
   their files.

3. Bandit is not in the venv by default; installed for the gate. Exit 0.
4. `frontend/` was not touched (deferred by the packet). No frontend suite
   was run, and none of the UI is certified by any backend commit here.

## CI-equivalent local gates

Recorded at two points, because comparing pass counts across different trees
is not evidence. The first column is the pre-resweep head; the second is the
resweep head, which also includes Hermes's concurrent commits.

| Gate | pre-resweep | resweep head |
| --- | --- | --- |
| `qc/audit/truth_audit.sh` | 227 passed / 0 failed | 226 passed / 0 failed |
| `ruff check .` (0.15.22) | clean | clean |
| `bandit -r . --severity-level medium …` | exit 0 | exit 0 |
| `pytest tests/ -m "not flaky_env" --cov=.` | 6711 passed / 37 skipped / 1 error, coverage 68.03% | not re-run to completion; see below |
| `pytest tests/solstice tests/routes` | not measured separately | 783 passed ×3, one 781/2 run recorded |
| `py_compile` on every changed backend module | 3.12-syntax clean | clean |

Two honest notes on these numbers:

- The truth audit's rule set is **selected by the commit subject**, so its
  count varies (226 vs 227) between heads. Zero failed in both. It is not a
  regression signal.
- `tests/solstice` + `tests/routes` was run **four times** at the final head:
  one run reported `781 passed / 2 failed`
  (`tests/routes/test_ml_artifact_load_error.py::test_failed_load_is_not_cached`
  and one other), and three subsequent identical runs reported
  **783 passed / 0 failed**. The failing file passes on its own, alone
  alongside the new contract-route test three times over, and touches ML
  artifact loading rather than anything on this branch. So: an order- or
  state-dependent flake, observed once and not reproduced. It is recorded
  rather than smoothed over, because a single unexplained red run is
  evidence, and because this branch has already produced one that turned
  out to be real.
- The full suite was not re-run end-to-end at the final head: the run
  exceeds the session's practical budget, and the one failing test it did
  surface was Hermes's cost-envelope test, which now passes. What was run at
  the final head, green: `tests/solstice` + `tests/routes` = **783 passed**
  (×3), 65 across the wall-desk / Eastern-clock / rank / public-path files,
  61 across the three public-path files, 426 in `tests/solstice` alone after
  the contract-identity slice. Coverage was measured at the pre-resweep head
  (68.03% against a 60% gate); the resweep adds tested modules and removes
  none, so it does not lower coverage, but that is an **inference**, not a
  measurement.

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
