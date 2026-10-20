import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import TriadDesk from './TriadDesk';
import TriadExposure from './TriadExposure';

const date = '2026-10-19';
const listed = (ticker = 'SPY', rows = [{ expiry: date, dte: 0, admitted: true }]) => ({
  version: 'coverage.v1', ticker, window: { min_dte: 0, max_dte: 7 }, expiries: rows,
  range_map: { admitted_expiries: rows.map(r => r.expiry) },
});
const contract = (type = 'call', extra = {}) => ({
  type, expiry: date, strike: 100, osi: `SPY261019${type === 'call' ? 'C' : 'P'}00100000`,
  bid: type === 'call' ? 1 : 2, ask: type === 'call' ? 1.1 : 2.3,
  delta: type === 'call' ? 0.5 : -0.4, gex: type === 'call' ? 50 : null,
  gex_basis: type === 'call' ? 'OI' : 'OI_UNKNOWN',
  bid_event_time: '2026-10-19T14:00:01Z', ask_event_time: null,
  received_at: '2026-10-19T14:00:03Z', ...extra,
});
const chain = (extra = {}) => ({
  ok: true, ticker: 'SPY', spot: 100, expiries: [date], contracts: [contract(), contract('put')],
  fetched_at: '2026-10-19T14:00:02Z', event_time: null, data_source: 'public_api',
  exposure_by_strike: { series_version: 'triad-projection.backend.v1', formula_version: 'gex.v2',
    ticker: 'SPY', spot: 100, fetched_at: '2026-10-19T14:00:02Z',
    strikes: [{ strike: 100, gex: 50, n_measured: 1, n_total: 2, partial: true,
      gex_basis: 'OI_PARTIAL', expiries: [date] }] }, ...extra,
});
const ok = data => ({ ok: true, json: async () => data });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const flush = async () => { for (let i = 0; i < 20; i += 1) await Promise.resolve(); };
const routes = (inventory = listed(), body = chain()) => {
  global.fetch = jest.fn(async url => ok(String(url).includes('/expiries?') ? inventory : body));
};
afterEach(() => { jest.useRealTimers(); });

test('clicking the active scope leaves its pending request alive and able to finish', async () => {
  const pending = deferred();
  global.fetch = jest.fn((url) => String(url).includes('/expiries?') ? Promise.resolve(ok(listed())) : pending.promise);
  render(<TriadDesk ticker="SPY" />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
  const signal = global.fetch.mock.calls[1][1].signal;
  fireEvent.click(screen.getByRole('button', { name: '0DTE' }));
  expect(signal.aborted).toBe(false);
  await act(async () => { pending.resolve(ok(chain())); await flush(); });
  expect(screen.getByRole('table')).toBeInTheDocument();
});

test.each(['inventory', 'chain'])('%s pending read reaches a deadline and manual retry recovers', async stage => {
  jest.useFakeTimers();
  global.fetch = jest.fn(url => stage === 'inventory' || !String(url).includes('/expiries?')
    ? new Promise(() => {}) : Promise.resolve(ok(listed())));
  render(<TriadDesk ticker="SPY" />);
  await act(flush);
  expect(screen.getByRole('status')).toHaveTextContent(/Loading/);
  await act(async () => { jest.advanceTimersByTime(20001); await flush(); });
  expect(screen.getByRole('alert')).toHaveTextContent(/timed out/);
  routes();
  fireEvent.click(screen.getByRole('button', { name: /Retry/ }));
  await act(flush);
  expect(screen.getByRole('table')).toBeInTheDocument();
});

test('next scope clears a previous empty note, shows dated chain pending, and supports failed-read recovery', async () => {
  const inventory = listed('SPY', [{ expiry: '2026-10-20', dte: 1, admitted: true }]);
  const pending = deferred();
  global.fetch = jest.fn(url => String(url).includes('/expiries?') ? Promise.resolve(ok(inventory)) : pending.promise);
  render(<TriadDesk ticker="SPY" />);
  await screen.findByText(/No same-day series listed/);
  fireEvent.click(screen.getByRole('button', { name: 'Review next listed expiry' }));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(3));
  expect(screen.queryByText(/No same-day series listed/)).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent(/Loading.*2026-10-20/);
  await act(async () => { pending.resolve({ ok: false, status: 503 }); await flush(); });
  expect(screen.getByRole('alert')).toHaveTextContent(/chain HTTP 503/);
  expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument();
});

test('superseded ticker/scope reads abort, and late replies cannot replace the current scope', async () => {
  const old = deferred();
  global.fetch = jest.fn(url => {
    const u = String(url);
    if (u.includes('ticker=SPY')) return Promise.resolve(ok(listed()));
    if (u.includes('ticker=QQQ')) return Promise.resolve(ok(listed('QQQ', [])));
    return old.promise;
  });
  const ui = render(<TriadDesk ticker="SPY" />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
  const signal = global.fetch.mock.calls[1][1].signal;
  ui.rerender(<TriadDesk ticker="QQQ" />);
  await screen.findByText(/QQQ: same-day chain not verified/);
  expect(signal.aborted).toBe(true);
  await act(async () => { old.resolve(ok(chain())); await flush(); });
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.queryByText('Spot 100.00')).not.toBeInTheDocument();
});

