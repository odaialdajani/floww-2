# Research reports and parent adjudications

## Harness outcome — no fabricated completion

Four read-only OpenCode specialists were launched using `nvidia/z-ai/glm-5.3`: chart-engine, data-replay, workspace-ux, test-gates. Data/replay returned a full source-cited report. The other three timed out at750s. Persisted session exports confirm providerID=nvidia/modelID=z-ai/glm-5.3; timed-out sessions lack final completion. Four bounded direct NIM followups also failed: workspace/test budgets were exhausted wholly by reasoning, chart/refuter requests timed out. A documented low-effort pilot timed out too. Failed/incomplete attempts have no findings attributed to them.

Parent finished chart-engine/UX/test audits directly from the source, primary documentation, transcript and focused tests. The independent fallback refuter is native-model, explicitly not NIM. Its eight final findings and parent-applied adjudications are recorded below; implementation-specific evidence remains gated.

API usage metadata retained in EVIDENCE.json is reported usage, not a billing invoice. OpenCode cost0 fields cannot establish free inference or actual account credit consumption. Never promote a timeout, empty message or max-token reasoning response into a successful audit.

## Parent evidence-backed audits and decisions

1. **Chart render:** current Plotly function rebuilds candle+gap-separated wall traces; no orb magnitude. PriceNodeHistory is the existing seam and its controlled open contract stays intact. Plotly supports a minimal incremental upgrade without dependency approval; dedicated LWC is a conditional later adapter.
2. **Extra consumer:** Trinity's `WallPricePath` uses the same route for an SVG close/zone path, so keep the endpoint stable. Flowseeker ChartModal and frozen Dash Atlas are separate surfaces, not migration targets.
3. **Archive correction:** full `grids_json` and metadata columns already exist conditionally. The report's recommendation to add `orbs_json` is not adopted as default. Audit available archived grid coverage first, keep wall roles and strike orbs distinct, then add only missing capture fields.
4. **Critical VEX trap:** local source verifies legacy aggregator VOMMA alias differs from canonical VANNA VEX. New contract requires metric/model/unit/basis tags; no cross-channel sum or ML formula change.
5. **King ranking:** existing argmax output is not proof of absolute ranking. New signed-king and P-threshold rules need independent characterization fixtures, including zero/unknown/ties.
6. **Replay limitation:** available-at nodes already defend late-arrival leakage, but eventual historical OHLC lacks recorded revision-arrival timing. Separate finalized-history review from time-faithful replay; never promise perfect replay from the present endpoint.
7. **ETH/instrument coverage:** adapter sessions filtering is not proof upstream toggle/entitlement is wired; get_bars currently defaults instrument_type EQUITY. Characterize instrument aliases/provider session support before exposing choices. Futures require their own contract/calendar/data.
8. **AI admission:** AskLodestar currently refuses history/replay and adjusted maps; exact server evidence resolution is a prerequisite, not a client-only context patch.
9. **Persistence:** local layouts are achievable without pretending a single deployment key is per-user identity. Cross-device account sync and authenticated owner-isolated writes are separately gated.
10. **Data feeds:** audited bar/chain adapter offers OHLCV/quotes/contracts, not an entitled classified print tape/dark feed. Existing microstructure/scanner calculations elsewhere are not proof of source licensing/history. Advanced features stay visibly gated until commissioning.
11. **Drawings/export:** logical coordinates, hit testing/arbitration, history/presets and composite exports are our code, not automatic LWC features. Preserve false/hidden choices and account quota semantics.
12. **Regression gates:** actual8+53 backend tests pass; craco invocation is blocked, not a frontend pass. Browser performance budgets are proposed, no measurements invented. The original dirty checkout remains dirty with its own unrelated work; preservation compares against baseline instead of claiming globally clean.

## Completed GLM5.3/NIM data/replay report

