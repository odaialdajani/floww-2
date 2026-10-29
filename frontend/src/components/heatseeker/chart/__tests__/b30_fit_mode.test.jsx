/** @jest-environment jsdom */
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import RecordedPriceChart from '../../RecordedPriceChart';
import PriceNodeHistory from '../../PriceNodeHistory';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const armPayload = (frames) => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames, candles_with_recorded_nodes: 0, scopes: [] } }));
};

// UI-05: fit-all must drive the REAL renderer's price scale — the chart's
// data-price-low/high must span the full loaded history, not just the
// visible window. fit-visible keeps the visible-window scale.
const FRAMES = [
  { time: '2026-09-10T14:00:00+00:00', open: 100, high: 101, low: 99, close: 100, nodes: [] },
  { time: '2026-09-10T14:01:00+00:00', open: 100, high: 102, low: 99, close: 101, nodes: [] },
  { time: '2026-09-10T14:02:00+00:00', open: 101, high: 200, low: 50, close: 150, nodes: [] },
];

test('fit-all spans the full loaded history on the real price scale', () => {
  const visibleOnly = render(<RecordedPriceChart ticker="SPY" frames={FRAMES.slice(0, 2)} />);
  const vChart = screen.getByTestId('recorded-price-chart');
  const vLow = Number(vChart.getAttribute('data-price-low'));
  const vHigh = Number(vChart.getAttribute('data-price-high'));
  visibleOnly.unmount();

  render(<RecordedPriceChart ticker="SPY" frames={FRAMES.slice(0, 2)} fitAllFrames={FRAMES} />);
  const chart = screen.getByTestId('recorded-price-chart');
  const low = Number(chart.getAttribute('data-price-low'));
  const high = Number(chart.getAttribute('data-price-high'));
  // fit-all: the far bar (50..200) is in the scale even though only two
  // bars are loaded into the visible data
  expect(low).toBeLessThan(51);
  expect(high).toBeGreaterThan(199);
  // and it is strictly wider than the visible-only scale
  expect(low).toBeLessThan(vLow);
  expect(high).toBeGreaterThan(vHigh);
});

test('the pane passes its full history through when fitMode is fit-all', async () => {
  armPayload(FRAMES);
  const reports = [];
  render(<PriceNodeHistory ticker="SPY" open fitMode="fit-all" onReplayState={r => reports.push(r)} />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  await act(async () => { await new Promise(r => setTimeout(r, 150)); });
  const chart = screen.getByTestId('recorded-price-chart');
  expect(Number(chart.getAttribute('data-candles'))).toBe(3);
  // all three frames are loaded (position at head): fit-all equals the
  // visible set here — the proof of span comes from the scrub below.
  const slider = screen.getByLabelText('Replay position');
  await act(async () => { fireEvent.change(slider, { target: { value: '0' } }); });
  await act(async () => { await new Promise(r => setTimeout(r, 150)); });
  const after = screen.getByTestId('recorded-price-chart');
  // scrubbed to the first bar: the visible data is 1 candle, but fit-all
  // keeps the WHOLE history's scale (high ~200), not the one-bar window
  expect(Number(after.getAttribute('data-candles'))).toBe(1);
  expect(Number(after.getAttribute('data-price-high'))).toBeGreaterThan(199);
});
