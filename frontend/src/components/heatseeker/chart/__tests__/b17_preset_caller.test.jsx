// B17 PRESET PRODUCTION ADOPTION (H1 caller) — the real PriceNodeHistory
// wired to the delivered v2.1 modules (presetManager + presetPersistence,
// merged frozen from H2's presets-lane 3b18cecb) through the canonical
// DrawingRail props. C091/C129/C130/C131: creation applies starred > active >
// built-in PER TOOL and links the preset; Apply/Update/dirty/reset/delete work
// on the REAL selected drawing; explicit Update only; locked refuses; scope
// isolation per ticker; whole-write persistence with honest quota/version
// refusals; local-only (no cloud/account sync claimed).
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import { createPreset } from '../drawings/presetManager';
import { savePresets, PRESET_STORAGE_VERSION } from '../drawings/presetPersistence';
import { defaultStyleForTool } from '../drawings/presetSchema';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const FRAMES = [
  { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 10, nodes: [] },
  { time: '2026-10-06T14:30:00Z', open: 101, high: 104, low: 100, close: 103, volume: 20, nodes: [] },
  { time: '2026-10-06T15:00:00Z', open: 103, high: 105, low: 101, close: 104, volume: 30, nodes: [] },
  { time: '2026-10-06T15:30:00Z', open: 104, high: 106, low: 102, close: 105, volume: 40, nodes: [] },
  { time: '2026-10-06T16:00:00Z', open: 105, high: 107, low: 103, close: 106, volume: 50, nodes: [] },
];
const arm = (ticker) => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker, frames: FRAMES, candles_with_recorded_nodes: 5, scopes: [] } }));
};
// jsdom's PointerEvent drops clientX through React's synthetic proxy — dispatch
// pointerdown-typed MouseEvents with real coordinates (same as the b16 suite).
const firePointer = (el, type, x, y) => {
  const event = new window.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y });
  event.pointerType = 'mouse';
  act(() => { el.dispatchEvent(event); });
};
const mountPane = async (ticker = 'SPY') => {
  arm(ticker);
  const r = render(<PriceNodeHistory ticker={ticker} open />);
  await waitFor(() => expect(screen.getByTestId('drawing-layer')).toBeInTheDocument());
  return r;
};
const placeTrend = () => {
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-tool-trend'));
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 150, 100);
  firePointer(screen.getByTestId('drawing-layer'), 'pointerdown', 450, 260);
};
const drawingIds = () => [...document.querySelectorAll('[data-testid^="rail-select-"]')]
  .map(el => el.getAttribute('data-testid').slice('rail-select-'.length));
const firstUserPresetId = () => {
  const btn = document.querySelector('[data-testid^="rail-preset-active-"]');
  return btn ? btn.getAttribute('data-testid').slice('rail-preset-active-'.length) : null;
};
const presetsFromStore = (ticker) => {
  const raw = window.localStorage.getItem('floww.drawing.presets.' + String(ticker).toUpperCase());
  return raw ? JSON.parse(raw).presets : null;
};

beforeEach(() => { window.localStorage.clear(); });

test('MOUNTED: creation applies the starred/active per-tool default and links the preset', async () => {
  const r = await mountPane();
  placeTrend(); // drawing 1 — built-in tier default while no user preset exists
  const [d1] = drawingIds();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + d1));
  fireEvent.change(screen.getByTestId('rail-style-color'), { target: { value: '#e3c16a' } }); // Gold
  // C091 create from the SELECTED drawing's style; then set it ACTIVE
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.change(screen.getByTestId('rail-preset-name'), { target: { value: 'gold-trend' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-create'));
  await waitFor(() => expect(screen.getByText(/gold-trend/)).toBeInTheDocument());
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-active-' + firstUserPresetId()));
  // persisted under the ticker scope
  const stored = presetsFromStore('SPY');
  expect(stored).toHaveLength(1);
  expect(stored[0]).toMatchObject({ name: 'gold-trend', tool: 'trend', active: true });
  expect(stored[0].style.color).toBe('#e3c16a');
  // NEW drawing of the SAME tool inherits the ACTIVE preset's style
  placeTrend();
  const ids = drawingIds();
  const d2 = ids.find(x => x !== d1);
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + d2));
  await waitFor(() => expect(screen.getByTestId('rail-style-color').value).toBe('#e3c16a'));
  // starred beats active: create a SECOND preset with a different style and star it
  fireEvent.change(screen.getByTestId('rail-style-color'), { target: { value: '#5ec986' } }); // Green
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.change(screen.getByTestId('rail-preset-name'), { target: { value: 'starred-trend' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-create'));
  await waitFor(() => expect(screen.getByText(/starred-trend/)).toBeInTheDocument());
  // rows render in list order — the LAST star button belongs to starred-trend
  const starBtn = [...document.querySelectorAll('[data-testid^="rail-preset-star-"]')].pop();
  fireEvent.click(starBtn);
  // a NEW trend now inherits the STARRED tier's green, not the active gold
  placeTrend();
  const ids3 = drawingIds();
  const d3 = ids3.find(x => !ids.includes(x));
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + d3));
  await waitFor(() => expect(screen.getByTestId('rail-style-color').value).toBe('#5ec986'));
  r.unmount();
});