The following is the specialist's original report. It is **review input**, not a blanket sign-off. Parent corrections above and the CONTRACT/MASTER_PLAN take precedence where proposals disagree. No report's claims of whole-repo absence, exact capture density or live DB fields are accepted without cited/source/runtime evidence.

---
# Atlas-style upgrade of the Solstice price/node chart — READ-ONLY research report

Scope audited: the ticker candle chart (`PriceNodeHistory`) embedded in the Solstice/Skylit heatmap dashboard, its backend data plane, the heatmap recorder, and GEX/VEX producers. 29 read/search calls used. Everything in §1 is code-verified with citations; §4–§7 are proposals. The pasted Atlas guide was treated as feature reference only.

## 1. Findings (code-verified)

### 1.1 Chart surface and callers
- The chart to upgrade is `frontend/src/components/heatseeker/PriceNodeHistory.jsx`, mounted at `frontend/src/components/heatseeker/SkylitDashboard.jsx:634` (import at `:2`). A second consumer exists: `frontend/src/components/TrinityView.jsx:479` calls the same endpoint. Jest mocks exist at `SolsticeCanvas.r11.test.jsx:11` and `agent/ScreenContextLifecycle.test.jsx:19` — the component is a seam other tests already stub.
- Render is Plotly (`PriceNodeHistory.jsx:6,70-77`); traces built by `priceNodeTraces.js:3-27`: one candlestick trace plus per-node horizontal line segments, `connectgaps: false`, node segments clipped to `min(duration, 900 - node_age)` (`priceNodeTraces.js:13-16`). Node label carries only level + known-at time (`:21`) — no sign, no magnitude, no king concept today.
- "Replay" today is a client-side reveal: a position slider + 250 ms interval playback over pre-joined frames (`PriceNodeHistory.jsx:35-42, 79-88`). It never re-computes available-at state; correctness comes entirely from the backend join.
- `AskLodestar` refuses chart-context questions in price-history mode (`AskLodestar.jsx:13-26`) and `SkylitDashboard.jsx:458,811` tags `displayMode:"price-history"` — any new chart modes must keep that context contract intact.

### 1.2 Price endpoint and provider
- `backend/routes/price_history.py:25-68` — `GET /api/heatseeker/price-history/{ticker}?days=&query_key=`. Router included at `server.py:3741-3744`. `days` is bounded 1–20 (`price_history.py:26`); interval is **hardcoded** from `days`: `days==1 → (DAY, ONE_MINUTE, 60)`, `≤5 → (WEEK, FIVE_MINUTES, 300)`, else `(MONTH, ONE_HOUR, 3600)` (`price_history.py:33`). There is no interval/session query parameter.
- Provider is Public.com only: `fetch_bars_by_interval` (`services/public_api_adapter.py:1158-1190`) → `PublicBroker.get_bars` (`services/public_api.py:650-680`). Vendor aggregations: ONE_MINUTE, FIVE/TEN/FIFTEEN/THIRTY_MINUTES, ONE_HOUR, ONE_DAY, ONE_WEEK, ONE_MONTH, THREE_MONTHS, SIX_MONTHS, ONE_YEAR; periods DAY→TEN_YEARS/ALL (`public_api.py:663-665`). Adapter-level timeframe vocab: `1Min…1Month` (`public_api_adapter.py:66-79`), alpha-style interval map `1min…monthly` (`:917-927`). **No 3m/2m/7m/90m and no 1H→4H**; anything Atlas-like custom interval must be aggregated client- or service-side from 1m/5m.
- Sessions: default is regular-only; `sessions="all"` opts into pre/after/unknown buckets (`public_api_adapter.py:930-1001`). Unknown vendor buckets are labeled `"unknown"`, never silently served as regular (`:959-963` — same honesty rule the orb work must copy). `PublicBroker.get_bars` exposes a `trading_session_toggle` kwarg (`public_api.py:656`) but **no caller passes it** — ETH support is unwired.
- Instrument identity: `_normalize_symbol` only uppercases/strips `^` (`public_api_adapter.py:167-169`); index family resolved via `resolve_public_instrument_type` (`public_api.py:1124-1139`): SPX/SPXW/NDX/RUT/VIX → `INDEX` (quote) or `UNDERLYING_SECURITY_FOR_INDEX_OPTION` (chain). Quote answers are symbol-matched, never substituted (`_matching_quote`, `public_api_adapter.py:148-164`). **No futures (ES/NQ), no cross-product or "derived" mapping, no ratio-lock exists anywhere in the audited code.**
- Budget: one token per fetch (`price_history.py:37-44`); `BudgetExhausted → bars=[] → price_status:"unavailable"` (`price_history.py:38-39,49`). Bucket: capacity 60, refill 8/s, MAX_INFLIGHT 4, 429 cooldown 15→300 s (`services/public_budget.py:34-38`).
- `services/market_bars.py` is a separate C13 consumer with stale-on-error cache (TTL 120 s intraday / 6 h daily, `market_bars.py:29-30`), OHLC quarantine (`:96-121`) and RTH day-slicing (`:141-153`). The chart route **deliberately bypasses** it so a failed fetch is visible, not mislabeled fresh (`price_history.py:34-35`).

