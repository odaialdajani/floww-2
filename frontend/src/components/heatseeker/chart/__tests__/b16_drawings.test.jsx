import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { TOOLS, createDrawing, magnet, reduceDrawings } from '../drawings/drawingReducer';
import DrawingRail from '../drawings/DrawingRail';
import { FIB_LEVELS, fibPrices, riskBox } from '../drawings/advancedTools';
import { PRESET_CAP, presetForNew, isDirty, applyPreset } from '../drawings/presetSchema';
test('drawings + presets', () => {
  expect(TOOLS).toContain('trend');
  expect(() => createDrawing('nope', [])).toThrow('unsupported-tool');
  const d = createDrawing('trend', [{ t: 1, p: 100 }]);
  expect(reduceDrawings([], { type: 'add', drawing: d })).toHaveLength(1);
  expect(reduceDrawings([d], { type: 'hide', id: d.id })[0].visible).toBe(false);
  expect(magnet(100.2, { open: 100, high: 101, low: 99, close: 100.5 })).toBe(100);
  expect(FIB_LEVELS).toContain(0.618);
  expect(fibPrices(100, 90)[0].price).toBe(100);
  expect(riskBox(100, 95, 110).analysisOnly).toBe(true);
  expect(PRESET_CAP).toBe(50);
  expect(presetForNew({ starred: 's', active: 'a' })).toBe('s');
  expect(isDirty({ style: { w: 1 } }, { style: { w: 2 } })).toBe(true);
  expect(applyPreset({ style: {} }, { style: { w: 2 } }).dirty).toBe(false);
});
test('rail lists drawings with select/delete/lock/hide actions', () => {
  const drawings = [
    { id: 'd1', tool: 'trend', visible: true, locked: false },
    { id: 'd2', tool: 'horizontal', visible: false, locked: true },
  ];
  const calls = {};
  const on = (name) => (id) => { calls[name] = id; };
  render(<DrawingRail drawings={drawings} selectedId="d1" onSelect={on('select')}
    onDelete={on('delete')} onToggleLock={on('lock')} onToggleHide={on('hide')} />);
  expect(screen.getByTestId('drawing-rail')).toBeInTheDocument();
  expect(screen.getAllByTestId('rail-drawing')).toHaveLength(2);
  fireEvent.click(screen.getByTestId('rail-select-d2'));
  expect(calls.select).toBe('d2');
  fireEvent.click(screen.getByTestId('rail-delete-d1'));
  expect(calls.delete).toBe('d1');
  fireEvent.click(screen.getByTestId('rail-lock-d1'));
  expect(calls.lock).toBe('d1');
  fireEvent.click(screen.getByTestId('rail-hide-d1'));
  expect(calls.hide).toBe('d1');
});
test('alert lines render armed levels and refuse stale ones on the chart', () => {
  const { default: RecordedPriceChart } = require('../../RecordedPriceChart');
  const frames = [
    { time: '2026-10-06T13:30:00+00:00', open: 100, high: 102, low: 99, close: 101, duration_seconds: 60, nodes: [] },
    { time: '2026-10-06T13:31:00+00:00', open: 101, high: 103, low: 100, close: 102, duration_seconds: 60, nodes: [] },
  ];
  const { unmount } = render(<RecordedPriceChart ticker="SPY" frames={frames}
    alertLines={[{ id: 'a1', price: 101, state: 'armed' }, { id: 'a2', price: 100.5, state: 'stale' }]} />);
  const lines = screen.getAllByTestId('alert-line');
  expect(lines).toHaveLength(2);
  expect(lines[0].getAttribute('data-state')).toBe('armed');
  expect(lines[1].getAttribute('data-state')).toBe('stale');
  expect(screen.getByRole('note')).toHaveTextContent(/stale alert refused/i);
  unmount();
});
test('tool registry covers evidence-backed tools, rejects the rest', () => {
  const { DRAWING_TOOLS, isSupportedTool, anchorsFor } = require('../drawings/toolRegistry');
  expect(DRAWING_TOOLS.length).toBeGreaterThanOrEqual(9);
  for (const tool of DRAWING_TOOLS) {
    expect(typeof tool.id).toBe('string');
    expect(anchorsFor(tool.id)).toBeGreaterThanOrEqual(1);
    expect(isSupportedTool(tool.id)).toBe(true);
  }
  expect(isSupportedTool('nope')).toBe(false);
  expect(anchorsFor('fib')).toBe(2);
  expect(anchorsFor('horizontal')).toBe(1);
});
test('drawing persistence isolates symbols, recovers corrupt rows, caps quota', () => {
  const { saveDrawings, loadDrawings, clearDrawings } = require('../drawings/drawingPersistence');
  clearDrawings('SPY'); clearDrawings('QQQ');
  expect(loadDrawings('SPY')).toEqual([]);
  saveDrawings('SPY', [{ id: 'd1', tool: 'trend' }]);
  expect(loadDrawings('SPY')).toHaveLength(1);
  expect(loadDrawings('QQQ')).toEqual([]);
  window.localStorage.setItem('floww.drawings.SPY', '{{{');
  expect(loadDrawings('SPY')).toEqual([]);
  const many = Array.from({ length: 200 }, (_, i) => ({ id: 'd' + i, tool: 'trend' }));
  expect(() => saveDrawings('SPY', many)).toThrow(/quota/);
});

