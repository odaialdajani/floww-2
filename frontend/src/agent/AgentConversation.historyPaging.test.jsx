
import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import AgentProvider,{useAgent} from './AgentProvider';
import AgentConversation from './AgentConversation';
import {publishScreenContext} from './useScreenContext';
jest.mock('./AgentModelSettings',()=>()=>null);
jest.mock('./AgentPanelAnswer',()=>({turn})=><p>{turn.answer?.summary || turn.text || 'Full answer unavailable'}</p>);
const id=n=>'12345678-1234-1234-1234-'+String(n).padStart(12,'0');
const summary=n=>({turn_id:id(n),ticker:'SPY',question:'Paged saved question '+n,status:'completed',horizon:'all',created_at:'2026-10-01T15:00:00Z',preview:'Preview '+n});
const response=data=>({ok:true,json:async()=>data});
function Seed(){const a=useAgent();return <button onClick={()=>a.pushTurn({turn_id:id(99),ticker:'SPY',question:'My current question',status:'completed',answer:{summary:'My current full answer'}},a.context)}>Keep my answer</button>;}
const view=()=>render(<AgentProvider><Seed/><AgentConversation/></AgentProvider>);
beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));
beforeEach(()=>{publishScreenContext({ticker:'SPY',displayMode:'live',dte:'all'});global.fetch=jest.fn();});

test('all twenty older summaries remain reachable without displacing the current answer',async()=>{
 global.fetch.mockResolvedValue(response({turns:Array.from({length:20},(_,i)=>summary(20-i)),has_more:false,next_cursor:null}));
 view();fireEvent.click(screen.getByText('Keep my answer'));fireEvent.click(screen.getByRole('button',{name:'Saved answers'}));
 await screen.findByText('Paged saved question 1');
 for(let n=1;n<=20;n++)expect(screen.getByText('Paged saved question '+n)).toBeInTheDocument();
 expect(screen.getByText('My current full answer')).toBeInTheDocument();expect(screen.getByRole('button',{name:'Latest answers'})).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Older answers'})).not.toBeInTheDocument();
});

