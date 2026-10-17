# Proposed chart/v1 data and temporal contract

**Status: design proposal.** This contract is not served by the current backend. Keep `/api/heatseeker/price-history/{ticker}` and its existing consumers unchanged. B01 fixes the shared schema and characterizes provider timestamps before new consumer code is admitted.

## HTTP interface and bounds

Proposed route on existing price-history router: `GET /api/heatseeker/chart/v1/{ticker}`.
- `ticker`: validated display symbol resolved to explicit provider symbol, asset class, exchange/calendar/tick-size/multiplier. Reject invalid or unsupported identities; never strip ambiguity by mapping an index onto an ETF silently.
- `from`, `to`: timezone-aware ISO8601 UTC instants, `from < to`; half-open range `[from,to)`. Proposed synchronous range cap20 market sessions for intraday; wider ranges require cursor pagination and separate provider entitlement. Cap25000 base bars/50000 snapshot records per page, with explicit coverage/truncation.
- `interval`: `1m|3m|5m|10m|15m|30m|1h|2h|4h|1d|1w`, or validated custom `Nm` with integer N1–1440. These are requested chart labels, not automatic provider support. UI displays1H/1D while serialized tokens remain fixed lowercase.
- `session`: `rth|eth`, resolved by instrument calendar; reject if unavailable rather than silently falling back.
- `exposure_view`: `gex|vex|both|off`.
- `scope_id`: bounded opaque identifier from server capability/scope inventory; max2000 characters. It binds actual expiries/formula/basis, never just a count.
- `cursor`: opaque server pagination token bound to the entire resolved query; not an arbitrary SQL offset. Page and budget caps apply before DB work.
- `replay_at`: optional aware UTC instant ≤to; meaningful only with declared temporal capability. It does not change live broker/alert state.

Timezone is a display preference, not a server data selection parameter. If provider choice, adjustment mode or aliases vary, include them in resolved query/cache identity. B01 may revise proposed limits only with a measured fixture/provider justification; frontend and backend schema must change together.

Status policy:422 invalid request;404 unsupported instrument; bounded provider/database failure returns an explicit capability/status response or suitable503 with no fresh-market claim;429 includes retry guidance. Keep consistent with existing auth/public-read conventions. Every private workspace/drawing/alert read (including GET/list/history/export) and mutation requires an approved authenticated principal/owner resolver. These are not public market-data routes. Adding a public chart read does not authorize public private-data reads or writes.

## Response fields

Top level:
- `schema_version: "chart.v1"`, `request_id`, `generated_at`, `query_id`, `next_cursor`, `truncated`.
- `instrument`: `display_symbol`, `provider_symbol`, `asset_class`, `exchange`, `calendar_id`, `tick_size`, `multiplier`, `price_currency`, `volume_symbol|null`, `series`, `mapping_version|null`.
- `query`: requested/resolved interval, interval duration or calendar label, session, range, adjustment mode, exposure view, actual scope details, aggregation source.
- `capabilities`: list of `{id,status,reason,evidence_source,verified_at,temporal_support}`. Status supported/degraded/unavailable; permission missing differs from empty market data.
- `price_state`, `exposure_state`, `tape_state`: per-stream `{status,source,event_time,received_at,last_success_at,age_seconds,coverage,reason}`. `generated_at` only describes server response generation. Cached market data retains original observation time.
- `candles`, `exposure_readings`, optional eligible `overlay_events`; `warnings[]` with bounded typed reason codes.

Candle record:
```
start_time, end_time                 # aware UTC, session/calendar boundaries
open, high, low, close               # finite positive numbers, coherent OHLC
volume                              # finite nonnegative measured number or null
session_id, session_class           # regular/extended/unknown, not guessed UTC
complete                            # completion at the selected cursor
provider_event_time                 # actual source time or null
received_at, available_at            # real capture/arrival times or null
availability_quality                # recorded / inferred_bar_end / unknown
source, revision, adjustment_mode
aggregated_from, coverage_fraction   # base interval and known actual coverage
```
Do not synthesize a zero-trade flat candle for missing bars. If showing a line across a market closure, it is display geometry, not a fabricated source observation. Missing volume and zero volume differ. Duplicates resolve by a documented source revision/arrival rule; eventual corrections cannot overwrite the historical stream used for faithful replay.

