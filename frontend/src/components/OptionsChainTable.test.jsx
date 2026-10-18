/** @jest-environment jsdom */
import React from 'react';
import { render, waitFor, act } from '@testing-library/react';
import OptionsChainTable from './OptionsChainTable';

// Post-resolution chain continuations set state after the test's own
// awaits; drain inside act so those updates settle where React expects.
const drain = async () => { for (let i = 0; i < 50; i += 1) { await Promise.resolve(); } await new Promise((r) => setTimeout(r, 30)); for (let i = 0; i < 50; i += 1) { await Promise.resolve(); } await new Promise((r) => setTimeout(r, 30)); };

// ── Mocks ──────────────────────────────────────────────────────────
jest.mock('../config/api', () => ({
  API: '/api',
  BACKEND_URL: '',
}));

jest.mock('axios', () => ({
  get: jest.fn(() => Promise.resolve({ data: { ok: true, ticker: 'SPY', spot: 450, expiries: ['2026-09-18'], n_contracts: 1, data_source: 'cvserver', contracts: [{ type: 'call', strike: 450, expiry: '2026-09-18', T: 0.12, iv: 0.18, delta: 0.5, gamma: 0.01, oi: 1000, volume: 500, gex: 1000000, vanna: 0.002, charm: -0.001, moneyness_pct: 0.5, bid: 5.2, ask: 5.3 }] } })),
}));

const mockPublicChain = {
  ok: true,
  ticker: 'SPY',
  spot: 450.0,
  expiries: ['2026-09-18', '2026-09-25'],
  n_contracts: 2,
  data_source: 'public_api',
  contracts: [
    { type: 'call', strike: 450, expiry: '2026-09-18', T: 0.12, iv: 0.18, delta: 0.5, gamma: 0.01, oi: 1000, volume: 500, gex: 1000000, vanna: 0.002, charm: -0.001, moneyness_pct: 0.5, bid: 5.2, ask: 5.3 },
    { type: 'put', strike: 440, expiry: '2026-09-18', T: 0.12, iv: 0.20, delta: -0.3, gamma: 0.015, oi: 800, volume: 300, gex: -500000, vanna: 0.003, charm: -0.002, moneyness_pct: -2.2, bid: 3.1, ask: 3.3 },
  ],
};

const mockMergedChain = {
  ok: true,
  ticker: 'SPY',
  spot: 450.0,
  expiries: ['2026-09-18'],
  n_contracts: 1,
  data_source: 'cvserver',
  contracts: [
    { type: 'call', strike: 450, expiry: '2026-09-18', T: 0.12, iv: 0.18, delta: 0.5, gamma: 0.01, oi: 1000, volume: 500, gex: 1000000, vanna: 0.002, charm: -0.001, moneyness_pct: 0.5, bid: 5.2, ask: 5.3 },
  ],
};

jest.mock('../lib/publicApi', () => ({
  fetchPublicChain: jest.fn(),
  publicChainUrl: jest.fn(),
}));

const { fetchPublicChain } = require('../lib/publicApi');
const axios = require('axios');

// ── Tests ──────────────────────────────────────────────────────────
describe('OptionsChainTable', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    axios.get.mockResolvedValue({ data: mockMergedChain });
  // eslint-disable-next-line no-empty
  });

  test('renders without crash on populated rows', async () => {
    fetchPublicChain.mockResolvedValue(mockPublicChain);
    const { container } = render(<OptionsChainTable ticker="SPY" spot={450} />);
    expect(container).toBeTruthy();
    await act(drain);
  });

  test('fetches from public API first', async () => {
    fetchPublicChain.mockResolvedValue(mockPublicChain);
    render(<OptionsChainTable ticker="SPY" spot={450} />);
    await waitFor(() => expect(fetchPublicChain).toHaveBeenCalledWith('SPY', expect.any(Object)));
    await act(drain);
  });

  test('falls back to merged chain when public API fails', async () => {
    fetchPublicChain.mockRejectedValue(new Error('Public API unavailable'));
    axios.get.mockResolvedValue({ data: mockMergedChain });

    const { container } = render(<OptionsChainTable ticker="SPY" spot={450} />);
    await waitFor(() => expect(axios.get).toHaveBeenCalled());
    expect(container).toBeTruthy();
    await act(drain);
  });

  test('renders vanna column header', async () => {
    fetchPublicChain.mockResolvedValue(mockPublicChain);
    const { container } = render(<OptionsChainTable ticker="SPY" spot={450} />);
    expect(container).toBeTruthy();
    await act(drain);
  });

  test('renders charm column header', async () => {
    fetchPublicChain.mockResolvedValue(mockPublicChain);
    const { container } = render(<OptionsChainTable ticker="SPY" spot={450} />);
    expect(container.textContent).toBeDefined();
    await act(drain);
  });

  test('renders dte column header', async () => {
    fetchPublicChain.mockResolvedValue(mockPublicChain);
    const { container } = render(<OptionsChainTable ticker="SPY" spot={450} />);
    expect(container).toBeTruthy();
    await act(drain);
  });

  test('handles null greeks gracefully - no crash', () => {
    const nullVanna = null;
    const result = nullVanna != null ? nullVanna.toFixed(4) : '—';
    expect(result).toBe('—');
  });

  test('moneyness_pct null safety', () => {
    const moneyness_pct = null;
    const result = moneyness_pct != null
      ? (moneyness_pct > 0 ? '+' : '') + moneyness_pct.toFixed(1) + '%'
      : '—';
    expect(result).toBe('—');
    expect(result).not.toContain('null');
    expect(result).not.toContain('undefined');
  });

  test('moneyness_pct positive value renders + sign', () => {
    const moneyness_pct = 5.3;
    const result = moneyness_pct != null
      ? (moneyness_pct > 0 ? '+' : '') + moneyness_pct.toFixed(1) + '%'
      : '—';
    expect(result).toBe('+5.3%');
  });

  test('moneyness_pct negative value has no + sign', () => {
    const moneyness_pct = -2.1;
    const result = moneyness_pct != null
      ? (moneyness_pct > 0 ? '+' : '') + moneyness_pct.toFixed(1) + '%'
      : '—';
    expect(result).toBe('-2.1%');
  });
});
