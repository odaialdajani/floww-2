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
