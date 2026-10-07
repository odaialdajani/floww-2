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

test('a hung research request times out with a recoverable error',async()=>{
 // jsdom lacks AbortSignal.timeout; polyfill it with a fake-clock-driven
 // timer so the test drives the same abort the platform timeout produces.
 const realTimeoutFn=AbortSignal.timeout;
 if(typeof realTimeoutFn!=='function'){
  AbortSignal.timeout=(ms)=>{const c=new AbortController();setTimeout(()=>c.abort(),ms);return c.signal;};
 }
 jest.useFakeTimers();
 const events=[];
 global.fetch=jest.fn(async(url,opts)=>{
  if(String(url).endsWith('/session'))return reply({});
  if(String(url).endsWith('/ask'))return new Promise((_,reject)=>{
   opts.signal.addEventListener('abort',()=>reject(new DOMException('The operation was aborted.','AbortError')));
  });
  throw new Error('unexpected fetch '+url);
 });
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 try {
  let settled='pending';
  act(()=>{result.current.ask({question:'hung'}).then(v=>{settled=v;});});
  await act(async()=>{}); // flush session resolution so the hung ask (and its timer) is reached
  await act(async()=>{jest.advanceTimersByTime(46000);});
  expect(settled).toBeNull();
  expect(result.current.state).toBe('error');
  const errors=events.filter(([kind])=>kind==='error');
  expect(errors).toHaveLength(1);
  expect(String(errors[0][1]?.error||'')).toMatch(/timed out|recover/i);
 } finally {
  jest.useRealTimers();
  if(typeof realTimeoutFn!=='function')delete AbortSignal.timeout;
 }
});


test.each(['network','response','timeout'])('a failed first saved-turn read reconnects without another model request: %s',async failure=>{
 jest.useFakeTimers();const events=[];let reads=0,pending;
 global.fetch=jest.fn(async url=>{
  if(url.endsWith('/session'))return reply({});
  if(url.endsWith('/ask'))return reply({turn_id:'accepted'});
  if(++reads===1){
   if(failure==='response')return {ok:false,status:503};
   if(failure==='timeout')throw new DOMException('The operation was aborted.','AbortError');
   throw new TypeError('Temporary network loss');
  }
  return reply({turn_id:'accepted',status:'completed',text:'Recovered answer'});
 });
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 try {
  await act(async()=>{pending=result.current.ask({question:'Research once'});});
  expect(result.current.state).toBe('reconnecting');
  await act(async()=>{jest.advanceTimersByTime(1000);});
  await act(async()=>{await pending;});
  expect(result.current.state).toBe('completed');
  expect(events.filter(([kind])=>kind==='done')).toHaveLength(1);
  expect(events.filter(([kind])=>kind==='error')).toHaveLength(0);
  expect(reads).toBe(2);
  expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/ask'))).toHaveLength(1);
 } finally {act(()=>result.current.disconnect());jest.useRealTimers();}
});


test('first-read reconnect remains bounded and never resubmits research',async()=>{
 jest.useFakeTimers();const events=[];let pending;
 global.fetch=jest.fn(async url=>{
  if(url.endsWith('/session'))return reply({});
  if(url.endsWith('/ask'))return reply({turn_id:'accepted'});
  return {ok:false,status:503};
 });
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 try {
  await act(async()=>{pending=result.current.ask({question:'Research once'});});
  expect(result.current.state).toBe('reconnecting');
  for(let i=0;i<130;i++)await act(async()=>{jest.advanceTimersByTime(1000);});
  await act(async()=>{await pending;});
  expect(result.current.state).toBe('interrupted');
  expect(events.filter(([kind])=>kind==='error')).toEqual([['error',{status:'interrupted',error:'Connection lost. Reopen history to recover the saved request.'}]]);
  expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/ask'))).toHaveLength(1);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/turn/'))).toHaveLength(131);
 } finally {act(()=>result.current.disconnect());jest.useRealTimers();}
});

test('cancelling during first-read reconnect targets the accepted request once',async()=>{
 jest.useFakeTimers();const events=[];let pending;
 global.fetch=jest.fn(async url=>{
  if(url.endsWith('/session'))return reply({});
  if(url.endsWith('/ask'))return reply({turn_id:'accepted'});
  if(url.includes('/cancel/'))return reply({turn_id:'accepted',status:'cancelled'});
  throw new TypeError('Temporary network loss');
 });
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 try {
  await act(async()=>{pending=result.current.ask({question:'Research once'});});
  expect(result.current.state).toBe('reconnecting');
  await act(async()=>{await result.current.cancel();jest.advanceTimersByTime(1000);});
  await act(async()=>{await pending;});
  expect(result.current.state).toBe('cancelled');
  expect(events.filter(([kind])=>kind==='done')).toHaveLength(0);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/cancel/'))).toHaveLength(1);
  expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/ask'))).toHaveLength(1);
 } finally {act(()=>result.current.disconnect());jest.useRealTimers();}
});