### 1.3 Recorder, snapshot schema, retention
- `services/heatmap_history.py` — "Solstice recorder + deterministic replay (T09)" (`:1-12`). `heatmap_snapshots_v2` DDL (`:97-105`): `snapshot_id` PK, `ticker, query_key, expiries, spot, data_source, exposure_basis, formula_version, asof_ts, received_at, n_contracts, n_usable, digest, strikes_json, walls_json`; additive migrations add `coverage/quality/scenarios/interactions/grid_meta/grids/metrics_full/context` JSON columns (`:180-197`). This additive-column pattern is the sanctioned way to extend the recorder.
- `record_snapshot` (`:342-501`): single-writer lock + one transaction (BEGIN→dedup-verify→insert header+contracts→COMMIT; failed commit rolls back, `:490-500`). Identity is content-addressed via `observation_id_for` (`:71-81`); idempotent retry completes missing contracts. `walls_json` persists `payload["metrics"]["walls"]` verbatim (`:371,448-457`), and `strikes_json` stores up to 500 strike rows (`:456`).
- **No retention/pruning exists** — the only DELETE is the crash-recovery dedupe (`:400-403`). DuckDB growth is unbounded; any orb history inherits this.
- Capture is not guaranteed: `routes/solstice.py:265-317` `recorder_health` reports `worker_state ∈ {absent, wired_off, active}`; the scheduled price-path recorder is explicitly "a commissioning item" (`routes/solstice.py:324-333`). Historical orb density is therefore bounded by whatever the capture worker has actually been doing.
- Read path for the chart: `read_snapshots` selects 9 columns with `TRY_CAST(asof_ts AS TIMESTAMPTZ)` range + `LIMIT 50001` (`price_history.py:14-22`); truncation flagged (`:59-61`); `node_status:"unavailable"` on DB error, `"not_loaded"` when no bars (`:48-58`).

### 1.4 Walls, sign and magnitude provenance
- Walls are produced per build: `server.py:1519-1524` — `discover_walls(strikes|vendor_rows, spot, scope={"symbol", "formula":"gex.v2"})` → `metrics["walls"]`, `metrics["nearest_walls"]`, `metrics["nearest_by_side"]`; per-wall breakdown via `wall_metric_breakdown` (`server.py:1528-1530`); off-screen landmarks (`:1536-1541`). Wall dicts carry `wall_id, low, high, mid, members` (verified shape in `tests/solstice/test_solstice_slice2.py:279`, `tests/fixtures/wall_desk_fixture_v1.py:40`) and wall-metric contexts carry gross/net magnitudes (`tests/agent/test_display_map.py:153`).
- **The discard point is `recorded_nodes`** (`services/price_node_history.py:39-58`): it keeps only `id/level/low/high` from `walls_json` — sign, magnitude, gross/net, and membership are dropped on the floor at read time. The persisted `walls_json` likely already contains magnitude for recent snapshots, but this was **not verified against a live DB row** (see blockers).
- `wall_events_v1`, `node_lifecycle_v1`, `wall_last_state_v1` tables exist (`heatmap_history.py:106-121`) — wall identity lifecycle is already a first-class recorded concept.