// --- B16 geometry, arbitration, magnet, mounted creation/drag/keyboard ---
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const geom = require('../drawings/drawingReducer');
const frames2 = [
  { time: '2026-09-10T14:00:00+00:00', open: 100, high: 102, low: 99, close: 101 },
  { time: '2026-09-10T14:01:00+00:00', open: 101, high: 103, low: 99.5, close: 102 },
];

test('B16 logical anchors survive zoom/resize through real projection', () => {
  const vp1 = geom.viewportFor(frames2, 600, 320);
  const vp2 = geom.viewportFor(frames2, 1200, 480); // resize
  const zoomed = { ...vp1, tMin: vp1.tMin + 15000, pMax: vp1.pMax - 0.5 }; // zoom in
  expect(vp1).toBeTruthy();
  const anchor = { t: Date.parse('2026-09-10T14:00:30+00:00'), p: 100.5 };
  const px1 = geom.projectAnchor(anchor, vp1);
  const px2 = geom.projectAnchor(anchor, vp2);
  expect(px1).not.toEqual(px2); // pixels move…
  // …but the logical anchor round-trips identically through EVERY viewport.
  for (const vp of [vp1, vp2, zoomed]) {
    const back = geom.unprojectPoint(geom.projectAnchor(anchor, vp), vp);
    expect(back.t).toBe(anchor.t);
    expect(back.p).toBeCloseTo(anchor.p, 9);
  }
  expect(geom.viewportFor([], 600, 320)).toBe(null); // honest empty refusal
  expect(geom.viewportFor(frames2, 0, 320)).toBe(null);
});

test('B16 OHLC-only magnet: snaps to candle values only, honors radius', () => {
  const vp = geom.viewportFor(frames2, 600, 320);
  // x=150,y=100 -> logical ~ (14:00:15, 101.12): nearest frame 14:00, OHLC 101.
  const snapped = geom.magnetPoint(geom.unprojectPoint({ x: 150, y: 100 }, vp), frames2, 0.25, vp);
  expect(snapped.t).toBe(Date.parse('2026-09-10T14:00:00+00:00'));
  expect([100, 102, 99, 101]).toContain(snapped.p);
  // Far from every OHLC value: no invented snap — the raw price stays.
  const far = geom.magnetPoint({ t: Date.parse('2026-09-10T14:00:00+00:00'), p: 99.99 }, frames2, 0.001, vp);
  expect(far.p).toBe(99.99);
  // Empty frames: point passes through untouched.
  expect(geom.magnetPoint({ t: 1, p: 2 }, [], 0.25, vp)).toEqual({ t: 1, p: 2 });
});

