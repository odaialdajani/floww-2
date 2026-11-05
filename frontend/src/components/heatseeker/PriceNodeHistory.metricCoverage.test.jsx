import React from 'react';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import axios from 'axios';
import PriceNodeHistory from './PriceNodeHistory';

jest.mock('axios',()=>({get:jest.fn()}));

const scope='SPY:day:None:False|expiries=2026-10-14|gex.v2|OI';
const frames=Array.from({length:3},(_,i)=>({time:new Date(Date.UTC(2026,9,8,14,0,i)).toISOString(),open:100+i,high:102+i,low:99+i,close:101+i,nodes:[]}));

const mockHistory=(data)=>axios.get.mockImplementation(async(url)=>({data:url.includes('/price-history/')?{ticker:'SPY',query_key:scope,frames,scopes:[scope],node_status:'available',candles_with_recorded_nodes:3,...data}:{status:'unavailable'}}));

beforeEach(()=>{axios.get.mockReset();});

const openDetails=async()=>{
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','3'));
  fireEvent.click(screen.getByRole('button',{name:'Chart data details'}));
};

test('a recorded zero metric reading is not counted as a qualified saved reading',async()=>{
  mockHistory({metric_line_coverage:{vex:{checked_candles:3,zero_candles:1},charm:{checked_candles:3,zero_candles:0}}});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await openDetails();
  expect(screen.getByText(/VEX \/ Vanna: 3 of 3 candles checked, 2 with a qualified saved reading, 1 recorded zero/)).toBeVisible();
  expect(screen.getByText(/Charm: 3 of 3 candles checked, 3 with a qualified saved reading, 0 recorded zero/)).toBeVisible();
});

test('an unknown metric key keeps its own name instead of being called Charm',async()=>{
  mockHistory({metric_line_coverage:{gamma:{checked_candles:2,zero_candles:0}}});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await openDetails();
  expect(screen.getByText(/gamma: 2 of 3 candles checked, 2 with a qualified saved reading, 0 recorded zero/)).toBeVisible();
  expect(screen.queryByText(/^Charm:/)).not.toBeInTheDocument();
});

test('an unavailable metric detail check is never reported as a measured zero',async()=>{
  mockHistory({metric_line_coverage:{vex:{checked_candles:0,zero_candles:0},charm:{checked_candles:0,zero_candles:0}},metric_details_status:'unavailable'});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await openDetails();
  expect(screen.getByText(/Saved metric-line detail check was unavailable/)).toBeVisible();
  expect(screen.getByText(/VEX \/ Vanna: 0 of 3 candles checked, 0 with a qualified saved reading, 0 recorded zero/)).toBeVisible();
});

test('no metric coverage payload means no metric claim at all',async()=>{
  mockHistory({});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await openDetails();
  expect(screen.queryByText(/candles checked/)).not.toBeInTheDocument();
});
