import { openStockPanel } from '../../testUtils/openStockPanel';
import React from 'react';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import axios from 'axios';
import PriceNodeHistory from './PriceNodeHistory';
import {chartScopeFor} from './chart/scopeEcho';

jest.mock('axios',()=>({get:jest.fn()}));
const older='SPY:day:None:False|expiries=2026-10-08|gex.v2|OI';
const latest='SPY:day:None:False|expiries=2026-10-14|gex.v2|OI';
const frame={time:'2026-10-08T14:00:00Z',open:100,high:102,low:99,close:101,nodes:[]};
const requests=()=>axios.get.mock.calls.filter(([url])=>url.includes('/price-history/'));

beforeEach(()=>{
  axios.get.mockImplementation(async(url,config)=>({data:url.includes('/price-history/')?{ticker:'SPY',frames:[frame],scopes:[older,latest],query_key:config.params.query_key||latest,node_status:'available',candles_with_recorded_nodes:config.params.query_key===older?1:0}: {status:'unavailable'}}));
});

test('explicit recorder scope wins over the different request echo without client reconstruction',()=>{
  expect(chartScopeFor({scope_echo:'request',history_scope:older},false)).toBe(older);
  expect(chartScopeFor({scope_echo:'request',history_scope:older},true)).toBeNull();
});

test('a missing forced scope is explained and is never silently replaced by another view',async()=>{
  render(<PriceNodeHistory ticker="SPY" open forcedScope="request"/>);
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','1'));
  expect(screen.getByRole('button',{name:'Chart data details'})).toHaveTextContent('Saved map scope missing');
  expect(screen.getByText(/No saved readings match the map scope/)).not.toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Chart data details'}));
  expect(screen.getByText(/No saved readings match the map scope/)).toBeVisible();
  expect(requests().every(([,config])=>config.params.query_key==='request')).toBe(true);
});

test('an explicit saved-view choice is reachable even while the map owns the default scope',async()=>{
  render(<PriceNodeHistory ticker="SPY" open forcedScope="request"/>);
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','1'));
  fireEvent.click(screen.getByRole('button',{name:'Chart tools'}));
  openStockPanel('data');
  fireEvent.click(screen.getByRole('checkbox',{name:'Follow map scope'}));
  const picker=await screen.findByRole('combobox',{name:'Saved node view'});
  fireEvent.change(picker,{target:{value:older}});
  await waitFor(()=>expect(requests().at(-1)[1].params.query_key).toBe(older));
  expect(screen.getByText(/Saved-view review.*not the current map scope/)).toBeVisible();
});

test('a ticker switch never sends the previous ticker saved scope',async()=>{
  const {rerender}=render(<PriceNodeHistory ticker="SPY" open forcedScope="request"/>);
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','1'));
  fireEvent.click(screen.getByRole('button',{name:'Chart tools'}));
  openStockPanel('data');
  fireEvent.click(screen.getByRole('checkbox',{name:'Follow map scope'}));
  fireEvent.change(await screen.findByRole('combobox',{name:'Saved node view'}),{target:{value:older}});
  await waitFor(()=>expect(requests().at(-1)[1].params.query_key).toBe(older));
  axios.get.mockImplementation(async()=>({data:{ticker:'QQQ',frames:[frame],scopes:[],candles_with_recorded_nodes:0}}));
  rerender(<PriceNodeHistory ticker="QQQ" open forcedScope="QQQ-map"/>);
  await waitFor(()=>expect(requests().some(([url])=>url.endsWith('/QQQ'))).toBe(true));
  expect(requests().filter(([url])=>url.endsWith('/QQQ')).every(([,config])=>config.params.query_key==='QQQ-map')).toBe(true);
});

test('budget refusal has its own explanation without blaming missing saved observations',async()=>{
  axios.get.mockResolvedValue({data:{ticker:'SPY',frames:[],price_status:'unavailable',price_failure:{reason:'inflight_cap',retry_after_seconds:5}}});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('free provider slot'));
  expect(screen.getByRole('alert')).toHaveTextContent('5 seconds');
  expect(screen.queryByText(/No recorded nodes match/)).not.toBeInTheDocument();
});
