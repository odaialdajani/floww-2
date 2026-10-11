import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import RecordedPriceChart from '../../RecordedPriceChart';
import PriceNodeHistory from '../../PriceNodeHistory';

jest.mock('axios', () => ({ get: jest.fn() }));

const frames = [
  { time: '2026-10-06T13:30:00+00:00', open: 100, high: 102, low: 99, close: 101, volume: 12000, duration_seconds: 60, nodes: [] },
  { time: '2026-10-06T13:31:00+00:00', open: 101, high: 103, low: 100, close: 102, volume: 34000, duration_seconds: 60, nodes: [] },
];
const contractBars = [
  { t: '2026-10-06T13:30:00Z', o: 5.0, h: 5.4, l: 4.8, c: 5.2, v: 120 },
  { t: '2026-10-06T13:31:00Z', o: 5.2, h: 5.6, l: 5.0, c: 5.5, v: 90 },
];

beforeEach(() => {
  jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 480, width: 800, height: 480, toJSON: () => ({}) });
  window.localStorage.clear();
});
afterEach(() => jest.restoreAllMocks());

test('selected contract renders its own premium path with honest axis separation', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames}
    contractBars={contractBars} contractSymbol="SPY261017C00650000" contractStatus="available" />);
  const pane = screen.getByTestId('contract-premium-pane');
  expect(pane).toBeInTheDocument();
  expect(pane.querySelector('[data-testid="contract-premium"]')).toBeInTheDocument();
  // Own dollars, not underlying dollars — the axis honesty is explicit.
  expect(pane.textContent).toMatch(/premium/i);
  expect(pane.textContent).toMatch(/not.*underlying|own.*scale/i);
  // Underlying candles keep their own scale — no premium mixing.
  expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '2');
});

test('missing contract premium renders explicit unavailable — never a flat line', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames}
    contractSymbol="SPY261017C00650000" contractStatus="unavailable" contractBars={[]} />);
  expect(screen.queryByTestId('contract-premium')).not.toBeInTheDocument();
  expect(screen.getByTestId('contract-premium-unavailable')).toBeInTheDocument();
});

test('no contract selected renders no premium pane', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames} />);
  expect(screen.queryByTestId('contract-premium-pane')).not.toBeInTheDocument();
  expect(screen.queryByTestId('contract-premium-unavailable')).not.toBeInTheDocument();
});

test('chart page contract picker loads premium bars through price-history', async () => {
  axios.get.mockResolvedValue({ data: { ticker: 'SPY', frames, candles_with_recorded_nodes: 0,
    contract_symbol: 'SPY261017C00650000', contract_status: 'available', contract_bars: contractBars } });
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText(/option contract/i), { target: { value: 'SPY261017C00650000' } });
  fireEvent.click(screen.getByRole('button', { name: /load contract/i }));
  await waitFor(() => expect(screen.getByTestId('contract-premium-pane')).toBeInTheDocument());
  const lastCall = axios.get.mock.calls.at(-1);
  expect(lastCall[1].params.contract_symbol).toBe('SPY261017C00650000');
});