test.each(['request','body'])('early cancellation with a stalled %s is bounded and observes the accepted answer once',async failure=>{
 jest.useFakeTimers();let admit,pending;const events=[];
 global.fetch=jest.fn(async url=>{
  if(url.endsWith('/session'))return reply({});
  if(url.endsWith('/ask'))return new Promise(resolve=>{admit=resolve;});
  if(url.includes('/cancel/'))return failure==='request'?new Promise(()=>{}):{ok:true,json:()=>new Promise(()=>{})};
  return reply({turn_id:'accepted-cancel',status:'completed',text:'Saved after cancellation timeout'});
 });
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 try{
  await act(async()=>{pending=result.current.ask({question:'Admit only once'});});
  expect(admit).toBeDefined();
  await act(async()=>{await result.current.cancel();});
  await act(async()=>admit(reply({turn_id:'accepted-cancel'})));
  expect(result.current.state).toBe('cancelling');
  await act(async()=>{jest.advanceTimersByTime(15001);});
  expect(result.current.state).toBe('completed');
  await act(async()=>{await pending;});
  expect(events.filter(([kind])=>kind==='done')).toEqual([['done',{turn_id:'accepted-cancel',status:'completed',text:'Saved after cancellation timeout'}]]);
  expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/ask'))).toHaveLength(1);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/cancel/'))).toHaveLength(1);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/turn/')).map(([url])=>url.split('/').pop())).toEqual(['accepted-cancel']);
 }finally{act(()=>result.current.disconnect());jest.useRealTimers();}
});

test('early cancel discovering a completed accepted request emits one admission before one final answer',async()=>{
 let admit,pending;const events=[];
 global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({})
  :url.endsWith('/ask')?new Promise(resolve=>{admit=resolve;})
  :reply({turn_id:'early-completed',status:'completed',text:'Completed before cancel'}));
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,payload)=>events.push([kind,payload])}));
 act(()=>{pending=result.current.ask({question:'Submit once',screen:{ticker:'SPY'}});});
 await waitFor(()=>expect(admit).toBeDefined());
 await act(async()=>result.current.cancel());
 await act(async()=>{admit(reply({turn_id:'early-completed'}));await pending;});
 expect(result.current.state).toBe('completed');
 expect(events.map(([kind])=>kind)).toEqual(['started','done']);
 expect(events[0][1]).toEqual({turn_id:'early-completed',screen:{ticker:'SPY'}});
 expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/ask'))).toHaveLength(1);
 expect(global.fetch.mock.calls.filter(([url])=>url.includes('/cancel/'))).toHaveLength(1);
});

test('a stopped admission cannot publish a late accepted event or answer',async()=>{
 let admit,pending;const events=[];
 global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({})
  :new Promise(resolve=>{admit=resolve;}));
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,payload)=>events.push([kind,payload])}));
 act(()=>{pending=result.current.ask({question:'Stop observing'});});
 await waitFor(()=>expect(admit).toBeDefined());
 act(()=>result.current.disconnect());
 await act(async()=>{admit(reply({turn_id:'late-accepted'}));await pending;});
 expect(result.current.state).toBe('idle');
 expect(events).toEqual([]);
});

test.each(['TimeoutError','AbortError'])('a first session %s gives a useful timeout without claiming a saved question exists',async name=>{
 const events=[];global.fetch=jest.fn(async()=>{throw new DOMException('The operation timed out.',name);});
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 await act(async()=>{await result.current.ask({question:'Explain this activity'});});
 expect(result.current.state).toBe('error');expect(events[0][1].error).toMatch(/connection timed out/i);
 expect(events[0][1].error).toMatch(/no question was sent/i);expect(global.fetch).toHaveBeenCalledTimes(1);
});


