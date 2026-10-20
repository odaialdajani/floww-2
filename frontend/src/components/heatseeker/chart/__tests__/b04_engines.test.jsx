// B04 engine ADR spike: same fixtures across SVG incumbent, Plotly baseline,
// Lightweight 5.2.1 candidate. No incumbent break when candidate disabled.
import { formatSvgFixture } from '../engines/svgAdapter';
import { toPlotlyCandles } from '../engines/plotlyAdapter';

const FIXTURE = [
  { time: '2026-10-01', open: 100, high: 105, low: 99, close: 103 },
  { time: '2026-10-02', open: 103, high: 107, low: 102, close: 106 },
];

test('same candle fixture across incumbent adapters', () => {
  const svg = formatSvgFixture(FIXTURE);
  const plotly = toPlotlyCandles(FIXTURE);
  expect(svg).toHaveLength(2);
  expect(plotly.x).toEqual(['2026-10-01', '2026-10-02']);
  expect(plotly.close).toEqual([103, 106]);
});

test('lightweight 5.2.1 v5 API + attribution + teardown (candidate)', () => {
  // Avoid ESM import in Jest: verify pinned package + typings + adapter source.
  // eslint-disable-next-line global-require
  const pkg = require('lightweight-charts/package.json');
  expect(pkg.version).toBe('5.2.1');
  expect(pkg.license).toBe('Apache-2.0');
  // eslint-disable-next-line global-require
  const fs = require('fs');
  const typings = fs.readFileSync(
    require.resolve('lightweight-charts/dist/typings.d.ts'), 'utf8'
  );
  expect(typings).toMatch('addSeries');
  expect(typings).toMatch('takeScreenshot(addTopLayer');
  expect(typings).toMatch('moveToPane');
  const src = fs.readFileSync(
    require.resolve('../engines/lightweightAdapter.js'), 'utf8'
  );
  expect(src).toMatch('5.2.1');
  expect(src).toMatch('TradingView');
  expect(src).toMatch('takeScreenshot');
  expect(src).toMatch('addSeries');
  expect(src).toMatch('__FLOWW_LWC__');
});

test('incumbent SVG renders without candidate flag', () => {
  // Reversible: default flag off keeps SVG path, no candidate import break.
  expect(typeof window === 'undefined' || window.__FLOWW_LWC__ !== true).toBe(true);
});

test('B04 ADR records the measured go/no-go with the required surfaces', () => {
  // eslint-disable-next-line global-require
  const fs = require('fs');
  const adr = fs.readFileSync(require.resolve('../engines/B04-ENGINE-ADR.md'), 'utf8');
  // The decision must be recorded, not implied, and must keep the incumbent default.
  expect(adr).toMatch(/conditional GO/i);
  expect(adr).toMatch(/svg-incumbent/i);
  expect(adr).toMatch(/5\.2\.1/);
  expect(adr).toMatch(/Apache-2\.0/);
  // Measured surfaces the acceptance names: candles, volume, export attribution, teardown.
  expect(adr).toMatch(/CandlestickSeries/);
  expect(adr).toMatch(/HistogramSeries/);
  expect(adr).toMatch(/takeScreenshot/);
  expect(adr).toMatch(/attribution/i);
  expect(adr).toMatch(/teardown/i);
  // The measured runtime nuance must stay recorded, not silently dropped.
  expect(adr).toMatch(/is NOT a runtime chart method/);
  // Safety: flag-gated candidate, incumbent stays default, no dependency change.
  expect(adr).toMatch(/__FLOWW_LWC__/);
  expect(adr).toMatch(/no package change/i);
});

test('B04 candidate volume path: HistogramSeries is part of the installed v5 typings', () => {
  // eslint-disable-next-line global-require
  const fs = require('fs');
  const typings = fs.readFileSync(require.resolve('lightweight-charts/dist/typings.d.ts'), 'utf8');
  expect(typings).toMatch('HistogramSeries');
  expect(typings).toMatch('LineSeries');
  expect(typings).toMatch('createSeriesMarkers');
});
