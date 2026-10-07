
import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import AgentProvider,{useAgent} from './AgentProvider';
import {publishScreenContext} from './useScreenContext';
const id=n=>'12345678-1234-1234-1234-'+String(n).padStart(12,'0');
const summary=n=>({turn_id:id(n),ticker:'SPY',question:'Saved question '+n,horizon:'all',status:'completed',created_at:'2026-10-01T15:00:00Z',saved:true,preview:'Saved preview '+n});
const body=n=>({...summary(n),answer:{summary:'Full saved answer '+n,facts:[]},text:'Full saved answer '+n});
const page=(start,next_cursor=null)=>({turns:Array.from({length:20},(_,i)=>summary(start-i)),next_cursor,has_more:next_cursor!==null});
const response=data=>({ok:true,status:200,json:async()=>data});
function Probe(){const a=useAgent();return <>
 <button onClick={()=>a.pushTurn(body(99),a.context)}>Keep current answer</button>
 <button onClick={()=>a.pushTurn(body(7),a.context)}>Keep cached answer</button>
 <button onClick={a.loadHistory}>Latest page</button>
 <button onClick={()=>a.loadOlderHistory?.()}>Older page</button>
 <button onClick={()=>a.openSavedTurn?.(a.turns[0])}>Open first summary</button>
 <button onClick={()=>a.askQuestion('Explain the selected SPY reading')}>Start question</button>
 <output data-testid="page-records">{JSON.stringify(a.turns)}</output>
 <output data-testid="page-ids">{a.turns.map(turn=>turn.turn_id).join(',')}</output>
 <output data-testid="active-record">{JSON.stringify(a.activeTurn)}</output>
 <output data-testid="active-grounding">{a.answerContextStatus}</output>
 <output data-testid="active-body">{a.activeTurn?.answer?.summary || a.activeTurn?.text}</output>
 <output data-testid="parent-id">{a.parentTurn?.turn_id}</output>
 <button onClick={()=>a.askQuestion('Open screener')}>Open screener from chat</button>
 <button onClick={()=>a.askQuestion('Open NVDA chart')}>Open chart from chat</button>
 <output data-testid="pending-id">{a.pendingTurn?.turn_id}</output>
 <output data-testid="paging-more">{String(a.historyHasMore)}</output>
 <output data-testid="paging-view">{String(a.historyBrowsing)}</output>
 <output data-testid="history-busy">{String(a.historyLoading)}</output>
 <output data-testid="history-error">{a.error}</output>
</>;}
const ids=()=>screen.getByTestId('page-ids').textContent.split(',').filter(Boolean);
beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));
beforeEach(()=>{publishScreenContext({ticker:'SPY',displayMode:'live',dte:'all'});global.fetch=jest.fn();});

test('older pages replace the bounded list while the current full answer remains open',async()=>{
 global.fetch.mockImplementation(async url=>response(String(url).includes('cursor=older-20')?page(20,'older-40'):page(40,'older-20')));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));
 await act(async()=>fireEvent.click(screen.getByText('Latest page')));
 expect(ids()).toEqual(page(40).turns.map(turn=>turn.turn_id));expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 99');
 await act(async()=>fireEvent.click(screen.getByText('Older page')));
 expect(ids()).toEqual(page(20).turns.map(turn=>turn.turn_id));expect(ids()).toHaveLength(20);
 expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 99');expect(screen.getByTestId('paging-more')).toHaveTextContent('true');
 expect(global.fetch.mock.calls[0][0]).toMatch(/\/agent\/history\/page\?limit=20$/);
 expect(global.fetch.mock.calls[1][0]).toContain('cursor=older-20');
 await act(async()=>fireEvent.click(screen.getByText('Latest page')));
 expect(ids()).toEqual(page(40).turns.map(turn=>turn.turn_id));expect(global.fetch.mock.calls[2][0]).not.toContain('cursor=');
});

