// Candidate Lightweight Charts 5.2.1 adapter behind reversible flag.
// License: Apache-2.0, Copyright 2025 TradingView. Preserve visible
// attribution/link + LICENSE/NOTICE before shipping. No CDN workaround.
// Uses v5 addSeries + takeScreenshot primitives; native panes share timeline.
import { CandlestickSeries, createChart } from 'lightweight-charts';

export const LIGHTWEIGHT_VERSION = '5.2.1';
export const ATTRIBUTION = 'Charting by Lightweight Charts (TradingView, Apache-2.0) — https://www.tradingview.com/';

export function isLightweightEnabled() {
  return typeof window !== 'undefined' && window.__FLOWW_LWC__ === true;
}

export function toLightweightCandles(candles) {
  return (Array.isArray(candles) ? candles : []).map((c) => ({
    time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
  }));
}

export function createLightweightChart(container, options = {}) {
  const chart = createChart(container, { width: 800, height: 480, ...options });
  const series = chart.addSeries(CandlestickSeries, {});
  return { chart, series, attribution: ATTRIBUTION };
}

export function captureLightweight(chart, { addTopLayer = true, includeCrosshair = false } = {}) {
  // Intended v5 primitive-inclusive capture; DOM sidecar composition separate.
  return chart.takeScreenshot(addTopLayer, includeCrosshair);
}

export function destroyLightweight(chart) {
  chart.remove();
}
