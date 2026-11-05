import React from 'react';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import axios from 'axios';
import PriceNodeHistory from './PriceNodeHistory';

jest.mock('axios',()=>({get:jest.fn()}));

const scope='SPY:day:None:False|expiries=2026-10-14|gex.v2|OI';
const frames=Array.from({length:70},(_,i)=>({time:new Date(Date.UTC(2026,9,8,14,0,i)).toISOString(),open:100+i,high:102+i,low:99+i,close:101+i,nodes:[]}));

const mockHistory=(data)=>axios.get.mockImplementation(async(url,config)=>({data:url.includes('/price-history/')?{ticker:'SPY',query_key:(config&&config.params&&config.params.query_key)||scope,...data}:{status:'unavailable'}}));

beforeEach(()=>{axios.get.mockReset();});

test('a failed saved-node read never reports a measured zero saved-node count',async()=>{
  mockHistory({frames,scopes:[scope],node_status:'unavailable',candles_with_recorded_nodes:0});
  render(<PriceNodeHistory ticker="SPY" open/>);
  await waitFor(()=>expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles','70'));
  const chip=screen.getByRole('button',{name:'Chart data details'});
  expect(chip).toHaveTextContent('Saved lines unavailable');
  fireEvent.click(chip);
  expect(screen.getByText(/Saved-node count is unknown for these 70 candles/)).toBeVisible();
  expect(screen.queryByText(/0 of 70 candles have saved nodes/)).not.toBeInTheDocument();
});

test('the workspace quality report keeps a failed saved-node count unknown',async()=>{
  mockHistory({frames,scopes:[scope],node_status:'unavailable',candles_with_recorded_nodes:0});
  const onQuality=jest.fn();
  render(<PriceNodeHistory ticker="SPY" open onQuality={onQuality}/>);
  await waitFor(()=>expect(onQuality.mock.calls[onQuality.mock.calls.length-1][0].status).toBe('ready'));
  const report=onQuality.mock.calls[onQuality.mock.calls.length-1][0];
  expect(report.coverage).toBe('saved-node coverage unknown for 70 candles');
  expect(report.coverage).not.toMatch(/0 of 70/);
});

test('a measured zero of saved nodes still reports the zero',async()=>{
  mockHistory({frames,scopes:[scope],node_status:'available',candles_with_recorded_nodes:0});
  const onQuality=jest.fn();
  render(<PriceNodeHistory ticker="SPY" open onQuality={onQuality}/>);
  await waitFor(()=>expect(onQuality.mock.calls[onQuality.mock.calls.length-1][0].status).toBe('ready'));
  const report=onQuality.mock.calls[onQuality.mock.calls.length-1][0];
  expect(report.coverage).toBe('0 of 70 candles carry saved nodes');
});
