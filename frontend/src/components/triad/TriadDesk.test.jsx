/* TriadDesk wall-desk tests: scope, empty states, exposure, chain, rail.
   Synthetic inline fixtures (not producer output). No network (fetch
   mocked), no order surfaces (every fetch URL asserted). */
import React from 'react';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import TriadDesk from './TriadDesk';

const EXPIRIES = {
 version: 'coverage.v1', ticker: 'SPY',
 window: {min_dte: 0, max_dte: 7},
 expiries: [
  {expiry: '2026-10-07', dte: 0, admitted: true, reason: null, display_envelope: true},
  {expiry: '2026-10-14', dte: 7, admitted: true, reason: null, display_envelope: true},
 ],
 range_map: {admitted_expiries: ['2026-10-07', '2026-10-14']},
};
const CHAIN = {
 ok: true, ticker: 'SPY', spot: 779.09, fetched_at: '2026-10-07T13:00:00+00:00',
 data_source: 'public_api', expiries: ['2026-10-07'],
 contracts: [
  {strike: 775, expiry: '2026-10-07', type: 'call', bid: 1.2, ask: 1.3, delta: 0.4, osi: 'SPY261007C00775000', gex: 150.5, gex_basis: 'OI'},
  {strike: 775, expiry: '2026-10-07', type: 'put', bid: 0.9, ask: 1.0, delta: -0.35, osi: 'SPY261007P00775000', gex: -120.25, gex_basis: 'OI'},
  {strike: 780, expiry: '2026-10-07', type: 'call', bid: 0.8, ask: 0.9, delta: 0.3, osi: 'SPY261007C00780000', gex: 200.0, gex_basis: 'OI'},
  {strike: 780, expiry: '2026-10-07', type: 'put', bid: 1.1, ask: 1.2, delta: -0.45, osi: 'SPY261007P00780000', gex: null, gex_basis: 'OI_UNKNOWN'},
  {strike: 785, expiry: '2026-10-07', type: 'call', bid: 0.5, ask: 0.6, delta: 0.2, osi: 'SPY261007C00785000', gex: 80.0, gex_basis: 'OI'},
  {strike: 785, expiry: '2026-10-07', type: 'put', bid: 1.5, ask: 1.6, delta: -0.55, osi: 'SPY261007P00785000', gex: -60.0, gex_basis: 'OI'},
 ],
};
const ok = data => ({ok: true, json: async () => data});
const mockRoutes = (expiries = EXPIRIES, chain = CHAIN) => {
 global.fetch = jest.fn(async url => {
  const u = String(url);
  if (u.includes('/solstice/price-paths/expiries')) return ok(expiries);
  if (u.includes('/api/public/chain')) return ok(chain);
  throw new Error(`unexpected fetch ${u}`);
 });
};
const orderSurfacesUntouched = () => {
 expect(global.fetch.mock.calls.every(([url]) => {
  const u = String(url);
  return !u.includes('/alpaca') && !u.includes('/public/order');
 })).toBe(true);
};

test('0DTE desk renders exposure, chain and rail with zero order-surface calls', async () => {
 mockRoutes();
 const { container } = render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('img', { name: /Signed exposure by strike/ });
 expect(screen.getAllByText('Spot 779.09')).toHaveLength(2);
 expect(screen.getByRole('table')).toBeInTheDocument();
 expect(screen.getByText(/Contract: RANGE_CONTRACT_UNAVAILABLE|Selected contract/)).toBeInTheDocument();
 expect(container.querySelectorAll('g[data-action="cell"]').length).toBeGreaterThan(0);
 orderSurfacesUntouched();
});

test('no same-day series renders the empty panel with next-listed action', async () => {
 const no0dte = { ...EXPIRIES, expiries: EXPIRIES.expiries.filter(r => r.dte !== 0),
  range_map: { admitted_expiries: ['2026-10-14'] } };
 mockRoutes(no0dte);
 render(<TriadDesk ticker="SPY" />);
 await screen.findByText(/same-day chain not verified/);
 expect(screen.getByText(/No same-day series listed/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button', { name: 'Review next listed expiry' }));
 await screen.findByRole('img', { name: /Signed exposure by strike/ });
 orderSurfacesUntouched();
});

test('SPX without same-day names the entitlement check explicitly', async () => {
 const no0dte = { ...EXPIRIES, expiries: [{ expiry: '2026-10-26', dte: 21, admitted: true, reason: null }],
  range_map: { admitted_expiries: ['2026-10-26'] } };
 mockRoutes(no0dte);
 render(<TriadDesk ticker="^SPX" />);
 await screen.findByText(/Index-option entitlement/);
});

test('chain failure is an honest error, never a crash or fabrication', async () => {
 global.fetch = jest.fn(async url => String(url).includes('expiries') ? ok(EXPIRIES) : Promise.reject(new Error('down')));
 render(<TriadDesk ticker="SPY" />);
 await screen.findByText(/Triad scope unavailable/);
 expect(screen.queryByRole('img', { name: /Signed exposure/ })).not.toBeInTheDocument();
 orderSurfacesUntouched();
});

test('chain Review selects the strike and the rail shows measured vs unknown truthfully', async () => {
 mockRoutes();
 render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('img', { name: /Signed exposure by strike/ });
 fireEvent.click(screen.getByRole('button', { name: 'Review strike 780' }));
 expect(await screen.findByText(/Wall context attached · SPY · 780 · 2026-10-07/)).toBeInTheDocument();
 expect(screen.getByText(/SPY261007C00780000/)).toBeInTheDocument();
 expect(screen.getByText(/unknown \(not zero\)|200 \(OI\)/)).toBeInTheDocument();
 expect(screen.getByText(/Execution owner: unselected/)).toBeInTheDocument();
 orderSurfacesUntouched();
});

test('copy triad context writes the frozen scope and failure surfaces status', async () => {
 const written = [];
 Object.defineProperty(navigator, 'clipboard', { value: { writeText: jest.fn(async t => { written.push(t); }) }, configurable: true });
 mockRoutes();
 render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('img', { name: /Signed exposure by strike/ });
 fireEvent.click(screen.getByRole('button', { name: 'Copy Triad context' }));
 await screen.findByText('Context copied.');
 const payload = JSON.parse(written[0]);
 expect(payload).toMatchObject({ kind: 'triad-context', ticker: 'SPY', scope: '0dte', expiry: '2026-10-07' });
 expect(payload.note).toMatch(/not an execution permission/);
 orderSurfacesUntouched();
});

test('ticker change aborts and clears the desk', async () => {
 let release;
 mockRoutes();
 global.fetch.mockImplementation(async url => {
  if (String(url).includes('/api/public/chain')) await new Promise(r => { release = r; });
  return ok(String(url).includes('expiries') ? EXPIRIES : CHAIN);
 });
 const ui = render(<TriadDesk ticker="SPY" />);
 await waitFor(() => expect(global.fetch.mock.calls.some(([u]) => String(u).includes('/api/public/chain'))).toBe(true));
 const signal = global.fetch.mock.calls.find(([u]) => String(u).includes('/api/public/chain'))[1].signal;
 ui.rerender(<TriadDesk ticker="QQQ" />);
 expect(signal.aborted).toBe(true);
 expect(screen.queryByRole('img', { name: /Signed exposure/ })).not.toBeInTheDocument();
});
