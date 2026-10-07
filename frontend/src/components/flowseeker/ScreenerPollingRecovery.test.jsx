import React from 'react';
import {act,render,screen} from '@testing-library/react';
import FlowseekerProBlademap from './FlowseekerProBlademap';
import {clearScreenerReading} from './screenerReadingCache';
jest.mock('./MarketCoverage',()=>()=>null);
jest.mock('../heatseeker/useTickerDirectory',()=>()=>({tickers:['SPY'],status:'complete',retry:jest.fn()}));
const payload={rows:[['SPY','SPY261106C00760000','call',760,'2026-11-06',5000,1200,.22,.4,755]],source:'public-scan',stale:false,cache_age_seconds:0};
beforeEach(()=>{jest.useFakeTimers();localStorage.clear();clearScreenerReading();localStorage.setItem('th-prefs-v1',JSON.stringify({pollMs:5000}));});
afterEach(()=>{jest.useRealTimers();clearScreenerReading();});
test('actual screener automatic poll recovers after a first hung JSON body',async()=>{
 let scanReads=0,firstSignal;
 global.fetch=jest.fn(async(url,options)=>{
  if(String(url).includes('/scan?limit=')){scanReads++;if(scanReads===1){firstSignal=options.signal;return {ok:true,status:200,json:()=>new Promise(()=>{})};}return {ok:true,status:200,json:async()=>payload};}
  return {ok:true,status:200,json:async()=>({})};
 });
 const view=render(<FlowseekerProBlademap active/>);
 await act(async()=>{await Promise.resolve();});
 expect(scanReads).toBe(1);
 await act(async()=>{jest.advanceTimersByTime(20001);await Promise.resolve();});
 expect(scanReads).toBe(1);
 await act(async()=>{jest.advanceTimersByTime(5000);await Promise.resolve();});
 expect(scanReads).toBe(2);
 expect(firstSignal.aborted).toBe(true);
 const row=document.querySelector('#pulse tbody tr');
 expect(row).not.toBeNull();expect(row.textContent).toContain('SPY');
 expect(screen.queryByRole('alert')).toBeNull();
 expect(global.fetch.mock.calls.every(([,options])=>!options?.method || options.method==='GET')).toBe(true);
 view.unmount();
});