test('B16 reducer: edit/nudge refuse locked drawings; toggle cases; arbitration contract', () => {
  const d = geom.createDrawing('trend', [{ t: 1, p: 100 }, { t: 2, p: 101 }]);
  const locked = { ...d, locked: true };
  expect(geom.canEdit(d)).toBe(true);
  expect(geom.canEdit(locked)).toBe(false);
  // update on locked: returned unchanged (same revision, same anchors).
  const refused = geom.reduceDrawings([locked], { type: 'update', id: locked.id, anchors: [{ t: 9, p: 9 }] })[0];
  expect(refused.revision).toBe(locked.revision);
  expect(refused.anchors).toEqual(locked.anchors);
  // nudge shifts anchors + bumps revision; locked refuses.
  const nudged = geom.reduceDrawings([d], { type: 'nudge', id: d.id, dt: 10, dp: -1 })[0];
  expect(nudged.anchors[0]).toEqual({ t: 11, p: 99 });
  expect(nudged.revision).toBe(d.revision + 1);
  const nudgedLocked = geom.reduceDrawings([locked], { type: 'nudge', id: locked.id, dt: 10, dp: -1 })[0];
  expect(nudgedLocked.anchors).toEqual(locked.anchors);
  expect(geom.reduceDrawings([d], { type: 'toggleLock', id: d.id })[0].locked).toBe(true);
  expect(geom.reduceDrawings([d], { type: 'toggleVisible', id: d.id })[0].visible).toBe(false);
  expect(geom.reduceDrawings([d], { type: 'undo' })).toEqual([]);
  // Interaction arbitration: only a live selected-drawing drag suppresses pan.
  expect(geom.suppressesPan({ mode: 'drawing-drag', id: d.id })).toBe(true);
  expect(geom.suppressesPan({ mode: 'pan', id: d.id })).toBe(false);
  expect(geom.suppressesPan(null)).toBe(false);
});

test('B16 geometryFor renders every named tool family', () => {
  const vp = geom.viewportFor(frames2, 600, 320);
  const a = { t: Date.parse('2026-09-10T14:00:00+00:00'), p: 100 };
  const b = { t: Date.parse('2026-09-10T14:01:00+00:00'), p: 101.5 };
  for (const tool of ['horizontal', 'trend', 'vertical', 'arrow']) {
    const g = geom.geometryFor(tool, [a, b], vp);
    expect(g.kind).toBe('line');
    expect(g.points).toHaveLength(2);
  }
  const rect = geom.geometryFor('rectangle', [a, b], vp);
  expect(rect.kind).toBe('rect');
  expect(rect.width).toBeGreaterThan(0);
  expect(geom.geometryFor('text', [a], vp).kind).toBe('label');
  expect(geom.geometryFor('trend', [], vp)).toBe(null);
  expect(geom.geometryFor('trend', [{ t: NaN, p: 1 }], vp)).toBe(null);
});


// jsdom's PointerEvent does not carry clientX/pointerType through React's
// synthetic proxy, so pointer geometry is dispatched as pointerdown-typed
// MouseEvents with real coordinates (real browsers need no such help).
const firePointer = (el, type, x, y) => {
  const { act } = require('@testing-library/react');
  const event = new window.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y });
  event.pointerType = 'mouse';
  act(() => { el.dispatchEvent(event); });
  return event;
};