test('older controls follow checked paging metadata and reopening a summary reads the full answer',async()=>{
 let requests=0;global.fetch.mockImplementation(async url=>String(url).includes('/turn/')?response({...summary(20),answer:{summary:'The fetched full answer'}}):response(++requests===1?{turns:[summary(40)],has_more:true,next_cursor:'older'}:{turns:[summary(20)],has_more:false,next_cursor:null}));
 view();fireEvent.click(screen.getByRole('button',{name:'Saved answers'}));fireEvent.click(await screen.findByRole('button',{name:'Older answers'}));
 await screen.findByText('Paged saved question 20');expect(screen.queryByText('Paged saved question 40')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Open full answer'}));expect(await screen.findByText('The fetched full answer')).toBeInTheDocument();
 expect(global.fetch.mock.calls.filter(([url])=>String(url).includes('/turn/'))).toHaveLength(1);
});

test('a saved-date choice writes a fully specified stock draft without sending a question',()=>{
 view();fireEvent.click(screen.getByText('Compare a saved date'));
 fireEvent.change(screen.getByLabelText('Saved date'),{target:{value:'2026-10-01'}});fireEvent.click(screen.getByRole('button',{name:'Use this date'}));
 const draft=screen.getByRole('textbox').value;expect(draft).toContain('SPY');expect(draft).toContain('2026-10-01');expect(draft).toMatch(/latest compatible saved observation/i);expect(draft).toMatch(/New York market time/i);
 expect(draft).toMatch(/missing data unknown/i);expect(draft).toMatch(/not substitute another date/i);expect(screen.getByRole('textbox')).toHaveFocus();expect(global.fetch).not.toHaveBeenCalled();
 expect(screen.getByText(/Dates use New York market time/)).toBeInTheDocument();
});

test.each([
 [{ticker:null,displayMode:'live'},/Choose one stock/i],
 [{ticker:'SPY',scope:'market',displayMode:'live'},/market-wide/i],
 [{ticker:'SPY',displayMode:'replay'},/replay/i],
 [{ticker:'SPY',displayMode:'range-replay'},/replay/i],
])('a saved-date action is unavailable for unsupported selection: %j',context=>{
 publishScreenContext(context);view();fireEvent.click(screen.getByText('Compare a saved date'));fireEvent.change(screen.getByLabelText('Saved date'),{target:{value:'2026-10-01'}});
 expect(screen.getByRole('button',{name:'Use this date'})).toBeDisabled();expect(screen.getByText(context.scope==='market'?/market-wide/i:!context.ticker?/Choose one stock/i:/Saved-date comparisons.*replay/i)).toBeInTheDocument();
 expect(screen.getByRole('textbox').value).toBe('');expect(global.fetch).not.toHaveBeenCalled();
});

test('a date draft uses the newly selected stock while the saved answer stays unchanged',()=>{
 view();fireEvent.click(screen.getByText('Keep my answer'));fireEvent.click(screen.getByText('Compare a saved date'));fireEvent.change(screen.getByLabelText('Saved date'),{target:{value:'2026-10-01'}});
 act(()=>publishScreenContext({ticker:'NVDA',displayMode:'live',dte:'all'}));fireEvent.click(screen.getByRole('button',{name:'Use this date'}));
 expect(screen.getByRole('textbox').value).toContain('For NVDA');expect(screen.getByText('My current full answer')).toBeInTheDocument();expect(global.fetch).not.toHaveBeenCalled();
});


test('Enter in the date field cannot send an existing question draft',()=>{
 view();fireEvent.change(screen.getByRole('textbox'),{target:{value:'Explain SPY now'}});fireEvent.click(screen.getByText('Compare a saved date'));
 const date=screen.getByLabelText('Saved date');fireEvent.change(date,{target:{value:'2026-10-01'}});fireEvent.keyDown(date,{key:'Enter'});
 expect(screen.getByRole('textbox').value).toBe('Explain SPY now');expect(global.fetch).not.toHaveBeenCalled();
});


function StartOwnedQuestion(){const a=useAgent();return <button onClick={()=>a.askQuestion('Explain the selected SPY reading')}>Send owned question</button>;}
test.each(['queued','running'])('a delayed same-id %s summary cannot hide or duplicate the newly completed visible answer',async earlierState=>{
 let pageReply,newReading;global.fetch.mockImplementation(async url=>String(url).endsWith('/session')?response({}):String(url).endsWith('/ask')?response({turn_id:id(98)}):String(url).includes('/history/page')?new Promise(resolve=>{pageReply=resolve;}):new Promise(resolve=>{newReading=resolve;}));
 render(<AgentProvider><StartOwnedQuestion/><AgentConversation/></AgentProvider>);fireEvent.click(screen.getByText('Send owned question'));await waitFor(()=>expect(newReading).toBeDefined());fireEvent.click(screen.getByRole('button',{name:'Saved answers'}));await waitFor(()=>expect(pageReply).toBeDefined());
 await act(async()=>newReading(response({...summary(98),answer:{summary:'New verified full answer'}})));expect(screen.getByText('New verified full answer')).toBeInTheDocument();
 await act(async()=>pageReply(response({turns:[{...summary(98),status:earlierState}],has_more:false,next_cursor:null})));
 expect(screen.getAllByText('New verified full answer')).toHaveLength(1);expect(screen.queryByText('This saved question is still in progress.')).not.toBeInTheDocument();
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(1);
});


function ParentState(){const a=useAgent();return <output data-testid="conflict-parent">{a.parentTurn?.turn_id}</output>;}
test('a conflicting terminal summary keeps the earlier current body visible once with an explicit state warning and checked-details read',async()=>{
 let checked;global.fetch.mockImplementation(async url=>String(url).includes('/turn/')?new Promise(resolve=>{checked=resolve;}):response({turns:[{...summary(99),status:'failed'}],has_more:false,next_cursor:null}));
 render(<AgentProvider><Seed/><ParentState/><AgentConversation/></AgentProvider>);fireEvent.click(screen.getByText('Keep my answer'));expect(screen.getByTestId('conflict-parent')).toHaveTextContent(id(99));fireEvent.click(screen.getByRole('button',{name:'Saved answers'}));
 expect(await screen.findByText(/latest saved state.*failed/i)).toBeInTheDocument();expect(screen.getAllByText('My current full answer')).toHaveLength(1);expect(screen.getAllByText('My current question')).toHaveLength(1);expect(screen.getByTestId('conflict-parent').textContent).toBe('');
 fireEvent.click(screen.getByRole('button',{name:'Check saved details'}));await waitFor(()=>expect(checked).toBeDefined());expect(screen.getByText('My current full answer')).toBeInTheDocument();
 await act(async()=>checked(response({...summary(99),status:'failed',error:'Confirmed stored failure'})));
 expect(screen.getByText('Confirmed stored failure')).toBeInTheDocument();expect(screen.queryByText('My current full answer')).not.toBeInTheDocument();expect(screen.getByTestId('conflict-parent').textContent).toBe('');
 expect(global.fetch.mock.calls.filter(([url])=>String(url).includes('/turn/'))).toHaveLength(1);expect(global.fetch.mock.calls.some(([url])=>String(url).endsWith('/ask'))).toBe(false);
});
