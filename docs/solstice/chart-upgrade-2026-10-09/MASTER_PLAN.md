# Solstice ticker/candlestick workspace — implementation plan

> **For Hermes:** Use subagent-driven-development for implementation, with separate spec and code-quality review. For OpenCode Spark 1.3: start with `SPARK_HANDOFF.md`, then execute one task from `IMPLEMENTATION_TASKS.json` at a time. This packet is planning, not permission to execute all phases or alter frozen files.

**Goal:** Upgrade the existing React price chart into an Atlas-inspired, provenance-aware ticker workspace while preserving the current heatmap, Trinity workflows, financial conventions and execution safeguards.

**Architecture:** Put a chart workspace behind the existing `PriceNodeHistory` entry point. Separate normalized market/exposure data, deterministic replay, pane/layout state and engine rendering. Keep the current endpoint and Plotly implementation as a working fallback; migrate only the candle workspace to a dedicated financial-chart engine after a measured spike and explicit dependency approval.

**Tech stack:** Current repository declares React 19, CRA/craco, Plotly/react-plotly, TanStack Query, react-resizable-panels, FastAPI and DuckDB. Recommended candidate: Lightweight Charts 5.2.1, Apache-2.0, behind an adapter. Declaration is not installation: local `frontend/node_modules/.bin/craco` was absent during this audit.

**Scope:** Architecture/research only. No production code, runtime restart, dependency/config change, broker action or source migration was performed for this plan. Paths below are relative to `/Users/nav/Documents/GitHub/floww-2` unless otherwise stated. Verify current ownership and file hashes before implementing: this checkout has existing unrelated WIP.

## 1. Executive decisions

1. Keep the good heatmap intact. Build the ticker chart first; dock/reuse existing map components later. Do not replace `SkylitDashboard` or the application shell wholesale.
2. The first deliverable is reliable candles plus honest historical exposure, not an enormous toolbar. A pretty orb without signed magnitude and timestamp provenance is not acceptable.
3. Recommend Lightweight Charts for the eventual multi-pane price workspace, not for every visualization. It supplies chart/series/pane/coordinate primitives; it does **not** supply our drawings, profiles, replay, data feeds, indicators, persistence, alerts or trade engine.
4. Preserve Plotly as the no-install fallback and kill switch. Dependency adoption is gated because `frontend/package.json` is architect-frozen. Never use a CDN script to bypass that gate.
5. Treat GEX and VEX as separate signed measures. Do not sum unlike units or transplant vendor formulas into the repository. Preserve the S² display / S¹ ML distinction in `CLAUDE.md`.
6. Use bitemporal availability for every replay overlay. Missing archived values remain missing; today's option chain, today's price ratio, future extrema and future flow totals must never leak backwards.
7. Data-derived advanced features are capability-gated. Existing bars/chain volume are not a consolidated trade tape. Flow bars, CVD, footprint, true volume-at-price and dark-pool levels require separately verified evidence and entitlements.
8. Ship read-only chart position overlays before considering any chart execution. No live trading is part of this upgrade; replay is a non-executing mode at UI and server boundaries.

## 2. What exists now — verified source and runtime

### Actual candle path

`frontend/src/components/heatseeker/SkylitDashboard.jsx:634` mounts `PriceNodeHistory` with the current ticker and controlled open state. `PriceNodeHistory.jsx:25–33` fetches `/api/heatseeker/price-history/{ticker}`, aborts obsolete requests and checks response ticker identity. Its controls are period (1/5/20), opaque saved-view scopes, reload, replay play/pause, slider and show-all. It renders a lazy-loaded Plotly candlestick and line segments; height is 420px, UTC labels, pan/zoom and rangeslider (`:69–87`). Replay rebuilds the visible prefix every 250ms; there is no chart streaming subscription in this component.

`priceNodeTraces.js:3–27` returns a candle trace and gap-separated horizontal saved-node segments. These are **wall level lines, not signed magnitude orbs**. There is no interval/session/TZ control, drawing editor, indicator registry, chart workspace persistence or synchronized ticker panes in this component.

`backend/routes/price_history.py:25–68` ties history depth to aggregation: 1 day → DAY/ONE_MINUTE; ≤5 days → WEEK/FIVE_MINUTES; >5 days → MONTH/ONE_HOUR. It requests regular sessions only. Consequently “20 sessions” is an interface label/request choice, not a verified exact session count. There is no independent interval parameter. Its query reads `walls_json`, not signed per-strike exposure. It deliberately avoids `market_bars` stale-on-error behavior; budget/provider failure is not labelled a fresh read. Snapshot reads cap at 50,001 and report truncation after 50,000.

`backend/services/price_node_history.py:75–127` validates positive finite OHLC and aware timestamps, deduplicates bar timestamps, chooses one scope, joins only snapshots available by the **provider candle timestamp**, and expires node state after 900 seconds measured from source as-of. Availability uses `max(asof_ts, received_at)`. A late old reading cannot rewind a newer reading. Scope includes actual expiries, formula version and exposure basis. Preserve these properties and the old endpoint's timestamp semantics.

### Recorder reuse — important correction

The recorder is richer than the current price-history response. `backend/services/heatmap_history.py:414–464` writes named optional columns including `grids_json`, `grid_meta_json`, quality/coverage and context when the DB schema has them; base columns include `strikes_json`, `walls_json`, actual expiries, source timestamps, formula and basis. Therefore **do not assert that all signed historical exposure must be newly recorded**. First audit schema/row coverage and parse available archived grids. Older rows or missing metric scopes may still lack it. Add additive recorder coverage only for proven missing inputs; never destructively rebuild or relabel older archives.

