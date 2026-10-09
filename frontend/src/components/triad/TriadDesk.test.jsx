/* TriadDesk wall-desk tests: scope, empty states, exposure, chain, rail.
   Synthetic inline fixtures (not producer output). No network (fetch
   mocked), no order surfaces (every fetch URL asserted). */
import React from 'react';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import TriadDesk from './TriadDesk';
import paired from '../../test-fixtures/triad-exposure.paired.json';
import TriadExposure from './TriadExposure';

test('signed Triad bars use the same restrained palette and support keyboard strike review',()=>{
 const select=jest.fn();
 render(<TriadExposure series={{strikes:[{strike:450,gex:-40,n_measured:1,n_total:1,partial:false},{strike:451,gex:100,n_measured:1,n_total:1,partial:false}]}} selectedStrike={450} onSelect={select} />);
 const negative=screen.getByRole('button',{name:/Strike 450/});
 expect(negative.getAttribute('aria-pressed')).toBe('true');
 expect(negative.querySelector('rect').getAttribute('fill')).toBe('rgb(55, 48, 107)');
 fireEvent.keyDown(negative,{key:'Enter'});
 expect(select).toHaveBeenCalledWith(450);
});

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
// Hand-authored legacy UI examples remain synthetic. The separate paired
// fixture above is also verified by the canonical backend producer.
CHAIN.exposure_by_strike = {
 series_version: 'triad-projection.backend.v1', formula_version: 'gex.v2',
 ticker: 'SPY', spot: CHAIN.spot, fetched_at: CHAIN.fetched_at,
 coverage: {}, source_coverage: {},
 strikes: [
  {strike:775,gex:30.25,n_measured:2,n_total:2,partial:false,gex_basis:'OI',expiries:['2026-10-07']},
  {strike:780,gex:200,n_measured:1,n_total:2,partial:true,gex_basis:'OI_PARTIAL',expiries:['2026-10-07']},
  {strike:785,gex:20,n_measured:2,n_total:2,partial:false,gex_basis:'OI',expiries:['2026-10-07']},
 ],
};
const ok = data => ({ok: true, json: async () => data});
const mockRoutes = (expiries = EXPIRIES, chain = CHAIN) => {
 global.fetch = jest.fn(async url => {
  const u = String(url);
  if (u.includes('/solstice/price-paths/expiries')) return ok(expiries);
  if (u.includes('/api/public/chain')) {
   const selected = new URL(u, 'http://test.local').searchParams.get('expiration');
   if (selected === '2026-10-14' && chain === CHAIN) return ok({ ...chain,
    contracts: chain.contracts.map(r => ({ ...r, expiry: selected })),
    exposure_by_strike: { ...chain.exposure_by_strike,
     strikes: chain.exposure_by_strike.strikes.map(r => ({ ...r, expiries: [selected] })) } });
   return ok(chain);
  }
  throw new Error(`unexpected fetch ${u}`);
 });
};
const orderSurfacesUntouched = () => {
 expect(global.fetch.mock.calls.every(([url]) => {
  const u = String(url);
  return !u.includes('/alpaca') && !u.includes('/public/order');
 })).toBe(true);
};

test('overlay draws the paired admitted series instead of recalculating chain rows', async () => {
 const chain = { ...CHAIN, ticker: paired.input.ticker, spot: paired.input.spot,
  fetched_at: paired.input.fetched_at, contracts: [{ ...CHAIN.contracts[0], strike: 450, gex: 999999 }],
  exposure_by_strike: paired.expected };
 mockRoutes(EXPIRIES, chain);
 const { container } = render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
 const cell = container.querySelector('g[data-strike="450"]');
 expect(cell.getAttribute('data-exposure')).toBe('202500');
 expect(cell.getAttribute('data-partial')).toBe('true');
 expect(cell.getAttribute('data-known')).toBe('1');
 expect(cell.getAttribute('data-total')).toBe('2');
 expect(screen.getByText(/Source coverage includes skipped expiries/)).toBeInTheDocument();
 orderSurfacesUntouched();
});

test.each(['missing', 'version', 'ticker', 'receipt', 'expiry'])(
 'unadmitted %s series shows unavailable without a browser calculation fallback', async defect => {
  const series = JSON.parse(JSON.stringify(paired.expected));
  if (defect === 'version') series.series_version = 'future.v99';
  if (defect === 'ticker') series.ticker = 'QQQ';
  if (defect === 'receipt') series.fetched_at = '2026-10-08T14:01:00Z';
  if (defect === 'expiry') series.strikes[0].expiries = ['2026-10-14'];
  mockRoutes(EXPIRIES, { ...CHAIN, fetched_at: paired.input.fetched_at,
   exposure_by_strike: defect === 'missing' ? undefined : series });
  render(<TriadDesk ticker="SPY" />);
  await screen.findByText(/Admitted exposure unavailable/);
  expect(screen.queryByRole('group', { name: /Signed exposure by strike/ })).not.toBeInTheDocument();
  expect(screen.getByRole('table')).toBeInTheDocument();
  orderSurfacesUntouched();
 });