### 1.5 GEX/VEX outputs and scale discipline
- Display GEX is the S² scale: `sign * gamma * OI * 100 * spot² * 0.01` (`services/gex_aggregator.py:139-164`); sign is +calls/−puts dealer convention; king-node analog already exists as `argmax(gex_1d)` (`gex_aggregator.py:412-420`); zero-gamma crossings via interpolation (`:453-489`); `weight_basis` is explicit (`:441-442`); optional short-DTE volume-for-OI substitution is env-gated and tagged (`:75-88, 374-394`).
- **Two different "VEX" exist and must never be mixed** (F20 contract, `gex_aggregator.py:41-53`): the aggregator's `vex_surface` is VOMMA-based S²; the canonical Solstice VEX is VANNA-based — `services/gex_core.py`: `VEX_MODEL_VERSION = "local-bs-vanna.v1"` (`:1496`), per-strike `vex_net_1volpt` (`:1501-1541`), 2D grid with `exposure_basis:"VEX_1VOLPT"`, `formula_version:"gex.v2"`, `missing_vanna_inputs/quarantined/invalid_type` counters and `NO_VEX_COVERAGE` reason (`:1643-1709`). Dollar-VEX convention: `vanna*oi*100*spot*0.01` (`bs_greeks.py:81-88`).
- VEX rides every display path with its own status, never zero-filled: `server.py:1038-1065` attaches `vex_grid, vex_strike_gross, vex_meta{exposure_basis, model, status, reason, missing_vanna_inputs, …}`; charm gets the same honesty rule (`:1043-1052`). Per-expiry vanna (vanna_v1, units separate from vomma) is computed by `services/solstice_vanna.py:19-46` and attached at `server.py:1889-1892`; it is persisted into `context_json` by the recorder (`heatmap_history.py:437-444`).
- Additional live VEX consumers: `routes/analytics.py:150-214` (`/vanna-exposure`), exposure alerts `RULE_VEX_WALL` (`services/exposure_alerts.py:4-35`). The frozen-scale rules in CLAUDE.md (S¹ vs S²) apply unchanged to any orb magnitude.

### 1.6 Available-at join and scope identity (the part to preserve)
`services/price_node_history.py` is the semantic core the Atlas-style upgrade must not break:
- `MAX_NODE_AGE_SECONDS = 900` (`:12`); known-at = `max(asof_ts, received_at)` (`:82-85`); node age measured from observation, not arrival (`:115-118`).
- Scope identity = `query_key|expiries…|formula_version|exposure_basis` (`scope_id`, `:61-72`); scopes never mix; default scope = latest snapshot's scope, and later-arriving different views cannot hijack the default (`:98-104`).
- Node levels are never backfilled from today's chain or carried across gaps (`:1-5, 119-122`) — this is exactly Atlas's "Scroll as replay" honesty rule, already enforced server-side.
- Frames annotate `snapshot_id, nodes_known_at, node_age_seconds` (`:119-122`); route adds `duration_seconds/bar_seconds` per frame (`price_history.py:63-64`) and summary keys (`candles_with_recorded_nodes`, `node_max_age_seconds`, scopes, statuses).
- The recorder-side equivalent is `replay_snapshot`'s known-at join (`heatmap_history.py:868-915`): only rows with that `snapshot_id`; late revisions are separate rows, never merged.