`backend/services/market_bars.py` normalizes OHLCV, budgets upstream fetches, caches and deliberately serves stale bars on failure. This is useful infrastructure but not a provenance-complete chart contract. Wrap/extend with explicit freshness rather than weakening other consumers' behavior.

`frontend/src/components/flowseeker/chart/ChartModal.jsx` is a separate Flowseeker investigation modal displaying contract-history/net-premium lists, not the heatmap ticker candle renderer. Frozen `backend/services/dash_ui.py` is a different embedded Dash surface. Neither is the migration target.

### Live and test evidence

A real GET to `http://127.0.0.1:8000/api/heatseeker/price-history/SPY?days=1` returned HTTP 200 with 376 candles, 12 candles with recorded nodes, 60-second duration, and no truncation. Node keys were only `id`, `level`, `low`, `high`. This proves a sampled route response, not complete history, feed entitlement, zero latency or loaded-source identity.

Focused execution: root `tests/test_price_node_history.py` ran **8 tests, OK**; backend market-bars/Public-bars services and routes ran **53 passed, 27 warnings**. Full suites were not run. Frontend baseline invocation failed because local craco was missing; no frontend pass or browser benchmark is claimed. Detailed argv/output is in `EVIDENCE.json`.

### Preserve shared consumers and chart-context safety

`TrinityView.jsx:469–522` also consumes the legacy price-history endpoint for `WallPricePath`, an SVG recent-close path with wall-zone shading and an explicit VWAP-unavailable caption. Keep that response and behavior stable; it is not another full candle workspace to replace.

`SkylitDashboard.jsx:458–462` clears live heatmap context when price history is open; `AskLodestar` receives `displayMode="price-history"`. `AskLodestar.jsx:24–27` **currently refuses** price-history, replay and adjusted-map questions; its comment explains that the server admits only live Raw-map evidence. A context UI change alone cannot enable chart AI. P7 must first implement exact-surface/snapshot resolution and reviewed server admission, preserving existing refusals until that passes. AI must read the focused pane and cursor's server-resolved evidence, not client-asserted numbers, hidden future data or an unrelated ticker's map.

Additional verified naming trap: `gex_aggregator.py:41–53` calls its legacy VOMMA-based surface `vex_surface` while explicitly warning it differs from canonical Solstice VANNA VEX. `gex_core.py:1496–1509` defines `local-bs-vanna.v1`, USD delta-notional change per +1 vol point. The new VEX orbs must consume the canonical VANNA grid/`VEX_1VOLPT` metadata, **never** that legacy VOMMA alias. Existing argmax helpers are reuse candidates, not proof they rank absolute magnitude or satisfy the new signed-king contract.

## 3. Reference evidence and intended experience

The supplied Atlas guide and public primary docs are design references, **not our existing implementation**. The supplied video was researched using its successfully retrieved English timestamped transcript; no frame-by-frame visual review or measurement of undocumented slider values is claimed. `SOURCES.md` and `VIDEO_TRANSCRIPT.md` preserve evidence and contradictions.

Video-supported index workspace:
- Around 00:38–01:34: three ticker panes; link interval, time and settings. Symbols are SPX, SPY, QQQ in the walkthrough, arranged to match Trinity panels.
- Around 02:05–02:28: Front exposure for the index routine. Front means nearest tradable expiry, **not unconditionally today's date** despite the spoken shortcut.
- Around 02:54–05:19: Trinity focus/king, king-relative display, precision, dim/fade, palettes and 5/10/15-minute velocity halo preferences. Reuse the existing heatmap controls; this is not a new heatmap project.
- Around 06:02–07:57: top-N or king-relative node threshold; narrator picks P25 and Mono candles / Default exposure palette.
- Around 08:09–10:25: filtered flow drilldown and dark-pool levels. Transcript mentions top 10 / 30 days / hover; public article limits differ. Make validated settings data-driven instead of treating the video as an API schema.
- Around 10:31–11:37: VWAP, EMA/SMA/Bollinger, GEX VWAP, profiles and help; around 11:43–12:28: drawings; around 13:34–14:17: import a layout JSON file.

Suggested shipped preset: `Index desk` with SPX-family, SPY and QQQ panes; independent price scales; interval/time/settings linkage; optional Trinity dock; Front; P25; Mono candles; distinct positive/negative exposure palette; session VWAP and EMA 9. Flow/dark-pool start unavailable/off unless evidence is commissioned. SPX/SPXW/ES symbol aliases must be validated; no fake symbol substitution. This is an ergonomic preset, not a tested trading edge.

## 4. Full capability inventory and disposition

`CAPABILITIES.json` is the machine-readable coverage ledger. Every feature has an ID, category, current status, target phase, prerequisite, implementation block, acceptance and evidence source. Nothing disappears because it is deferred. “Data-gated” and “out of scope” are explicit outcomes, not pretend implementations.

