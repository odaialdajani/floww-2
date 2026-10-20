import React from 'react';
import {render, screen, fireEvent, within, waitFor} from '@testing-library/react';
import axios from 'axios';
import ReviewInspector from './ReviewInspector';
import WallInspector from './WallInspector';
import ExactContractReview from './ExactContractReview';
import AskFlow from './AskFlow';
import {GroundedPublicReview} from '../public/PublicHandoffReview';

jest.mock('axios', () => ({get: jest.fn()}));
const mockAsk = jest.fn();
const originalFetch = global.fetch;
jest.mock('../../agent/AgentProvider', () => ({useAgent: () => ({
  state: 'idle', context: {ticker: 'SPY'}, messages: [], turns: [],
  setOpen: jest.fn(), askQuestion: mockAsk,
})}));

const wall = {wall_id: 'raw:SPY:very-long-record-id', low: 100, high: 101,
  members: [100, 101], gross: 1200000, net: -400000, exposure_basis: 'OI',
  formula_version: 'gex.v2', oi_effective_dates: ['2026-10-16']};
const metrics = {wall_metrics: {[wall.wall_id]: {
  daddex_gross: 600000, daddex_net: -200000, daddex_usable: 3,
  daddex_missing: 1, daddex_invalid: 0,
  session_delta_volume_gross: 0, session_delta_volume_net: 0,
  session_delta_volume_usable: 2, session_delta_volume_missing: 0, session_delta_volume_invalid: 0,
}}, wall_window: {[wall.wall_id]: {window_daddex: 15000, coverage: {active_strikes: 1, member_strikes: 2}}}};

beforeEach(() => {axios.get.mockReset(); mockAsk.mockClear(); global.fetch = jest.fn();});
afterEach(() => {global.fetch = originalFetch;});

test('Now and identity stay visible while each available primary measure names gross, net and units', () => {
  render(<WallInspector wall={wall} metrics={metrics} quality={{state: 'partial', reasonCodes: ['GREEK_TIME_UNKNOWN']}}/>);
  expect(screen.getByText('Now')).toBeVisible();
  expect(screen.getByTestId('wall-identity-line')).toBeVisible();
  for (const id of ['raw', 'delta', 'voldelta']) {
    const reading = screen.getByTestId('wall-focused-'+id);
    expect(within(reading).getByText('Gross')).toBeVisible();
    expect(within(reading).getByText('Net')).toBeVisible();
    expect(reading).toHaveTextContent('USD/1% move');
  }
  expect(screen.getByTestId('wall-focused-voldelta')).toHaveTextContent('Gross$0Net$0');
  expect(screen.getByTestId('wall-focused-delta')).toHaveTextContent('1 delta missing');
  expect(screen.getByTestId('wall-focused-window')).toHaveTextContent('1/2 strikes');
  const evidence = screen.getByTestId('wall-provenance');
  expect(evidence.closest('details')).not.toHaveAttribute('open');
  expect(evidence).not.toBeVisible();
  expect(evidence).toHaveTextContent(wall.wall_id);
  expect(evidence).toHaveTextContent('GREEK_TIME_UNKNOWN');
  expect(evidence).toHaveTextContent('gex.v2');
});

test('Escape closes the nearest inspector evidence disclosure before its containing drawer', () => {
  const drawerKey = jest.fn();
  render(<div onKeyDown={drawerKey}><ReviewInspector selectionKey="s1" wall={<details open>
    <summary>Evidence</summary><button>Evidence action</button>
  </details>}/></div>);
  const summary = screen.getByText('Evidence');
  screen.getByRole('button', {name: 'Evidence action'}).focus();
  fireEvent.keyDown(document.activeElement, {key: 'Escape'});
  expect(summary.closest('details')).not.toHaveAttribute('open');
  expect(summary).toHaveFocus();
  expect(drawerKey).not.toHaveBeenCalled();
  fireEvent.keyDown(summary, {key: 'Escape'});
  expect(drawerKey).toHaveBeenCalledTimes(1);
});

test('a known zero distance does not turn a missing distance percentage into zero percent', () => {
  render(<WallInspector wall={{...wall, distance: 0, distance_pct: null}}/>);
  fireEvent.click(screen.getByText('Exposure details and coverage'));
  const distance = screen.getByText('Distance').closest('.skylit-metric-row');
  expect(distance).toHaveTextContent('0.00');
  expect(distance).toHaveTextContent('percentage unavailable');
  expect(distance).not.toHaveTextContent('0.00%');
  expect(distance).not.toHaveTextContent('NaN');
});

test('all four real inspector children mount without reads; exact selection reads once and tab switches preserve it', async () => {
  const osi = 'SPY261019C00100000';
  const data = {snapshotId: 's1', grid: {expiries: ['2026-10-19']}, scout: {shortlist: {CALLS: [
    {osi, strike: 100, expiry: '2026-10-19', type: 'call', bid: 1, ask: 1.1},
  ]}}};
  axios.get.mockResolvedValue({data: {status: 'ok', ticker: 'SPY', snapshot_id: 's1',
    matched_identity: {osi, strike: 100, expiry: '2026-10-19', type: 'call'}, quote: {bid: 1, ask: 1.1}}});
  render(<ReviewInspector selectionKey="s1" wall={<WallInspector wall={wall} metrics={metrics}/>}
    contract={<ExactContractReview ticker="SPY" data={data} wall={wall}/>}
    flow={<AskFlow/>} publicAgent={<GroundedPublicReview/>}/>);
  expect(screen.getAllByRole('tabpanel', {hidden: true})).toHaveLength(4);
  expect(axios.get).toHaveBeenCalledTimes(0);
  expect(global.fetch).toHaveBeenCalledTimes(0);
  expect(mockAsk).toHaveBeenCalledTimes(0);
  fireEvent.click(screen.getByRole('tab', {name: 'Contract'}));
  fireEvent.click(screen.getByRole('button', {name: 'Review '+osi}));
  await waitFor(() => expect(screen.getByTestId('exact-contract-result')).toBeVisible());
  expect(axios.get).toHaveBeenCalledTimes(1);
  expect(axios.get.mock.calls[0][1].params).toEqual({osi, snapshot_id: 's1'});
  fireEvent.click(screen.getByRole('tab', {name: 'Flow'}));
  const askTrigger = screen.getByRole('button', {name: 'Ask Flow'});
  fireEvent.click(askTrigger);
  expect(screen.getByRole('menu', {name: 'Ask Flow questions'})).toBeVisible();
  fireEvent.keyDown(document.activeElement, {key: 'Escape'});
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  expect(askTrigger).toHaveFocus();
  expect(screen.getByRole('tabpanel', {name: 'Flow'})).toBeVisible();
  expect(mockAsk).toHaveBeenCalledTimes(0);
  for (const name of ['Flow', 'Public agent', 'Wall', 'Contract']) fireEvent.click(screen.getByRole('tab', {name}));
  expect(screen.getByTestId('exact-contract-result')).toBeVisible();
  expect(axios.get).toHaveBeenCalledTimes(1);
  expect(global.fetch).toHaveBeenCalledTimes(0);
  expect(mockAsk).toHaveBeenCalledTimes(0);
});
