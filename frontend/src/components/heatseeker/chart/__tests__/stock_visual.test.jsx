// Visual-reset-20261025 — the Stock contextual right workspace composition:
// a short visible Indicators/Data/Review row (no Tools→Studies→disclosure dead
// end), one docked workspace with stable tabs/close/reopen, and Add Volume
// visibly driving the REAL measured-volume pane (never a no-op saved row).
import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const FRAMES = [
  { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 10, nodes: [] },
  { time: '2026-10-06T14:30:00Z', open: 101, high: 104, low: 100, close: 103, volume: 20, nodes: [] },
  { time: '2026-10-06T15:00:00Z', open: 103, high: 105, low: 101, close: 104, volume: 30, nodes: [] },
  { time: '2026-10-06T15:30:00Z', open: 104, high: 106, low: 102, close: 105, volume: 40, nodes: [] },
  { time: '2026-10-06T16:00:00Z', open: 105, high: 107, low: 103, close: 106, volume: 50, nodes: [] },
];
beforeEach(() => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: FRAMES, candles_with_recorded_nodes: 5, scopes: [] } }));
  window.localStorage.clear();
});
const mountPane = async (props = {}) => {
  const r = render(<PriceNodeHistory ticker="SPY" open {...props} />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '5'));
  return r;
};

test('the dock renders open with all three tabs; studies reachable without any Tools disclosure', async () => {
  await mountPane();
  const dock = screen.getByTestId('stock-inspector');
  expect(dock).toHaveAttribute('data-open', 'true');
  expect(dock).toHaveAttribute('data-active-tab', 'indicators');
  // the catalog paints IN the Indicators tab — no nested summary, no Tools disclosure
  expect(screen.queryByTestId('studies-panel-summary')).not.toBeInTheDocument();
  expect(screen.getByTestId('indicators-search')).toBeInTheDocument();
  expect(screen.queryAllByTestId(/^catalog-add-/).length + document.querySelectorAll('[data-testid^="catalog-add-"]').length).toBeGreaterThan(0);
  expect(document.querySelector('[data-testid="indicators-panel"]').closest('details')).toBeNull();
  // the three dock buttons are visible in the chart row
  expect(screen.getByTestId('stock-dock-open-indicators')).toBeInTheDocument();
  expect(screen.getByTestId('stock-dock-open-data')).toBeInTheDocument();
  expect(screen.getByTestId('stock-dock-open-review')).toBeInTheDocument();
});

test('tabs switch with real content; close and reopen are stable', async () => {
  await mountPane();
  fireEvent.click(screen.getByTestId('stock-inspector-tab-data'));
  await waitFor(() => expect(screen.getByTestId('stock-inspector')).toHaveAttribute('data-active-tab', 'data'));
  // the Data tab carries the pane data actions (reload lives here now)
  expect(screen.getByRole('button', { name: /reload history/i })).toBeInTheDocument();
  fireEvent.click(screen.getByTestId('stock-inspector-tab-review'));
  await waitFor(() => expect(screen.getByTestId('stock-inspector')).toHaveAttribute('data-active-tab', 'review'));
  // the review tab names the eight analytics families honestly
  expect(screen.getByTestId('stock-review-families')).toHaveTextContent(/levels, patterns, income, history, moves, structure, exposure, briefing/);
  // close -> closed state; reopen from the chart row
  fireEvent.click(screen.getByTestId('stock-inspector-close'));
  await waitFor(() => expect(screen.getByTestId('stock-inspector')).toHaveAttribute('data-open', 'false'));
  fireEvent.click(screen.getByTestId('stock-dock-open-indicators'));
  await waitFor(() => expect(screen.getByTestId('stock-inspector')).toHaveAttribute('data-open', 'true'));
  // reopening the Indicators tab re-exposes the catalog directly — no summary
  expect(screen.getByTestId('indicators-search')).toBeInTheDocument();
  expect(screen.getByTestId('indicators-panel').closest('details')).toBeNull();
});

test('the Volume pane row drives the REAL measured-volume bars pane — both ways', async () => {
  await mountPane();
  // default: the measured volume bars pane renders (real rects under the candles)
  const bars = () => document.querySelectorAll('[data-testid="volume-bar"]').length;
  expect(bars()).toBeGreaterThan(0);
  // the pane row turns the REAL bars pane OFF — not the profile, not a saved row
  fireEvent.click(screen.getByTestId('pane-toggle-volume-pane'));
  await waitFor(() => expect(bars()).toBe(0));
  expect(screen.getByLabelText('Toggle volume pane')).not.toBeChecked();
  // the panel row's pressed state mirrors the REAL pane state (adversarial)
  expect(screen.getByTestId('pane-toggle-volume-pane')).toHaveAttribute('aria-pressed', 'false');
  // and back ON
  fireEvent.click(screen.getByTestId('pane-toggle-volume-pane'));
  await waitFor(() => expect(bars()).toBeGreaterThan(0));
  expect(screen.getByLabelText('Toggle volume pane')).toBeChecked();
  // the chart's own checkbox drives the SAME shared state
  fireEvent.click(screen.getByLabelText('Toggle volume pane'));
  await waitFor(() => expect(bars()).toBe(0));
});

test('the review tab shows the real current selection and families context', async () => {
  await mountPane();
  fireEvent.click(screen.getByTestId('stock-inspector-tab-review'));
  // no drawing selected -> the honest empty teaching state
  expect(screen.getByTestId('stock-review-context')).toHaveTextContent(/no drawing selected/i);
  expect(screen.getByTestId('stock-review-study')).toHaveTextContent(/no active studies/i);
  // the families note names all eight honestly and points to the workflow band
  expect(screen.getByTestId('stock-review-families')).toHaveTextContent(/levels, patterns, income, history, moves, structure, exposure, briefing/);
  // a placed drawing reflects in the Review tab (real selected-object context)
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-tool-trend'));
  const layer = screen.getByTestId('drawing-layer');
  const event = new window.MouseEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 150, clientY: 100 });
  event.pointerType = 'mouse'; act(() => { layer.dispatchEvent(event); });
  const event2 = new window.MouseEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 450, clientY: 240 });
  event2.pointerType = 'mouse'; act(() => { layer.dispatchEvent(event2); });
  const id = [...document.querySelectorAll('[data-testid^="rail-select-"]')].map(b => b.getAttribute('data-testid').slice('rail-select-'.length))[0];
  fireEvent.click(screen.getByTestId('stock-dock-open-drawings'));
  fireEvent.click(screen.getByTestId('rail-select-' + id));
  fireEvent.click(screen.getByTestId('stock-inspector-tab-review'));
  await waitFor(() => expect(screen.getByTestId('stock-review-selection')).toHaveTextContent(/trend drawing/));
  expect(screen.getByTestId('stock-review-selection')).toHaveTextContent(/built-in|unlinked/);
});
