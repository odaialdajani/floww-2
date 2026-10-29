import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import ChartWorkspace from '../ChartWorkspace';
import { createReplayState, reduceCaches, routeEvent, sweepExtrema, barAt, visibleSnapshot } from '../replay/replayReducer';

// Bare factory + per-test re-arm (durable pattern for this CRA setup).
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const armPayload = (frames) => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames, candles_with_recorded_nodes: 0, scopes: [] } }));
};

// Real-shaped frames with distinct extrema so future-data exclusion is
// provable: f2.high=103 must never appear in extrema swept at cursor=f1.
const FRAMES = [
  { time: '2026-09-10T14:00:00+00:00', open: 100, high: 102, low: 99, close: 101, nodes: [] },
  { time: '2026-09-10T14:01:00+00:00', open: 101, high: 103, low: 100, close: 102, nodes: [] },
];

test('B15 mounted pane reports replay algebra: cursor, bar, extrema, provenance', async () => {
  armPayload(FRAMES);
  const reports = [];
  render(<PriceNodeHistory ticker="SPY" open onReplayState={r => reports.push(r)} />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  await act(async () => { await new Promise(r => setTimeout(r, 120)); });
  expect(reports.length).toBeGreaterThanOrEqual(1);
  const head = reports[reports.length - 1];
  // Head position: cursor at the newest frame, head bar is forming (partial),
  // extrema sweep covers every visible bar.
  expect(head.cursor).toBe(Date.parse('2026-09-10T14:01:00+00:00'));
  expect(head.visibleBars).toBe(2);
  expect(head.bar.complete).toBe(false); // forming head bar stays partial
  expect(head.extrema.status).toBe('ok');
  expect(head.extrema.high).toBe(103);
  // Scrub back to the first candle: replay-derived delta, and the swept
  // extrema can NEVER include the future bar's high.
  const slider = screen.getByLabelText('Replay position');
  await act(async () => { fireEvent.change(slider, { target: { value: '0' } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 120)); });
  const back = reports[reports.length - 1];
  expect(back.cursor).toBe(Date.parse('2026-09-10T14:00:00+00:00'));
  expect(back.visibleBars).toBe(1);
  expect(back.extrema.high).toBe(102); // 103 is future data — excluded
  expect(back.delta.every(e => e.origin === 'replay')).toBe(true); // provenance
  // Return to the head: the head frame is a live observation.
  await act(async () => { fireEvent.change(slider, { target: { value: '1' } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 120)); });
  const fwd = reports[reports.length - 1];
  expect(fwd.cursor).toBe(Date.parse('2026-09-10T14:01:00+00:00'));
});

// R21-02: origin is live ONLY at the advancing head — a paused cursor moved
// forward anywhere behind the newest frame is replay, whichever way it moved.
// The old rule labeled a paused forward scrub "live" because it keyed on the
// playing flag and the move direction instead of the cursor's true position.
test('B15 paused forward scrub behind the head reports replay provenance', async () => {
  const THREE = [
    { time: '2026-09-10T14:00:00+00:00', open: 100, high: 101, low: 99, close: 100, nodes: [] },
    { time: '2026-09-10T14:01:00+00:00', open: 100, high: 102, low: 99, close: 101, nodes: [] },
    { time: '2026-09-10T14:02:00+00:00', open: 101, high: 103, low: 100, close: 102, nodes: [] },
  ];
  armPayload(THREE);
  const reports = [];
  render(<PriceNodeHistory ticker="SPY" open onReplayState={r => reports.push(r)} />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  await act(async () => { await new Promise(r => setTimeout(r, 120)); });
  const slider = screen.getByLabelText('Replay position');
  let last = reports[reports.length - 1];
  expect(last.delta.every(e => e.origin === 'live')).toBe(true); // head is live
  // scrub back to the first frame, then FORWARD to the middle frame:
  // paused, moved forward, still behind the head — replay, not live.
  await act(async () => { fireEvent.change(slider, { target: { value: '0' } }); });
  await act(async () => { fireEvent.change(slider, { target: { value: '1' } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 120)); });
  last = reports[reports.length - 1];
  expect(last.cursor).toBe(Date.parse('2026-09-10T14:01:00+00:00'));
  expect(last.delta.length).toBeGreaterThan(0);
  expect(last.delta.every(e => e.origin === 'replay')).toBe(true);
});

test('B15 mounted workspace: the focused pane drives a real replay readout', async () => {
  armPayload(FRAMES);
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    render(<ChartWorkspace ticker="SPY" open useNew />);
    await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
    await act(async () => { await new Promise(r => setTimeout(r, 150)); });
    const readout = screen.getByTestId('replay-readout');
    expect(readout).toHaveAttribute('data-bar-state', 'partial'); // forming head
    expect(readout.getAttribute('data-cursor')).toBe(String(Date.parse('2026-09-10T14:01:00+00:00')));
    // Live head observation landed in the live cache; the replay cache is empty.
    expect(readout.getAttribute('data-live-count')).toBe('1');
    expect(readout.getAttribute('data-replay-count')).toBe('0');
    // Scrub the focused pane back: a replay-derived event is admitted to the
    // REPLAY cache only — the live cache never receives replay data.
    const slider = screen.getByLabelText('Replay position');
    await act(async () => { fireEvent.change(slider, { target: { value: '0' } }); });
    await act(async () => { await new Promise(r => setTimeout(r, 150)); });
    expect(screen.getByTestId('replay-readout').getAttribute('data-replay-count')).toBe('1');
    expect(screen.getByTestId('replay-readout').getAttribute('data-live-count')).toBe('1'); // untouched
    // At cursor 14:00 the 14:00 bar is still forming — its window closes at
    // 14:01, AFTER the cursor — so the honest algebra reports partial.
    // (Completion at cursor >= window end is pinned in the unit test above.)
    expect(screen.getByTestId('replay-readout').getAttribute('data-bar-state')).toBe('partial');
    expect(screen.getByTestId('replay-readout').textContent).toContain('replay events never enter live caches');
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});

test('B15 algebra pinned: no future data to extrema; unknown origin dropped', () => {
  const bars = [
    { time: 100, high: 102, low: 99 },
    { time: 200, high: 105, low: 98 },
  ];
  expect(sweepExtrema(bars, 150).high).toBe(102); // 105 is future
  expect(sweepExtrema(bars, 150).count).toBe(1);
  const caches = reduceCaches(createReplayState().caches, [
    { id: 'a', symbol: 'SPY', value: 1, time: 1, origin: 'live' },
    { id: 'b', symbol: 'SPY', value: 2, time: 2, origin: 'replay' },
    { id: 'c', symbol: 'SPY', value: 3, time: 3, origin: 'mystery' },
  ]);
  expect(Object.keys(caches.live.SPY)).toEqual(['a']);
  expect(Object.keys(caches.replay.SPY)).toEqual(['b']);
  const routed = routeEvent(caches, { id: 'x', symbol: 'SPY' });
  expect(routed.dropped).toEqual(['x']);
  expect(visibleSnapshot([{ id: 's1', known_at: 5 }, { id: 's2', known_at: 3 }], 4).id).toBe('s2');
  // R21-02: the [1,2) bar is FORMING at cursor 1 — its window has not
  // closed. The old pin claimed completion from a caller-invented windowEnd
  // equal to the cursor itself; the owning-bucket algebra refuses that.
  expect(barAt([{ event_time: 1, available_at: 1, open: 10, close: 11 }], 1, 1).complete).toBe(false);
});