test('next listed uses the earliest admitted date inside seven days, not range-map order or an outside date', async () => {
  routes(listed('SPY', [
    { expiry: '2026-11-01', dte: 13, admitted: true },
    { expiry: '2026-10-26', dte: 7, admitted: true },
    { expiry: '2026-10-20', dte: 1, admitted: true },
  ]));
  render(<TriadDesk ticker="SPY" />);
  await screen.findByText(/No same-day series listed/);
  fireEvent.click(screen.getByRole('button', { name: 'Next listed' }));
  await waitFor(() => expect(global.fetch.mock.calls.some(([u]) => String(u).includes('expiration=2026-10-20'))).toBe(true));
  expect(global.fetch.mock.calls.some(([u]) => String(u).includes('expiration=2026-11-01'))).toBe(false);
  expect(screen.getByText(/Listed window: 0–7 days/)).toBeInTheDocument();
});

test('strike focus requires a separate explicit exact-side contract choice; missing exposure stays unknown', async () => {
  routes(); render(<TriadDesk ticker="SPY" />);
  await screen.findByRole('table');
  fireEvent.click(screen.getByRole('button', { name: 'Review strike 100' }));
  const review = screen.getByRole('complementary', { name: 'Triad wall review' });
  expect(within(review).getByText(/No contract selected/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Review put SPY261019P00100000' }));
  expect(within(review).getByText(/SPY261019P00100000/)).toBeInTheDocument();
  expect(within(review).getByText(/unknown \(not zero\)/)).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Call Δ' })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Put Δ' })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Call spread' })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Put spread' })).toBeInTheDocument();
  expect(screen.getAllByText(/Ask observed unknown/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Receipt 2026-10-19T14:00:03Z/).length).toBeGreaterThan(0);
});

test.each([
  ['wrong expiry', { expiry: '2026-10-20' }], ['wrong ticker', { ticker: 'QQQ' }],
  ['wrong OSI root', { osi: 'QQQ261019C00100000' }], ['wrong OSI side', { osi: 'SPY261019P00100000' }],
  ['wrong OSI strike', { osi: 'SPY261019C00105000' }],
])('%s contract is withheld and cannot admit the exposure snapshot', async (_, defect) => {
  routes(listed(), chain({ contracts: [contract('call', defect)] }));
  render(<TriadDesk ticker="SPY" />);
  await screen.findByText(/Contract identity unavailable/);
  expect(screen.queryByRole('button', { name: /^Review call/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('group', { name: /Signed exposure/ })).not.toBeInTheDocument();
});

test.each([false, true])('duplicate contract rows (conflicting=%s) never choose an arbitrary quote or admit aggregate exposure', async conflicting => {
  routes(listed(), chain({ contracts: [contract(), contract('call', conflicting ? { ask: 9 } : {})] }));
  render(<TriadDesk ticker="SPY" />);
  await screen.findByText(/Contract identity unavailable/);
  expect(screen.queryByRole('button', { name: /^Review call/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('group', { name: /Signed exposure/ })).not.toBeInTheDocument();
});

test('a failed inventory is unavailable, not a no-0DTE conclusion', async () => {
  global.fetch = jest.fn(async () => ({ ok: false, status: 503 }));
  render(<TriadDesk ticker="SPY" />);
  await screen.findByRole('alert');
  expect(screen.queryByText(/No same-day series listed/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument();
});

const series = strikes => ({ strikes: strikes.map(strike => ({ strike, gex: 1,
  n_measured: 1, n_total: 1, partial: false })) });
test('irregular strikes interpolate spot between the actual adjacent displayed slots', () => {
  const { container } = render(<TriadExposure series={series([100, 105, 120])} spot={110} />);
  expect(Number(container.querySelector('[data-spot-marker] line').getAttribute('x1'))).toBeCloseTo(65 + 31 * (1 + 5 / 15));
});
test('the 21-strike window has explicit extent/navigation and reports off-window spot without extrapolating', () => {
  const { container } = render(<TriadExposure series={series(Array.from({ length: 45 }, (_, i) => 100 + i))} spot={100} />);
  expect(container.querySelectorAll('g[data-strike]')).toHaveLength(21);
  expect(screen.getByText(/Showing strikes 1–21 of 45/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Higher strikes' }));
  expect(screen.getByText(/Showing strikes 22–42 of 45/)).toBeInTheDocument();
  expect(screen.getByText(/Spot 100.00 is below this window/)).toBeInTheDocument();
  expect(container.querySelector('[data-spot-marker]')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Center on spot' }));
  expect(screen.getByText(/Showing strikes 1–21 of 45/)).toBeInTheDocument();
});