test('a page summary opens only after the matching full saved answer is read',async()=>{
 let openBody;global.fetch.mockImplementation(async url=>String(url).includes('/turn/')?new Promise(resolve=>{openBody=resolve;}):response(page(40,'older')));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));
 await act(async()=>fireEvent.click(screen.getByText('Latest page')));fireEvent.click(screen.getByText('Open first summary'));
 await waitFor(()=>expect(openBody).toBeDefined());expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 99');
 await act(async()=>openBody(response(body(40))));expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 40');
 expect(global.fetch.mock.calls.filter(([url])=>String(url).includes('/turn/'))).toHaveLength(1);expect(ids()).toHaveLength(20);
 expect(global.fetch.mock.calls.find(([url])=>String(url).includes('/turn/'))[1].credentials).toBe('include');
});

test('a locally cached full completion opens without another saved-body request',async()=>{
 global.fetch.mockResolvedValue(response({turns:[summary(7)],has_more:false,next_cursor:null}));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep cached answer'));
 await act(async()=>fireEvent.click(screen.getByText('Latest page')));await act(async()=>fireEvent.click(screen.getByText('Open first summary')));
 expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 7');expect(global.fetch.mock.calls.filter(([url])=>String(url).includes('/turn/'))).toHaveLength(0);
});

test.each([
 {turns:[summary(19)],has_more:true,next_cursor:null},
 {turns:[summary(19)],has_more:false,next_cursor:'unused'},
 {turns:[summary(19)],has_more:'true',next_cursor:'older'},
 {turns:[summary(19),summary(19)],has_more:false,next_cursor:null},
 {turns:Array.from({length:21},(_,i)=>summary(20-i)),has_more:false,next_cursor:null},
])('bad paging metadata retains the last checked page and does not claim completeness: %j',async invalid=>{
 let calls=0;global.fetch.mockImplementation(async()=>response(++calls===1?page(40,'older'):invalid));
 render(<AgentProvider><Probe/></AgentProvider>);await act(async()=>fireEvent.click(screen.getByText('Latest page')));
 await act(async()=>fireEvent.click(screen.getByText('Older page')));
 expect(ids()).toEqual(page(40).turns.map(turn=>turn.turn_id));expect(screen.getByTestId('history-error')).toHaveTextContent(/saved|history/i);expect(screen.getByTestId('paging-more')).toHaveTextContent('true');
});

test.each(['same cursor','overlapping page'])('an older %s cannot skip or repeat checked saved answers',async failure=>{
 let calls=0;global.fetch.mockImplementation(async()=>response(++calls===1?page(40,'older'):failure==='same cursor'?page(20,'older'):page(21,'next')));
 render(<AgentProvider><Probe/></AgentProvider>);await act(async()=>fireEvent.click(screen.getByText('Latest page')));await act(async()=>fireEvent.click(screen.getByText('Older page')));
 expect(ids()).toEqual(page(40).turns.map(turn=>turn.turn_id));expect(screen.getByTestId('history-error')).toHaveTextContent(/saved|history/i);
});

test('the last page cannot issue an older request without a valid cursor',async()=>{
 global.fetch.mockResolvedValue(response(page(20)));render(<AgentProvider><Probe/></AgentProvider>);
 await act(async()=>fireEvent.click(screen.getByText('Latest page')));await act(async()=>fireEvent.click(screen.getByText('Older page')));
 expect(global.fetch).toHaveBeenCalledTimes(1);expect(screen.getByTestId('paging-more')).toHaveTextContent('false');
});