### 1.7 What does not exist (verified absence)
- **No trade tape, no aggressor-side, no CVD/footprint source**: bars are OHLCV only (`public_api.py` bar shape; `market_bars.py:114`), quotes carry `bid_size/ask_size/volume` (`public_api.py:69-92`), option contracts carry `volume` + NBBO (`:111-145`). Volume Profile/TPO are *approximable* from bar volume; CVD is not derivable from anything in these providers.
- **No dark-pool prints** in any audited provider.
- **No streaming**: every path is httpx request/response (`public_api.py:236-247`); chart refresh is manual reload (`PriceNodeHistory.jsx:56`). "Realtime values" à la Atlas would be poll-based at best, budget-capped at 8 tokens/s refill.
- **No proxy volume for index products** (no SPXW→ES anywhere), **no cross-product derived mapping**, **no projection/past-last-candle exposure zones**, **no ETH session on the price-history route**.

## 2. Reuse inventory
| Need | Reusable piece |
|---|---|
| Candles + honest gaps | `priceNodeTraces.js`, `build_history` frame contract (`price_node_history.py:123-127`) |
| King-node math | `gex_1d` argmax/min + zero crossings (`gex_aggregator.py:412-423, 453-489`) |
| Signed VEX per strike/expiry | `compute_vex_grid_local` + meta contract (`gex_core.py:1643-1709`; `server.py:1054-1062`) |
| Per-expiry orb filter | `expiries` already in scope_id + `expiries_json` column (`heatmap_history.py:100`; `price_node_history.py:61-72`) |
| Wall bands + identity | `walls_json` verbatim persist (`heatmap_history.py:448-457`); `wall_events_v1/node_lifecycle_v1` |
| Additive schema evolution | `ALTER TABLE … ADD COLUMN IF NOT EXISTS` migration loop (`heatmap_history.py:180-211`) |
| Unavailable-not-zero status | `price_status/node_status` pattern (`price_history.py:48-58`); `vex_meta.status/reason` pattern |
| Session honesty | `_session_label` unknown-bucket rule (`public_api_adapter.py:959-969`) |
| Budget discipline | `public_budget` acquire/release + `BudgetExhausted` structured degrade |

## 3. Blockers / unknowns
1. **Live `walls_json` field inventory unverified.** Fixtures show `low/high/mid/members` (and gross/net in wall-metric fixtures), but whether production snapshots persist a signed magnitude inside `walls_json` must be confirmed from a real DuckDB row before the orb contract can rely on it. If absent, magnitude exists only in `strikes_json`/`wall_metrics` — still recoverable without fabrication.
2. **No historical exposure may be invented**: orbs sized for past candles can only come from snapshots actually recorded; capture worker state (`routes/solstice.py:302-316`) governs depth. Early charts will legitimately show gap-heavy orbs.
3. **Interval vocabulary is vendor-bounded**; custom/calendar intervals require local aggregation and an explicit `aggregated_from` provenance tag (proposal, not built).
4. **No aggressor-side/volume-delta feed is entitled** — CVD/Flow-style panes are out of scope until a tape provider is approved (ADR-0002 routing would govern any new source).
5. **`days≤20` + `LIMIT 50001`** cap replay depth; longer horizons need pagination or a `from/to` design.
6. **Query-key/scope UX**: multi-scope handling exists (`PriceNodeHistory.jsx:54-55`) but a "Front/To-Friday" style expiry selector would change `query_key` semantics — must ride the existing scope mechanism, not bypass it.

## 4. Recommended design (proposals)
**Contract v2 (additive, versioned).** Keep `/api/heatseeker/price-history/{ticker}` and extend the frame payload; gate via `?schema=v2` (default stays v1 so TrinityView and tests are untouched):
- `nodes[]` entries gain `magnitude_net` (signed, S² display scale for GEX view; `VEX_1VOLPT` scale when the VEX view is requested), `magnitude_gross`, `basis` (`OI|VOLUME_SCALP|OI_UNKNOWN`), `model` (`vendor-supplied-greeks|local-bs-fallback|local-bs-vanna.v1`), `is_king` + `king_ratio` computed **within a single snapshot** (never across time), and `status/reason` when inputs were missing.
- New top-level `contract_version: 2`, `exposure_view` (`gex|vex`), and `node_provenance: {formula_version, exposure_basis, scale: "S2-display"|"VEX_1VOLPT"}` so the frontend can never mix scales (mirrors `vex_meta`, `server.py:1054-1062`).

