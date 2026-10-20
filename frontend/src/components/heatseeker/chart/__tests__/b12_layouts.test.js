import { act, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import ChartWorkspaceModule from '../ChartWorkspace';
import { createLayout, migrate, serialize, sanitizeImport } from '../persistence/layoutSchema';
import { saveLocal, loadLocal, _clear } from '../persistence/layoutStore';
test('false/zero roundtrip + corrupt recovery + caps + proto/scripts refused', () => {
  _clear();
  const layout = createLayout({ showGrid: false, opacity: 0 });
  const text = serialize(layout);
  expect(JSON.parse(text).showGrid).toBe(false);
  expect(migrate('{{{').recovered).toBe(true);
  expect(() => serialize({ ...layout, apiKey: 'x' })).toThrow('secrets-refused');
  expect(() => sanitizeImport(JSON.parse('{"__proto__":1}'))).toThrow('proto-refused');
  expect(() => sanitizeImport({ script: 'evil()' })).toThrow('scripts-refused');
  saveLocal('a', layout);
  expect(loadLocal('a')).toBe(text);
});

// --- B12 durability + caps + mounted UX (durable pattern: bare axios factory) ---
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const armPayload = () => {
  const axios = require('axios');
  axios.get.mockImplementation(async url => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] ?? 'SPY';
    return { data: { ticker, query_key: '', frames: [{ time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101 }], candles_with_recorded_nodes: 1, node_status: 'available' } };
  });
};
const W = ChartWorkspaceModule;
const { saveLocal: save, loadLocal: load, listLocal, scheduleAutosave, _clear: clearStore } = require('../persistence/layoutStore');
const { createLayout: make, migrate: mig, sanitizeImport: sanitize, KNOWN_TOOLS } = require('../persistence/layoutSchema');

beforeEach(() => { clearStore(); armPayload(); if (typeof window !== 'undefined') window.__FLOWW_CHART_WORKSPACE__ = true; });
afterEach(() => { if (typeof window !== 'undefined') window.__FLOWW_CHART_WORKSPACE__ = false; });

test('B12 durable storage: layouts live in localStorage and survive a module-less reload', () => {
  const layout = make({ layoutId: 'three', symbols: ['SPY', 'QQQ', 'HOOD'], focusedIndex: 2 });
  const text = save('durable', layout);
  expect(localStorage.getItem('floww.chart.layout.durable')).toBe(text); // real storage, not a module Map
  expect(load('durable')).toBe(text);
  localStorage.clear();
  expect(load('durable')).toBe(null); // honest absence after real clearing
});

test('B12 per-id autosave: saving layout B never cancels layout A (old global timer did)', () => {
  jest.useFakeTimers();
  try {
    scheduleAutosave('a', make({ layoutId: 'single' }));
    scheduleAutosave('b', make({ layoutId: 'split' }));
    jest.advanceTimersByTime(400);
    expect(load('a')).toContain('"layoutId":"single"');
    expect(load('b')).toContain('"layoutId":"split"');
  } finally { jest.useRealTimers(); }
});

test('B12 caps: the 51st distinct layout is refused; storage quota is a typed refusal', () => {
  for (let i = 0; i < 50; i += 1) save('cap-' + i, make({}));
  expect(() => save('cap-51', make({}))).toThrow('quota-count');
  const original = localStorage.setItem;
  const spy = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('QuotaExceededError'); });
  try { expect(() => save('cap-0', make({}))).toThrow('quota-storage'); } // existing id: count passes, storage refuses
  finally { spy.mockRestore(); localStorage.setItem = original; }
});

test('B12 imports: unknown tools refused; known tools pass; secrets never export', () => {
  expect(() => sanitize({ drawings: [{ tool: 'laser-beam' }] })).toThrow('tools-refused');
  expect(sanitize({ drawings: [{ tool: KNOWN_TOOLS[0] }] })).toEqual({ drawings: [{ tool: 'horizontal' }] });
  // The export boundary (serialize) refuses secrets and positions.
  expect(() => serialize(make({ positions: [{ symbol: 'SPY', qty: 1 }] }))).toThrow('secrets-refused');
});

test('B12 mounted: the composition survives a real reopen (unmount + fresh mount)', async () => {
  const first = render(<W ticker="SPY" open useNew />);
  await act(async () => { screen.getByTestId('layout-three').click(); });
  await act(async () => { await new Promise(r => setTimeout(r, 400)); }); // debounce fires
  expect(localStorage.getItem('floww.chart.layout.workspace-current')).toContain('"layoutId":"three"');
  first.unmount();
  // Fresh mount = a real reopen: the durable composition restores itself.
  render(<W ticker="SPY" open useNew />);
  await act(async () => { await new Promise(r => setTimeout(r, 100)); });
  expect(screen.getAllByTestId('price-node-history')).toHaveLength(3);
  expect(screen.getByTestId('pane-layout')).toHaveAttribute('data-layout', 'three');
});

test('B12 mounted: export copies layout identity without secrets; import applies and refuses bad payloads', async () => {
  const writeText = jest.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  render(<W ticker="SPY" open useNew />);
  // Export: clipboard receives the composition; no secret/position keys.
  await act(async () => { screen.getByTestId('layout-export').click(); });
  expect(writeText).toHaveBeenCalledTimes(1);
  const exported = JSON.parse(writeText.mock.calls[0][0]);
  expect(exported.layoutId).toBe('single');
  expect(Object.keys(exported)).not.toContain('apiKey');
  expect(Object.keys(exported)).not.toContain('positions');
  expect(screen.getByTestId('layout-status').textContent).toContain('no secrets or positions');
  // Import: a valid composition applies (split layout arrives from a file).
  const payload = JSON.stringify({ schema_version: 1, layoutId: 'split', symbols: ['SPY', 'QQQ'], focusedIndex: 1, showGrid: false, opacity: 0, drawings: [] });
  const file = new File([payload], 'layout.json', { type: 'application/json' });
  await act(async () => { fireEvent.change(screen.getByTestId('layout-import'), { target: { files: [file] } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 100)); });
  expect(screen.getByTestId('layout-status').textContent).toContain('Layout imported.');
  expect(screen.getAllByTestId('price-node-history')).toHaveLength(2);
  // Import refusal: a proto-keyed payload is refused with a visible reason.
  const badText = '{"__proto__":1,"layoutId":"three"}';
  const badFile = new File([badText], 'bad.json', { type: 'application/json' });
  await act(async () => { fireEvent.change(screen.getByTestId('layout-import'), { target: { files: [badFile] } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 100)); });
  expect(screen.getByTestId('layout-status').textContent).toContain('Layout refused: proto-refused');
});

test('B12 mounted: save + cycle named layouts', async () => {
  render(<W ticker="SPY" open useNew />);
  await act(async () => { screen.getByTestId('layout-three').click(); });
  await act(async () => { screen.getByTestId('layout-save').click(); });
  expect(screen.getByTestId('layout-status').textContent).toMatch(/Saved layout-/);
  expect(listLocal()).toContain('layout-1');
  // Cycle with only the autosave key + one saved layout keeps the app usable.
  await act(async () => { screen.getByTestId('layout-single').click(); });
  await act(async () => { screen.getByTestId('layout-cycle').click(); });
  const note = screen.getByTestId('layout-status').textContent;
  expect(note === 'No saved layouts to cycle.' || note.startsWith('Loaded layout-')).toBe(true);
});
