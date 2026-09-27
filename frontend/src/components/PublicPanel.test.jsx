/** @jest-environment jsdom */
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import PublicPanel from './PublicPanel';

jest.mock('../config/api', () => ({ API: '/api', BACKEND_URL: '' }));

const ACCOUNT = { account_id: 'TEST-1', cash: 100, buying_power: 200 };
const PORTFOLIO = {
  cash: 100, buying_power: 200, portfolio_value: 5000, position_count: 1,
  positions: [{ symbol: 'SPY', quantity: 10, current_price: 450, pnl: 50 }],
};
const ORDERS = { orders: [{ order_id: 'O1', symbol: 'SPY', side: 'BUY', quantity: 1, status: 'FILLED' }] };

function mockFetchOnce(account = ACCOUNT, portfolio = PORTFOLIO, orders = ORDERS) {
  const bodies = [account, portfolio, orders];
  global.fetch = jest.fn(async () => {
    const body = bodies.shift() || {};
    return { ok: true, json: async () => body };
  });
}

afterEach(() => { jest.restoreAllMocks(); window.localStorage.clear(); });

test('renders account, positions, and orders from the brokerage endpoints', async () => {
  window.localStorage.setItem('floww_app_key', 'test-key');
  mockFetchOnce();
  await act(async () => { render(<PublicPanel />); });
  await waitFor(() => expect(screen.getByTestId('public-panel')).toBeInTheDocument());
  expect(screen.getByText('TEST-1', { exact: false })).toBeInTheDocument();
  expect(screen.getAllByText('SPY').length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText('FILLED')).toBeInTheDocument();
  const urls = global.fetch.mock.calls.map((c) => c[0]);
  expect(urls).toContain('/api/public/account');
  expect(urls).toContain('/api/public/portfolio');
  expect(urls).toContain('/api/public/orders');
  for (const c of global.fetch.mock.calls) {
    expect(c[1].headers).toEqual({ 'X-API-Key': 'test-key' });
  }
});

test('shows the key hint without prompting when no key is stored', async () => {
  const prompt = jest.spyOn(window, 'prompt').mockReturnValue('x');
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => ({}) }));
  await act(async () => { render(<PublicPanel />); });
  await waitFor(() => expect(screen.getByTestId('public-panel-error')).toBeInTheDocument());
  expect(screen.getByText('Backend key missing or rejected', { exact: false })).toBeInTheDocument();
  expect(global.fetch).not.toHaveBeenCalled();
  expect(prompt).not.toHaveBeenCalled();
});

test('shows the error tile when the backend is unreachable', async () => {
  global.fetch = jest.fn(async () => { throw new Error('down'); });
  await act(async () => { render(<PublicPanel />); });
  await waitFor(() => expect(screen.getByTestId('public-panel-error')).toBeInTheDocument());
});


test('restores position detail and complete asset totals without hiding later rows', async () => {
  window.localStorage.setItem('floww_app_key', 'test-key');
  const positions = Array.from({length: 26}, (_, i) => ({symbol: 'S'+i, quantity: 1.5, current_price: 80,
    market_value: 120, cost_basis: 100, pnl: 20, day_gain_pct: 2.5, total_gain_pct: 20, asset_type: 'EQUITY'}));
  mockFetchOnce(ACCOUNT, {...PORTFOLIO, positions, position_count: 26});
  await act(async () => { render(<PublicPanel />); });
  expect(screen.getByText('S25')).toBeInTheDocument();
  expect(screen.getByRole('columnheader', {name: 'Market value'})).toBeInTheDocument();
  expect(screen.getAllByText('2.50%')).toHaveLength(26);
  expect(screen.getAllByText('20.00%')).toHaveLength(26);
  expect(screen.getByLabelText('EQUITY total market value')).toHaveTextContent('$3,120.00');
  expect(screen.getByLabelText('EQUITY total cost')).toHaveTextContent('$2,600.00');
});

test('unknown position values make asset totals unavailable, while true zero remains zero', async () => {
  window.localStorage.setItem('floww_app_key', 'test-key');
  mockFetchOnce(ACCOUNT, {...PORTFOLIO, positions: [
    {symbol: 'KNOWN', market_value: 10, cost_basis: 10, pnl: 0, asset_type: 'EQUITY'},
    {symbol: 'MISSING', market_value: null, cost_basis: null, pnl: null, asset_type: 'EQUITY'},
  ]});
  await act(async () => { render(<PublicPanel />); });
  expect(screen.getByLabelText('EQUITY total market value')).toHaveTextContent('Unavailable');
  expect(screen.getByLabelText('EQUITY total cost')).toHaveTextContent('Unavailable');
  expect(screen.getAllByText('$0.00').length).toBeGreaterThan(0);
});