**Recorder additions (no fabrication).** Add one additive column `heatmap_snapshots_v2.orbs_json VARCHAR` via the existing migration loop (`heatmap_history.py:180-197` pattern), populated in `record_snapshot` from data already in the payload: per-wall `{wall_id, low, high, mid, net, gross, basis, model}` sourced from `metrics.walls` + `wall_metrics`/`gex_1d`/vex grid of that same snapshot. Old rows: `orbs_json IS NULL` → frontend renders the current unsigned line style with an explicit "magnitude not recorded" state. **Never backfill** — consistent with "Nodes are shown only when recorded" (`price_node_history.py:127`).
- Extend `read_snapshots` (`price_history.py:14-22`) to select `orbs_json`; extend `recorded_nodes` (`price_node_history.py:39-58`) to parse it with the same defensive `_positive`-style checks (signed variant needs a `_finite_signed`).

**Chart (frontend).** In `priceNodeTraces.js`: render orbs as Plotly `marker` circles sized by `|magnitude_net|` (clamped), color by sign (positive/negative palettes), king marked distinctly; per-frame duration clipping already correct (`priceNodeTraces.js:13-16`). Keep the reveal-based replay; add interval selector limited to vendor-native steps (1m/5m/15m/30m/1H) mapped to route params; any 3m/90m/weekly-Monday interval must be labeled `aggregated` and computed only from vendor-native bars.

**Cross-product / derived (explicitly deferred).** No mapping exists. If Nav wants SPY-on-SPXW-style derived orbs, it must be a *declared* mapping table with `derived: true` + ratio source tagged, and it fabricates nothing only if both products' snapshots were recorded. Recommend deferring; not required for the equity/ETF tickers the chart currently serves.

**Proxy volume / CVD (refuse for now).** Persist unavailability honestly (`status:"no_tape"`) rather than inventing buy/sell splits — matches the project's unknown-stays-unknown doctrine (`public_api.py:139-145`, `_session_label`).

## 5. Ordered small tasks (exact paths)
1. `backend/tests/services/test_price_node_orbs.py` (new, TDD, fails first): `recorded_nodes` parses `orbs_json` with sign/magnitude; null-safe; old rows degrade to current shape.
2. `backend/services/heatmap_history.py`: add `orbs_json` to DDL + migration loop + `_base_cols/_base_vals` in `record_snapshot` (persist from in-payload walls/metrics only).
3. `backend/services/price_node_history.py`: signed-magnitude parser + king-ratio computation inside `build_history` frame loop (per-snapshot only).
4. `backend/routes/price_history.py`: `schema=v2` param, `exposure_view` param, select+project `orbs_json`, statuses `node_magnitude:"recorded|not_recorded"`.
5. `backend/tests/routes/test_price_history_v2.py` (new): v2 contract, scope isolation unchanged, truncation + budget-exhausted paths unchanged.
6. `frontend/src/components/heatseeker/priceNodeTraces.js`: orb markers (size/sign/king), no-bridge rule kept.
7. `frontend/src/components/heatseeker/PriceNodeHistory.jsx`: interval selector (vendor-native only), magnitude-legend + "not recorded" chip; keep `displayMode:"price-history"` context intact.
8. `frontend/src/components/heatseeker/priceNodeTraces.test.js` + `PriceNodeHistory.test.jsx`: extend; no xfail/skip.

