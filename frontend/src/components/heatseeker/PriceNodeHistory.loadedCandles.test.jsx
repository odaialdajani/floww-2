import React from 'react';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import axios from 'axios';
import PriceNodeHistory from './PriceNodeHistory';

jest.mock('axios',()=>({get:jest.fn()}));

const scope='SPY:day:None:False|expiries=2026-10-14|gex.v2|OI';
const frames=Array.from({length:70},(_,i)=>({time:new Date(Date.UTC(2026,9,8,14,0,i)).toISOString(),open:100+i,high:102+i,low:99+i,close:101+i,nodes:[]}));
const requests=()=>axios.get.mock.calls.filter(([url])=>url.includes('/price-history/'));

const mockHistory=(data)=>axios.get.mockImplementation(async(url,config)=>({data:url.includes('/price-history/')?{ticker:'SPY',query_key:(config&&config.params&&config.params.query_key)||scope,...data}:{status:'unavailable'}}));

beforeEach(()=>{axios.get.mockReset();});

test('loaded price candles stay explicit when the saved lines are unavailable',async()=>{
  mockHistory({frames,scopes:[scope],node_status:'unavailable'});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','70'));
  const chip=screen.getByRole('button',{name:'Chart data details'});
  expect(chip).toHaveTextContent('70 candles loaded');
  expect(chip).toHaveTextContent('Saved lines unavailable');
  expect(chip.textContent).not.toMatch(/undefined/);
  fireEvent.click(chip);
  expect(screen.getByText(/Saved node history is currently unavailable/)).toBeVisible();
  expect(screen.getByText(/Saved-node count is unknown for these 70 candles/)).toBeVisible();
  expect(requests().length).toBeGreaterThan(0);
});

test('a missing map scope keeps the loaded candle count visible',async()=>{
  mockHistory({frames,scopes:[scope],node_status:'available',candles_with_recorded_nodes:0});
  render(<PriceNodeHistory ticker="SPY" open forcedScope="request"/>);
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','70'));
  const chip=screen.getByRole('button',{name:'Chart data details'});
  expect(chip).toHaveTextContent('70 candles loaded');
  expect(chip).toHaveTextContent('Saved map scope missing');
  fireEvent.click(chip);
  expect(screen.getByText(/No saved readings match the map scope/)).toBeVisible();
  expect(requests().every(([,config])=>config.params.query_key==='request')).toBe(true);
});

test('no loaded candles never claims a candle count',async()=>{
  mockHistory({frames:[],scopes:[scope],node_status:'unavailable'});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Retry price history'})).toBeTruthy());
  expect(screen.queryByText(/candles loaded/)).not.toBeInTheDocument();
});

test('a measured zero of saved nodes keeps its own wording',async()=>{
  mockHistory({frames,scopes:[scope],node_status:'available',candles_with_recorded_nodes:0});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','70'));
  const chip=screen.getByRole('button',{name:'Chart data details'});
  expect(chip).toHaveTextContent('0/70 saved');
  fireEvent.click(chip);
  expect(screen.getByText(/No recorded nodes match these candles/)).toBeVisible();
});

test('an unmeasured saved-node count keeps the unknown wording',async()=>{
  mockHistory({frames,scopes:[scope],node_status:'available'});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','70'));
  const chip=screen.getByRole('button',{name:'Chart data details'});
  expect(chip).toHaveTextContent('Unknown/70 saved');
  fireEvent.click(chip);
  expect(screen.getByText(/Saved-node count is unknown for these 70 candles/)).toBeVisible();
  expect(screen.queryByText(/No recorded nodes match these candles/)).not.toBeInTheDocument();
});
