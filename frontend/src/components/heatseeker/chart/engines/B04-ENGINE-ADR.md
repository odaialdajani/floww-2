# B04 — Chart engine ADR: SVG incumbent vs Lightweight Charts 5.2.1 candidate

Status: **MEASURED — conditional GO for a reversible, flag-gated trial (B06); SVG incumbent stays the default renderer.**
Date: 2026-10-19 · Owner: Hermes-1 (frontend) · Review: Hermes-3 · Program: FLOWW revision 2026-10-19-R2, job CHART-B04.

## Context

The mounted Stock-chart renderer is the hand-written SVG in `RecordedPriceChart.jsx`
(adapter: `engines/svgAdapter.js`, engine id `svg-incumbent`). The older
`PriceNodeHistory-Plotly` description in `engines/plotlyAdapter.js` is a historical
research baseline, not the current product path. `lightweight-charts@5.2.1` is
already declared in `frontend/package.json` and installed in this lane's
`node_modules` — **no package change and no dependency approval is required to
evaluate it**, and none was made.

## Measured evaluation (real Chrome 26, installed dist, no CDN)

Harness: the installed `dist/lightweight-charts.standalone.production.js` served
locally and driven in headless Chrome; fixtures are the SAME candle fixture the
incumbent adapters' test renders, plus 70 unique daily bars. Evidence:
`outputs/h1-compiled-evidence/b04-lwc-spike.json` + `b04-lwc-spike.png`.

| Surface | Result |
|---|---|
| Runtime version | `5.2.1` (verified at runtime, matches package.json) |
| v5 API present | `createChart`, `CandlestickSeries`, `HistogramSeries`, `LineSeries`, `createSeriesMarkers` — all present, none missing |
| Candle fixture parity | 72 bars (2-candle incumbent fixture + 70 daily) rendered via `chart.addSeries(CandlestickSeries).setData(...)` |
| Volume | `addSeries(HistogramSeries, {}, 1)` renders a native second pane (paneCount = 2 measured) |
| Panes | native multi-pane works through the `addSeries(..., paneIndex)` argument. **`chart.moveToPane` is NOT a runtime chart method in 5.2.1** (it appears in typings only) — pane management is `addSeries`/`panes()`. Recorded nuance, not a blocker. |
| Export | `chart.takeScreenshot(addTopLayer, includeCrosshair)` — the v5 signature works at runtime and returns a `CANVAS` element. Attribution is NOT embedded in the canvas; the caller must compose it. Our adapter carries `ATTRIBUTION = 'Charting by Lightweight Charts (TradingView, Apache-2.0) — https://www.tradingview.com/'` and any shipped export must include it plus LICENSE/NOTICE review before release. |
| Teardown | `chart.remove()` in 0.4 ms; mounted DOM 44 nodes → 0 (no leaks) |
| Render cost | 4.1 ms for 72 candles + 70 volume bars (indicative only; the 10k-bar/3-pane performance campaign is B28, not this spike) |
| Page errors | 0 |

## Incumbent safety (measured through three production builds)

- The candidate adapter imports `lightweight-charts` at module top level but has
  **no mounted caller**, so it is tree-shaken from the shipped bundle; the
  incumbent compiled green in all three pinned `:8002` builds of this lane
  (`main.301df05e.js`, `main.10f9af2d.js`).
- The candidate is flag-gated: `isLightweightEnabled()` requires
  `window.__FLOWW_LWC__ === true`; the default (flag off) keeps the SVG path —
  pinned by the existing b04 suite.

## Decision

**Conditional GO**: the installed 5.2.1 candidate provides every primitive the
chart roadmap needs at this stage (candle/volume/line series, series markers,
native panes, primitive-inclusive screenshot export, clean teardown) with zero
page errors — enough to proceed to CHART-B06's *reversible single-pane
workspace integration* behind the existing flag.

**NOT a go for wholesale migration**: the SVG incumbent remains the default and
the safe fallback. Adoption proceeds only if B06 measures full parity on the
real surfaces the incumbent already ships — saved node lines, orbs, exposure
polylines, contract-premium pane, replay, keyboard/focus, data-details
disclosure — and only after export attribution + LICENSE/NOTICE review for any
shipped image. If parity fails on any surface, the incumbent is retained and
this ADR's verdict downgrades to NO-GO with the measured gaps.

## Constraints honored

No dependency change, no install, no CDN, no incumbent break, no provider/model
calls. The candidate never activates without the explicit runtime flag.