Exposure record:
```
snapshot_id, scope_id, asof_time, received_at, known_at
actual_expiries[], formula_version, source, coverage
metric_channels: {
  gex: {status,unit,basis,model,values:[{strike,signed_value,gross_value?,status}]},
  vex: {status,unit,basis,model,values:[{strike,signed_value,gross_value?,status}]}
}
wall_roles[]                         # separate IDs/bands/roles, not strike orbs
```
Each channel must carry requested-versus-observed expiry/strike/input coverage and its own metric/model/basis/unit identity; contract-count coverage alone is insufficient. Default full-scope ranking is disabled on incomplete, malformed or contradictory inputs. An explicitly chosen observed-subset view has a distinct scope/coverage identity and prominent “observed subset, not full-board king” label; it never inherits the requested full-scope identity. A genuinely different narrower selected scope is valid only if its own complete inputs and timestamped selection are recorded. GEX display is S² convention with recorded basis; canonical Solstice VEX is VANNA `VEX_1VOLPT`/`local-bs-vanna.v1` with USD delta-notional change per+1vol point, not legacy VOMMA `vex_surface`. Require the canonical channel model/basis/unit together; its parent formula_version may legitimately remain `gex.v2`. A key called VEX or that parent formula alone cannot identify VANNA. Missing or contradictory channel identity is unavailable, never relabelled. Never recompute new historical Greeks from today's chains.

## Strict ingress parsing

Accept native finite numbers or explicitly grammar-validated numeric strings where the provider contract requires them. Reject booleans, null, empty/blank strings, arrays/objects, NaN and Infinity. Prices/strikes positive; volume nonnegative; exposure signed and may equal zero. JSON cannot encode NaN/Infinity: serializer must reject/quarantine them, not produce nonstandard JSON. Normalize numeric strike keys explicitly without losing decimal tick precision; use exact tick/decimal identity for equality and sorting.

Characterize old parser behavior rather than globally changing `_positive`/market-bars consumers. New strict parsing belongs to the new contract, with compatibility fixtures around old callers. Unknown values retain status and reason, not a synthetic numeric sentinel.

## Temporal algebra and replay modes

Exposure visibility at cursor R:
1. Same symbol/scope/model/basis; actual expiry membership matches.
2. `known_at=max(asof_time,received_at)` is a real recorded time, and `known_at≤R`.
3. Choose the newest observed source-asof among time-eligible readings **before** validating whether its values can be displayed; a newer malformed/incomplete observation supersedes prior valid display with an explicit degraded/unavailable state. Do not filter invalid rows out and silently revive the old board. A late older source-asof cannot rewind a newer state. Immutable revision identity and recorded arrival order break ties deterministically.
4. `0≤R-asof_time≤900 seconds` by current node freshness policy unless a separately versioned policy is approved.
5. No carried exposure across unknown source gaps or no-longer-eligible expiry boundaries.

**Important limitation:** the existing route joins nodes at a provider candle timestamp, not an explicitly characterized candle end. It exposes eventual historical OHLC without recorded revision-arrival history. Timestamp semantics must be measured/confirmed; never shift legacy joins by interval merely to make them look denser.

Support two honest modes:
- **Historical review:** finalized provider history may be available, but historical first-seen/revision availability is unknown. Completed-candle visibility is `characterized_end_time <= R`; never show the eventual high/low/close/volume before that end even in review. `inferred_bar_end` is permitted only as a characterized calendar endpoint for review and is never recorded arrival evidence. Display a “finalized history / revision timing unavailable” limitation; recorded overlays retain real known-at constraints. If start/end semantics cannot be characterized, cursor review is unavailable rather than guessing. Do not market finalized review as exact historical tape playback.
- **Time-faithful replay:** each candle/base event and correction has recorded availability evidence. Completed revision visibility is `availability_quality == recorded AND end_time <= R AND recorded_revision_available_at <= R`; unknown or inferred timing cannot satisfy it. Choose only an eligible revision, never the later final correction. Partial candles use only base events with event_time <= R and real recorded_available_at <= R within the current bucket; aggregate their eligible OHLC/volume with complete=false. If capture is absent, this mode is unavailable. No future final high/low/volume, normalization king, ratio, day flow total, session high or event classification may appear.

All pane clocks are UTC R. A QQQ pane uses latest eligible QQQ state at R, not SPY's frame index. A missing timestamp/arrival is unavailable, not replaced with R. The active cursor is not passed into live providers as a new current market reading. Random start uses a seed and eligible archived coverage; exact selected dates remain disclosed.