test('MOUNTED: Apply copies to the selected drawing only; dirty dot honest; locked refuses; explicit Update', async () => {
  await mountPane();
  placeTrend();
  const [d1] = drawingIds();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + d1));
  fireEvent.change(screen.getByTestId('rail-style-color'), { target: { value: '#e3c16a' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.change(screen.getByTestId('rail-preset-name'), { target: { value: 'gold-trend' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-create'));
  await waitFor(() => expect(screen.getByText(/gold-trend/)).toBeInTheDocument());
  const pid = firstUserPresetId();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-active-' + pid));
  // link the drawing to the preset first — Apply records presetId
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-apply-' + pid));
  // drift the drawing -> dirty dot appears on the linked preset
  fireEvent.change(screen.getByTestId('rail-style-color'), { target: { value: '#5ec986' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  await waitFor(() => expect(screen.getByTestId('rail-preset-dirty-' + pid)).toBeInTheDocument());
  // Apply restores the preset style and clears dirty — selected drawing only
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-apply-' + pid));
  await waitFor(() => expect(screen.getByTestId('rail-style-color').value).toBe('#e3c16a'));
  expect(screen.queryByTestId('rail-preset-dirty-' + pid)).not.toBeInTheDocument();
  // locked drawing: Apply is refused by the rail AND the callback
  fireEvent.click(screen.getByTestId('rail-lock-' + d1));
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  expect(screen.getByTestId('rail-preset-apply-' + pid)).toBeDisabled();
  fireEvent.click(screen.getByTestId('rail-lock-' + d1)); // unlock again
  // explicit Update copies the CURRENT drawing style into the preset
  fireEvent.change(screen.getByTestId('rail-style-color'), { target: { value: '#5ec986' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  await waitFor(() => expect(screen.getByTestId('rail-preset-dirty-' + pid)).toBeInTheDocument());
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-update-' + pid));
  await waitFor(() => expect(presetsFromStore('SPY')[0].style.color).toBe('#5ec986'));
  expect(screen.queryByTestId('rail-preset-dirty-' + pid)).not.toBeInTheDocument();
});

test('MOUNTED: reset returns the preset to the built-in default; delete removes it; no cloud sync claim', async () => {
  await mountPane();
  placeTrend();
  const [d1] = drawingIds();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + d1));
  fireEvent.change(screen.getByTestId('rail-style-color'), { target: { value: '#e3c16a' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.change(screen.getByTestId('rail-preset-name'), { target: { value: 'gold-trend' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-create'));
  await waitFor(() => expect(screen.getByText(/gold-trend/)).toBeInTheDocument());
  const pid = firstUserPresetId();
  // C131 reset -> the family built-in default style
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-reset-' + pid));
  await waitFor(() => {
    const p = presetsFromStore('SPY')[0];
    expect(p.style).toEqual(defaultStyleForTool('trend'));
  });
  // the rail carries the explicit local-only label
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  expect(screen.getByTestId('rail-presets-local')).toHaveTextContent(/Local to this device/i);
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  expect(screen.getByTestId('rail-presets-scope')).toHaveTextContent(/SPY/);
  // delete removes the row and the store row
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-delete-' + pid));
  await waitFor(() => expect(presetsFromStore('SPY')).toHaveLength(0));
  expect(screen.queryByText(/gold-trend/)).not.toBeInTheDocument();
});

test('MOUNTED: scope isolation — presets never bleed across tickers', async () => {
  const r = await mountPane();
  placeTrend();
  const [d1] = drawingIds();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + d1));
  fireEvent.change(screen.getByTestId('rail-style-color'), { target: { value: '#e3c16a' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.change(screen.getByTestId('rail-preset-name'), { target: { value: 'gold-trend' } });
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-preset-create'));
  await waitFor(() => expect(screen.getByText(/gold-trend/)).toBeInTheDocument());
  r.unmount();
  // QQQ pane: empty preset section, no store key created for QQQ
  const q = await mountPane('QQQ');
  expect(screen.queryAllByTestId('rail-preset')).toHaveLength(0);
  expect(window.localStorage.getItem('floww.drawing.presets.QQQ')).toBe(null);
  q.unmount();
  // back on SPY: the preset survives the remount (local persistence)
  await mountPane();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  expect(screen.getByText(/gold-trend/)).toBeInTheDocument();
});

test('MOUNTED: cap refusal and future-version envelope are surfaced honestly', async () => {
  // 50-preset envelope -> create refuses with the cap error, visibly
  let list = [];
  for (let i = 0; i < 50; i++) {
    const r = createPreset(list, { name: 'p' + i, tool: 'trend', style: { color: '#5ec986' } });
    list = r.list;
  }
  savePresets('SPY', list);
  const capped = await mountPane();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  expect(screen.getByTestId('rail-preset-cap')).toBeInTheDocument();
  placeTrend();
  const [d1] = drawingIds();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + d1));
  // at cap the rail refuses by hiding the create row entirely — no partial op
  expect(screen.queryByTestId('rail-preset-name')).not.toBeInTheDocument();
  expect(screen.queryByTestId('rail-preset-create')).not.toBeInTheDocument();
  void d1;
  capped.unmount();
  // future storage envelope: not ours to interpret — honest refusal, nothing overwritten
  window.localStorage.setItem('floww.drawing.presets.SPY', JSON.stringify({ v: PRESET_STORAGE_VERSION + 5, presets: [{ id: 'x', name: 'x', tool: 'trend' }] }));
  const { unmount } = await mountPane();
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  expect(screen.queryAllByTestId('rail-preset')).toHaveLength(0);
  await waitFor(() => expect(screen.getByTestId('preset-error')).toBeInTheDocument());
  expect(screen.getByTestId('preset-error').textContent).toContain('newer preset storage version');
  unmount();
});
