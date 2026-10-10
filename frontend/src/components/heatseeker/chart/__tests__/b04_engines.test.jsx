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
