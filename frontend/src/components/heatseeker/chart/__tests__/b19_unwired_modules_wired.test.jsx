// B19 — the previously-unwired frozen modules, wired in production (H3's
// queue-inspection exact misses):
//   B07 exposureSettings — the exposure settings surface with the honest
//     mismatch disclosure, persisted per ticker;
//   B29 workspaceFlags — the discoverable controlled entry (Data-tab toggle +
//     chart-row re-entry) and the reversible kill switch (no data loss).
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const FRAMES = [
  { time: '2026-10-22T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 10, nodes: [] },
  { time: '2026-10-22T14:30:00Z', open: 101, high: 104, low: 100, close: 103, volume: 20, nodes: [] },
  { time: '2026-10-23T14:00:00Z', open: 103, high: 105, low: 101, close: 104, volume: 40, nodes: [] },
];
beforeEach(() => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: FRAMES, candles_with_recorded_nodes: 3, scopes: [] } }));
  window.localStorage.clear();
});
const setSelect = (tid, val) => {
  const s = screen.getByTestId(tid);
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
  act(() => { setter.call(s, val); s.dispatchEvent(new Event('change', { bubbles: true })); });
};

test('B07 wired: the exposure settings surface renders with the honest mismatch disclosure', async () => {
  const { unmount } = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '3'));
  fireEvent.click(screen.getByTestId('stock-dock-open-data'));
  // the surface is in the Data tab with all four frozen-module inputs
  expect(screen.getByTestId('exposure-settings')).toBeInTheDocument();
  expect(screen.getByLabelText('ORB exposure scope')).toBeInTheDocument();
  expect(screen.getByLabelText('ORB exposure nodes')).toBeInTheDocument();
  expect(screen.getByLabelText('Exposure VWAP scope')).toBeInTheDocument();
  expect(screen.getByLabelText('Exposure VWAP nodes')).toBeInTheDocument();
  // same scope/nodes -> the match note; the frozen module says no mismatch
  expect(screen.getByTestId('exposure-match-note')).toBeInTheDocument();
  // diverge the VWAP scope -> the module's mismatch disclosure appears
  setSelect('exposure-vwap-scope', 'top-nodes');
  expect(screen.getByTestId('exposure-mismatch-note')).toHaveTextContent(/different node universes/i);
  // the selection persists per ticker
  const persisted = JSON.parse(window.localStorage.getItem('floww.pane.config.SPY'));
  expect(persisted.exposure).toMatchObject({ orbScope: 'all', vwapScope: 'top-nodes' });
  // restore -> the match note returns
  setSelect('exposure-vwap-scope', 'all');
  expect(screen.getByTestId('exposure-match-note')).toBeInTheDocument();
  unmount();
});

test('B29 wired: the workspace toggle is the controlled entry; the kill switch reverts with no data loss', async () => {
  const { unmount } = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '3'));
  // the gate ships ON: the docked workspace is the accepted default
  expect(screen.getByTestId('workspace-v1-toggle')).toBeChecked();
  expect(screen.getByTestId('stock-inspector')).toHaveAttribute('data-open', 'true');
  // the kill switch: chart-only, the openers hide, the re-entry shows, honest note
  fireEvent.click(screen.getByTestId('stock-dock-open-data'));
  fireEvent.click(screen.getByTestId('workspace-kill-switch'));
  await waitFor(() => expect(screen.queryByTestId('stock-inspector')).toBeNull());
  expect(screen.queryByTestId('stock-dock-open-indicators')).toBeNull();
  expect(screen.queryByTestId('stock-dock-open-drawings')).toBeNull();
  expect(screen.getByTestId('workspace-reentry')).toBeInTheDocument();
  expect(screen.getByTestId('workspace-fallback-note')).toHaveTextContent(/no data lost/i);
  // re-entry is the discoverable controlled way back
  fireEvent.click(screen.getByTestId('workspace-reentry'));
  await waitFor(() => expect(screen.getByTestId('stock-inspector')).toHaveAttribute('data-open', 'true'));
  expect(screen.getByTestId('stock-dock-open-indicators')).toBeInTheDocument();
  // nothing the user saved was touched by the round trip
  expect(JSON.parse(window.localStorage.getItem('floww.drawing.presets.SPY') || 'null')).toBeNull();
  unmount();
});