Coverage includes: symbol/interval/custom intervals; RTH/ETH/TZ/candle palettes/fullscreen/export/auto-fit; pane arrangements and five independent sync dimensions; workspace autosave/account portability/import-export; GEX/VEX/combined/derived/expiry choices/top-N/P15–P60/labels/realtime/scaling/projection; the complete indicator families and flow filters/drilldown; all sidecars; fixed/follow-node alerts; all listed drawing tools and presets; deterministic replay; plugins; paper positions/followed traders; chart-context AI; accessibility, performance, provenance and supplied October regression cases (weekly alignment, hidden drawings, watchlist removals, mobile replay, local settings editors and replay order gating).

## 5. Architecture and file boundaries

Proposed new modules (not present until implemented):

```text
frontend/src/components/heatseeker/chart/
  ChartWorkspace.jsx          # panes/settings/docks; no market calculations
  ChartPane.jsx               # lifecycle + engine adapter boundary
  chartContract.js            # strict ingress parsing and capabilities
  chartReducer.js             # focused pane, links, mode, transaction tokens
  useChartData.js             # cache/subscriptions, request generation, abort
  engines/plotlyAdapter.js    # reversible incumbent
  engines/lightweightAdapter.js # approved candidate, v5 API only
  primitives/ExposureOrbs.js  # signed magnitude + coordinate-aware hit test
  indicators/registry.js     # independent instances + schemas + requirements
  replay/replayReducer.js    # one cursor, deterministic event visibility
  drawings/drawingReducer.js # logical anchors/history/snap; no broker writes
  persistence/layoutSchema.js # versioned safe imports/migrations
  ChartWorkspace.css         # repository theme variables, responsive rails
backend/services/chart_history.py # contract assembly + provenance
backend/services/chart_exposure.py # parse recorded inputs; no new Greek formula
backend/services/chart_resample.py # exchange-calendar bucket semantics
backend/services/chart_capabilities.py # instrument/source/entitlement evidence
backend/routes/price_history.py   # additive chart route beside old route
```

Integrate initially inside `PriceNodeHistory.jsx` via a conservative workspace toggle; retain the legacy chart and controlled `open` contract. Larger docking/chart-context changes need small reviewed modifications in `SkylitDashboard.jsx`. `TrinityView.jsx` is currently an independent page-like surface: isolate a read-only reusable panel/body rather than recursively mounting a full dashboard inside each candle pane. Preserve polling, selection and teardown ownership. Chart shell references existing heatmap state; no duplicate market calculations in the renderer.

Do not touch frozen `App.js`, `dash_ui.py`, `ml/inference.py`, model artifacts, `.env`, craco config or conftest. Package adoption requires Nav approval first. Lockfiles are an explicitly owned dependency lane, not a way around the package freeze. Do not bundle other agents' pre-existing package/lock changes.

### Adapter contract

Use local interface, not an off-the-shelf promise:
`mount(container, paneConfig)`, `setSeries(series)`, `upsertBar(bar)`, `setOverlays(overlays)`, `setVisibleRange(range, transactionId)`, `setCrosshair({time,price,paneId,seriesId},transactionId)`, `clearCrosshair(transactionId)`, `timeToX(time,paneId)`, `xToTime(x,paneId)`, `priceToY(price,{paneId,seriesId})`, `yToPrice(y,{paneId,seriesId})`, `getPaneGeometry(paneId)`, `setInteractionSuppressed(reason,enabled)`, `subscribeInteraction(handler)`, `subscribeViewport(handler)`, `captureEngineImage(options)`, `destroy()`. Subscriptions return an idempotent unsubscribe. Coordinate conversions are pane/series-qualified and return null for unknown/off-screen/unmappable values; consumers cannot interpret null as zero. Viewport events include zoom/scroll/price-range/resize/DPR changes and invalidate primitive hit-test caches.

Workspace-level `exportComposite` combines engine image capture with owned drawing/primitive/DOM-sidecar layers and source watermark; it is not an engine method that magically screenshots arbitrary DOM. Logical timestamp/price anchors survive resize and zoom; never persist pixel coordinates. Off-screen coordinates may be null. Candle/volume series stay inside the chart engine; exposure/drawing/profile primitives render against its coordinate model. UI popovers are DOM overlays, not thousands of React circles. Batch updates once per animation frame; cancel observers/listeners on unmount. Settings and pane links use transaction origin IDs so receiving a synchronized event never echoes it back indefinitely. Time/crosshair link across unlike symbols; price-scale linking defaults **off** unless intentionally comparable. Linked settings are an allowlist of presentation preferences, not foreign opaque scope IDs. Resolve actual expiries/calendars/metric identity/capabilities per destination instrument. Atomically invalidate and generation-bind chart evidence on focus/symbol/scope/cursor change; late responses or removed panes cannot republish stale AI context.

Layer order: session shading → derived/projection zones → exposure orbs → candles/price studies → selected drawings/alert lines → labels/hover/focus. Use a hit-test registry with explicit z-order and pixel tolerance; a drawing drag cannot also pan or fire an alert. Preserve accessible textual OHLC/exposure readouts alongside canvas.

### Engine adoption gate

Compare the incumbent Plotly against Lightweight Charts 5.2.1 in an isolated owned lane using identical real-shaped fixtures. Required: candle/volume panes, 3 ticker panes, 20 visible nodes per bar, redraw on zoom/DPR, crosshair sync, primitive hit test, drawing anchors, composite screenshot and teardown. Use current v5 `addSeries(CandlestickSeries, options)` rather than guessing v4 `addCandlestickSeries` API. Library pane support is indicator subpanes in one chart; it is not our multi-symbol workspace/layout controller.

