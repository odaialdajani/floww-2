/** @jest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import OptionsChainTable from './OptionsChainTable';
import { fetchPublicChain } from '../lib/publicApi';
import axios from 'axios';

jest.mock('../config/api', () => ({ API: '/api' }));
jest.mock('../lib/publicApi', () => ({ fetchPublicChain: jest.fn() }));
jest.mock('axios', () => ({ get: jest.fn() }));

const contracts = [
  { type: 'call', strike: 110, expiry: '2026-10-02', T: 1 / 365, oi: 200, moneyness_pct: -10 },
  { type: 'call', strike: 90, expiry: '2026-10-30', T: 30 / 365, oi: 500, moneyness_pct: 10 },
  { type: 'call', strike: 100, expiry: '2026-10-02', T: 7 / 365, oi: 300, moneyness_pct: 0 },
].map(c => ({ ...c, iv: 0.2, delta: 0.5, gamma: 0.1, volume: 50 }));
const response = (ticker = 'SPY', rows = contracts) => ({ ticker, spot: 100, n_contracts: rows.length, expiries: ['2026-10-02', '2026-10-30'], contracts: rows });
const strikes = container => [...container.querySelectorAll('tbody tr')].map(r => Number(r.children[1].textContent));
const select = (container, index, value) => fireEvent.change(container.querySelectorAll('select')[index], { target: { value } });
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
beforeEach(() => { jest.resetAllMocks(); fetchPublicChain.mockResolvedValue(response()); });

for (const source of ['public', 'merged']) {
  describe(`${source} chain selection`, () => {
    beforeEach(() => {
      if (source === 'merged') {
        fetchPublicChain.mockRejectedValue(new Error('unavailable'));
        const { contracts: sourceRows, ...rest } = response();
        axios.get.mockResolvedValue({ data: { ...rest, rows: sourceRows.map(({ T, ...r }) => ({ ...r, dte: Math.round(T * 365) })), count: 3 } });
      }
    });
    test.each([
      ['expiry', c => select(c, 1, '2026-10-02'), [100, 110]],
      ['minimum OI', () => fireEvent.change(screen.getByPlaceholderText('Min OI'), { target: { value: '400' } }), [90]],
      ['in the money', c => select(c, 0, 'itm'), [90]],
      ['out of the money', c => select(c, 0, 'otm'), [110]],
      ['at the money', c => select(c, 0, 'atm'), [100]],
      ['maximum DTE', () => fireEvent.change(screen.getByPlaceholderText('Max DTE'), { target: { value: '7' } }), [100, 110]],
      ['descending strike', () => fireEvent.click(screen.getByRole('button', { name: '↑' })), [110, 100, 90]],
      ['OI sort', c => select(c, 2, 'oi'), [110, 100, 90]],
    ])('%s changes visible rows', async (_name, change, expected) => {
      const { container } = render(<OptionsChainTable ticker="SPY" spot={100} />);
      await waitFor(() => expect(strikes(container)).toEqual([90, 100, 110]));
      change(container);
      expect(strikes(container)).toEqual(expected);
      expect(fetchPublicChain).toHaveBeenCalledTimes(1);
    });
  });
}

test('put moneyness reverses call moneyness, and filters combine', async () => {
  fetchPublicChain.mockResolvedValue(response('SPY', [...contracts, ...contracts.map(c => ({ ...c, type: 'put' }))]));
  const { container } = render(<OptionsChainTable ticker="SPY" spot={100} />);
  await waitFor(() => expect(strikes(container)).toHaveLength(6));
  fireEvent.click(screen.getByRole('button', { name: 'PUTS' }));
  select(container, 0, 'itm');
  select(container, 1, '2026-10-02');
  expect(strikes(container)).toEqual([110]);
  select(container, 0, 'otm');
  expect(strikes(container)).toEqual([]);
  select(container, 1, '');
  expect(strikes(container)).toEqual([90]);
});

test('ticker change immediately hides old rows and late old completion cannot replace new rows', async () => {
  const older = deferred(), newer = deferred();
  fetchPublicChain.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
  const { container, rerender } = render(<OptionsChainTable ticker="SPY" spot={100} />);
  rerender(<OptionsChainTable ticker="QQQ" spot={200} />);
  await act(async () => newer.resolve(response('QQQ', [{ ...contracts[0], strike: 220 }])));
  expect(strikes(container)).toEqual([220]);
  await act(async () => older.resolve(response()));
  expect(strikes(container)).toEqual([220]);
  expect(axios.get).not.toHaveBeenCalled();
  const third = deferred();
  fetchPublicChain.mockReturnValueOnce(third.promise);
  rerender(<OptionsChainTable ticker="IWM" spot={300} />);
  expect(strikes(container)).toEqual([]);
  await act(async () => third.resolve(response('IWM', [{ ...contracts[0], strike: 330 }])));
  expect(strikes(container)).toEqual([330]);
});

test('late public failure does not start an obsolete fallback', async () => {
  const older = deferred();
  fetchPublicChain.mockReturnValueOnce(older.promise).mockResolvedValueOnce(response('QQQ'));
  const { rerender } = render(<OptionsChainTable ticker="SPY" spot={100} />);
  rerender(<OptionsChainTable ticker="QQQ" spot={100} />);
  await act(async () => older.reject(new Error('late failure')));
  expect(axios.get).not.toHaveBeenCalled();
});

test('missing values stay unavailable and sort last in both directions', async () => {
  fetchPublicChain.mockResolvedValue(response('SPY', [{ ...contracts[0], gex: null }, { ...contracts[1], gex: 0 }, { ...contracts[2], gex: -10 }]));
  const { container } = render(<OptionsChainTable ticker="SPY" spot={100} />);
  await waitFor(() => expect(strikes(container)).toHaveLength(3));
  select(container, 2, 'gex');
  expect(strikes(container)).toEqual([100, 90, 110]);
  const cells = [...container.querySelectorAll('tbody tr')].at(-1).children;
  expect(cells[9].textContent).toBe('—');
  expect(cells[10].textContent).toBe('—');
  expect(cells[11].textContent).toBe('—');
  fireEvent.click(screen.getByRole('button', { name: '↑' }));
  expect(strikes(container)).toEqual([90, 100, 110]);
});

test('unknown OI and DTE never pass active numeric filters', async () => {
  fetchPublicChain.mockResolvedValue(response('SPY', [{ ...contracts[0], oi: null }, { ...contracts[1], T: null }]));
  const { container } = render(<OptionsChainTable ticker="SPY" spot={100} />);
  await waitFor(() => expect(strikes(container)).toEqual([90]));
  fireEvent.change(screen.getByPlaceholderText('Min OI'), { target: { value: '0' } });
  expect(strikes(container)).toEqual([90, 110]);
  fireEvent.change(screen.getByPlaceholderText('Max DTE'), { target: { value: '7' } });
  expect(strikes(container)).toEqual([110]);
});

test('both sources failing shows an error and no old ticker rows', async () => {
  const { container, rerender } = render(<OptionsChainTable ticker="SPY" spot={100} />);
  await waitFor(() => expect(strikes(container)).toHaveLength(3));
  fetchPublicChain.mockRejectedValue(new Error('public failed'));
  axios.get.mockRejectedValue(new Error('merged failed'));
  rerender(<OptionsChainTable ticker="QQQ" spot={100} />);
  await screen.findByRole('alert');
  expect(strikes(container)).toEqual([]);
});

test('ticker change resets an expiry unavailable on the new symbol', async () => {
  const { container, rerender } = render(<OptionsChainTable ticker="SPY" spot={100} />);
  await waitFor(() => expect(strikes(container)).toHaveLength(3));
  select(container, 1, '2026-10-02');
  fetchPublicChain.mockResolvedValue({ ...response('QQQ', [{ ...contracts[0], strike: 220, expiry: '2026-11-20' }]), expiries: ['2026-11-20'] });
  rerender(<OptionsChainTable ticker="QQQ" spot={220} />);
  await waitFor(() => expect(strikes(container)).toEqual([220]));
  expect(container.querySelectorAll('select')[1].value).toBe('');
});

test('near-spot highlight uses the same response spot as filtering', async () => {
  const { container } = render(<OptionsChainTable ticker="SPY" spot={110} />);
  await waitFor(() => expect(strikes(container)).toHaveLength(3));
  const rows = [...container.querySelectorAll('tbody tr')];
  expect(rows.find(r => r.children[1].textContent === '100').className).toContain('bg-slate-700/30');
  expect(rows.find(r => r.children[1].textContent === '110').className).not.toContain('bg-slate-700/30');
});
