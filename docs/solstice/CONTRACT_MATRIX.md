# Solstice Contract Matrix — user-visible field → producer chain (R5)

Every user-visible Solstice field, its source, adapter, store, replay and UI
consumer. No mandatory field has an unowned producer. Status: implemented +
tested unless marked otherwise.

Conventions: `c × |δ|` everywhere delta-weighted; gross = `|call|+|put|`
(never `|net|`); missing inputs are unavailable, never zero-filled.

## Grid (SkylitHeatmapGrid)

| Field | Source | Adapter | Store | Replay | UI consumer |
|---|---|---|---|---|---|
| Cell value (raw net) | `raw.contracts[].gamma × OI` | `public_api_adapter` → `gex_core.compute_gex_grid_vendor` | `grids_json.grid` | `replayToDisplay` → `metrics.grids` | Grid matrix |
| Cell value (Δ-weighted) | raw + `|δ|` | `gex_core.compute_gex_grid_delta_weighted` (unavailable when all-δ-missing) | `grids_json` | same | Grid overlay, `metricBasis` label |
| Cell value (activity) | raw + cumulative volume | `gex_core.compute_gex_grid_volume` (explicit `VOLUME_*` basis) | grid-meta only | n/a (live recompute) | Grid overlay |
| Strike-rail bar | `call_gex/put_gex` rows | `compute_gex_by_strike_vendor` (adjusted quarantined) | `strikes_json` | strikes | Rail (`|call|+|put|`) |
| Expiry header % | `|net cells|` per expiry | grid `expMeta` (**absolute net**, labeled as such) | grid-meta | grids | Header |
| Missing/stale cells | null/NaN from chain | `safe_float_or_none` (never 0-fill) | nulls preserved | nulls preserved | Hatch/dash, never zero color |

## Inspector (WallInspector, five blocks)

| Block | Source | Notes |
|---|---|---|
| Why here (zone/gross/net/call/put/scope) | `wall_structure.discover_walls` (scoped IDs, gap-aware, zero-break) | Raw identity locked across metric switches |
| Distance | wall mid vs display spot | Replay shows recorded spot |
| Per-expiry | same-snapshot grids × member strikes | Missing grid → row hidden |
| Δ/Raw (scope) | `magnitude_ratio_delta_over_raw` (snapshot-wide) | Labeled scope-wide; wall-local needs same-wall grids |
| **Window activity** | `window_contract_activity` over recorder baseline (epoch/scope-bound) | Value, `VOLUME_REBASE`, or no-baseline — never raw fallback |
| Δ provenance | `dadgex_usable/missing` counts | Mixed pairs blocked without policy |
| OI date | per-strike `oi_dates` → wall union `oi_effective_dates` (capped 4) | `gex_core` buckets + `wall_structure._zone` | strike rows + wall record | strike rows + wall record | Inspector "OI eff. date" row (unavailable when no member metadata) |
| What price did (state/touches) | `wall_interaction` + history join (scoped ID, dwell clocks, gaps) | `taps_reason` when unknown; polls never counted |
| Two paths | `scenario_for` (scoped wall ID, direction-correct) | Filtered to selected wall, never `scenarios[0]` |
| Limits (data) | canonical `quality` (state/reasonCodes) | Same object feeds status strip, session, evidence |

## Status / session / evidence

| Field | Source | Agreement rule |
|---|---|---|
| Status strip state | `payload.quality` (canonical camelCase + state) | Same object as inspector/scout/evidence inputs |
| Session permission | `solstice_session` (weekday, 09:30 ET open, quality, eligibility) | Entry blocked ⇒ management still allowed; pre-open/holiday limits stated |
| Evidence packet | `solstice_evidence` from displayed snapshot + wall | Facts: SPOT/BASIS/WALL/QUALITY/INTERACTION/SCENARIO/WINDOW; validator binds every prose number; wall/snapshot mismatch rejected |
| Scout candidates | `contract_scout` (side-first, finite, fresh, same-day, adjusted-quarantined) | Strict in production (`session_date`); decisions recorded per side incl. abstentions |

## Recording / replay / research

| Artifact | Writer (production caller) | Reader |
|---|---|---|
| Snapshot + contracts + cells + quality/scenarios/interactions | `server.build_heatmap` → `record_snapshot` (single-writer lock, one txn, explicit coverage) | `replay_snapshot` (available-at join), grid, evidence route |
| Wall events | `server.build_heatmap` interaction attach (best-effort) | `latest_wall_state` (newest-wins vs memory) |
| Decisions + candidate quotes | `server.build_heatmap` scout attach, both sides incl. waits | session review, outcome join |
| Outcomes | `record_outcome` (explicit caller: review/replay jobs) | `outcome_labels_v1` by decision ID |
| Capability observations | `server.build_heatmap` (`heatmap_build`) | `/capability` unified with registry + manifest |
| Gaps/heartbeat | `session_manifest(expected_cadence_s)` | ReplayStrip, `/manifest` route (default 300s) |
| Health | `recorder_status` (memory never durable) | `/recorder_health` |

## Known producer gaps (owned, scheduled)

- Holiday/half-day calendar + AM/PM series cutoffs in `solstice_session`
  (series-metadata owned; regular-hours boundary enforced).
- Outcome attachment awaits recorded price paths (labels + censoring ready).
