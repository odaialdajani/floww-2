import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import { createDrawing, geometryFor, TOOLS } from '../drawings/drawingReducer';
import { DRAWING_TOOLS, isSupportedTool, anchorsFor } from '../drawings/toolRegistry';
import { FIB_LEVELS, fibPrices } from '../drawings/advancedTools';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const arm = () => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: [
    { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, nodes: [] },
    { time: '2026-10-06T14:30:00Z', open: 101, high: 104, low: 100, close: 103, nodes: [] },
    { time: '2026-10-06T15:00:00Z', open: 103, high: 105, low: 101, close: 104, nodes: [] },
  ], candles_with_recorded_nodes: 3, scopes: [] } }));
};

// B17: the six basics are pinned (b16/b43); the advanced evidence-backed
// tools (brush, fib, horizontal-ray — all in the nine-tool registry) now
// CREATE and RENDER through the same reducer/geometry the basics use.
test('the reducer accepts every registry tool and still refuses the rest', () => {
  const registryIds = DRAWING_TOOLS.map(t => t.id);
  expect(registryIds).toEqual(expect.arrayContaining(['brush', 'fib', 'horizontal-ray']));
  for (const id of registryIds) {
    expect(TOOLS).toContain(id);
    expect(() => createDrawing(id, [{ t: 1, p: 100 }, { t: 2, p: 101 }])).not.toThrow();
  }
  // CHART-C090 (owner-approved 2026-10-24): "Alt+L/S analysis entry/stop/target
  // risk box, never broker intent" — the anchor semantics the old refusal
  // guarded are defined BY the preserved requirement row, so 'risk' is now a
  // creatable three-anchor analysis tool (pinned in b17_risk.test.jsx);
  // the analysis-only marker is part of the tool contract.
  expect(isSupportedTool('risk')).toBe(true);
  expect(anchorsFor('risk')).toBe(3);
  expect(() => createDrawing('madeup', [])).toThrow('unsupported-tool');
});

test('fib geometry renders the seven evidence-backed levels across the anchor span', () => {
  const vp = { width: 600, height: 320, tMin: 0, tMax: 300000, pMin: 90, pMax: 110 };
  const anchors = [{ t: 0, p: 110 }, { t: 300000, p: 90 }];
  const g = geometryFor('fib', anchors, vp);
  expect(g.kind).toBe('fib');
  expect(g.levels).toHaveLength(FIB_LEVELS.length);
  // level prices match advancedTools.fibPrices exactly (high 110, low 90)
  const expected = fibPrices(110, 90);
  g.levels.forEach((level, i) => {
    expect(level.ratio).toBe(expected[i].ratio);
    expect(level.price).toBe(expected[i].price);
  });
  // each level spans the anchors' x-range inside the viewport
  const xs = g.levels[0].points.map(p => p.x);
  expect(Math.min(...xs)).toBeGreaterThanOrEqual(0);
  expect(Math.max(...xs)).toBeLessThanOrEqual(vp.width);
});

test('horizontal-ray renders from the anchor to the right edge only', () => {
  const vp = { width: 600, height: 320, tMin: 0, tMax: 300000, pMin: 90, pMax: 110 };
  const g = geometryFor('horizontal-ray', [{ t: 100000, p: 100 }], vp);
  expect(g.kind).toBe('line');
  expect(g.points).toHaveLength(2);
  expect(g.points[1].x).toBe(vp.width);
});

test('brush geometry is a plain free line through its anchors', () => {
  const vp = { width: 600, height: 320, tMin: 0, tMax: 300000, pMin: 90, pMax: 110 };
  const g = geometryFor('brush', [{ t: 0, p: 100 }, { t: 200000, p: 95 }], vp);
  expect(g.kind).toBe('line');
  expect(g.points).toHaveLength(2);
});

test('B17 MOUNTED: the rail offers every registry tool including brush and fib', async () => {
  arm();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  const rail = document.querySelector("[aria-label='Drawing tools']");
  expect(rail).not.toBeNull();
  for (const id of ['brush', 'fib', 'horizontal-ray', 'text', 'trend']) {
    expect(screen.getByTestId('rail-tool-' + id)).toBeInTheDocument();
  }
});

// B17 MOUNTED: a persisted fib drawing renders its seven level lines on the
// REAL chart layer (per-level testids + ratios), through the same persisted
// store the basics use.
test('B17 MOUNTED: a persisted fib drawing renders seven labeled levels on the real layer', async () => {
  arm();
  const { saveDrawings } = require('../drawings/drawingPersistence');
  const { createDrawing } = require('../drawings/drawingReducer');
  saveDrawings('SPY', [createDrawing('fib', [
    { t: Date.parse('2026-10-06T14:00:00Z'), p: 104 },
    { t: Date.parse('2026-10-06T15:00:00Z'), p: 100 },
  ])]);
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('drawing-layer')).toBeInTheDocument());
  const levels = document.querySelectorAll('[data-testid="fib-level"]');
  expect(levels).toHaveLength(7);
  const ratios = [...levels].map(l => l.getAttribute('data-ratio'));
  expect(ratios).toEqual(['0', '0.236', '0.382', '0.5', '0.618', '0.786', '1']);
});

// H3 b17 residual: the brush magnet:false bypass was correct in bytes but
// unpinned. This is the pointer-path proof — a brush placed mid-candle keeps
// its RAW anchors (never on OHLC), while a trend placed at the SAME pixel
// snaps to OHLC. The contrast pins the dispatch branch, not just the helpers.
test('B17 pointer path: brush anchors stay raw (off-OHLC); trend at the same pixel snaps', async () => {
  arm();
  const { saveDrawings: seed, loadDrawings } = require('../drawings/drawingPersistence');
  window.localStorage.clear();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('drawing-layer')).toBeInTheDocument());
  await act(async () => { fireEvent.click(screen.getByText('Drawings')); });
  const layer = screen.getByTestId('drawing-layer');
  const OHLC = new Set([99, 100, 101, 102, 104, 105, 103, 101, 100]);
  const place = async (tool, x1, y1, x2, y2) => {
    window.localStorage.removeItem('floww.drawings.SPY');
    await act(async () => { fireEvent.click(screen.getByTestId('rail-tool-' + tool)); });
    await act(async () => { fireEvent.pointerDown(layer, { clientX: x1, clientY: y1, pointerId: 1 }); fireEvent.pointerUp(layer, { pointerId: 1 }); });
    await act(async () => { fireEvent.pointerDown(layer, { clientX: x2, clientY: y2, pointerId: 1 }); fireEvent.pointerUp(layer, { pointerId: 1 }); });
    return loadDrawings('SPY');
  };
  const brush = await place('brush', 200, 200, 400, 300);
  expect(brush).toHaveLength(1);
  expect(brush[0].tool).toBe('brush');
  for (const a of brush[0].anchors) expect(OHLC.has(a.p)).toBe(false);  // raw, never snapped
  const trend = await place('trend', 200, 200, 400, 300);
  const trendDrawing = trend.find(d => d.tool === 'trend');
  expect(trendDrawing).toBeDefined();
  // the same pixel through the magnetized path lands ON candle values
  expect(OHLC.has(trendDrawing.anchors[0].p)).toBe(true);
  expect(OHLC.has(trendDrawing.anchors[1].p)).toBe(true);
});
