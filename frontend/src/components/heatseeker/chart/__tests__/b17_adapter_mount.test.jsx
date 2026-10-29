// B17/C130 ADAPTER MOUNT (H1 render integration) — the frozen
// presetRendering.buildPresetRenderSpec is consumed by the REAL drawing
// layer: full-family styles render visibly (fib per-level colors, hidden
// levels, bands, line extensions, rect fill), while refusals fall back to
// the incumbent rendering so a drawing is never lost or unhit-testable.
// The pure adapter semantics are pinned by H2's b17_preset_rendering suite;
// this suite pins the MOUNT.
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const FRAMES = [
  { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 10, nodes: [] },
  { time: '2026-10-06T14:30:00Z', open: 101, high: 104, low: 100, close: 103, volume: 20, nodes: [] },
  { time: '2026-10-06T15:00:00Z', open: 103, high: 105, low: 101, close: 104, volume: 30, nodes: [] },
  { time: '2026-10-06T15:30:00Z', open: 104, high: 106, low: 102, close: 105, volume: 40, nodes: [] },
  { time: '2026-10-06T16:00:00Z', open: 105, high: 107, low: 103, close: 106, volume: 50, nodes: [] },
];
const firePointer = (el, type, x, y) => {
  const event = new window.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y });
  event.pointerType = 'mouse';
  act(() => { el.dispatchEvent(event); });
};
const mountPane = async (fresh = true) => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: FRAMES, candles_with_recorded_nodes: 5, scopes: [] } }));
  if (fresh) window.localStorage.clear();
  const r = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('drawing-layer')).toBeInTheDocument());
  return r;
};
const placeFib = () => {
  fireEvent.click(document.querySelector('[data-testid="stock-dock-open-drawings"]') || screen.getByTestId('stock-inspector-tab-drawings'));
  fireEvent.click(screen.getByTestId('rail-tool-fib'));
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 150, 100);
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 450, 240);
};
const drawingId = (n) => [...document.querySelectorAll('[data-testid^="rail-select-"]')].map(b => b.getAttribute('data-testid').slice('rail-select-'.length))[n];
const drawingStore = () => JSON.parse(window.localStorage.getItem('floww.drawings.SPY') || '[]');

test('MOUNTED: fib preset style renders per-level colors, hidden levels, bands and labels', async () => {
  const first = await mountPane();
  placeFib();
  const id = drawingId(0);
  fireEvent.click(document.querySelector('[data-testid="stock-dock-open-drawings"]') || screen.getByTestId('stock-inspector-tab-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + id));
  // fib full-family style through the drawing style: distinct per-level colors,
  // one level hidden, bands on, labels off
  fireEvent.change(screen.getByTestId('rail-style-width'), { target: { value: '2' } });
  const drawing = drawingStore()[0];
  const styled = { ...drawing, style: { ...drawing.style, ratios: [0.382, 0.5, 0.618], levelColors: ['#e06c75', '#5ec986', '#72d7df'], showLevels: [true, false, true], fillOpacity: 0.35, labels: false, color: '#7fa6c0', width: 2 } };
  window.localStorage.setItem('floww.drawings.SPY', JSON.stringify([styled]));
  first.unmount();
  const { unmount } = await mountPane(false);
  // the HIDDEN level (showLevels[1]=false) is not painted: 2 visible levels
  await waitFor(() => expect(document.querySelectorAll('[data-testid="fib-level"]').length).toBe(2));
  const levels = [...document.querySelectorAll('[data-testid="fib-level"]')];
  // per-level colors ride the polylines (generic color never overrode them)
  const strokes = levels.map(l => l.getAttribute('stroke'));
  expect(strokes).toEqual(['#e06c75', '#72d7df']);
  // all painted levels carry geometry
  expect(levels.every(l => l.getAttribute('points'))).toBe(true);
  // band rects render between consecutive VISIBLE levels with the fill alpha
  expect(document.querySelectorAll('[data-testid="preset-band"]').length).toBe(1);
  // labels:false -> no level labels
  expect(document.querySelectorAll('[data-testid="preset-level-label"]').length).toBe(0);
  unmount();
});

test('MOUNTED: line extendRight projects to the domain edge; refusals keep the incumbent rendering', async () => {
  const r = await mountPane();
  fireEvent.click(document.querySelector('[data-testid="stock-dock-open-drawings"]') || screen.getByTestId('stock-inspector-tab-drawings'));
  fireEvent.click(screen.getByTestId('rail-tool-trend'));
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 150, 100);
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 450, 240);
  const id = drawingId(0);
  fireEvent.click(document.querySelector('[data-testid="stock-dock-open-drawings"]') || screen.getByTestId('stock-inspector-tab-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + id));
  const drawing = drawingStore()[0];
  // extendRight through the style row is not exposed for line yet — apply via
  // the persisted style directly (the adapter consumes d.style)
  window.localStorage.setItem('floww.drawings.SPY', JSON.stringify([{ ...drawing, style: { color: '#e3c16a', extendRight: true } }]));
  r.unmount();
  const r2 = await mountPane(false);
  await waitFor(() => expect(document.querySelector('[data-testid="drawing-shape"]')).toBeInTheDocument());
  const shape = document.querySelector('[data-testid="drawing-shape"]');
  const points = shape.getAttribute('points').split(' ').map(p => p.split(',').map(Number));
  expect(points[1][0]).toBeGreaterThan(450); // projected past the second anchor
  r2.unmount();
  // log scale on a nonpositive anchor refuses -> incumbent fallback keeps the
  // drawing painted and hit-testable
  const r3 = await mountPane();
  placeFib();
  const fid = drawingId(0);
  fireEvent.click(document.querySelector('[data-testid="stock-dock-open-drawings"]') || screen.getByTestId('stock-inspector-tab-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + fid));
  const fd = drawingStore()[0];
  window.localStorage.setItem('floww.drawings.SPY', JSON.stringify([{ ...fd, anchors: [{ t: fd.anchors[0].t, p: -5 }, { t: fd.anchors[1].t, p: -1 }], style: { logScale: true } }]));
  r3.unmount();
  const r4 = await mountPane(false);
  await waitFor(() => expect(document.querySelector('[data-testid="drawing-shape"]')).toBeInTheDocument());
  // refusal fallback: the incumbent fib wrapper renders with real level geometry
  expect(document.querySelector('[data-testid="drawing-shape"] polyline')).toBeTruthy();
  expect(document.querySelector('[data-testid="drawing-shape"] polyline').getAttribute('points')).toBeTruthy();
  r4.unmount();
});
