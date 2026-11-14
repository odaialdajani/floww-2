import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import PriceNodeHistory from './PriceNodeHistory';
import { openStockPanel } from '../../testUtils/openStockPanel';

jest.mock('axios', () => ({ get: jest.fn() }));
const frames = Array.from({ length: 125 }, (_, i) => ({
  time: new Date(Date.UTC(2026, 9, 19, 13, 30) + i * 1800000).toISOString(),
  open: 100 + i, high: 102 + i, low: 99 + i, close: 101 + i, nodes: [],
}));
const history = (count = 120, query_key = 'saved-scope', ticker = 'SPY') => ({
  data: { ticker, frames: frames.slice(0, count), query_key, candles_with_recorded_nodes: 0 },
});
const chart = () => screen.getByTestId('recorded-price-chart');
const view = () => Object.fromEntries(['window-start', 'visible-candles', 'price-low', 'price-high']
  .map(key => [key, chart().getAttribute('data-' + key)]));
const holdZoomedView = () => {
  fireEvent.click(screen.getByRole('button', { name: 'Zoom in time' }));
  fireEvent.click(screen.getByRole('button', { name: 'Auto scale' }));
};
const earlier = () => {
  fireEvent.click(screen.getByRole('button', { name: 'Chart tools' }));
  fireEvent.click(screen.getByRole('button', { name: 'Earlier candles' }));
};
const reload = () => {
  openStockPanel('data');
  fireEvent.click(screen.getByRole('button', { name: 'Reload history' }));
};
beforeEach(() => {
  jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 480, width: 800, height: 480,
    toJSON: () => ({}),
  });
});
afterEach(() => { axios.get.mockReset(); jest.restoreAllMocks(); });

test('same-scope reload retains a panned zoom and held price scale through empty loading', async () => {
  let finish;
  axios.get.mockResolvedValueOnce(history()).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '120'));
  holdZoomedView(); earlier();
  const before = view();
  reload();
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '0'));
  expect(screen.getByRole('button', { name: 'Auto scale' })).toHaveAttribute('aria-pressed', 'false');
  await act(async () => finish(history(125)));
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '125'));
  expect(view()).toEqual(before);
  expect(screen.getByRole('button', { name: 'Auto scale' })).toHaveAttribute('aria-pressed', 'false');
});

test('same-scope reload follows appended bars only from the right edge, retaining zoom and price lock', async () => {
  axios.get.mockResolvedValueOnce(history()).mockResolvedValueOnce(history(125));
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '120'));
  holdZoomedView();
  fireEvent.keyDown(screen.getByRole('region', { name: 'SPY candle chart' }), { key: 'End' });
  const before = view();
  expect(before['window-start']).toBe('60');
  reload();
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '125'));
  await waitFor(() => expect(view()).toEqual({ ...before, 'window-start': '65' }));
});

test.each([
  ['interval', 'Candle interval', '15'],
  ['session', 'Session coverage', 'all'],
  ['period', 'History sessions', '20'],
])('changing the %s resets a held range even when the response scope is identical', async (_, label, value) => {
  axios.get.mockResolvedValue(history());
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '120'));
  holdZoomedView(); earlier();
  fireEvent.change(screen.getByRole('combobox', { name: label }), { target: { value } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Auto scale' })).toHaveAttribute('aria-pressed', 'true'));
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '120'));
  expect(chart()).toHaveAttribute('data-visible-candles', '80');
});

test('a different resolved recorded scope on reload resets the held range', async () => {
  axios.get.mockResolvedValueOnce(history()).mockResolvedValueOnce(history(120, 'different-scope'));
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '120'));
  holdZoomedView(); earlier(); reload();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Auto scale' })).toHaveAttribute('aria-pressed', 'true'));
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '120'));
  expect(chart()).toHaveAttribute('data-visible-candles', '80');
});


test.each(['ticker', 'requested scope'])('changing the %s resets the range', async dimension => {
  axios.get.mockImplementation(url => Promise.resolve(history(120, 'saved-scope', url.endsWith('/QQQ') ? 'QQQ' : 'SPY')));
  const { rerender } = render(<PriceNodeHistory ticker="SPY" forcedScope="map-a" primary />);
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '120'));
  holdZoomedView(); earlier();
  rerender(<PriceNodeHistory ticker={dimension === 'ticker' ? 'QQQ' : 'SPY'} forcedScope={dimension === 'requested scope' ? 'map-b' : 'map-a'} primary />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Auto scale' })).toHaveAttribute('aria-pressed', 'true'));
  await waitFor(() => expect(chart()).toHaveAttribute('data-candles', '120'));
  expect(chart()).toHaveAttribute('data-visible-candles', '80');
});
