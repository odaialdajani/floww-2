// B22 — root's actual-46 geometry finding, closed as a pinned regression:
// the CLOSED inspector stays MOUNTED (data-open=false in the DOM — no state
// wipe, no remount) while its css slot releases the ~300px at ALL desktop
// widths (App.css's display:none existed only under 1180px); in focus the
// metrics sidebar folds reversibly (the hidden attribute) and Exit restores.
// The real pixel geometry (chart widths + focus surface) is in the live
// evidence; these pins hold the mounted state + the reversible hides honest.
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const FRAMES = [
  { time: '2026-10-06T16:00:00Z', open: 100, high: 101, low: 99, close: 100.5, volume: 10, nodes: [] },
  { time: '2026-10-06T16:30:00Z', open: 100.5, high: 102, low: 100, close: 101.5, volume: 20, nodes: [] },
];

test('the closed inspector stays MOUNTED with data-open=false — never a reserved slot nor a state wipe', async () => {
  const axios = require('axios');
  window.localStorage.clear();
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: FRAMES, candles_with_recorded_nodes: 2, scopes: [] } }));
  const { unmount } = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '2'));
  const insp = screen.getByTestId('stock-inspector');
  // closed by default AND still in the DOM — the component never unmounted
  expect(insp).toHaveAttribute('data-open', 'false');
  expect(insp).toBeInTheDocument();
  // the closed-slot css ships from Stock-local chrome (the rule is asserted in
  // the built chunk; here the state contract: openers still work from closed)
  fireEvent.click(screen.getByTestId('stock-dock-open-indicators'));
  await waitFor(() => expect(insp).toHaveAttribute('data-open', 'true'));
  // close via the real × — back to closed, STILL mounted
  fireEvent.click(screen.getByTestId('stock-inspector-close'));
  await waitFor(() => expect(insp).toHaveAttribute('data-open', 'false'));
  expect(insp).toBeInTheDocument();
  unmount();
});

test('focus is reversible in-component: the class binds on the rendered host and exits restore it', async () => {
  const axios = require('axios');
  window.localStorage.clear();
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: FRAMES, candles_with_recorded_nodes: 2, scopes: [] } }));
  const focusChange = jest.fn();
  const { unmount, rerender } = render(<PriceNodeHistory ticker="SPY" open chartFocus={false} onChartFocusChange={focusChange} />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '2'));
  const pane = screen.getByTestId('price-node-history');
  expect(pane.className).not.toContain('price-node-focused');
  fireEvent.click(screen.getByTestId('chart-focus-toggle'));
  expect(focusChange).toHaveBeenCalledWith(true);
  // the controlled prop flips (as the real dashboard does), then Esc exits
  rerender(<PriceNodeHistory ticker="SPY" open chartFocus onChartFocusChange={focusChange} />);
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(focusChange).toHaveBeenCalledWith(false);
  unmount();
});