License verified through GitHub SPDX and npm metadata: Apache-2.0. Preserve license/NOTICE, visible TradingView attribution/link per upstream instructions, and identify any plugin/sample's own license separately. Do not mistake Lightweight Charts for proprietary Advanced Charts or assume a license/market feed is included. B04 can finish its discovery with an explicit Plotly-only measured verdict; candidate adoption is not a prerequisite for the incumbent adapter. Do not leave a static or dynamic import of an uninstalled candidate package in a compiled source path: a false feature flag does not prevent bundler module resolution. If approval or measurements fail, implement P0/P1 and the agreed Plotly scope first; postpone engine-only features, never bypass frozen files.

## 6. Versioned data contract — proposal, not existing API

Add `GET /api/heatseeker/chart/v1/{ticker}` to the already registered price-history router; keep the legacy route unchanged. Proposed validated parameters: bounded `from`/`to` UTC range, `interval`, `session`, stable exposure scope, view and cursor; return supported choices rather than accepting arbitrary provider enums. UI TZ is display-only. Actual query spelling is fixed by P0's shared schema before coding consumers.

Response fields:
- `schema_version`, canonical instrument (display/provider symbols, asset type, exchange/calendar, tick size, multiplier, volume symbol), requested/resolved interval/session/range.
- `capabilities[]` with supported/degraded/unavailable + reason and evidence, not a global boolean entitlement.
- Sorted candles: start/end UTC, OHLC, nullable volume, session ID, completion flag, provider event time, received/available time, source and revision. Positive finite prices; volume zero is real zero, null is unknown; bool/blank/NaN/Infinity rejected.
- Exposure readings: immutable snapshot ID, scope ID, source event time, received time, known-at, selected **actual** expiries, formula version, basis/unit and per-strike signed GEX/VEX values/status. Keep wall-role lines separately from strike orbs.
- Per-stream freshness/coverage/errors, cursor/pagination, maximum age, truncation and generated-at. `generated_at` is not market freshness. HTTP 200 plus empty list does not prove a measured zero market.

Scope identity includes symbol/series, actual expiry selection, metric/formula/basis and source/mapping version. Canonical hashing is deterministic; human-readable scope metadata replaces “Saved view 1”. Replay filters by both event and available times, not merely a slider slice.

### Candles, calendars and live corrections

Use proven provider capabilities, not advertised symbols. Verify equity/ETF/index/futures historical access separately. Build custom 7m/90m intervals from timestamped base bars if supported and sufficiently complete; do not interpolate missing bars. Intraday bins align to the chosen exchange session open; end-of-session partial candles remain explicit. RTH for US equities is calendar-aware 09:30–16:00 ET, not a fixed UTC offset. ETH and futures have different session calendars and possible maintenance breaks. Reuse audited `solstice_calendar`/time helpers rather than inventing holiday logic. Weekly bars are Monday calendar weeks, holiday-shortened as applicable; labels/TZ changes cannot change membership. Preserve split/dividend adjustment mode in response and scope; no mix of raw and adjusted history.

Fresh live bars may update only the active candle; new candles append. Corrections replace their exact timestamp/revision. Refetch backfill after reconnect and reject obsolete request generations even if symbol is identical but interval/session/scope differs. A current quote is not a fabricated trade candle. Start with budgeted shared polling if no proven chart stream exists; share identical queries across panes and pause hidden-pane work. Do not promise tick streaming based on the presence of another WebSocket.

### Exposure math and visual semantics

Extract signed grids with complete expiry coverage first. Front/wider selection must operate on observed eligible expiries as of the cursor, including instrument settlement rules; OPEX and quarter presets use maintained calendars. Unknown/unrecorded expiries are not assumed zero. Preserve source units and formula metadata; pin characterization of repository calculations instead of recomputing Greeks in React.

For a complete metric and scope, king is largest absolute eligible exposure. Incomplete/malformed metric grids disable full-scope king/top-N/P-ranking by default; an intentionally chosen observed-subset view gets its own identity and badge. A newer invalid/incomplete observation supersedes prior display state rather than silently restoring an old valid board. Require per-channel requested/observed coverage and VANNA model/basis/unit, not only parent formula or contract counts. Fixed-count ranking uses absolute magnitude with deterministic strike tie-break. P25 means `abs(value)/king >= 0.25` (inclusive), not top quartile or ±25% proximity. When king is zero, ratios are undefined: draw no magnitude-ranked orbs and show a measured-zero board label; missing king is unavailable. In combined mode render independently normalized GEX and VEX channels with explicit legend; never add unlike dollars. Proposed radius uses square-root relative magnitude so screen area reflects strength; clamp visual radii, never data; separate king opacity. Mark sign with palette **and** shape/text, not color alone. Palette matching may use board min/max colors that do not mean sign; raw signed tooltip remains authoritative.

**Scroll as replay** on uses only eligible readings at each cursor for ranking/normalization. It must not rescale early orbs against a future session king. If off, label retrospective normalization explicitly. Live Front-only realtime sizing restrictions are reference behavior, not a reason to hide a missing feed; publish actual supported scope capabilities.

### Derived levels and projection

