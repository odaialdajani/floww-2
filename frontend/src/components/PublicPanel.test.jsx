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

afterEach(() => { jest.restoreAllMocks(); });

test('renders account, positions, and orders from the brokerage endpoints', async () => {
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
});

test('shows the error tile when the backend is unreachable', async () => {
  global.fetch = jest.fn(async () => { throw new Error('down'); });
  await act(async () => { render(<PublicPanel />); });
  await waitFor(() => expect(screen.getByTestId('public-panel-error')).toBeInTheDocument());
});
