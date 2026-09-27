import {act, renderHook, waitFor} from '@testing-library/react';
import useAgentStream from './useAgentStream';

beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));
const reply=data=>({ok:true,json:async()=>data});

test('cancel during second admission targets the new request and cannot publish it later',async()=>{
 let admitSecond;
 let count=0;
 const events=[];
 global.fetch=jest.fn(async(url)=>{
  if(url.endsWith('/session'))return reply({});
  if(url.endsWith('/ask')){count++; return count===1?reply({turn_id:'first'}):new Promise(resolve=>{admitSecond=resolve;});}
  if(url.includes('/cancel/'))return reply({turn_id:url.split('/').pop(),status:'cancelled'});
  return reply({turn_id:'first',status:'completed'});
 });
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 await act(async()=>{await result.current.ask({question:'first'});});
 let pending;
 act(()=>{pending=result.current.ask({question:'second'});});
 await waitFor(()=>expect(admitSecond).toBeDefined());
 await act(async()=>{await result.current.cancel();});
 await act(async()=>{admitSecond(reply({turn_id:'second'})); await pending;});
 const cancelled=global.fetch.mock.calls.filter(([url])=>url.includes('/cancel/')).map(([url])=>url.split('/').pop());
 expect(cancelled).toEqual(['second']);
 expect(events.filter(([kind])=>kind==='done')).toHaveLength(1);
 expect(result.current.state).toBe('cancelled');
});

test('a completed answer wins a late cancellation',async()=>{
 let resolveRead;
 global.fetch=jest.fn(async url=>{
  if(url.endsWith('/session'))return reply({});
  if(url.endsWith('/ask'))return reply({turn_id:'one'});
  if(url.includes('/cancel/'))return reply({turn_id:'one',status:'completed',answer:{summary:'Saved'}});
  return new Promise(resolve=>{resolveRead=resolve;});
 });
 const events=[];
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 let pending;
 act(()=>{pending=result.current.ask({question:'one'});});
 await waitFor(()=>expect(resolveRead).toBeDefined());
 await act(async()=>{await result.current.cancel();resolveRead(reply({status:'running'}));await pending;});
 expect(result.current.state).toBe('completed');
 expect(events.filter(([kind])=>kind==='done')).toHaveLength(1);
});


test.each([
 ['Choose at most three valid tickers'],
 ['Choose one explicit expiry scope per question'],
 ['Research for this display is unavailable; return to the live raw chart before asking'],
])('a rejected request shows its actionable validation reason: %s',async detail=>{
 const events=[];
 global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({}):{ok:false,status:422,json:async()=>({detail})});
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 await act(async()=>{await result.current.ask({question:'Explain the chosen market'});});
 expect(result.current.state).toBe('error');
 expect(events).toEqual([['error',{status:'error',error:detail}]]);
 expect(global.fetch.mock.calls.map(([url])=>url.split('/').pop())).toEqual(['session','ask']);
});


test.each([null,{detail:''},{detail:42},{detail:['not a visible string']},{detail:'x'.repeat(501)}])('malformed validation reasons retain a plain fallback: %j',async payload=>{
 const events=[];
 global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({}):{ok:false,status:422,json:async()=>payload});
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 await act(async()=>{await result.current.ask({question:'Explain SPY'});});
 expect(events[0][1].error).toBe('Research request could not start');
});

test('unreadable validation JSON and internal error text never become a broken or private alert',async()=>{
 const events=[];
 let next={ok:false,status:422,json:async()=>{throw new Error('bad JSON');}};
 global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({}):next);
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 await act(async()=>{await result.current.ask({question:'first'});});
 const json=jest.fn(async()=>({detail:'INTERNAL PRIVATE FAILURE'}));
 next={ok:false,status:500,json};
 await act(async()=>{await result.current.ask({question:'second'});});
 expect(events.map(([,data])=>data.error)).toEqual(['Research request could not start','Research request could not start']);
 expect(json).not.toHaveBeenCalled();
});

test('a delayed rejection from an older request cannot replace the new saved answer',async()=>{
 let release;
 let asks=0;
 const events=[];
 global.fetch=jest.fn(async url=>{
  if(url.endsWith('/session'))return reply({});
  if(url.endsWith('/ask'))return ++asks===1?{ok:false,status:422,json:()=>new Promise(resolve=>{release=resolve;})}:reply({turn_id:'new'});
  return reply({turn_id:'new',status:'completed',answer:{summary:'New saved answer'}});
 });
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 let old;
 act(()=>{old=result.current.ask({question:'old'});});
 await waitFor(()=>expect(release).toBeDefined());
 await act(async()=>{await result.current.ask({question:'new'});});
 await act(async()=>{release({detail:'Old rejection'});await old;});
 expect(result.current.state).toBe('completed');
 expect(events.filter(([kind])=>kind==='error')).toHaveLength(0);
 expect(events.find(([kind])=>kind==='done')[1].turn_id).toBe('new');
});


test('cancel ends a known rejected request even while its message body is stuck',async()=>{
 let release;
 const events=[];
 global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({}):{ok:false,status:422,json:()=>new Promise(resolve=>{release=resolve;})});
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 let pending;
 act(()=>{pending=result.current.ask({question:'rejected'});});
 await waitFor(()=>expect(release).toBeDefined());
 try {
  await act(async()=>{await result.current.cancel();});
  expect(result.current.state).toBe('cancelled');
  expect(global.fetch.mock.calls.find(([url])=>url.endsWith('/ask'))[1].signal.aborted).toBe(true);
 } finally {await act(async()=>{release({detail:'Late rejection'});await pending;});}
 expect(events.filter(([kind])=>kind==='done')).toHaveLength(0);
 expect(global.fetch.mock.calls.some(([url])=>url.includes('/cancel/'))).toBe(false);
});

test('a stalled validation body has a bounded wait without admitting any research',async()=>{
 jest.useFakeTimers();
 let release,pending;
 const events=[];
 const read=jest.fn(()=>new Promise(resolve=>{release=resolve;}));
 global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({}):{ok:false,status:422,json:read});
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 try {
  await act(async()=>{pending=result.current.ask({question:'rejected'});});
  expect(read).toHaveBeenCalledTimes(1);
  await act(async()=>{jest.advanceTimersByTime(3000);});
  expect(result.current.state).toBe('error');
  expect(events[0][1].error).toBe('Research request could not start');
  expect(global.fetch.mock.calls.find(([url])=>url.endsWith('/ask'))[1].signal.aborted).toBe(true);
 } finally {
  await act(async()=>{release({detail:'Late rejection'});await pending;});
  jest.useRealTimers();
 }
});