test('B16 MOUNTED: create by pointer, drag with pan suppressed, nudge by keyboard, undo, cancel', async () => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: frames2, candles_with_recorded_nodes: 0, scopes: [] } }));
  const { default: PriceNodeHistory } = require('../../PriceNodeHistory');
  const { waitFor } = require('@testing-library/react');
  window.localStorage.removeItem('floww.drawings.SPY'); // isolate from earlier fixtures
  const before = window.localStorage.getItem('floww.drawings.SPY');
  expect(before).toBe(null);
  const { unmount } = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  expect(screen.getByTestId('drawing-layer')).toBeInTheDocument();
  // Creation: pick trend, place two anchors — both magnetized to OHLC times.
  fireEvent.click(screen.getByTestId('rail-tool-trend'));
  expect(screen.getByTestId('rail-cancel')).toBeInTheDocument();
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 150, 100);
  expect(screen.getAllByTestId('draft-anchor')).toHaveLength(1);
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 450, 260);
  expect(screen.queryByTestId('draft-anchor')).not.toBeInTheDocument(); // draft committed
  const persisted = JSON.parse(window.localStorage.getItem('floww.drawings.SPY'));
  expect(persisted).toHaveLength(1);
  expect(persisted[0].tool).toBe('trend');
  expect(persisted[0].anchors[0].t).toBe(Date.parse('2026-09-10T14:00:00+00:00'));
  expect(persisted[0].anchors[1].t).toBe(Date.parse('2026-09-10T14:01:00+00:00'));
  const [p0, p1] = persisted[0].anchors.map(a => a.p);
  expect([100, 102, 99, 101]).toContain(p0);
  expect([101, 103, 99.5, 102]).toContain(p1);
  const shape = screen.getByTestId('drawing-shape');
  expect(shape.getAttribute('points').split(' ')).toHaveLength(2); // rendered line
  // Drag: pointer on the shape starts a selected-drawing drag (pan suppressed).
  firePointer(shape, 'pointerdown', 450, 260);
  expect(screen.getByTestId('drawing-layer').getAttribute('data-arbitration')).toBe('drawing-drag');
  firePointer(screen.getByTestId('drawing-layer'), 'pointermove', 300, 200);
  const dragged = JSON.parse(window.localStorage.getItem('floww.drawings.SPY'))[0];
  expect(dragged.anchors).not.toEqual(persisted[0].anchors); // moved
  expect(dragged.revision).toBeGreaterThan(persisted[0].revision);
  firePointer(screen.getByTestId('drawing-layer'), 'pointerup', 300, 200);
  expect(screen.getByTestId('drawing-layer').getAttribute('data-arbitration')).toBe('idle');
  // Keyboard nudge: arrows move the selected drawing by one logical step.
  firePointer(shape, 'pointerdown', 300, 200); // select + drag start
  firePointer(screen.getByTestId('drawing-layer'), 'pointerup', 300, 200);
  const beforeNudge = JSON.parse(window.localStorage.getItem('floww.drawings.SPY'))[0].anchors;
  fireEvent.keyDown(window, { key: 'ArrowLeft' });
  const afterNudge = JSON.parse(window.localStorage.getItem('floww.drawings.SPY'))[0].anchors;
  expect(afterNudge[0].t).toBeLessThan(beforeNudge[0].t);
  // Lock refuses nudging: revision frozen while locked.
  fireEvent.click(screen.getByTestId('rail-lock-' + dragged.id));
  const lockedRev = JSON.parse(window.localStorage.getItem('floww.drawings.SPY'))[0].revision;
  fireEvent.keyDown(window, { key: 'ArrowUp' });
  expect(JSON.parse(window.localStorage.getItem('floww.drawings.SPY'))[0].revision).toBe(lockedRev);
  // Escape cancels an active draft before any anchor lands.
  fireEvent.click(screen.getByTestId('rail-tool-text'));
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByTestId('rail-cancel')).not.toBeInTheDocument();
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 200, 200);
  expect(JSON.parse(window.localStorage.getItem('floww.drawings.SPY'))).toHaveLength(1); // nothing added
  // Undo removes the drawing and persists the removal.
  fireEvent.click(screen.getByTestId('rail-undo'));
  expect(JSON.parse(window.localStorage.getItem('floww.drawings.SPY'))).toEqual([]);
  unmount();
});

test('B16 MOUNTED: persisted drawings survive a real remount through the layer', async () => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: frames2, candles_with_recorded_nodes: 0, scopes: [] } }));
  window.localStorage.setItem('floww.drawings.SPY', JSON.stringify([
    { id: 'keep1', tool: 'rectangle', anchors: [{ t: Date.parse('2026-09-10T14:00:00+00:00'), p: 100 }, { t: Date.parse('2026-09-10T14:01:00+00:00'), p: 102 }], visible: true, locked: false },
  ]));
  const { waitFor } = require('@testing-library/react');
  const { default: PriceNodeHistory } = require('../../PriceNodeHistory');
  const first = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('drawing-shape')).toBeInTheDocument());
  expect(screen.getByTestId('drawing-shape').tagName).toBe('rect');
  first.unmount();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('drawing-shape')).toBeInTheDocument());
  expect(screen.getByTestId('rail-drawing')).toHaveTextContent('rectangle');
});
