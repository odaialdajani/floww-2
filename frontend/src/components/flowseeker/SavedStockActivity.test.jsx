import React from 'react';
import {render,screen,fireEvent,waitFor,act,within} from '@testing-library/react';
import SavedStockActivity from './SavedStockActivity';
import {BUILTIN_SCREENS} from './tideFeed';

const now=Date.parse('2026-10-07T14:00:00Z');
const raw=(ticker,i=0)=>[ticker,ticker+'-contract-'+i,'call',100+i,'2026-10-16',500,100,.3,.5,100];
const key=r=>[r[0],r[2],r[3],r[4]].join('|');
const payload=(rows,{offset=0,total=rows.length,next=null}={})=>({columns:['underlying_ticker','ticker','contract_type','strike_price','expiration_date','day_volume','open_interest','implied_volatility','delta','underlying_price'],rows,count:rows.length,total,offset,limit:100,next_offset:next,status:'partial',quote_truth:{},row_observations:Object.fromEntries(rows.map(r=>[key(r),{received_at:(now-100000)/1000,volume_source_time:null,quote_source_time:null,data_status:'legacy_limited',live:false,trade_eligible:false}])),observations_by_ticker:Object.fromEntries(rows.map(r=>[r[0],{received_at:(now-100000)/1000,data_status:'legacy_limited',rows_per_ticker_cap:3,original_retained_rows:10}])),coverage:{observed_tickers:125,missing_tickers:100,legacy_limited_tickers:125,legacy_retention_ticker_limit:500,legacy_examples_per_ticker_limit:3,rows_per_ticker_cap:120,symbol_limit:20000}});
const reply=data=>({ok:true,json:async()=>data});
beforeEach(()=>{jest.spyOn(Date,'now').mockReturnValue(now);global.fetch=jest.fn();});
afterEach(()=>{jest.restoreAllMocks();});

test('all rows on both server pages remain reachable, including the last of 125 stocks',async()=>{
 const rows=Array.from({length:125},(_,i)=>raw('T'+String(i).padStart(3,'0')));
 global.fetch.mockImplementation(async url=>new URL(String(url)).searchParams.get('offset')==='100'?reply(payload(rows.slice(100),{offset:100,total:125})):reply(payload(rows.slice(0,100),{total:125,next:100})));
 render(<SavedStockActivity active screen={BUILTIN_SCREENS[0]}/>);
 await screen.findByRole('button',{name:'Open current stock T000'});
 expect(screen.getByRole('button',{name:'Load next saved group'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Last rows page'}));
 expect(screen.getByRole('button',{name:'Open current stock T099'})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Load next saved group'}));
 await screen.findByRole('button',{name:'Open current stock T100'});
 fireEvent.click(screen.getByRole('button',{name:'Last rows page'}));
 expect(screen.getByRole('button',{name:'Open current stock T124'})).toBeInTheDocument();
 expect(global.fetch).toHaveBeenCalledTimes(2);
 expect(global.fetch.mock.calls.every(([url,options])=>String(url).includes('/scan-public/observations?') && options.method==='GET')).toBe(true);
});

test('a late response for the old stock filter cannot replace the new group',async()=>{
 let old;global.fetch.mockImplementation(url=>new URL(String(url)).searchParams.get('ticker')==='SPY'?new Promise(resolve=>{old=resolve;}):Promise.resolve(reply(payload([raw('NVDA')]))));
 const view=render(<SavedStockActivity active filters={{q:'SPY'}}/>);
 await waitFor(()=>expect(old).toBeDefined());
 const oldSignal=global.fetch.mock.calls[0][1].signal;
 view.rerender(<SavedStockActivity active filters={{q:'NVDA'}}/>);
 await screen.findByRole('button',{name:'Open current stock NVDA'});
 expect(oldSignal.aborted).toBe(true);
 await act(async()=>old(reply(payload([raw('SPY')]))));
 expect(screen.queryByRole('button',{name:'Open current stock SPY'})).toBeNull();
 expect(screen.getByRole('button',{name:'Open current stock NVDA'})).toBeInTheDocument();
});

test('saved-read failure reports unavailable and never says there was no activity',async()=>{
 global.fetch.mockResolvedValue({ok:false,status:503,json:async()=>({detail:'saved unavailable'})});
 render(<SavedStockActivity active/>);
 await screen.findByRole('alert');
 expect(screen.getByRole('alert')).toHaveTextContent(/Saved activity is unavailable/);
 expect(screen.queryByText(/No activity/)).toBeNull();
});

test('unknown source clocks stay unknown, legacy limitations are visible, and opening passes only the stock',async()=>{
 const pick=jest.fn();global.fetch.mockResolvedValue(reply(payload([raw('NVDA')])));
 render(<SavedStockActivity active onPickTicker={pick}/>);
 const button=await screen.findByRole('button',{name:'Open current stock NVDA'});
 fireEvent.click(button);expect(pick).toHaveBeenCalledWith('NVDA');
 expect(pick.mock.calls[0]).toHaveLength(1);
 expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0);
 expect(screen.getByText(/receipt.*not.*market time/i)).toBeInTheDocument();
 expect(screen.getByText(/three.*example|3.*example/i)).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:/trade|order|model/i})).toBeNull();
 expect(screen.queryByRole('columnheader',{name:'IV'})).toBeNull();
});