Forbidden-file check: none of the proposed tasks touch `services/ml/inference.py`, `services/dash_ui.py`, `tests/conftest.py`, model artifacts, `frontend/App.js`, or env/package files. `gex_history.py` (ML feature scale) is untouched.

## 6. Acceptance tests
- `recorded_nodes` returns `{level, low, high, magnitude_net, magnitude_gross, basis, model}` from an `orbs_json` fixture; `magnitude_net` may be negative; malformed JSON → `[]` (never a fabricated orb).
- `build_history`: orb for candle at time t uses only snapshots with `max(asof,received) ≤ t` and age ≤ 900 s; a scope with different `formula_version` never leaks into another scope's frames (extend the pattern of existing tests in `backend/tests/solstice/`).
- Route v2: `price_status:"unavailable"` when budget-exhausted; `node_status` unchanged; `records_truncated` still triggered at 50001; v1 response byte-identical when `schema` absent (TrinityView contract pinned).
- Recorder: inserting a snapshot without orb data → `orbs_json` NULL, v2 renders "magnitude not recorded", never zeros.
- Frontend: orbs never bridge across a node-less candle (`connectgaps:false` preserved); king marker matches argmax of `|magnitude_net|` within the frame's snapshot.
- Full backend sweep + `ruff check .` from `backend/`, `CI=true npx craco test --watchAll=false` from `frontend/` — no regressions (60% coverage floor is binding, `--cov=.`).

## 7. Risks
- **Scale confusion (highest).** S² display GEX vs S¹ ML features vs VEX_1VOLPT vs VOMMA-vex — a magnitude rendered from the wrong scale is a silent lie. Mitigate with mandatory `scale`/`basis`/`model` fields on every orb and a golden test pinning them (oracle pattern of `test_gex_aggregator_oracle.py`).
- **Replay honesty regression.** Any "fill the gap" convenience breaks the recorded-only invariant that `price_node_history.py:1-5` guarantees; reviewers must reject backfill PRs on sight.
- **DuckDB growth.** Adding `orbs_json` widens every row; no retention exists (`heatmap_history.py` has no pruning). Flag to Nav; a retention policy is a separate decision, not this feature.
- **Budget contention.** New interval options multiply `fetch_bars_by_interval` calls against the shared 8/s-refill bucket (`public_budget.py:34-38`) used by the live heatmap path; the chart must stay single-fetch per load (it is today, `price_history.py:37-44`).
- **Snapshot-dependence.** Orb quality is a direct function of capture-worker uptime (`routes/solstice.py:302-316`); a stalled worker yields gap-heavy charts that will be reported as "the feature is broken" — ship with the recorder-health status surfaced next to the chart.
- **Two consumers.** TrinityView shares the endpoint; keep v1 stable behind `schema=v2` and pin both in tests.

## Independent fallback refutation

Reviewer: bounded native-model fallback, explicitly **not GLM/NIM**. Runtime receipt: delegation `deleg_6f00a38d`, duration97.71s. The reviewer returned “revise before implementation handoff,” eight concrete findings, and did not claim tests/network/edits. Parent applied the plan corrections below; this is not application readiness approval.

### IR01 — HIGH: Final OHLC visibility

Disposition: **applied**. CONTRACT: review end_time<=cursor, faithful recorded revision arrival predicate, inferred end never sufficient; B01/B15 future intra-bar/correction fixtures.

### IR02 — HIGH: Incomplete metric board and supersession

Disposition: **applied**. CONTRACT: requested/observed per-channel coverage, disable full-scope rankings on incomplete board, separate observed-subset identity, invalid newer observation supersedes old display; B02/B07 fixtures.

### IR03 — HIGH: Release DAG deadlock

Disposition: **applied**. Task variants: B04 incumbent/candidate, B13 discovery/account, B17 local/account, B23 calendar/approximate/tape; B28 conditional enabled-capability closure and R1/R2/R3 profiles; shared router/capability ownership serialized.

### IR04 — HIGH: Private read identity and owner isolation

