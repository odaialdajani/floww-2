/* TriadDesk staleness + missing-reading caption pins (Hermes-2, M2 2026-10-24).
   The desk's source/receipt caption has a three-way staleness branch
   (TriadDesk.jsx): chain.stale === true -> "stale snapshot",
   chain.stale === false -> "producer reports not stale",
   otherwise -> "freshness unknown"; and the scope header shows
   "Spot unknown" when the chain carries no finite spot. The browser
   campaign observed the stale===false branch live (next-listed scope,
   2026-10-24), but none of the branches was test-pinned — these
   characterization pins protect the honest stale/missing states without
   changing behavior. Synthetic inline fixtures (not producer output);
   fetch mocked, no network, no order surfaces (every fetch URL asserted). */
import React from 'react';
import { render, screen } from '@testing-library/react';
import TriadDesk from './TriadDesk';

const drain = async () => { for (let i = 0; i < 50; i += 1) { await Promise.resolve(); } await new Promise((r) => setTimeout(r, 30)); for (let i = 0; i < 50; i += 1) { await Promise.resolve(); } await new Promise((r) => setTimeout(r, 30)); };

const EXPIRIES = {
  version: 'coverage-read.v1', ticker: 'SPY',
  window: { min_dte: 0, max_dte: 7 },
  expiries: [{ expiry: '2026-10-07', dte: 0, admitted: true, reason: null, display_envelope: true }],
  range_map: { admitted_expiries: ['2026-10-07'] },
};
const baseChain = stale => ({
  ok: true, ticker: 'SPY', spot: 779.09, fetched_at: '2026-10-07T13:00:00+00:00',
  event_time: '2026-10-07T13:00:01+00:00', stale,
  data_source: 'public_api', expiries: ['2026-10-07'],
  contracts: [
    { strike: 775, expiry: '2026-10-07', type: 'call', bid: 1.2, ask: 1.3, delta: 0.4, osi: 'SPY261007C00775000', gex: 150.5, gex_basis: 'OI' },
  ],
});
const ok = data => ({ ok: true, json: async () => data });
const mountDesk = chain => {
  global.fetch = jest.fn(async url => {
    const u = String(url);
    if (u.includes('/solstice/price-paths/expiries')) return ok(EXPIRIES);
    if (u.includes('/api/public/chain')) return ok(chain);
    throw new Error(`unexpected fetch ${u}`);
  });
  return render(<TriadDesk ticker="SPY" />);
};
const orderSurfacesUntouched = () => {
  expect(global.fetch.mock.calls.every(([url]) => {
    const u = String(url);
    return !u.includes('/alpaca') && !u.includes('/public/order');
  })).toBe(true);
};

const caption = async chain => {
  mountDesk(chain);
  await screen.findByText(/Receipt 2026-10-07T13:00:00\+00:00/);
  await drain();
  // Two .chart-caption rows exist (listed-window note + source/receipt);
  // the staleness branches live on the one that carries the Receipt.
  const captionEl = [...document.querySelectorAll('.wall-desk .chart-caption')]
    .find(e => e.textContent.includes('Receipt'));
  orderSurfacesUntouched();
  return captionEl.textContent.replace(/\s+/g, ' ');
};

test('chain stale === true is reported as a stale snapshot, never as fresh', async () => {
  const text = await caption(baseChain(true));
  expect(text).toContain('Source public_api · Receipt 2026-10-07T13:00:00+00:00');
  expect(text).toContain('chain observation 2026-10-07T13:00:01+00:00');
  expect(text).toContain('stale snapshot.');
  expect(text).not.toContain('producer reports not stale');
  expect(text).not.toContain('freshness unknown');
});

test('chain stale === false reports the producer claim, not an independent freshness verdict', async () => {
  const text = await caption(baseChain(false));
  expect(text).toContain('producer reports not stale.');
  expect(text).not.toContain('stale snapshot');
  // The caption attributes the claim to the producer — the desk does not
  // assert its own freshness.
  expect(text).toContain('producer reports not stale');
});

test('missing staleness reading stays freshness-unknown, never coerced to fresh', async () => {
  const chain = baseChain(undefined);
  delete chain.stale;
  const text = await caption(chain);
  expect(text).toContain('freshness unknown.');
  expect(text).not.toContain('stale snapshot');
  expect(text).not.toContain('producer reports not stale');
});

test('missing chain observation time stays unknown on the caption', async () => {
  const chain = baseChain(false);
  delete chain.event_time;
  const text = await caption(chain);
  expect(text).toContain('chain observation unknown');
});

test('chain with no finite spot shows Spot unknown in the scope header', async () => {
  const chain = baseChain(false);
  chain.spot = null;
  mountDesk(chain);
  await screen.findByText(/Receipt 2026-10-07T13:00:00\+00:00/);
  await drain();
  const scope = document.querySelector('.wall-desk-scope').textContent.replace(/\s+/g, ' ');
  expect(scope).toContain('Spot unknown');
  expect(scope).not.toMatch(/Spot 779/);
  orderSurfacesUntouched();
});
