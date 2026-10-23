import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

// S2: the five link dimensions (interval, crosshair, time, price, session)
// must reach ACTUAL CHART EVENTS in the mounted workspace — a user change on
// one pane propagates to the other panes' real requests and real renderer
// state (price never crosses unlike symbols), not just reducer helpers.
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));

// 120 synthetic frames: more than the 80-candle default window so a real
// time zoom is observable in data-visible-candles.
const FRAMES = Array.from({ length: 120 }, (_, i) => ({
  time: new Date(Date.parse('2026-10-06T14:00:00Z') + i * 1800000).toISOString(),
  open: 100 + (i % 7), high: 102 + (i % 5), low: 98 + (i % 3), close: 101 + (i % 4), nodes: [],
}));

const arm = () => {
  const axios = require('axios');
  axios.get.mockReset();
  axios.get.mockImplementation(async url => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] ?? 'SPY';
    return { data: { ticker, query_key: '', frames: FRAMES, candles_with_recorded_nodes: 120, node_status: 'available' } };
  });
};

// every test starts from a clean durable store — a previous test's saved
// composition must never leak into the next mount as a fake "restored" state
beforeEach(() => {
  require('../persistence/layoutStore')._clear();
});

const mountSplit = async (ticker = 'SPY') => {
  const W = require('../ChartWorkspace').default;
  const view = render(<W ticker={ticker} open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart').length).toBeGreaterThan(0));
  await act(async () => { screen.getByTestId('layout-split').click(); });
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(2));
  await act(async () => { await new Promise(r => setTimeout(r, 150)); });
  return view;
};

test('S2 MOUNTED: an interval change on one pane reaches the other pane\'s real request', async () => {
  arm();
  await mountSplit();
  const axios = require('axios');
  const before = axios.get.mock.calls.filter(c => c[1]?.params?.interval_minutes === 5).length;
  // user changes the FIRST pane's candle interval to 5 minutes
  const select = screen.getAllByLabelText('Candle interval')[0];
  await act(async () => { fireEvent.change(select, { target: { value: '5' } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 400)); });
  // BOTH panes now request 5-minute candles (the origin refetches and the
  // other pane adopts the synced interval)
  const after = axios.get.mock.calls.filter(c => c[1]?.params?.interval_minutes === 5).length;
  expect(after).toBeGreaterThanOrEqual(before + 2);
});

test('S2 MOUNTED: a session change on one pane reaches the other pane\'s real request', async () => {
  arm();
  await mountSplit();
  const axios = require('axios');
  const before = axios.get.mock.calls.filter(c => c[1]?.params?.sessions === 'all').length;
  const select = screen.getAllByLabelText('Session coverage')[0];
  await act(async () => { fireEvent.change(select, { target: { value: 'all' } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 400)); });
  const after = axios.get.mock.calls.filter(c => c[1]?.params?.sessions === 'all').length;
  expect(after).toBeGreaterThanOrEqual(before + 2);
});

test('S2 MOUNTED: a price zoom on one pane reaches the other pane\'s real price scale', async () => {
  arm();
  await mountSplit();
  const charts = screen.getAllByTestId('recorded-price-chart');
  const aBefore = charts[0].getAttribute('data-price-low');
  const bBefore = charts[1].getAttribute('data-price-low');
  // user price-zooms the FIRST pane's chart (shift+wheel on its surface).
  // jsdom reports zero-sized rects, which would turn the wheel's coordinate
  // math into NaN — a real browser delivers real geometry, so the test
  // stubs the surface rect and sends real client coordinates.
  const surface = document.querySelectorAll('.recorded-chart-surface')[0];
  surface.getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 480 });
  await act(async () => { fireEvent.wheel(surface, { shiftKey: true, deltaY: -120, clientX: 400, clientY: 240 }); });
  await act(async () => { await new Promise(r => setTimeout(r, 250)); });
  const aAfter = charts[0].getAttribute('data-price-low');
  const bAfter = charts[1].getAttribute('data-price-low');
  expect(aAfter).not.toBe(aBefore);       // the zoom really changed pane A
  expect(bAfter).toBe(aAfter);           // pane B adopted the SAME zoomed scale
  expect(bAfter).not.toBe(bBefore);
});

