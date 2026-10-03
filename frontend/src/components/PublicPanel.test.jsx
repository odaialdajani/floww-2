/** @jest-environment jsdom */
import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import PublicPanel from './PublicPanel';
import inventoryFixture from '../fixtures/integration/lifecycle-inventory.v1.json';

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

const inventory = () => JSON.parse(JSON.stringify(inventoryFixture.inventory));
async function mountedPublic() {
  window.localStorage.setItem('floww_app_key', 'test-key'); mockFetchOnce();
  let ui; await act(async () => { ui = render(<PublicPanel/>); });
    fireEvent.click(screen.getByText('Local lifecycle inventory · read-only')); return ui;
}
async function readInventory(body = inventory()) {
  await mountedPublic(); global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => body });
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Read local lifecycle inventory' })));
}

test('lifecycle inventory is an explicit authenticated read, never an execution control', async () => {
  await readInventory();
  expect(global.fetch).toHaveBeenLastCalledWith('/api/public/execution-lifecycle/inventory', expect.objectContaining({ headers: { 'X-API-Key': 'test-key' }, signal: expect.anything() }));
  const review = screen.getByRole('region', { name: 'Local lifecycle review' });
  expect(review).toHaveTextContent('Account attribution unavailable');
  expect(review).toHaveTextContent('Account-wide limits UNSET');
  expect(review).toHaveTextContent('3 stored nonterminal rows');
  expect(review).toHaveTextContent('not a producer or broker clock');
  expect(review).toHaveTextContent('Store registered; restart survival unverified');
  expect(global.fetch.mock.calls.every(([,options]) => !options.method || options.method === 'GET')).toBe(true);
});

test('local UNKNOWN/native/protection/approval reports never establish safety or remote ownership', async () => {
  await readInventory(); const review = screen.getByRole('region', { name: 'Local lifecycle review' });
  expect(review).toHaveTextContent('order-unknown'); expect(review).toHaveTextContent('UNKNOWN');
  expect(review).toHaveTextContent('no-verified-protection'); expect(review).toHaveTextContent('local-swing');
  expect(review).toHaveTextContent('Local approval field present; authentication unverified');
  expect(review).toHaveTextContent('not verified remote workflows');
  expect(review).toHaveTextContent('Entry remains unavailable');
  expect(review).toHaveTextContent('not exchange-calendar enforcement');
});

test('zero storeless records do not mean the account has no orders', async () => {
  await readInventory({ ...inventory(), durable: false, storeless: true, intents: { n_known: 0, n_open: 0, n_unknown: 0, open: [], unknown: [] }, recovery: { durable_nonterminal_rows: null } });
  expect(screen.getByRole('region', { name: 'Local lifecycle review' })).toHaveTextContent('Storeless; open broker inventory unknown');
});

test.each([
  ['unsupported version', { version: 'lifecycle-inventory.v2' }, 'INVENTORY_VERSION_UNSUPPORTED'],
  ['count mismatch', { intents: { ...inventory().intents, n_unknown: 0 } }, 'INVENTORY_SHAPE_UNAVAILABLE'],
  ['unknown arm flag', { live_submission_armed: null }, 'INVENTORY_SHAPE_UNAVAILABLE'],
  ['object order identity', { intents: { ...inventory().intents, open: [{ ...inventory().intents.open[0], order_id: { unsafe: 'not-an-order-id' } }] } }, 'INVENTORY_SHAPE_UNAVAILABLE'],
  ['object native status', { native_workflows: [{ strategy: 'local-swing', venue: 'public', status: { unsafe: 'not-a-status' } }] }, 'INVENTORY_SHAPE_UNAVAILABLE'],
])('malformed lifecycle inventory refuses %s', async (_label, override, reason) => {
  await readInventory({ ...inventory(), ...override });
  expect(screen.getByRole('region', { name: 'Local lifecycle review' })).toHaveTextContent(reason);
  expect(screen.queryByRole('table', { name: 'Process-local intent records' })).not.toBeInTheDocument();
});

test('authentication rejection clears earlier local inventory instead of presenting a stale approval', async () => {
  await readInventory(); global.fetch.mockResolvedValue({ ok: false, status: 401 });
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Read local lifecycle inventory' })));
  expect(screen.getByRole('region', { name: 'Local lifecycle review' })).toHaveTextContent('APP_KEY_REJECTED');
  expect(screen.queryByText('order-unknown')).not.toBeInTheDocument();
});

test('key revocation aborts and discards a late inventory response', async () => {
  await mountedPublic(); let release;
  global.fetch.mockImplementation(() => new Promise(resolve => { release = resolve; }));
  fireEvent.click(screen.getByRole('button', { name: 'Read local lifecycle inventory' }));
  const signal = global.fetch.mock.calls.at(-1)[1].signal;
  window.localStorage.removeItem('floww_app_key');
  act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'floww_app_key', newValue: null })));
  expect(signal.aborted).toBe(true);
  await act(async () => release({ ok: true, json: async () => inventory() }));
  expect(screen.queryByText('order-unknown')).not.toBeInTheDocument();
});

test('Public unmount aborts the read without a late remount inventory', async () => {
  const ui = await mountedPublic(); let release;
  global.fetch.mockImplementation(() => new Promise(resolve => { release = resolve; }));
  fireEvent.click(screen.getByRole('button', { name: 'Read local lifecycle inventory' }));
  const signal = global.fetch.mock.calls.at(-1)[1].signal; ui.unmount(); expect(signal.aborted).toBe(true);
  await act(async () => release({ ok: true, json: async () => inventory() }));
  await mountedPublic(); expect(screen.queryByText('order-unknown')).not.toBeInTheDocument();
});

test('partial fill keeps actual filled and remaining quantities, not acknowledgment as fill',async()=>{
 window.localStorage.setItem('floww_app_key','test-key');
 mockFetchOnce(ACCOUNT,PORTFOLIO,{orders:[{order_id:'partial-1',symbol:'SPY261002C00500000',side:'BUY',quantity:3,filled_quantity:1,status:'PARTIAL'}]});
 await act(async()=>render(<PublicPanel/>));
 expect(screen.getByLabelText('Filled quantity for partial-1')).toHaveTextContent('1');
 expect(screen.getByLabelText('Remaining quantity for partial-1')).toHaveTextContent('2');
 expect(screen.getByText(/Received at .*not a broker event clock/)).toBeVisible();
 expect(screen.getByText(/Public live account reads.*no entry approval/)).toBeVisible();
});

test('account/portfolio identity conflict refuses the combined account view',async()=>{
 window.localStorage.setItem('floww_app_key','test-key');
 mockFetchOnce(ACCOUNT,{...PORTFOLIO,account_id:'OTHER-ACCOUNT'});
 await act(async()=>render(<PublicPanel/>));
 expect(screen.getByTestId('public-panel-error')).toHaveTextContent('ACCOUNT_IDENTITY_MISMATCH');
 expect(screen.queryByTestId('public-panel')).not.toBeInTheDocument();
});

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
