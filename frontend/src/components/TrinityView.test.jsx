/** @jest-environment jsdom */
import React from 'react';
import { render, waitFor, fireEvent } from '@testing-library/react';
import axios from 'axios';
import { fetchPublicChain } from '../lib/publicApi';
import TrinityView from './TrinityView';

// NOTE: CRA jest sets resetMocks:true, so factory implementations are wiped
// before each test — assign them in beforeEach, never in the factory.
// ── Mocks ──────────────────────────────────────────────────────────
jest.mock('../config/api', () => ({
  API: '/api',
  BACKEND_URL: '',
  BACKEND_BASE: '',
}));

jest.mock('../lib/publicApi', () => ({
  fetchPublicChain: jest.fn(),
  publicChainUrl: jest.fn((t) => `/api/public/chain/${t}`),
  publicQuoteUrl: jest.fn((t) => `/api/public/quotes/${t}`),
}));

jest.mock('axios', () => ({
  get: jest.fn(),
}));

const PUB_CONTRACTS = [
  { type: 'call', strike: 650, expiry: '2026-09-18', T: 0.04, iv: 0.18, delta: 0.5, gamma: 0.01, oi: 1000, volume: 50, gex: 2000000, bid: 1.2, ask: 1.3 },
  { type: 'put', strike: 650, expiry: '2026-09-18', T: 0.04, iv: 0.20, delta: -0.4, gamma: 0.012, oi: 800, volume: 40, gex: -1500000, bid: 1.1, ask: 1.25 },
  { type: 'call', strike: 640, expiry: '2026-09-18', T: 0.04, iv: 0.19, delta: 0.6, gamma: 0.011, oi: 500, volume: 20, gex: 900000, bid: 2.1, ask: 2.2 },
];

const CONTRACT_DETAIL = {
  ticker: 'SPY',
  strike: 650,
  expiry: '2026-09-18',
  contracts: [
    { osi: 'SPY260918C00650000', type: 'call', strike: 650, expiry: '2026-09-18', bid: 1.2, ask: 1.3, last: 1.25, iv: 0.18, delta: 0.5, open_interest: 100 },
    { osi: 'SPY260918P00650000', type: 'put', strike: 650, expiry: '2026-09-18', bid: 1.1, ask: 1.25, last: 1.2, iv: 0.2, delta: -0.4, open_interest: 80 },
  ],
};

beforeEach(() => {
  fetchPublicChain.mockImplementation(async (ticker) => ({
    ok: true,
    ticker,
    spot: 645.0,
    expiries: ['2026-09-18'],
    n_contracts: PUB_CONTRACTS.length,
    data_source: 'public_api',
    contracts: PUB_CONTRACTS,
  }));
  axios.get.mockImplementation(async (url) => {
    if (String(url).includes('/contract/')) return { data: CONTRACT_DETAIL };
    return { data: { ok: true } };
  });
});

// ── Tests ──────────────────────────────────────────────────────────
test('row click emits base selection immediately, then Public-enriched selection with OSI', async () => {
  const onTradeSelect = jest.fn();
  const { container, unmount } = render(
    <TrinityView onTradeSelect={onTradeSelect} />
  );

  // Rows render from the mocked Public chain. Panels mount in
  // panelTickers order (^SPX, SPY, QQQ) — scope clicks to the SPY panel.
  const rows = await waitFor(
    () => {
      const panels = container.querySelectorAll('.trinity-panel');
      expect(panels.length).toBeGreaterThan(1);
      const els = panels[1].querySelectorAll('tr.trinity-dom-row');
      expect(els.length).toBeGreaterThan(0);
      return els;
    },
    { timeout: 8000 }
  );

  fireEvent.click(rows[0]);

  // 1. Base selection fires synchronously (panel opens instantly).
  expect(onTradeSelect).toHaveBeenCalledTimes(1);
  expect(onTradeSelect.mock.calls[0][0]).toMatchObject({ ticker: 'SPY', strike: 650 });

  // 2. Public contract detail upgrades the selection with OSI + prices.
  await waitFor(
    () => {
      const enriched = onTradeSelect.mock.calls.find(
        (c) => c[0] && c[0].oi_symbol === 'SPY260918C00650000'
      );
      expect(enriched).toBeTruthy();
      expect(enriched[0]).toMatchObject({
        expiry: '2026-09-18',
        call_ask: 1.3,
        put_bid: 1.1,
      });
    },
    { timeout: 8000 }
  );

  // 3. The enrichment hit /api/contract (Public-backed), not a vendor API.
  const contractCalls = axios.get.mock.calls.filter((c) => String(c[0]).includes('/contract/'));
  expect(contractCalls.length).toBeGreaterThan(0);
  expect(contractCalls[0][0]).toContain('/api/contract/SPY/650/2026-09-18');

  unmount();
});

test('row click still emits base selection when Public contract fetch fails', async () => {
  axios.get.mockImplementation(async (url) => {
    if (String(url).includes('/contract/')) throw new Error('Public down');
    return { data: { ok: true } };
  });
  const onTradeSelect = jest.fn();
  const { container, unmount } = render(
    <TrinityView onTradeSelect={onTradeSelect} />
  );

  const rows = await waitFor(
    () => {
      const panels = container.querySelectorAll('.trinity-panel');
      expect(panels.length).toBeGreaterThan(1);
      const els = panels[1].querySelectorAll('tr.trinity-dom-row');
      expect(els.length).toBeGreaterThan(0);
      return els;
    },
    { timeout: 8000 }
  );

  fireEvent.click(rows[0]);
  expect(onTradeSelect).toHaveBeenCalledTimes(1);
  expect(onTradeSelect.mock.calls[0][0]).toMatchObject({ ticker: 'SPY', strike: 650 });

  // No enrichment arrives — give the rejected promise a tick to settle.
  await new Promise((r) => setTimeout(r, 100));
  expect(onTradeSelect).toHaveBeenCalledTimes(1);

  unmount();
});