Require contemporaneous observed source/target prices, known-at times, instrument units, mapping version and freshness bounds before mapping strike to target coordinate. A simple ratio, `target_price/source_price`, is a documented mapping approximation, not proof of futures basis equivalence. SPY/SPXW/SPX→ES, QQQ/NDXP/NDX→NQ, GLD/SLV/DIA/IWM→related futures remain data-gated until aliases/contracts/entitlements are commissioned. Distinct diamonds/triangles preserve source identity. Historical mode uses historical known ratios; “latest ratio” is an explicitly different display mode and unavailable for no-lookahead practice. Missing mapping is a visible gap, never a guessed constant.

Projection renders the latest eligible exposure into future chart whitespace with interval-aware visual extent and a dashed scenario legend. It is not a forecast and generates neither pseudo-future candles nor future exposure records.

## 7. Indicator contracts and honest data gates

Registry instances have ID/type/settings schema/input requirements/pane/compute version/replay support/source status. Allow multiple VWAP/MA instances. Pure deterministic calculations take validated inputs; heavy calculations move to worker/server only after profiling. Changing settings changes display/selection, not archived market data.

- EMA/SMA/Bollinger: audited close-based formulas, warmup/null behavior and std convention pinned with fixtures.
- Volume: native measured volume; unknown stays unknown. SPX-family proxy ES volume is allowed only with entitled historical ES data, explicit `volume_symbol`, session/time alignment and proxy badge.
- Session/week/month/quarter/year VWAP and up to three bands: tape exact when tape exists. HLC3×bar-volume implementation is labelled **bar-based approximation**. Corporate-event anchors require verified event dates and adjustment treatment. No volume → no VWAP.
- GEX/VEX VWAP: name is exposure centre, not traded-volume VWAP. Pick and characterize absolute-vs-signed weighting, unit and bands in a reviewed spec. Do not silently adopt misleading “flip” labels or normalize a near-zero signed denominator.
- Flow histograms: call premium up, put premium down; premium dollars, not share volume or chain volume differences. Require immutable tape print identity/contract/multiplier/event+received time and classification evidence. Single/multi, sweep/non-sweep, ITM/ATM/OTM, bid/mid/ask, DTE, score, premium bounds have explicit unknown categories. Bid/ask is aggressor evidence, not proof of opening trades. The **Flow Bucket** drilldown uses the **same filter hash** and cutoff as bar totals; click only that subpane, empty buckets do not invent trades. Include trade count, calls/puts/net, bucket/day put-call and top contracts. Multi-leg prints need economic grouping/dedup, not double counted legs.
- Net Premium/Flow VWAP: define signed cashflow convention from an actual tape. Call premium minus put premium is a descriptive difference, not proof of net opening direction. Session reset and replay truncation include no future prints.
- Dark Pool: exact real off-exchange equity print price, not a clustered average; top N/notional/lookback/date/report availability; no invented buyer/seller direction. Report time can be delayed. Equities-only unless a separate proven mapping is explicitly displayed. Existing scanner fields alone do not establish a licensed historical dark feed.
- CVD/Candle Delta/Footprint: require trade-level size and auditable aggressor classification, condition codes and correction handling. Up/down candle volume is **not** true CVD. Unclassified volume is separate. Do not manufacture a heatmap from OHLC and call it footprint.
- Volume Profile: exact trade volume-at-price needs trades; any bar-distributed approximation is distinct/off by default. Specify bins, tick size, session range, POC tie-break and value-area algorithm. Retrieved vendor Volume Profile defaults to 68% value area, lower-price POC tie and upper-side expansion tie; its price allocation is bar-distributed even when sided totals are measured. Do not silently use a 70% target for vendor parity. TPO is a separately defined bar-period occupancy profile (not volume or tick-exact residence); its value-area target and Initial Balance duration are not quantified on the retrieved page and remain reviewed settings, not guessed vendor constants. Bar-based TPO can proceed without a trade-price tape when eligible period coverage exists; exact trade VAP remains gated.
- Session Levels/Zones: previous complete session, premarket, Asia/London, initial balance, week/month levels and opens each need instrument session rules and availability boundaries. Current-session high/low cannot use the eventual full-day extrema during replay.

## 8. Workspace, drawings, alerts and persistence

Settings blocks: Session/TZ/Interval/Candles; Exposure; Projection; Add/indicator rows; docks; Alerts; Drawings/presets; Replay; Layout. Local card/popover editors are progressive enhancement; mobile bottom sheets avoid keyboard/Replay overlays. Do not flood the first release with disabled menus: group unsupported features under “Requires data” with a reason.

Workspace state separates focus/pane symbols, intervals, settings and link dimensions (settings/interval/crosshair/time/price). Support Single, 2-Up/2-Stack, 3-Up/3-Stack, 1+2/1|2, 4-Grid/4-Up/4-Stack and a tested five-pane cap, with stacked phone layouts and lazy hidden panes. Prefer three-pane index desk before five panes. Dock Heatmap/Trinity/Watchlist/Alerts once per workspace, following the focused pane by explicit setting; avoid five repeated full map fetch loops. Trinity can have up to ten boards only after budget/performance validation.

Persistence: versioned JSON schema, autosave debounce, bounded imports, migration tests and safe fallback after corruption. Local storage first where appropriate; **account sync is a separate authenticated backend store**, not a localStorage claim. Existing preferences can store global defaults after proving schema/ownership; large pane/drawing documents need proper user/workspace identity, optimistic revision, conflict policy, quota and export. No broker account ID, tokens or positions in portable layout exports. Imported JSON is declarative only; reject scripts/HTML/prototype pollution/unknown plugin types. Preserve tombstones so removed watchlist items do not reappear after sync.