test('hanging page bodies are bounded, overlap is blocked, and a late body cannot replace the retry',async()=>{
 jest.useFakeTimers();let oldBody;global.fetch.mockResolvedValue({ok:true,json:()=>new Promise(resolve=>{oldBody=resolve;})});
 render(<AgentProvider><Probe/></AgentProvider>);
 try{
  fireEvent.click(screen.getByText('Latest page'));fireEvent.click(screen.getByText('Latest page'));await act(async()=>{});expect(global.fetch).toHaveBeenCalledTimes(1);
  await act(async()=>jest.advanceTimersByTime(15001));expect(screen.getByTestId('history-busy')).toHaveTextContent('false');expect(global.fetch.mock.calls[0][1].signal.aborted).toBe(true);
  global.fetch.mockResolvedValue(response(page(20)));await act(async()=>fireEvent.click(screen.getByText('Latest page')));
  await act(async()=>oldBody(page(40,'older')));expect(ids()).toEqual(page(20).turns.map(turn=>turn.turn_id));
 }finally{jest.useRealTimers();}
});

test('ending the session aborts a full-body read and ignores its late private answer',async()=>{
 let openBody;global.fetch.mockImplementation(async url=>String(url).includes('/turn/')?new Promise(resolve=>{openBody=resolve;}):response(page(40,'older')));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));await act(async()=>fireEvent.click(screen.getByText('Latest page')));fireEvent.click(screen.getByText('Open first summary'));await waitFor(()=>expect(openBody).toBeDefined());
 const signal=global.fetch.mock.calls.find(([url])=>String(url).includes('/turn/'))[1].signal;
 act(()=>window.dispatchEvent(new Event('floww-research-session-ended')));expect(signal.aborted).toBe(true);
 await act(async()=>openBody(response(body(40))));expect(ids()).toHaveLength(0);expect(screen.getByTestId('active-body').textContent).toBe('');expect(screen.getByTestId('paging-view')).toHaveTextContent('false');
});

test('an unfinished admitted question remains pending while an older saved page is opened',async()=>{
 global.fetch.mockImplementation(async url=>String(url).endsWith('/session')?response({}):String(url).endsWith('/ask')?response({turn_id:id(98)}):String(url).includes('/history/page')?response(page(20)):new Promise(()=>{}));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));fireEvent.click(screen.getByText('Start question'));await waitFor(()=>expect(screen.getByTestId('pending-id')).toHaveTextContent(id(98)));
 await act(async()=>fireEvent.click(screen.getByText('Latest page')));expect(ids()).toHaveLength(20);expect(screen.getByTestId('pending-id')).toHaveTextContent(id(98));expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 99');
});


test('an old full-answer read cannot take selection or parent from a newly completed question',async()=>{
 let oldReading;global.fetch.mockImplementation(async url=>String(url).endsWith('/session')?response({}):String(url).endsWith('/ask')?response({turn_id:id(98)}):String(url).includes('/history/page')?response(page(40)):String(url).endsWith('/'+id(40))?new Promise(resolve=>{oldReading=resolve;}):response(body(98)));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));await act(async()=>fireEvent.click(screen.getByText('Latest page')));fireEvent.click(screen.getByText('Open first summary'));await waitFor(()=>expect(oldReading).toBeDefined());
 const signal=global.fetch.mock.calls.find(([url])=>String(url).endsWith('/'+id(40)))[1].signal;
 fireEvent.click(screen.getByText('Start question'));await waitFor(()=>expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 98'));
 await act(async()=>oldReading(response(body(40))));expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 98');expect(screen.getByTestId('parent-id')).toHaveTextContent(id(98));expect(signal.aborted).toBe(true);
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(1);
});

test('a new question completion keeps selection and parent when an older full read started during its work',async()=>{
 let oldReading,newReading;global.fetch.mockImplementation(async url=>String(url).endsWith('/session')?response({}):String(url).endsWith('/ask')?response({turn_id:id(98)}):String(url).includes('/history/page')?response(page(40)):new Promise(resolve=>{if(String(url).endsWith('/'+id(40)))oldReading=resolve;else newReading=resolve;}));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));await act(async()=>fireEvent.click(screen.getByText('Latest page')));fireEvent.click(screen.getByText('Start question'));await waitFor(()=>expect(newReading).toBeDefined());
 fireEvent.click(screen.getByText('Open first summary'));await waitFor(()=>expect(oldReading).toBeDefined());const signal=global.fetch.mock.calls.find(([url])=>String(url).endsWith('/'+id(40)))[1].signal;
 await act(async()=>newReading(response(body(98))));expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 98');
 await act(async()=>oldReading(response(body(40))));expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 98');expect(screen.getByTestId('parent-id')).toHaveTextContent(id(98));expect(signal.aborted).toBe(true);
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(1);
});