test('returning to the tab reuses the saved page and aborts a pending request on unmount',async()=>{
 global.fetch.mockResolvedValue(reply(payload([raw('NVDA')])));
 const view=render(<SavedStockActivity active/>);
 await screen.findByRole('button',{name:'Open current stock NVDA'});
 view.rerender(<SavedStockActivity active={false}/>);
 view.rerender(<SavedStockActivity active/>);
 await screen.findByRole('button',{name:'Open current stock NVDA'});
 expect(global.fetch).toHaveBeenCalledTimes(1);
 let release;global.fetch.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
 fireEvent.click(screen.getByRole('button',{name:'Read saved pages again'}));
 await waitFor(()=>expect(release).toBeDefined());
 const signal=global.fetch.mock.calls.at(-1)[1].signal;
 view.unmount();expect(signal.aborted).toBe(true);
 await act(async()=>release(reply(payload([raw('SPY')]))));
});


test('changing the stock filter from a later group starts only the new first group',async()=>{
 const rows=Array.from({length:125},(_,i)=>raw('T'+String(i).padStart(3,'0')));
 global.fetch.mockImplementation(async url=>{
  const query=new URL(String(url)).searchParams;
  if(query.get('ticker')==='NVDA')return reply(payload([raw('NVDA')],{offset:Number(query.get('offset')),total:125}));
  return query.get('offset')==='100'?reply(payload(rows.slice(100),{offset:100,total:125})):reply(payload(rows.slice(0,100),{total:125,next:100}));
 });
 const view=render(<SavedStockActivity active/>);
 await screen.findByRole('button',{name:'Open current stock T000'});
 fireEvent.click(screen.getByRole('button',{name:'Last rows page'}));fireEvent.click(screen.getByRole('button',{name:'Load next saved group'}));
 await screen.findByRole('button',{name:'Open current stock T100'});
 view.rerender(<SavedStockActivity active filters={{q:'NVDA'}}/>);
 await screen.findByRole('button',{name:'Open current stock NVDA'});
 const changed=global.fetch.mock.calls.filter(([url])=>new URL(String(url)).searchParams.get('ticker')==='NVDA');
 expect(changed).toHaveLength(1);expect(new URL(String(changed[0][0])).searchParams.get('offset')).toBe('0');
});

test('a stalled saved read has a bounded wait and cancels its own request',async()=>{
 jest.useFakeTimers();let release;
 global.fetch.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
 const view=render(<SavedStockActivity active/>);
 try {
  await act(async()=>{jest.advanceTimersByTime(15000);});
  expect(screen.getByRole('alert')).toHaveTextContent(/Saved activity is unavailable/);
  expect(global.fetch.mock.calls[0][1].signal.aborted).toBe(true);
  await act(async()=>release(reply(payload([raw('SPY')]))));
  expect(screen.queryByRole('button',{name:'Open current stock SPY'})).toBeNull();
 } finally {view.unmount();jest.useRealTimers();}
});

test('failed re-reading keeps an earlier checked group clearly marked',async()=>{
 global.fetch.mockResolvedValueOnce(reply(payload([raw('NVDA')]))).mockResolvedValueOnce({ok:false,status:503});
 render(<SavedStockActivity active/>);
 await screen.findByRole('button',{name:'Open current stock NVDA'});
 fireEvent.click(screen.getByRole('button',{name:'Read saved pages again'}));
 await screen.findByRole('alert');
 expect(screen.getByRole('alert')).toHaveTextContent(/earlier checked saved group remains shown/);
 expect(screen.getByRole('button',{name:'Open current stock NVDA'})).toBeInTheDocument();
});
