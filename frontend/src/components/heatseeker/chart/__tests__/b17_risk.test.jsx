import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import { openStockPanel } from '../../../../testUtils/openStockPanel';
import { createDrawing, geometryFor, TOOLS } from '../drawings/drawingReducer';
import { DRAWING_TOOLS, isSupportedTool, anchorsFor, toolFamily } from '../drawings/toolRegistry';
import { riskLevels } from '../drawings/advancedTools';
import { loadDrawings, saveDrawings } from '../drawings/drawingPersistence';
import { actionFor, DEFAULT_SHORTCUTS } from '../ChartShortcuts';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));

const firePointer = (el, type, x, y, extra = {}) => {
  const event = new window.PointerEvent(type, { bubbles: true, clientX: x, clientY: y, pointerType: 'mouse', ...extra });
  act(() => { el.dispatchEvent(event); });
  return event;
};
const arm = () => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: [
    { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, nodes: [] },
    { time: '2026-10-06T14:30:00Z', open: 101, high: 104, low: 100, close: 103, nodes: [] },
    { time: '2026-10-06T15:00:00Z', open: 103, high: 105, low: 101, close: 104, nodes: [] },
  ], candles_with_recorded_nodes: 3, scopes: [] } }));
};
const vp = { width: 600, height: 320, tMin: 0, tMax: 300000, pMin: 90, pMax: 110 };
const R3 = [{ t: 0, p: 100 }, { t: 150000, p: 90 }, { t: 300000, p: 110 }];

// CHART-C090 (preserved 310-row, owner-approved 2026-10-24): "Alt+L/S
// analysis entry/stop/target risk box, never broker intent" — the anchor
// semantics the old refusal guarded are defined BY the row: three anchors
// (entry/stop/target), analysis-only, never a broker intent.
test('riskLevels is order-independent and refuses degenerate/non-finite risk', () => {
  // any permutation of the same three prices yields the same long box
  const expectedLong = { entry: 100, stop: 90, target: 110, side: 'long', rMultiple: 1 };
  for (const perm of [[100, 90, 110], [90, 110, 100], [110, 100, 90], [90, 100, 110]]) {
    const box = riskLevels(perm, 'long');
    expect(box).toMatchObject(expectedLong);
  }
  // short flips stop/target around the middle price
  expect(riskLevels([100, 90, 110], 'short')).toMatchObject({ entry: 100, stop: 110, target: 90, side: 'short', rMultiple: 1 });
  // R-multiple is reward / risk: target 10 away, stop 5 away -> 2.0
  expect(riskLevels([100, 95, 110], 'long').rMultiple).toBe(2);
  // zero risk (entry == stop) is a division by zero — refused, never an invented R
  expect(riskLevels([100, 100, 110], 'long')).toBeNull();
  expect(riskLevels([100, NaN, 110], 'long')).toBeNull();
  expect(riskLevels([100, 90], 'long')).toBeNull();
});

test('the registry admits risk as a three-anchor analysis-only tool (CHART-C090)', () => {
  expect(isSupportedTool('risk')).toBe(true);
  expect(anchorsFor('risk')).toBe(3);
  expect(toolFamily('risk')).toBe('risk');
  expect(TOOLS).toContain('risk');
  expect(DRAWING_TOOLS.map(t => t.id)).toContain('risk');
  const d = createDrawing('risk', R3, { side: 'short' });
  expect(d.tool).toBe('risk');
  expect(d.side).toBe('short');
  expect(d.visible).toBe(true);
  expect(() => createDrawing('madeup', R3)).toThrow('unsupported-tool');
});

test('risk geometry is order-independent: any placement order renders the same levels', () => {
  const perms = [
    [{ t: 0, p: 100 }, { t: 150000, p: 90 }, { t: 300000, p: 110 }],
    [{ t: 300000, p: 110 }, { t: 0, p: 100 }, { t: 150000, p: 90 }],
    [{ t: 150000, p: 90 }, { t: 300000, p: 110 }, { t: 0, p: 100 }],
  ];
  const geometries = perms.map(anchors => geometryFor('risk', anchors, vp, { side: 'long' }));
  for (const g of geometries) {
    expect(g.kind).toBe('risk');
    expect(g.rMultiple).toBe(1);
    expect(g.x0).toBeLessThan(g.x1);
  }
  const first = geometries[0];
  for (const g of geometries.slice(1)) {
    expect(g.levels.map(l => l.role)).toEqual(first.levels.map(l => l.role));
    expect(g.levels.map(l => l.price)).toEqual(first.levels.map(l => l.price));
    expect(g.levels.map(l => l.y)).toEqual(first.levels.map(l => l.y));
  }
  const roles = Object.fromEntries(first.levels.map(l => [l.role, l.price]));
  expect(roles).toEqual({ entry: 100, stop: 90, target: 110 });
  // degenerate anchors render nothing (honest refusal, no fabricated zones)
  expect(geometryFor('risk', [{ t: 0, p: 100 }, { t: 1, p: 100 }, { t: 2, p: 110 }], vp, { side: 'long' })).toBeNull();
});

