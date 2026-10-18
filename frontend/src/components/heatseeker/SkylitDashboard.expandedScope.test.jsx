import React from 'react';
import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import axios from 'axios';
import SkylitDashboard from './SkylitDashboard';

jest.mock('axios', () => ({get: jest.fn(), post: jest.fn()}));
jest.mock('./PriceNodeHistory', () => () => null);
jest.mock('./SavedChartReadings', () => () => null);
jest.mock('./SkylitControlBar', () => () => null);
jest.mock('./SkylitMetricsSidebar', () => () => null);
jest.mock('./SolsticeStatusStrip', () => () => null);
jest.mock('./ExposureStrip', () => () => null);
jest.mock('./ExpiryCoverage', () => () => null);
jest.mock('./ReplayStrip', () => () => null);
jest.mock('./AskFlow', () => () => null);
jest.mock('../flowseeker/AlertEngineStrip', () => () => null);

const dates=['2026-10-19','2026-10-20'];
function map(ticker='SPY', expiries=dates.slice(0,1), strikes=[100]) {
  return {ticker,spot:100,asof:'2026-10-17T14:00:00Z',strikes:strikes.map(strike=>({strike,gex:100})),
    grid:{expiries,strikes,grid:Object.fromEntries(expiries.map(expiry=>[expiry,Object.fromEntries(strikes.map(strike=>[strike,100]))]))}};
}
const desk=props=><SkylitDashboard ticker="SPY" spot={100} data={map()} defaultStudy="options" {...props}/>;
const overlay=()=>screen.getByRole('dialog',{name:'Expanded heatmap grid'});
const cells=()=>within(overlay()).queryAllByRole('gridcell');
const open=()=>fireEvent.click(screen.getByTestId('skylit-expand-btn'));
const widen=()=>fireEvent.click(screen.getByTestId('skylit-expand-widen'));

beforeEach(()=>{
  sessionStorage.clear();
  axios.get.mockImplementation(()=>Promise.resolve({data:map()}));
});
afterEach(()=>jest.restoreAllMocks());

test('a valid empty wide result replaces the previous narrow cells',async()=>{
  axios.get.mockImplementation(url=>Promise.resolve({data:String(url).includes('expiries=8')?map('SPY',[],[]):map()}));
  render(desk()); open();
  await waitFor(()=>expect(cells()).toHaveLength(1));
  widen();
  await waitFor(()=>expect(cells()).toHaveLength(0));
  await waitFor(()=>expect(overlay()).toHaveTextContent('0 expiries · 0 strikes'));
  expect(within(overlay()).getByText('No heatmap data available')).toBeInTheDocument();
});

test('the successful expansion label counts returned expiry dates rather than the requested cap',async()=>{
  axios.get.mockImplementation(url=>Promise.resolve({data:String(url).includes('expiries=8')?map('SPY',dates):map()}));
  render(desk()); open();
  await waitFor(()=>expect(cells()).toHaveLength(1));
  widen();
  await waitFor(()=>expect(cells()).toHaveLength(2));
  expect(overlay().querySelector('.skylit-expanded-coverage')).toHaveTextContent('2 expiries · 1 strikes');
  expect(overlay().querySelector('.skylit-expanded-coverage')).not.toHaveTextContent('8 expiries');
});

test('a failed widen names the original scope and retries instead of claiming a wide success',async()=>{
  let failed=true;
  axios.get.mockImplementation(url=>String(url).includes('expiries=8')&&failed
    ?Promise.reject(new Error('provider unavailable')):Promise.resolve({data:String(url).includes('expiries=8')?map('SPY',dates):map()}));
  render(desk()); open();
  await waitFor(()=>expect(cells()).toHaveLength(1));
  widen();
  const failure=await within(overlay()).findByRole('alert');
  expect(failure).toHaveTextContent(/original.*1 expiries/i);
  expect(cells()).toHaveLength(1);
  expect(overlay().querySelector('.skylit-expanded-coverage')).not.toHaveTextContent('8 expiries');
  failed=false;
  fireEvent.click(within(overlay()).getByRole('button',{name:'Retry expanded scope'}));
  await waitFor(()=>expect(cells()).toHaveLength(2));
  expect(within(overlay()).queryByRole('alert')).not.toBeInTheDocument();
});

test.each([
  ['ticker',{ticker:'QQQ',data:map('QQQ')}],
  ['mode',{timeframe:'1h'}],
  ['expiry depth',{expiries:2}],
])('a late response from the previous %s request cannot replace the current expansion',async(_name,next)=>{
  let resolveOld,oldSignal,reads=0;
  axios.get.mockImplementation((url,config)=>{
    if(!String(url).includes('/heatmap/'))return Promise.resolve({data:{}});
    reads+=1;
    if(reads===1){oldSignal=config.signal;return new Promise(resolve=>{resolveOld=resolve;});}
    return Promise.resolve({data:map(next.ticker||'SPY',dates,[101])});
  });
  const ui=render(desk()); open();
  await waitFor(()=>expect(resolveOld).toEqual(expect.any(Function)));
  ui.rerender(desk(next));
  if(!screen.queryByRole('dialog',{name:'Expanded heatmap grid'}))open();
  await waitFor(()=>expect(cells()).toHaveLength(2));
  expect(oldSignal.aborted).toBe(true);
  await act(async()=>resolveOld({data:map('SPY',dates,[199])}));
  expect(cells()).toHaveLength(2);
  expect(cells().every(cell=>cell.getAttribute('aria-label').includes('101'))).toBe(true);
});
