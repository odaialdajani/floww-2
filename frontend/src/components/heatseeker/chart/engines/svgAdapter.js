// Incumbent SVG adapter: preserves RecordedPriceChart custom renderer.
// No new dependency. Used as baseline for B04 measured comparison.
// Attribution: owned FLOWW SVG, no upstream license.
export function svgAdapterInfo() {
  return { engine: 'svg-incumbent', renderer: 'RecordedPriceChart', reversible: true };
}
export function formatSvgFixture(candles) {
  return (Array.isArray(candles) ? candles : []).map((c) => ({
    time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
  }));
}