test('a navigation acknowledgement cannot be overwritten by an older full-answer read',async()=>{
 let oldReading;const navigate=jest.fn();global.fetch.mockImplementation(async url=>String(url).includes('/turn/')?new Promise(resolve=>{oldReading=resolve;}):response(page(40)));
 render(<AgentProvider onNavigate={navigate}><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));await act(async()=>fireEvent.click(screen.getByText('Latest page')));fireEvent.click(screen.getByText('Open first summary'));await waitFor(()=>expect(oldReading).toBeDefined());
 await act(async()=>fireEvent.click(screen.getByText('Open screener from chat')));expect(screen.getByTestId('active-body')).toHaveTextContent(/Opened.*Screener/i);
 await act(async()=>oldReading(response(body(40))));expect(screen.getByTestId('active-body')).toHaveTextContent(/Opened.*Screener/i);expect(screen.getByTestId('parent-id')).toHaveTextContent(id(99));expect(navigate).toHaveBeenCalledTimes(1);
 expect(global.fetch.mock.calls.some(([url])=>String(url).endsWith('/ask'))).toBe(false);
});


test.each([undefined,null,'legacy'])('an owned readable legacy full answer keeps unknown state and clears the previous parent: %j',async status=>{
 const older={...body(40),status};if(status===undefined)delete older.status;
 global.fetch.mockImplementation(async url=>String(url).includes('/turn/')?response(older):response({turns:[{...summary(40),status}],has_more:false,next_cursor:null}));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));expect(screen.getByTestId('parent-id')).toHaveTextContent(id(99));
 await act(async()=>fireEvent.click(screen.getByText('Latest page')));await act(async()=>fireEvent.click(screen.getByText('Open first summary')));
 expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 40');expect(screen.getByTestId('parent-id').textContent).toBe('');
 const opened=JSON.parse(screen.getByTestId('active-record').textContent);expect(opened.status).toBe(status);expect(opened.status).not.toBe('completed');expect(screen.getByTestId('active-grounding')).toHaveTextContent('unverified_history');
 expect(global.fetch.mock.calls.filter(([url])=>String(url).includes('/turn/'))).toHaveLength(1);expect(global.fetch.mock.calls.some(([url])=>String(url).endsWith('/ask'))).toBe(false);
});

test('an unknown-state legacy response without readable saved content cannot replace the current answer',async()=>{
 global.fetch.mockImplementation(async url=>String(url).includes('/turn/')?response({turn_id:id(40),status:null,answer:null,text:null}):response({turns:[{...summary(40),status:null}],has_more:false,next_cursor:null}));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));await act(async()=>fireEvent.click(screen.getByText('Latest page')));await act(async()=>fireEvent.click(screen.getByText('Open first summary')));
 expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 99');expect(screen.getByTestId('parent-id')).toHaveTextContent(id(99));expect(screen.getByTestId('history-error')).toHaveTextContent('saved answer is unavailable');
});