Drawing model: `{id, tool, instrument, anchors:[{time,price}], style, visible, locked, revision}`. States idle/placing/selecting/dragging; explicit undo/redo/cancel/delete; magnet selects visible candle OHLC only. MVP horizontal line/ray, trendline, vertical line, rectangle, text and arrow; then brush/Fibonacci/long-short risk boxes. Position drawing is analysis geometry, not an order. Advanced XABCD/Deep Gartley and Elliott tools need independent rule specs and tests, not vague parity promises. Drawing presets cap at 50 per account and preserve false-valued options, recent color/opacity and visibility when switching tools. Hidden drawings stay hidden; new drawings and “N hidden · Show” follow the supplied regression behavior.

Alerts: reuse existing persistence/evaluator only after contract audit. Exact price alerts and follow-role node alerts are different identities. Define touch/cross semantics with source precision, once/repeat cooldown, atomic trigger/update and idempotent notification delivery. Drag updates the persisted server target; round to tick size and retain audit. Server evaluation is independent of chart visibility. Private alert reads and writes require a real approved owner resolver, not just a deployment key. Replay-origin live-alert mutations are refused by default. A moving followed-node target alone does not prove a touch; reset crossing continuity on target revision and stale/gap data. Missing/stale prices or role scopes do not fire. Replay cannot create historical events in the live alert evaluator. Alert CRUD is authenticated; symbols/scopes are validated, not trusted from imported layouts.

Shortcuts: `?`; Shift+S/H/T/A/R/F/G/V/C; [ / ]; watchlist arrows; Alt+T/H/J/V/A/B/X/F/L/S/M/P and Alt+Shift+R. Apply only when chart is active and no input/editor is typing; macOS Option/OS conflicts require a rebindable alternative. Touch offers long-press/context-sheet equivalents; keyboard focus, escape paths and textual screen-reader readouts are mandatory. PNG/copy-image composites include primitives/sidecars as chosen, watermark source/timestamp/replay/proxy and respect clipboard permission failures.

## 9. Replay and execution boundaries

One UTC replay cursor owns all pane and overlay visibility. Play/step/pause/start-here/seeded random/speed/end/jump-live operate on the focused instrument's timeline; other panes show latest eligible data at that cursor or gaps, not their nth bar. Hide future candles, flow, derived ratios, profiles, alerts and normalized exposure extrema. Archive revision arrivals so corrections cannot time-travel. Higher-timeframe candles require a clear mode: completed candles only, or partial candles built from base bars known then; never display eventual final high/low at an early intra-bar cursor.

Replay/scroll practice is not a backtest or performance claim. The present price endpoint does not preserve historical bar revision-arrival timing. Split **historical review** (finalized candles, disclosed revision-timing limitation) from **time-faithful replay** (captured eligible base events/corrections); the latter stays unavailable where provenance is absent. A final OHLC fetched today is not proof of what was visible at a past intra-bar cursor. The exact bar start/end and known-at modes are specified in `CONTRACT.md` and must be characterized before the new route ships. Historical archive availability is shown before starting; deterministic random start selects only eligible ranges. On exit explicitly switch context back to current verified market state; do not feed replay into shared live caches.

Paper positions initially read-only, source/account/status stamped. Current live positions are hidden in time-faithful practice; any historical-review-only current-position display is segregated, labelled nonhistorical and excluded from AI/evidence. Read-only does not guarantee no-lookahead. Do not reinterpret option contract positions as underlying-share orders. Followed-trader/Nexus integration is an external product dependency, not present because the vendor supports it. Any later trading ticket requires separate architectural approval, broker paper-only checks, explicit confirmations, server refusal of new replay intents and preserved emergency cancel/close paths. Imported layouts and AI cannot submit orders.

## 10. Delivery blocks, dependencies and release gates

`IMPLEMENTATION_TASKS.json` supplies the exact files, RED/GREEN commands, fixture names, dependent IDs and narrow steps; commands referring to proposed tests are future acceptance commands, **not tests claimed run**.

- **P0 — Freeze the contract and prove substrate.** Characterize existing routes/calendars/scope/legacy behavior; inspect recorded grid coverage; capability census; engine ADR/spike; secure fixture contract. No dependency edit without approval.
- **P1 — Single-pane vertical slice.** Shared strict contract, independent interval/session/TZ, renderer adapter, legacy fallback, generation-safe data hook, states/freshness, signed orbs only where archived inputs exist. Exit: source-labelled candles, honest gaps, reversible migration, no heatmap regression.
- **P2 — Exposure controls and basic price studies.** Metric/expiry selection and coverage, count/P-threshold, palette/size/labels, EMA/SMA/Bollinger and eligible VWAP. Exit: formula characterizations and no future normalization.
- **P3 — Workspace and persistence.** Three-pane index preset, safe pane synchronization, docks reuse, local/authed layout persistence, import/export/mobile/shortcuts. Exit: no sync loops, no multiplied provider polling, old controls intact.
- **P4 — Deterministic replay.** Unified cursor/candle availability/corrections/ratios/overlays, random/start/step/speed and read-only safety. Exit: leakage fixtures across all enabled layers; recorded gaps visible.
- **P5 — Drawings and alerts.** Logical anchors/hit-test/magnet/undo/presets; fixed and follow-role alert semantics; export/focus. Exit: reload-safe drawings and server-idempotent touch alerts; no replay writes into live evaluators.
- **P6 — Advanced market context.** Contract/entitlement discovery first; flow/buckets/net premium, real dark-pool data, CVD/footprint, exact trade-price profiles and corporate anchors. Bar-distributed profiles and bar-occupancy TPO are separate labelled bar/calendar variants, not unconditional tape dependents. Each feature has its own go/no-go; absent substrate leaves it visibly unavailable.
- **P7 — Derived/projection/AI and optional integrations.** Known-ratio derived levels, scenario projection, focused chart AI context, read-only positions; plugins/followed traders/advanced drawing analyses are separately commissioned.
- **P8 — Hardening and rollout.** Real browser performance/visual/accessibility/recovery, feature flag canary, data-quality telemetry, fallback and independent review. No exact parity declaration while data gates remain open.