Flow/dark prints/corrections obey the same known-at principle: event time alone is insufficient when report time is delayed. Proxy/derived ratios require both source and target availability. “Latest ratio” during retrospective review is visibly distinct from no-lookahead practice.

## Exposure display math — independent of Greek computation

Only for a complete eligible metric/scope/cursor, `king_abs=max(abs(signed_value))` over its measured nodes. On incomplete inputs full-scope king/top-N/P-value ranking is unavailable by default; any intentionally selected observed-subset view is ranked only within its separate declared identity. `ratio=abs(value)/king_abs` only if king_abs>0. Fixed N chooses descending absolute strength, strike ascending tie-break. P-threshold keeps ratio≥P/100, inclusive. Measured all-zero board has no defined ratios; missing or incomplete board reports coverage, not zero king.

Proposed radius: `min(max_radius, max(min_radius, scale*sqrt(ratio)))`; opacity bounds independently applied. This changes screen geometry only. Canonical values and tooltip units stay unchanged; crosshair selection returns source identity, not a clamped value. Combined GEX/VEX uses separate normalization and distinguishable channels; there is no arithmetic sum. Scroll-as-replay normalization uses eligible current/past readings only. A global eventual-session maximum is forbidden in practice.

GEX/VEX exposure-centre studies must explicitly select absolute or signed weights in a reviewed contract. For signed weights, near-zero denominators are unavailable; calling an absolute-weighted centre a “gamma flip” is not justified. Preserve existing calculations under characterization instead of silently fixing domain docstrings.

## Native versus approximated studies

Every study declares `input_requirements`, `calculation_version`, `source`, `unit`, `approximation`, `replay_support` and independent instance ID/settings schema.
- Native OHLC MAs/bands need complete eligible windows.
- Session bar-VWAP may use HLC3 and measured bar volume only with approximation badge; traded VWAP needs tape. Zero denominator unavailable.
- ES proxy volume for SPX-family is explicit metadata, not SPX volume; futures data/calendar entitlement required.
- Options chain volume deltas are not a print tape and cannot generate Flow buckets. Sweep/leg/aggressor/open-close/score classifications remain unknown absent evidence.
- True delta/CVD/footprint need classified trade sizes and corrections; unknown volume separate.
- Exact volume-at-price requires actual trades; bar distribution is a distinctly labelled approximation. TPO requires documented time-at-price resolution and eligible interval coverage.
- Dark Pool is one real equity print at its exact price and known report time, not inferred direction or a scanner summary average.

## Persistence and interactions

Workspace: `schema_version`, `workspace_id`, `revision`, focused pane ID; pane list with stable pane ID, canonical symbol, interval/session/TZ/style/study instances/exposure settings; sync booleans; dock configs; drawing references; preferences. Never include API credentials, broker intents, broker account IDs or position records in portable JSON.

Drawing: `id`, `instrument`, `tool`, logical anchors, style, visibility/lock booleans and revision. Explicit false/zero choices survive defaults/serialization; use nullish rather than truthiness defaults. Presets capped50 and versioned. Imported strings render as text, never trusted HTML. Reject prototype keys, executable payloads and unsupported tools, enforce byte/object/point-depth caps.

Layout account sync needs an actual authenticated user identity. Existing deployment API key is not automatically a per-user account model. Owner/revision/quota and conflict/tombstone semantics must be designed before cross-device promises. `backend/auth.py:69–130` returns True for deployment-secret checks, not a user principal; general verification skips non-mutating methods. Require principal/owner resolution on every private GET/list/export and mutation, and cross-owner denial fixtures. Neither a supplied owner ID, X-API-Key nor broker account identity supplies a user principal. B13 discovery may record unavailable while local layouts/presets continue. A single-owner deployment store is a separate explicitly approved scope, not multi-user account sync.

Alerts: fixed price and follow-role identity are separate; tick-rounded price, symbol, scope, role/level, once/repeat, cooldown, enabled/revision. No alerts fire from stale/no-price/no-role data. Replay events never enter live evaluation; replay-origin live-alert create/update/drag/enable mutations are refused by default under server-resolved view-session mode, not a client boolean. A followed role moving the target alone does not constitute a price touch: reset crossing continuity at a target revision or missing/stale-price gap and wait for a fresh eligible market observation under the versioned touch predicate. Server owns evaluation and idempotent notifications; chart visibility has no authority to suspend server alerts. Any future chart order is independently approved and refused during replay by server-owned mode/session evidence, not a trustworthy client boolean.

