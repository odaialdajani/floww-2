// Canonical Plotly baseline shim: documents older research packet surface.
// Successor incumbent is SVG RecordedPriceChart; do not overwrite it.
// This adapter only exposes the legacy trace contract for comparison.
export function plotlyAdapterInfo() {
  return { engine: 'plotly-baseline', renderer: 'PriceNodeHistory-Plotly', reversible: true };
}
export function toPlotlyCandles(candles) {
  const rows = Array.isArray(candles) ? candles : [];
  return {
    x: rows.map((c) => c.time),
    open: rows.map((c) => c.open),
    high: rows.map((c) => c.high),
    low: rows.map((c) => c.low),
    close: rows.map((c) => c.close),
    type: 'candlestick',
  };
}