test('a saved risk drawing loads back and renders the analysis-only box on the real chart', async () => {
  arm();
  window.localStorage.clear();
  saveDrawings('SPY', [createDrawing('risk', R3, { side: 'long' })]);
  const loaded = loadDrawings('SPY');
  expect(loaded).toHaveLength(1);
  expect(loaded[0].tool).toBe('risk');
  expect(loaded[0].side).toBe('long');
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '3'));
  const shape = await screen.findByTestId('risk-shape');
  expect(shape).toBeInTheDocument();
  const label = screen.getByTestId('risk-label');
  expect(label.textContent).toMatch(/R 1\.0 · long · analysis only/);
  expect(screen.getByTestId('risk-zone-stop')).toBeInTheDocument();
  expect(screen.getByTestId('risk-zone-target')).toBeInTheDocument();
  // the rail lists the risk drawing like every other tool's output
  openStockPanel('drawings');
  expect(screen.getAllByTestId('rail-drawing').length).toBe(1);
  expect(screen.getAllByTestId('rail-drawing')[0]).toHaveTextContent(/risk/);
});

test('the rail offers the risk tool and picking it arms a three-anchor draft', async () => {
  arm();
  window.localStorage.clear();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '3'));
  if (document.querySelector('[data-testid="stock-dock-open-drawings"]')) fireEvent.click(document.querySelector('[data-testid="stock-dock-open-drawings"]') || screen.getByTestId('stock-inspector-tab-drawings'));
  fireEvent.click(screen.getByTestId('rail-tool-risk'));
  if (document.querySelector('[data-testid="stock-dock-open-drawings"]')) fireEvent.click(document.querySelector('[data-testid="stock-dock-open-drawings"]') || screen.getByTestId('stock-inspector-tab-drawings'));
  expect(screen.getByTestId('rail-tool-risk')).toHaveAttribute('aria-pressed', 'true');
  // the draft needs three anchors (CHART-C090 entry/stop/target) before it commits
  expect(anchorsFor('risk')).toBe(3);
  if (document.querySelector('[data-testid="stock-dock-open-drawings"]')) fireEvent.click(document.querySelector('[data-testid="stock-dock-open-drawings"]') || screen.getByTestId('stock-inspector-tab-drawings'));
  expect(screen.getByTestId('rail-cancel')).toBeInTheDocument();
});

test("CHART-C090: Alt+L/Alt+S arm the risk tool by side; modifier combos never fire plain-key chart shortcuts", async () => {
  // The workspace's rebindable single-key dispatch must not claim Alt combos
  // (the pulse-page precedent applied to the chart shell) — RED before the guard.
  expect(actionFor(DEFAULT_SHORTCUTS, { target: { tagName: "BODY" }, key: "l", altKey: true })).toBe(null);
  // plain keys keep their incumbent mapping
  expect(actionFor(DEFAULT_SHORTCUTS, { target: { tagName: "BODY" }, key: "l" })).toBe("layouts");
  arm();
  window.localStorage.removeItem("floww.drawings.SPY");
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("drawing-layer")).toBeInTheDocument());
  const layer = screen.getByTestId("drawing-layer");
  // Alt+L arms the risk tool with side long; three pointer anchors commit it
  openStockPanel('drawings');
  fireEvent.keyDown(window, { key: "l", altKey: true });
  expect(screen.getByTestId("rail-tool-risk")).toHaveAttribute("aria-pressed", "true");
  firePointer(layer, "pointerdown", 150, 90);
  firePointer(layer, "pointerdown", 300, 150);
  firePointer(layer, "pointerdown", 450, 210);
  let persisted = JSON.parse(window.localStorage.getItem("floww.drawings.SPY"));
  expect(persisted).toHaveLength(1);
  expect(persisted[0].tool).toBe("risk");
  expect(persisted[0].side).toBe("long");
  // Alt+S arms side short for the next box
  fireEvent.keyDown(window, { key: "s", altKey: true });
  expect(screen.getByTestId("rail-tool-risk")).toHaveAttribute("aria-pressed", "true");
  firePointer(layer, "pointerdown", 150, 90);
  firePointer(layer, "pointerdown", 300, 150);
  firePointer(layer, "pointerdown", 450, 210);
  persisted = JSON.parse(window.localStorage.getItem("floww.drawings.SPY"));
  expect(persisted).toHaveLength(2);
  expect(persisted[1].tool).toBe("risk");
  expect(persisted[1].side).toBe("short");
});