Current live positions are hidden during time-faithful practice by default; any review-only current-position display is explicitly segregated and labelled nonhistorical, excluded from chart AI and historical confluence. Read-only positions are not automatically no-lookahead. Emergency cancel/close paths remain independent of any future replay order-submit refusal.

## Pane identity and interaction contracts

Synchronize an allowlisted set of presentation preferences only. Resolve actual expiry membership, scope IDs, session calendars, source capability and metric identity per destination instrument; never broadcast one pane's opaque scope ID or trade context to another. Incompatible settings remain local or unavailable with reasons. Focus/symbol/scope/cursor changes atomically invalidate prior chart evidence and increment a context generation. Only an exact pane+query+generation server-resolvable descriptor can republish; late old-pane results, pane removal and replay exit cannot restore stale AI evidence. Transaction IDs prevent loops but are not identity validation.

## Golden fixture contract

Fixture files are synthetic test inputs, clearly labelled, never alleged historical market output. Cover exact clock boundaries, scope separation, missing/zero metrics, unavailable calendars/provider sessions, partial corporate-adjusted bars, all false settings, delayed print/correction arrival and malformed imports. Test command outputs are captured per task. This design document contains no fake API response, benchmark or fabricated trading result.

## Round2 detailed study/portability acceptance

The32 additional capability rows C112–C143 and block round2_acceptance_invariants are normative future acceptance criteria. They are not current implementation status.

1. **Exposure VWAP:** per-instance selected scope and permitted node filter; per-minute eligible boards produce centre/side-band values only under a reviewed versioned weighting formula. No board => gap, never prior-minute carry. Opening envelope default15m, valid8–60m, requires at least8 measured minute slots within the selected opening window and freezes only at its end; session envelope uses cursor-eligible extrema only. No future opening-window completion is exposed during replay. SPXW Trinity combine remains unavailable until same-unit known-at mapping/combination is approved.
2. **VWAP/CVD:** price source HLC3/Close and band basis deviation/percent are settings; bar-based versus tape-exact method is explicit. CVD/Volume use the same reconciled buy/sell/unclassified figures; classification provenance and tolerance accompany source data. Unknown volume is not zero or inferred direction. CVD zero resets, missing candles, provisional wick/source-minute precision and revisions are declared. Proxy-volume joins require verified price/volume clock alignment and never repurpose option-chain volume.
3. **Profiles:** VP default68% value area and200-bar fixed depth are reference choices; bin allocation method is versioned. POC ties downward; equal adjacent-area expansion upward; stop rather than skip adjacent empty rows, reporting attained fraction when below target. Zero-range bar allocation is pinned to a documented tick-aligned row; price allocation from OHLC ranges remains approximate even if side totals are measured. TPO occupancy does not measure exact tick residence. One TPO per workspace pane; fifth-period POC/single-print admission, daily composite20 eligible bars and next-session naked-level visibility; no unknown-gap proof of untouched. Auto row sizing uses only cursor-eligible range history. TPO VA percentage and IB duration are reviewed parameters, not invented vendor defaults.
4. **Presets:** starred > active > built-in priority applies independently per tool family. Selected drawing config snapshots do not mutate when named preset is edited. Preset edits save only through explicit Update/Save as; dirty state and false options roundtrip. Account quotas/conflicts are server-ordered and owner-scoped under the approved identity model; local storage never claims remote sync.
5. **Intervals/pages:** raw boundary admission occurs before legacy missing-volume/boolean/infinite coercion. Sorted immutable base events with a query/dataset-bound continuation cursor feed full bucket inputs across page seams; stalled cursor is an error. Intraday buckets start at the actual selected session open, end at session boundary, and expose incomplete final buckets. Equity1W membership uses Monday calendar weeks with actual open sessions and no padding; ETH/futures use verified independent calendars. Display TZ never changes membership. Prohibit silent cap clipping, interpolation and substitution of RTH for requested unavailable ETH. A page/coverage gap invalidates dependent unqualified study claims.
6. **Export:** engine capture explicitly controls primitive/crosshair inclusion; workspace DOM composition is separate. Series-move price-scale rebinding and historical-bar update/insert policy have adversarial adapter fixtures. Publicv5.2 docs and upstream master NOTICE do not approve a package install, a runtime benchmark or a release license inventory.