Disposition: **applied**. Parent independently read backend/auth.py69-130: deployment key returns True, general GET skipped. CONTRACT and B13/B18 now require approved principal on all private reads/mutations; unavailable discovery is not account feature acceptance.

### IR05 — HIGH: Per-pane scope compatibility and stale context

Disposition: **applied**. MASTER/CONTRACT/B11/B24: presentation allowlist, per-destination scope/calendar/capability resolution, atomic generation invalidation and late/removed-pane refusal.

### IR06 — MEDIUM: Incomplete adapter and export ownership

Disposition: **applied**. MASTER adapter now has inverse/pane-series-qualified coordinates, crosshair set/clear, viewport invalidation, null semantics, interaction suppression and idempotent unsubscribe; engine capture separate from workspace DOM composition.

### IR07 — MEDIUM: VANNA metadata identity

Disposition: **applied**. CONTRACT and B02/B07 require channel model+basis+unit; parent gex.v2/key VEX insufficient; contradictory archived identity unavailable.

### IR08 — MEDIUM: Replay alert writes and positions leakage

Disposition: **applied**. CONTRACT/MASTER/B18/B25: default refusal of replay-origin live mutations, role revision/gap resets crossing continuity, hide current positions in faithful practice and segregate review-only nonhistorical values.

Implementation remains held at each affected feature boundary until actual fixtures, source coverage, identities, entitlements and browser measurements pass. Discovery-unavailable can close discovery, never implement or accept a feature. The repaired release graph permits a supported Plotly/local/bar-calendar release without inventing completion of account/tape/candidate branches.

Review limits retained: no live archive-grid completeness, provider timestamp semantics, full account model, alert evaluator behavior, measured engine export/attribution or browser performance was established by this review. Those are explicit block prerequisites, not silently settled assumptions.

## Round2 research reconciliation and parent source-backed replacement

Delegation `deleg_cd1434d1` returned4 runtime statuses, not4 successful reports. Guide lane failedHTTP401; interval refuter failedHTTP402; code-audit was marked completed but returned corrupted text and did not create its required artifact. All three contribute failure evidence, not findings. The33-line saved LWC API report was readable and source-backed; its blanket “no blockers” conclusion was rejected. Parent independently fetched chart/time-scale/series/panes/primitives APIs and actual master NOTICE; adoption/browser/license gates remain.

No credentials/provider configuration were changed and no same-provider fanout was retried. Some failed children disclose OpenRouter GLM identity, while the other child identities were not established; this batch is not labelled successful NVIDIA NIM research. Parent runtime is openai-codex/gpt-6.1-sol. The original independent eight-finding review remains preserved. The failed second-round refuter was replaced by an explicitly parent inline adversarial pass, not a fabricated independent review.

Parent retrieved detailed GEX-VWAP, VWAP, CVD, Volume Profile, TPO, drawing presets, flow/dark-pool articles and OHLCV API pages, with source/hash receipts in EVIDENCE.json.32 atomic requirements are added asC112–C143; originalC001–C111 and all29 implementation blocks remain. Per-block future fixture criteria bind every added row. No feature readiness transferred from a source read.

Actual no-network standalone characterization confirmed missing volume=>0, boolean volume=>1, positive infinite volume accepted and unparseable date inputs retaining all sessions in market_bars helpers. Maintained calendar returned the2026 Thanksgiving closure/half-day and DST-varying UTC opens for March6/9. These are narrow observed behaviors, not complete provider/calendar commissioning or a source bugfix. Strictness belongs in the new canonical boundary with legacy characterization.

Adversarial dispositions: measured side totals do not prove price-at-trade precision; native study panes do not implement independent workspace charts; documented APIs do not prove runtime performance/export; expiration clocks do not supply ETH/futures schedules; bar-TPO does not unconditionally need a tape. Vendor video/docs conflicts and unpublished formula/TPO defaults remain explicit reviewed holds. All additions are proposed acceptance criteria.


