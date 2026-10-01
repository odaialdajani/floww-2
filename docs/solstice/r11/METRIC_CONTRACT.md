# Solstice metric display contract (R11-H01)

Status: live on branch `solstice/r11-opus`. Backwards compatible: every key
below either existed at `5312fe56` or is **additive**. No key was renamed
or removed. Producer: `server._build_heatmap_impl` (served by
`GET /api/heatmap/{t}` and `GET /api/data/{t}`); proof:
`backend/tests/solstice/test_r11_metric_contract.py`.

## Formulas (registry: `domain/exposure_metrics.py::METRIC_REGISTRY`)

u = Γ·m·S²·0.01 (USD per 1% spot move), c = +1 call / −1 put, unknown type rejected.

| UI name | Registry id | Formula | Basis |
| --- | --- | --- | --- |
| Raw OI | `gex_net_v1` / `gex_gross_v1` | Σ c·u·N / Σ u·N | `OI` |
| Δ-weighted OI | `dadgex_net_v1` / `dadgex_gross_v1` | Σ c·u·N·\|δ\| | `OI_DELTA_WEIGHTED` |
| Session volume (legacy "activity") | `volume_gamma_v1` | Σ c·u·V | `VOLUME` |
| Session volume × \|Δ\| | `session_delta_volume_gamma_v1` | Σ c·u·V·\|δ\| | `VOLUME_DELTA_WEIGHTED` |
| Window Δvolume × \|Δ\| | `window_dadgex_v1` (alias `window_daddex_v1`) | Σ c·u(open)·\|δ(open)\|·ΔV(W) | `VOLUME_WINDOW` |
| VEX | `vex_net_1volpt` | Σ c·m·N·S·vanna·0.01 (declared convention; not re-derived) | `VEX_1VOLPT` |
| Charm | (grid meta) | c·charm·w·m·S·0.01 | see `grid.charm_meta` |

Δ-weighted surfaces are **gamma exposure weighted by |delta|** — not
buyer-minus-seller flow, not dealer inventory. DUO/DVO exist as helpers only
and are **not** display surfaces.

## Field paths

| Concept | Path | Notes |
| --- | --- | --- |
| Raw grid | `grid.grid[exp][strikeKey]`, `grid.expiries`, `grid.strikes` | `metrics.grids.raw` is deliberately `null` |
| Δ-weighted grid | `metrics.grids.delta.grid[exp][strikeKey]` | + `usable`, `missing_delta`, `invalid_delta` (new: boolean/nonfinite/out-of-range readings), `cell_missing_delta`, `cell_invalid_delta` (new), `invalid_type`, `quarantined`, `status`, `reason` |
| Session volume grid | `metrics.grids.activity.grid[...]` | + `usable` (new) |
| Session volume × \|Δ\| grid | `metrics.grids.session_delta_volume.grid[...]` | + `usable`, `missing_delta`, `invalid_delta` (new), `cell_missing_delta`, `cell_invalid_delta` (new) |
| Window grid | `metrics.grids.window.grid[...]` (new) | `status: "unavailable"` + `reason` until a comparable baseline exists; `interval`, `greek_convention`, `provenance_note` |
| Window scalars | `metrics.window_dadgex_v1`, `metrics.window_daddex_v1`, `metrics.window_dadgex_reason`, `metrics.window_daddex_reason` | alias pair now always carries the same value **and** reason |
| Per-surface coverage | `metrics.surface_coverage.{raw,delta,activity,session_delta_volume,window,vex,charm}` (new) | each: `metric_id`, `basis`, `usable`, `missing_*`, `invalid`, `invalid_delta` (new on delta/session_delta_volume), `status ∈ ok/partial/unavailable`, `reason` |
| Contract version | `metrics.metric_contract_version` (new) | `solstice-metric-contract.v1` |
| Scope scalars | `metrics.gex_*`, `metrics.dadgex_*`, `metrics.volume_gamma_*`, `metrics.session_delta_volume_*` | unchanged |
| Per-wall | `metrics.wall_metrics[wall_id]` | `daddex_*` (Δ-OI) + **new** `daddex_invalid`, `volume_*` (Σc·u·V), **new** `sdv_gross`, `sdv_net`, `sdv_usable`, `sdv_missing_delta`, `bases{daddex,volume,session_delta_volume}`; legacy `basis` kept |
| Per-wall window | `metrics.wall_window[wall_id].window_daddex` + `coverage` | `scope_total` is a separate key, never wall-local |
| Provenance | `formula_version`, `exposure_basis`, `data_source`, `snapshotId`, `map_query`, `quality` | |
| Source age | `event_time`, `fetched_at`, `source_received_at`, `stale`, `stale_age_s`; `source_age_s` is `null` (not computed upstream) | unknown age stays unknown |

## Semantics the consumer must keep

- `cell_missing_delta[exp][k] = n` and a value at `grid[exp][k]` → **partial
  cell** (n contracts excluded for unknown delta). Entry without a value →
  contracts exist, delta unknown → render unavailable, never zero.
  `cell_invalid_delta[exp][k] = n` is the same shape for present-but-unusable
  delta readings (boolean, nonfinite, materially out of range): rendered with
  the distinct δ! marker, counted in `invalid_delta`, never merged into
  `missing_delta`. Missing and invalid are different facts; both keep a
  usable surface `partial`, never `ok`.
- `surface_coverage[*].status === "partial"` must stay visible as a short
  quality chip; it is not "ok".
- Window `reason` codes: `HISTORY_NOT_YET_RECORDED`, `NO_BASELINE`,
  `IDENTITY_UNDECLARED`, `TICKER_MISMATCH`, `PROVIDER_MISMATCH`,
  `SCOPE_MISMATCH`, `FORMULA_MISMATCH`, `SESSION_ROLL`, `SOURCE_OUT_OF_ORDER`,
  `SPOT_UNKNOWN`, `VOLUME_REBASE`, `NO_COMPARABLE_OBSERVATIONS`.
- Delta net may exceed raw net in magnitude (cancellation changes); do not
  assert |Δ net| ≤ |raw net|.
- The React consumer computes **no Greeks**. It may sum cells of one
  surface over one declared scope (profile), nothing else.

## Kernel repairs in this slice (red → green)

`services/solstice_enrichment.window_contract_activity` (the live window
kernel) previously: read boolean delta/gamma as 1.0; defaulted unknown option
type to put; turned an explicit 0/None/NaN multiplier into 100; silently
dropped NaN/inf/over-range delta without a count. Now: shared domain
validators (`abs_delta`, `is_valid_measurement`, `option_type_sign`,
`resolve_multiplier`); exclusions counted as `invalid` / `invalid_type`,
surfaced in `window_coverage.n_invalid` / `n_invalid_type`.