### Release-specific acceptance rather than all-feature deadlock

B04 discovery may select the measured Plotly-only route without dependency approval. B13 account discovery may remain unavailable while local layouts/presets advance. B23 session levels/bar-based study variants depend on validated calendars/bars, not an unentitled tape; exact tape profiles remain separately gated. B28/B29 evaluate an explicit release enabled-capability set and the dependency closure of those enabled variants. Every unavailable/deferred capability has a reason/hold, but is not a fictitious implementation pass or an unconditional blocker for a supported core release. `IMPLEMENTATION_TASKS.json` records discovery/implementation dispositions, variant dependencies and R1/R2/R3 profiles. Only accepted enabled variants count as delivered.

Parallelize isolated units only: backend contract/fixtures, pure state/math, engine adapter spike, persistence/drawing models, and independent spec review. Integration owner alone changes `PriceNodeHistory`/`SkylitDashboard`; serialize tasks touching shared `backend/routes/price_history.py` or `chart_capabilities.py` under their single owner.  test-infra/dependency owners alone alter their gates. Land tasks in dependency order; no simultaneous shared-shell rewrites.

## 11. Acceptance, performance and rollout

Baseline evidence is narrow and explicitly recorded. Implementation acceptance must include:
- Backward-compatible legacy API/component tests and existing exposure/time/calendar suites; new strict number/OHLC/timestamp/scope/cursor tests.
- Fixture pack: measured zero vs null; bool/empty/string/NaN/Infinity; invalid OHLC; duplicates/out-of-order/corrected bars; late snapshots; 900s/901s boundaries; absent expiries; ties and zero kings; missing volume/proxy; denied entitlements/429/outage; DST/half-day/holiday/week boundaries; data truncation.
- Frontend stale-response tests where same symbol changes interval/session/scope, replay teardown, on/off/default-false roundtrip, malformed imports, pane sync origin loops, selection vs pan, hidden drawings, watchlist tombstones and narrow mobile Replay controls.
- Replay adversarial fixture: source snapshot as-of 10:00, received 10:02, must be absent at 10:01; eventual high-of-day/future king/late dark print must be absent; cross-symbol gaps cannot fabricate observations.
- Real browser, not just mocked canvas: DPR 1/2, resizes, pan/zoom, export composition, keyboard screen-reader paths, touch, Chrome/Safari, three/five panes, long recorded session and all active data gates. Capture screen evidence when implementing.

**Proposed budgets, not measurements:** single-pane warm interaction p95 <16.7ms frame time, three-pane p95 <33ms, no >200ms main-thread task during ordinary pan; warm data update paint p95 <100ms; no more than one upstream request per shared query/cadence; hidden panes pause; 10 mount/unmount cycles show no accumulating listeners/timers. Test 10k bars × 20 nodes with viewport culling, capped visible nodes and memory/heap/GC traces. Measure actual hardware/browser/data density and publish before/after; if budgets fail, reduce visible work or postpone five-pane cap. Full history loading is paginated/bounded, never one unbounded 200k-node DOM tree.

Feature flag defaults to incumbent; dogfood single-pane first, then three-pane. Observe data fetch age/source, coverage, aborted/stale responses, query budget, dropped/invalid values, frame timing and loop-suppression counts without secrets. Rollback switches engine/workspace while preserving portable versioned state. Financial source calculations and live execution are untouched by a UI rollback.

## 12. Open decisions and stop conditions

Blocking decisions before the relevant phase: dependency/frozen-file approval; exact instrument aliases and tape entitlements; archived grid coverage; bar timestamp start/end and corporate adjustment conventions; exposure-centre weighting; user/account persistence model; current concurrent lane ownership and correct compiled frontend identity. These are task outputs, not unanswered reasons to stop the research.

Do not silently implement futures with equities calendars, free-index quotes with a ETF-scaled substitute, CVD with candle sign, footprint with OHLC, cross-device sync with localStorage, dark pools with scanner sentiment, or a video preset with inferred slider values. Do not change model exposure conventions to make circles look right. Do not enable chart orders to achieve vendor parity.

## 13. Packet verification

Run `python3 docs/solstice/chart-upgrade-2026-10-09/VERIFY.py`. The gate validates artifact existence/set, capability/task coverage and DAG, evidence records, source citations, artifact hashes and repository preservation against the captured baseline. It is a **research-packet gate**, not application-feature acceptance. The current source tests and frontend blocker are reported separately in `EVIDENCE.json`.

Read `SPARK_HANDOFF.md` for the actual model IDs discovered locally, task protocol and launch commands. `RESEARCH_REPORTS.md` retains model-lane reports and parent adjudications so a future implementer can distinguish verified code facts from recommendations.