test('0DTE desk renders exposure, chain and rail with zero order-surface calls', async () => {
 mockRoutes();
 const { container } = render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
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
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
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
 expect(screen.queryByRole('group', { name: /Signed exposure/ })).not.toBeInTheDocument();
 orderSurfacesUntouched();
});

test('chain Review selects the strike and the rail shows measured vs unknown truthfully', async () => {
 mockRoutes();
 render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
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
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
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
 expect(screen.queryByRole('group', { name: /Signed exposure/ })).not.toBeInTheDocument();
});

test('partial strike renders outlined partial subtotal, never silent zero', async () => {
 mockRoutes();
 const { container } = render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
 const cell780 = container.querySelector('g[data-strike="780"]');
 expect(cell780).not.toBeNull();
 expect(cell780.getAttribute('data-partial')).toBe('true');
 expect(cell780.getAttribute('data-known')).toBe('1');
 expect(cell780.getAttribute('data-total')).toBe('2');
 const title780 = cell780.querySelector('title');
 expect(title780).not.toBeNull();
 expect(title780.textContent.replace(/\s+/g, ' ')).toMatch(/Partial exposure 1\/2 measured/);
 const cell775 = container.querySelector('g[data-strike="775"]');
 expect(cell775.getAttribute('data-partial')).toBe('false');
 expect(cell775.getAttribute('data-known')).toBe('2');
 orderSurfacesUntouched();
});

test('axis ticks label raw dollars without M and millions with M', async () => {
 const { formatExposureTick } = require('./TriadExposure');
 expect(formatExposureTick(200)).toBe('+200');
 expect(formatExposureTick(-200)).toBe('−200');
 expect(formatExposureTick(1000000)).toMatch(/M$/);
 expect(formatExposureTick(200)).not.toMatch(/M/);
 mockRoutes();
 render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
 expect(screen.queryByText('+200M')).not.toBeInTheDocument();
 expect(screen.getByText('+200')).toBeInTheDocument();
 orderSurfacesUntouched();
});

test('Next listed skips same-day expiry when a later series coexists', async () => {
 mockRoutes();
 render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
 fireEvent.click(screen.getByRole('button', { name: 'Next listed' }));
 await waitFor(() => {
  const calls = global.fetch.mock.calls.map(([u]) => String(u));
  expect(calls.some(u => u.includes('expiration=2026-10-14'))).toBe(true);
 });
 expect(global.fetch.mock.calls.map(([u]) => String(u)).filter(u => u.includes('/api/public/chain') && u.includes('expiration=2026-10-07')).length).toBe(1);
 orderSurfacesUntouched();
});

test('measured-zero renders a known marker, all-unknown renders the gray slot', async () => {
 const zeroChain = { ...CHAIN, contracts: [
  {strike: 790, expiry: '2026-10-07', type: 'call', bid: 0.1, ask: 0.2, delta: 0.1, osi: 'SPY261007C00790000', gex: 0, gex_basis: 'OI'},
  {strike: 790, expiry: '2026-10-07', type: 'put', bid: 0.1, ask: 0.2, delta: -0.1, osi: 'SPY261007P00790000', gex: 0, gex_basis: 'OI'},
  {strike: 791, expiry: '2026-10-07', type: 'call', bid: 0.1, ask: 0.2, delta: 0.1, osi: 'SPY261007C00791000', gex: null, gex_basis: 'OI_UNKNOWN'},
  {strike: 791, expiry: '2026-10-07', type: 'put', bid: 0.1, ask: 0.2, delta: -0.1, osi: 'SPY261007P00791000', gex: null, gex_basis: 'OI_UNKNOWN'},
 ]};
 zeroChain.exposure_by_strike = { ...CHAIN.exposure_by_strike, strikes: [
  {strike:790,gex:0,n_measured:2,n_total:2,partial:false,gex_basis:'OI',expiries:['2026-10-07']},
  {strike:791,gex:null,n_measured:0,n_total:2,partial:false,gex_basis:'OI_UNKNOWN',expiries:['2026-10-07']},
 ] };
 mockRoutes(EXPIRIES, zeroChain);
 const { container } = render(<TriadDesk ticker="SPY" />);
 await screen.findByRole('group', { name: /Signed exposure by strike/ });
 const zero = container.querySelector('g[data-strike="790"]');
 expect(zero.getAttribute('data-partial')).toBe('false');
 expect(zero.getAttribute('data-known')).toBe('2');
 const unknown = container.querySelector('g[data-strike="791"]');
 expect(unknown.querySelector('title').textContent).toMatch(/Unknown exposure/);
 orderSurfacesUntouched();
});