test('S2 MOUNTED: a time zoom on one pane reaches the other pane\'s real window', async () => {
  arm();
  await mountSplit();
  const charts = screen.getAllByTestId('recorded-price-chart');
  const aBefore = charts[0].getAttribute('data-visible-candles');
  const bBefore = charts[1].getAttribute('data-visible-candles');
  expect(bBefore).toBe(aBefore);         // both panes start at the same window
  // user time-zooms the FIRST pane's chart in
  const zoomIn = screen.getAllByRole('button', { name: 'Zoom in time' })[0];
  await act(async () => { zoomIn.click(); });
  await act(async () => { await new Promise(r => setTimeout(r, 250)); });
  const aAfter = Number(charts[0].getAttribute('data-visible-candles'));
  const bAfter = Number(charts[1].getAttribute('data-visible-candles'));
  expect(aAfter).toBeLessThan(Number(aBefore));  // pane A really zoomed
  expect(bAfter).toBe(aAfter);                    // pane B adopted the same window
});

test('S2 MOUNTED: price never syncs across unlike symbols', async () => {
  arm();
  // seed a persisted split composition SPY + QQQ (B12 durable store)
  const { saveLocal, _clear } = require('../persistence/layoutStore');
  const { createLayout } = require('../persistence/layoutSchema');
  _clear();
  saveLocal('workspace-current', createLayout({ layoutId: 'split', symbols: ['SPY', 'QQQ'], focusedIndex: 0, fitMode: 'fit-visible' }));
  const view = await mountSplit('SPY');
  await act(async () => { await new Promise(r => setTimeout(r, 400)); });
  const bBefore = screen.getAllByTestId('recorded-price-chart')[1].getAttribute('data-price-low');
  // price-zoom the SPY pane (pane 0, the focused one)
  const surface = document.querySelectorAll('.recorded-chart-surface')[0];
  surface.getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 480 });
  await act(async () => { fireEvent.wheel(surface, { shiftKey: true, deltaY: -120, clientX: 400, clientY: 240 }); });
  await act(async () => { await new Promise(r => setTimeout(r, 250)); });
  const charts2 = screen.getAllByTestId('recorded-price-chart');
  const aAfter = charts2[0].getAttribute('data-price-low');
  const bAfter = charts2[1].getAttribute('data-price-low');
  expect(aAfter).not.toBe(bAfter);       // the QQQ pane did NOT adopt SPY's zoom
  expect(bAfter).toBe(bBefore);
  view.unmount();
});

// S2 persistence: per-pane interval/session/view state survives a reload —
// the durable store carries each pane's own state and the restored panes
// adopt it at mount (their first REAL request already uses it).
test('S2 MOUNTED: per-pane state survives a reload through the durable store', async () => {
  arm();
  const { _clear } = require('../persistence/layoutStore');
  _clear();
  const view1 = await mountSplit();
  const select = screen.getAllByLabelText('Candle interval')[0];
  await act(async () => { fireEvent.change(select, { target: { value: '5' } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 600)); }); // let the autosave fire
  const axios = require('axios');
  const fiveBefore = axios.get.mock.calls.filter(c => c[1]?.params?.interval_minutes === 5).length;
  expect(fiveBefore).toBeGreaterThanOrEqual(2);
  // full unmount + fresh mount = a reload
  view1.unmount();
  axios.get.mockClear();
  const W = require('../ChartWorkspace').default;
  render(<W ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart').length).toBeGreaterThan(0));
  await act(async () => { await new Promise(r => setTimeout(r, 600)); });
  // the restored composition is still the split, and the panes' persisted
  // 5-minute interval drives their first REAL request
  expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(2);
  const fiveAfter = axios.get.mock.calls.filter(c => c[1]?.params?.interval_minutes === 5).length;
  expect(fiveAfter).toBeGreaterThanOrEqual(2);
  const selects = screen.getAllByLabelText('Candle interval');
  expect(selects.every(s => s.value === '5')).toBe(true);
});