## 13. Round2: primary-subpage detail and candidate-API adjudication

The matrix now enumerates **143 capabilities**: the original111 retained plus32 atomic settings/behavior requirements. The existing29 blocks and145 repeating workflow steps remain; expanded block acceptance invariants are explicit future fixture obligations, not executed feature tests or duration estimates.

- Exposure-VWAP has its own board window/node filter, centre/band selection, per-minute gaps, opening-envelope window (default15m,8–60 allowed,minimum8 measured minutes) and nonshrinking session envelope. Independent indicator/orb scopes must be shown. Numerical weighting and SPXW Trinity-combine units are still reviewed definitions; public prose is not a formula implementation.
- Price-VWAP exposes HLC3/Close, deviation/percent band basis and three independent band pairs. Reset steps differ from real data gaps. SPXW+ES proxy-volume handling requires exact price/volume identities, joins and session coverage; a vendor feature is not floww entitlement.
- CVD uses one reconciled underlying sided-volume source shared with Volume. Unknown volume stays unknown; minute capture cannot establish subsecond historical wicks. Anchors/MA/zero line/axis badges are enumerated.
- Profiles separate measured volume totals from approximate price allocation. VP reference defaults are200 bars/68% area; deterministic ties and sparse-gap stopping are pinned. TPO has independent modes, row-size/period settings, fifth-period maturity,20-bar daily composite and next-session-only naked levels. Historical unknown price gaps cannot prove a level untouched.
- Drawing styles preserve family-specific starred > active > built-in precedence, dirty-dot/explicit Update semantics, complete false-valued options and a50-preset combined quota. Layout autosave is not preset autosave; an edited preset never silently restyles all prior drawings. Account synchronization remains unavailable without an approved owner resolver.
- Flow Bucket interactions are pane-qualified and generation-bound; histogram and drilldown use the same filter/cutoff, including cursor-bounded day totals. Ask/sweep is not proof of opening intent. Dark-pool levels are real exact prints without invented buy/sell direction.

### Inline source refutation, replacing unusable research lanes

`backend/services/market_bars.py:86–93` chooses base1minute or1day upstream aggregation; it is not a custom intraday/weekly resampler. `_slice_sessions` (`:141–153`) keys ET dates and retains the whole input if a timestamp is unparseable. `_validate` (`:96–121`) currently coerces missing volume to0, boolean volume to1 and accepts positive infinite volume; these behaviors were reproduced in a standalone characterization process. New strict chart admission must validate before lossy legacy normalization and must not globally change legacy consumers as a planning side effect.

`backend/services/solstice_calendar.py:36–61` supplies maintained XNYS regular session hours with explicit holiday/half-day/unknown outcomes. Direct calls returned2026-11-26 closed,2026-11-27 close13:00 ET and regular09:30–16:00 on2026-03-06/09. Those two opens map to14:30UTC and13:30UTC across DST. `solstice_time.py` is an expiry/last-trade clock, not complete ETH/futures session logic. Chart ETH/overnight/futures maintenance breaks remain separately validated inputs. Legacy `/price-history` selects candle interval from days and requests regular hours (`backend/routes/price_history.py:25–42`); preserve it while adding the independent canonical route.

The existing exposure-alert evaluator detects exposure-grid threshold crossings, not chart price-touch rules (`backend/services/exposure_alerts.py:18–20`). Mongo AlertRule CRUD does not prove role-follow/touch evaluation or owner-isolated reads. Preserve current live-only detector badges; commission the typed chart-price alert variant separately.

### Candidate library: documentation proof, not adoption proof

The usable saved report is a bounded third-party API inventory, not a measured spike. Parent fetched officialv5.2 chart/time-scale/series/panes/primitive docs directly. Native study subpanes share a chart timeline; independent ticker/timeframe workspace panes still need separate chart instances and our state/sync reducer. Confirmed documented building blocks include series-qualified price conversion/inverses, crosshair events/set/clear, visible logical-range subscriptions, primitives and historical-update support. Reacquire priceScale APIs after moving a series: old handles remain bound to the old pane/scale. Historical inserts and corrections require a characterized ordered/deduped update strategy, not blind `update`.

`takeScreenshot(addTopLayer?,includeCrosshair?)` defaults to omitting top-layer/primitives; candidate capture must pass the intended flag and test export pixel contents. It does not capture arbitrary DOM sidecars. Upstream master NOTICE was fetched and contains TradingView2025 attribution; exact approved package/release NOTICE, licensing/visible attribution and plugin licenses must still be checked before shipping. Documentation availability proves none of installed compatibility, frame latency, memory growth or export correctness. Reject the child summary's blanket “no blockers” inference.

### Strict request/page acceptance

Vendor API is a separate UDF endpoint with its own resolution-tier caps and columns, not our current provider contract. UX interval10m/custom7m does not establish vendor-native resolution support. Own chart responses never silently clip. Page identity binds symbol/source/session/scope/adjustment/interval and dataset revision; reject repeated/nonadvancing cursor or mismatched fingerprint. Finish cross-page buckets from sufficient eligible base inputs, fetch a necessary boundary prefix when lawful/bounded, and mark incomplete/truncated rather than fabricate. Weekly labels do not shift constituent sessions with display TZ. Missing calendar/ETH data is an unavailable capability, not an implicit RTH fallback.