test('a full read started during navigation cannot overwrite the later navigation acknowledgement',async()=>{
 let verify,oldReading;const navigate=jest.fn();global.fetch.mockImplementation(async url=>String(url).includes('/market/catalog?')?new Promise(resolve=>{verify=resolve;}):String(url).includes('/turn/')?new Promise(resolve=>{oldReading=resolve;}):response(page(40)));
 render(<AgentProvider onNavigate={navigate}><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));await act(async()=>fireEvent.click(screen.getByText('Latest page')));
 fireEvent.click(screen.getByText('Open chart from chat'));await waitFor(()=>expect(verify).toBeDefined());fireEvent.click(screen.getByText('Open first summary'));await waitFor(()=>expect(oldReading).toBeDefined());
 const signal=global.fetch.mock.calls.find(([url])=>String(url).includes('/turn/'))[1].signal;
 await act(async()=>verify(response({instruments:[{symbol:'NVDA'}],has_more:false,complete_provider_catalog:true})));expect(screen.getByTestId('active-body')).toHaveTextContent(/Opened.*NVDA/);
 await act(async()=>oldReading(response(body(40))));expect(screen.getByTestId('active-body')).toHaveTextContent(/Opened.*NVDA/);expect(screen.getByTestId('parent-id')).toHaveTextContent(id(99));expect(signal.aborted).toBe(true);
 expect(navigate).toHaveBeenCalledTimes(1);expect(global.fetch.mock.calls.some(([url])=>String(url).endsWith('/ask'))).toBe(false);
});


test.each(['queued','running'])('earlier %s page metadata cannot downgrade a verified completed body with the same identity',async earlierState=>{
 let pageReply,newReading;global.fetch.mockImplementation(async url=>String(url).endsWith('/session')?response({}):String(url).endsWith('/ask')?response({turn_id:id(98)}):String(url).includes('/history/page')?new Promise(resolve=>{pageReply=resolve;}):new Promise(resolve=>{newReading=resolve;}));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Start question'));await waitFor(()=>expect(newReading).toBeDefined());fireEvent.click(screen.getByText('Latest page'));await waitFor(()=>expect(pageReply).toBeDefined());
 await act(async()=>newReading(response(body(98))));expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 98');
 await act(async()=>pageReply(response({turns:[{...summary(98),status:earlierState}],has_more:false,next_cursor:null})));
 const row=JSON.parse(screen.getByTestId('page-records').textContent)[0];expect(row.answer.summary).toBe('Full saved answer 98');expect(row.status).toBe('completed');expect(row._historySummary).toBe(false);
 expect(ids()).toEqual([id(98)]);expect(screen.getByTestId('parent-id')).toHaveTextContent(id(98));expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(1);
});

test('missing and null legacy states reuse the same actual opened body without inventing a completed state',async()=>{
 let pages=0;const legacy={...body(40)};delete legacy.status;
 global.fetch.mockImplementation(async url=>String(url).includes('/turn/')?response(legacy):response({turns:[{...summary(40),status:++pages===1?undefined:null}],has_more:false,next_cursor:null}));
 render(<AgentProvider><Probe/></AgentProvider>);await act(async()=>fireEvent.click(screen.getByText('Latest page')));await act(async()=>fireEvent.click(screen.getByText('Open first summary')));
 await act(async()=>fireEvent.click(screen.getByText('Latest page')));const row=JSON.parse(screen.getByTestId('page-records').textContent)[0];expect(row.answer.summary).toBe('Full saved answer 40');expect(row.status).not.toBe('completed');expect(row._historySummary).toBe(false);
 expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 40');expect(screen.getByTestId('parent-id').textContent).toBe('');expect(global.fetch.mock.calls.filter(([url])=>String(url).includes('/turn/'))).toHaveLength(1);
});

test('later conflicting failed metadata does not present a cached completion as a newly checked saved state',async()=>{
 global.fetch.mockResolvedValue(response({turns:[{...summary(99),status:'failed'}],has_more:false,next_cursor:null}));
 render(<AgentProvider><Probe/></AgentProvider>);fireEvent.click(screen.getByText('Keep current answer'));await act(async()=>fireEvent.click(screen.getByText('Latest page')));
 const row=JSON.parse(screen.getByTestId('page-records').textContent)[0];expect(row.status).toBe('failed');expect(row._historySummary).toBe(true);expect(screen.getByTestId('active-body')).toHaveTextContent('Full saved answer 99');expect(ids()).toEqual([id(99)]);
});