test.each([
 ['session',15000],['admission request',45000],['admission body',45000],['saved read',15000],
])('missing native timeout still bounds a stalled %s',async(stage,deadline)=>{
 const originalTimeout=AbortSignal.timeout;AbortSignal.timeout=undefined;jest.useFakeTimers();
 const events=[];let pending;
 global.fetch=jest.fn(async url=>{
  if(url.endsWith('/session'))return stage==='session'?new Promise(()=>{}):reply({});
  if(url.endsWith('/ask'))return stage==='admission request'?new Promise(()=>{}):stage==='admission body'?{ok:true,json:()=>new Promise(()=>{})}:reply({turn_id:'bounded'});
  return new Promise(()=>{});
 });
 const {result,unmount}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 try{
  act(()=>{pending=result.current.ask({question:'Bound the request'});});await act(async()=>{});
  await act(async()=>{jest.advanceTimersByTime(deadline+1);});
  if(stage==='saved read')expect(result.current.state).toBe('reconnecting');
  else{expect(result.current.state).toBe('error');expect(events[0][1].error).toMatch(/timed out/i);}
  const call=global.fetch.mock.calls.find(([url])=>stage==='session'?url.endsWith('/session'):stage==='saved read'?url.includes('/turn/'):url.endsWith('/ask'));
  expect(call[1].signal.aborted).toBe(true);
  expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/ask'))).toHaveLength(stage==='session'?0:1);
 }finally{act(()=>result.current.disconnect());unmount();jest.useRealTimers();if(originalTimeout===undefined)delete AbortSignal.timeout;else AbortSignal.timeout=originalTimeout;}
});

test('unconfirmed early cancellation followed by admission timeout warns that the saved question may finish',async()=>{
 jest.useFakeTimers();const originalTimeout=AbortSignal.timeout;
 AbortSignal.timeout=ms=>{const controller=new AbortController();setTimeout(()=>controller.abort(new DOMException('The operation timed out.','TimeoutError')),ms);return controller.signal;};
 const events=[];let pending;
 global.fetch=jest.fn(async(url,options)=>url.endsWith('/session')?reply({}):new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('The operation timed out.','TimeoutError')))));
 const {result,unmount}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 try{
  act(()=>{pending=result.current.ask({question:'Already accepted, response lost'});});await act(async()=>{});
  await act(async()=>result.current.cancel());
  await act(async()=>{jest.advanceTimersByTime(45001);});
  expect(result.current.state).toBe('error');expect(events[0][1].error).toMatch(/saved|history/i);expect(events[0][1].error).not.toMatch(/no question was sent|cancelled before/i);
  expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/ask'))).toHaveLength(1);expect(global.fetch.mock.calls.some(([url])=>url.includes('/cancel/'))).toBe(false);
 }finally{act(()=>result.current.disconnect());unmount();jest.useRealTimers();if(originalTimeout===undefined)delete AbortSignal.timeout;else AbortSignal.timeout=originalTimeout;}
});


test.each(['request','successful response body'])('an unknown admission %s failure warns to recover the saved question before retrying',async failure=>{
 const events=[];
 global.fetch=jest.fn(async url=>{
  if(url.endsWith('/session'))return reply({});
  if(failure==='request')throw new TypeError('Failed to fetch');
  return {ok:true,json:async()=>{throw new SyntaxError('Unexpected end of JSON input');}};
 });
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 await act(async()=>{await result.current.ask({question:'Server may have accepted this question'});});
 expect(result.current.state).toBe('error');expect(events[0][1].error).toMatch(/history|saved answers/i);
 expect(events[0][1].error).not.toMatch(/no question was sent|cancelled before/i);
 expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/ask'))).toHaveLength(1);
 expect(global.fetch.mock.calls).toHaveLength(2);
});

test.each([422,503])('a known %s admission rejection never claims the saved question is running',async status=>{
 const events=[];
 global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({}):{ok:false,status,json:async()=>{throw new SyntaxError('Unreadable rejection body');}});
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 await act(async()=>{await result.current.ask({question:'Rejected question'});});
 expect(events).toEqual([['error',{status:'error',error:'Research request could not start'}]]);
 expect(global.fetch.mock.calls).toHaveLength(2);
});


test.each([null,{}, {turn_id:''}, {turn_id:42}])('an accepted response without a usable saved identity retains the recovery warning: %j',async admission=>{
 const events=[];global.fetch=jest.fn(async url=>url.endsWith('/session')?reply({}):reply(admission));
 const {result}=renderHook(()=>useAgentStream({onEvent:(kind,data)=>events.push([kind,data])}));
 await act(async()=>{await result.current.ask({question:'Recover its unknown saved identity'});});
 expect(result.current.state).toBe('error');expect(events[0][1].error).toMatch(/saved answers/i);
 expect(global.fetch.mock.calls).toHaveLength(2);
});
