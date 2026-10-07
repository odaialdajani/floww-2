import React from "react";
import {act,render,screen,fireEvent,waitFor,within} from "@testing-library/react";
import AgentProvider,{useAgent} from "./AgentProvider";
import {publishScreenContext} from "./useScreenContext";
import {rangeSelectionContext} from '../lib/rangeAnalytics';
import rangeComplete from '../fixtures/integration/range-analytics.v1/complete.json';
import rangePartial from '../fixtures/integration/range-analytics.v1/partial.json';

// The new route returns a checked bounded summary page; detail reads stay separate.
const historySummary=turn=>{const row={turn_id:turn.turn_id,status:turn.status || 'completed'};for(const key of ['ticker','question','horizon','created_at','updated_at','saved'])if(Object.prototype.hasOwnProperty.call(turn,key))row[key]=turn[key];if(typeof turn.preview==='string' || typeof turn.text==='string')row.preview=turn.preview || turn.text;return row;};
const historyPage=(turns,next_cursor=null)=>({turns:turns.map(historySummary),next_cursor,has_more:next_cursor!==null});
const savedBody=turn=>({ok:true,json:async()=>({...turn,status:turn.status || 'completed'})});
const timestampFields=turn=>Object.fromEntries(Object.entries(turn).filter(([key])=>['turn_id','created_at','updated_at'].includes(key)));
beforeAll(()=>{Object.defineProperty(globalThis,"crypto",{value:require("crypto").webcrypto,configurable:true});});
function Consumer(){const a=useAgent();return <><button onClick={()=>a.askQuestion("What changed?")}>Ask shared</button><button onClick={a.loadHistory}>Load history</button><button onClick={a.endSession}>End session</button><button onClick={()=>a.openSavedTurn(a.turns[0])}>Select saved answer</button><button onClick={a.returnToConversation}>Return current questions</button><div data-testid="error">{a.error}</div><div data-testid="notice">{a.sessionNotice}</div><div data-testid="history-count">{a.turns.length}</div><div data-testid="answer">{a.activeTurn?.text}</div><div data-testid="ticker">{a.activeTurn?.ticker}</div><div data-testid="grounding">{a.answerContextStatus}</div></>}
beforeEach(()=>{global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).endsWith("/session")?{}:String(url).endsWith("/ask")?{turn_id:"turn-one"}:{turn_id:"turn-one",status:"completed",ticker:"NVDA",text:"Saved final answer",ledger:{price:{value:178.4}}}}));});
test.each(['range-live','range-replay'])('incomplete range context refuses before any research transport: %s',async displayMode=>{
 publishScreenContext({page:'heatseeker',ticker:'SPY',displayMode,rangeRecordId:'rga1-record',rangeVersion:'range-analytics.v1'});
 render(<AgentProvider><Consumer/></AgentProvider>);
 fireEvent.click(screen.getByText('Ask shared'));
 await waitFor(()=>expect(screen.getByTestId('error')).toHaveTextContent('RANGE_RESEARCH_UNAVAILABLE'));
 expect(global.fetch).not.toHaveBeenCalled();
});

const storedRangeContext = (fixture=rangeComplete,metric='raw_oi') => rangeSelectionContext(
 fixture,metric,{strike:'590',expiry:'2026-10-26'},'replay');
const rangeReply = url => ({ok:true,json:async()=>String(url).endsWith('/session') ? {}
 : String(url).endsWith('/ask') ? {turn_id:'range-turn'}
 : {turn_id:'range-turn',status:'completed',ticker:'SPY',text:'Saved range research',contract:null,executable:false}});

test.each(['raw_oi','delta_weighted','volume'])('stored %s research is explicit, frozen and uses canonical range horizon only',async metric=>{
 const context=storedRangeContext(rangePartial,metric);context.dte='14–60';
 publishScreenContext(context);let release;
 global.fetch=jest.fn(url=>String(url).endsWith('/session') ? new Promise(resolve=>{release=resolve;}) : Promise.resolve(rangeReply(url)));
 render(<AgentProvider><Consumer/></AgentProvider>);expect(global.fetch).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('Ask shared'));
 act(()=>publishScreenContext({...context,selectedStrike:600}));
 expect(global.fetch).toHaveBeenCalledTimes(1);
 await act(async()=>release(rangeReply('/session')));
 await waitFor(()=>expect(screen.getByTestId('answer')).toHaveTextContent('Saved range research'));
 const askCall=global.fetch.mock.calls.find(([url])=>String(url).endsWith('/ask'));
 const payload=JSON.parse(askCall[1].body);
 expect(payload.horizon).toBe('range:14:60');expect(payload.screen).toEqual(context);
 expect(payload.screen.activePane).toBe('gex');expect(payload.screen.selectedStrike).toBe(590);
 expect(payload.screen.selectedContract).toBeNull();expect(payload.screen.selectedWall).toBeNull();
 expect(askCall[1].credentials).toBe('include');
 expect(screen.getByTestId('grounding')).toHaveTextContent('previous_selection');
 expect(screen.getByTestId('notice')).toHaveTextContent(/research only.*pending/i);
 expect(screen.getByTestId('notice')).toHaveTextContent(/native draft/i);
 const calls=global.fetch.mock.calls.length;
 act(()=>publishScreenContext({...context,selectedStrike:null,selectedExpiry:null}));
 expect(global.fetch).toHaveBeenCalledTimes(calls);expect(screen.getByTestId('answer')).toHaveTextContent('Saved range research');
 fireEvent.click(screen.getByText('Ask shared'));
 await waitFor(()=>expect(screen.getByTestId('error')).toHaveTextContent('RANGE_SELECTION_MISMATCH'));
 expect(global.fetch).toHaveBeenCalledTimes(calls);
});
test.each([
 ['live',c=>{c.displayMode='range-live';}],
 ['digest mismatch',c=>{c.rangeDigest='0'.repeat(64);}],
 ['missing snapshot',c=>{c.snapshotId=null;}],
 ['missing axes',c=>{c.mapStrikes=[];}],
 ['unavailable window',c=>{c.rangeMetric='window';c.overlayMetric='window';c.rangeBasis='VOLUME_WINDOW';c.rangeStatus='unavailable';}],
 ['invented contract',c=>{c.selectedContract={osi:'SPY-fake'};}],
 ['invented wall',c=>{c.selectedWall='classified-wall';}],
])('global range guard refuses %s before session/model/read requests',async(_,change)=>{
 const context=storedRangeContext();change(context);publishScreenContext(context);
 render(<AgentProvider><Consumer/></AgentProvider>);fireEvent.click(screen.getByText('Ask shared'));
 await waitFor(()=>expect(screen.getByTestId('error')).toHaveTextContent('RANGE_RESEARCH_UNAVAILABLE'));
 expect(global.fetch).not.toHaveBeenCalled();
});
test('backend range refusal cannot trigger a legacy/live fallback or a new model request',async()=>{
 publishScreenContext(storedRangeContext());
 global.fetch=jest.fn(async url=>String(url).endsWith('/session') ? rangeReply(url)
 : {ok:false,status:422,json:async()=>({detail:'RANGE_DIGEST_MISMATCH'})});
 render(<AgentProvider><Consumer/></AgentProvider>);fireEvent.click(screen.getByText('Ask shared'));
 await waitFor(()=>expect(screen.getByTestId('error')).toHaveTextContent('RANGE_DIGEST_MISMATCH'));
 expect(global.fetch).toHaveBeenCalledTimes(2);
 expect(global.fetch.mock.calls.every(([url])=>/\/agent\/(session|ask)$/.test(String(url)))).toBe(true);
 act(()=>publishScreenContext({...storedRangeContext(),selectedStrike:600}));expect(global.fetch).toHaveBeenCalledTimes(2);
});

test('recovered range history has unverified grounding and never binds itself to the new selected record',async()=>{
 publishScreenContext(storedRangeContext());const saved={turn_id:'history-range',ticker:'SPY',status:'completed',text:'Historical range answer'};
 global.fetch=jest.fn(async url=>String(url).includes('/turn/')?savedBody(saved):{ok:true,json:async()=>historyPage([saved])});
 render(<AgentProvider><Consumer/></AgentProvider>);fireEvent.click(screen.getByText('Load history'));
 await waitFor(()=>expect(screen.getByTestId('history-count')).toHaveTextContent('1'));
 await act(async()=>fireEvent.click(screen.getByText('Select saved answer')));
 expect(screen.getByTestId('answer')).toHaveTextContent('Historical range answer');expect(screen.getByTestId('grounding')).toHaveTextContent('unverified_history');
 act(()=>publishScreenContext(storedRangeContext(rangePartial)));
 expect(screen.getByTestId('grounding')).toHaveTextContent('unverified_history');expect(global.fetch).toHaveBeenCalledTimes(2);
 expect(global.fetch.mock.calls.every(([url])=>/history\/page|\/turn\//.test(String(url)))).toBe(true);
});


test("shared request freezes screen and stores final service answer",async()=>{
 publishScreenContext({page:"flowseeker-pro",ticker:"NVDA",dte:"all",selectedContract:"NVDA-test",observedAt:"2026-09-11T15:00:00Z"});
 render(<AgentProvider><Consumer/></AgentProvider>);
 fireEvent.click(screen.getByText("Ask shared"));
 await waitFor(()=>expect(screen.getByTestId("answer").textContent).toBe("Saved final answer"));
 act(()=>publishScreenContext({page:"heatseeker",ticker:"SPY",dte:"week"}));
 expect(screen.getByTestId("ticker").textContent).toBe("NVDA");
 const call=global.fetch.mock.calls.find(([url])=>String(url).endsWith("/ask"));
 expect(JSON.parse(call[1].body).screen.selectedContract).toBe("NVDA-test");
 expect(call[1].credentials).toBe("include");
});

test.each([
 {ticker:"QQQ"}, {page:"trinity"}, {snapshotId:"record-two"}, {selectedExpiry:"2026-10-09"},
 {selectedWall:{id:"wall-two",lower:601,upper:602}}, {overlayMetric:"session_delta_volume"},
 {selectedContract:{osi:"SPY261009C00600000"}}, {confirmationEvidence:["touch-two"]}, {displayMode:"replay"},
])("a material selection change labels the old answer without invoking another model: %j",async change=>{
 const selection={page:"heatseeker",ticker:"SPY",dte:"all",snapshotId:"record-one",selectedExpiry:"2026-10-02",
  selectedWall:{id:"wall-one",lower:600,upper:601},overlayMetric:"raw",selectedContract:null,
  confirmationEvidence:[],displayMode:"live"};
 publishScreenContext(selection);
 render(<AgentProvider><Consumer/></AgentProvider>);
 fireEvent.click(screen.getByText("Ask shared"));
 await waitFor(()=>expect(screen.getByTestId("answer").textContent).toBe("Saved final answer"));
 expect(screen.getByTestId("grounding").textContent).toBe("current");
 const calls=global.fetch.mock.calls.length;
 act(()=>publishScreenContext({...selection,...change}));
 expect(screen.getByTestId("grounding").textContent).toBe("previous_selection");
 expect(screen.getByTestId("answer").textContent).toBe("Saved final answer");
 expect(global.fetch).toHaveBeenCalledTimes(calls);
});

test("equivalent selection object order does not invalidate a grounded answer",async()=>{
 publishScreenContext({ticker:"SPY",selectedWall:{lower:600,upper:601,id:"wall"}});
 render(<AgentProvider><Consumer/></AgentProvider>);
 fireEvent.click(screen.getByText("Ask shared"));
 await waitFor(()=>expect(screen.getByTestId("answer").textContent).toBe("Saved final answer"));
 act(()=>publishScreenContext({selectedWall:{id:"wall",upper:601,lower:600},ticker:"SPY"}));
 expect(screen.getByTestId("grounding").textContent).toBe("current");
});

test("ending research clears private views and ignores an older history response",async()=>{
 publishScreenContext({ticker:"NVDA",dte:"all"});
 render(<AgentProvider><Consumer/></AgentProvider>);
 fireEvent.click(screen.getByText("Ask shared"));
 await waitFor(()=>expect(screen.getByTestId("answer").textContent).toBe("Saved final answer"));
 let release;
 global.fetch.mockImplementation(async url=>String(url).includes("/agent/history/page?")?await new Promise(resolve=>{release=resolve;}):{ok:true,json:async()=>({status:"signed-out"})});
 fireEvent.click(screen.getByText("Load history"));
 fireEvent.click(screen.getByText("End session"));
 await waitFor(()=>expect(screen.getByTestId("notice").textContent).toMatch(/session ended/));
 expect(screen.getByTestId("answer").textContent).toBe("");
 await act(async()=>release({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[{turn_id:"old",text:"Private"}]})}));
 expect(screen.getByTestId("history-count").textContent).toBe("0");
 const call=global.fetch.mock.calls.find(([url])=>String(url).endsWith("/session/logout"));
 expect(call[1]).toMatchObject({method:"POST",credentials:"include"});
});

test("failed session ending preserves the answer and reports that it is unconfirmed",async()=>{
 publishScreenContext({ticker:"NVDA",dte:"all"});
 render(<AgentProvider><Consumer/></AgentProvider>);
 fireEvent.click(screen.getByText("Ask shared"));
 await waitFor(()=>expect(screen.getByTestId("answer").textContent).toBe("Saved final answer"));
 global.fetch.mockResolvedValue({ok:false,status:503});
 fireEvent.click(screen.getByText("End session"));
 await waitFor(()=>expect(screen.getByTestId("error").textContent).toMatch(/could not be confirmed/));
 expect(screen.getByTestId("answer").textContent).toBe("Saved final answer");
 expect(screen.getByTestId("notice").textContent).toBe("");
});

test("another open research view drops private answers and late history after session end",async()=>{
 publishScreenContext({ticker:"NVDA",dte:"all"});
 render(<><section data-testid="first"><AgentProvider><Consumer/></AgentProvider></section><section data-testid="second"><AgentProvider><Consumer/></AgentProvider></section></>);
 const first=within(screen.getByTestId("first")),second=within(screen.getByTestId("second"));
 fireEvent.click(second.getByText("Ask shared"));
 await waitFor(()=>expect(second.getByTestId("answer").textContent).toBe("Saved final answer"));
 let release;
 global.fetch.mockImplementation(async url=>String(url).includes("/agent/history/page?")?await new Promise(resolve=>{release=resolve;}):{ok:true,json:async()=>({})});
 fireEvent.click(second.getByText("Load history"));
 fireEvent.click(first.getByText("End session"));
 await waitFor(()=>expect(second.getByTestId("answer").textContent).toBe(""));
 await act(async()=>release({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[{turn_id:"late-private"}]})}));
 expect(second.getByTestId("history-count").textContent).toBe("0");
 expect(second.getByTestId("notice").textContent).toMatch(/session ended/);
 act(()=>window.dispatchEvent(new StorageEvent("storage",{key:"floww-research-session-ended",newValue:"another-tab"})));
 expect(second.getByTestId("answer").textContent).toBe("");
});



test('a delayed history page retains the new completed answer and its local question exactly once',async()=>{
 publishScreenContext({ticker:'NVDA'});let release;const usual=global.fetch.getMockImplementation();
 global.fetch.mockImplementation(url=>String(url).includes('/agent/history/page?')?new Promise(resolve=>{release=resolve;}):usual(url));
 render(<AgentProvider><Consumer/></AgentProvider>);fireEvent.click(screen.getByText('Load history'));fireEvent.click(screen.getByText('Ask shared'));
 await waitFor(()=>expect(screen.getByTestId('answer')).toHaveTextContent('Saved final answer'));
 await act(async()=>release({ok:true,json:async()=>historyPage([{turn_id:'old',text:'Old saved answer'}])}));
 expect(screen.getByTestId('history-count')).toHaveTextContent('1');expect(screen.getByTestId('answer')).toHaveTextContent('Saved final answer');
 fireEvent.click(screen.getByText('Return current questions'));expect(screen.getByTestId('history-count')).toHaveTextContent('1');
 expect(screen.getByTestId('answer')).toHaveTextContent('Saved final answer');
 global.fetch.mockResolvedValue({ok:true,json:async()=>historyPage([{turn_id:'turn-one',text:'Stale version'},{turn_id:'old',text:'Old saved answer'}])});
 await act(async()=>fireEvent.click(screen.getByText('Load history')));expect(screen.getByTestId('history-count')).toHaveTextContent('2');
 const calls=global.fetch.mock.calls.length;await act(async()=>fireEvent.click(screen.getByText('Select saved answer')));
 expect(screen.getByTestId('answer')).toHaveTextContent('Saved final answer');expect(screen.getByTestId('grounding')).toHaveTextContent('current');expect(global.fetch).toHaveBeenCalledTimes(calls);
});


test('out-of-order timed-out history replies cannot replace the newest history',async()=>{
 jest.useFakeTimers();publishScreenContext({ticker:'NVDA'});const replies=[];
 global.fetch=jest.fn(url=>String(url).includes("/turn/")?Promise.resolve(savedBody({turn_id:"new-history",text:"Newest history"})):new Promise(resolve=>replies.push(resolve)));
 render(<AgentProvider><Consumer/></AgentProvider>);
 try{
  fireEvent.click(screen.getByText('Load history'));fireEvent.click(screen.getByText('Load history'));
  expect(global.fetch).toHaveBeenCalledTimes(1);
  await act(async()=>{jest.advanceTimersByTime(15001);});
  expect(global.fetch.mock.calls[0][1].signal.aborted).toBe(true);
  fireEvent.click(screen.getByText('Load history'));
  await act(async()=>replies[1]({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[{turn_id:'new-history',text:'Newest history'}]})}));
  await act(async()=>replies[0]({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[{turn_id:'old-history',text:'Outdated history'}]})}));
  await act(async()=>fireEvent.click(screen.getByText('Select saved answer')));
  expect(screen.getByTestId('answer')).toHaveTextContent('Newest history');
  expect(screen.getByTestId('grounding')).toHaveTextContent('unverified_history');
 }finally{jest.useRealTimers();}
});



test('a corrupt repeated-id history page keeps the current completed question exactly once',async()=>{
 publishScreenContext({ticker:'NVDA'});render(<AgentProvider><Consumer/></AgentProvider>);fireEvent.click(screen.getByText('Ask shared'));
 await waitFor(()=>expect(screen.getByTestId('answer')).toHaveTextContent('Saved final answer'));
 global.fetch.mockResolvedValue({ok:true,json:async()=>historyPage([{turn_id:'turn-one',text:'Stale answer'},{turn_id:'turn-one',text:'Duplicate answer'}])});
 await act(async()=>fireEvent.click(screen.getByText('Load history')));
 expect(screen.getByTestId('history-count')).toHaveTextContent('1');expect(screen.getByTestId('answer')).toHaveTextContent('Saved final answer');expect(screen.getByTestId('error')).toHaveTextContent('Saved history is unavailable');
 const calls=global.fetch.mock.calls.length;await act(async()=>fireEvent.click(screen.getByText('Select saved answer')));
 expect(screen.getByTestId('answer')).toHaveTextContent('Saved final answer');expect(global.fetch).toHaveBeenCalledTimes(calls);
});


test('a late failure from an older timed-out history request cannot replace newer success',async()=>{
 jest.useFakeTimers();publishScreenContext({ticker:'NVDA'});const replies=[];
 global.fetch=jest.fn(url=>String(url).includes("/turn/")?Promise.resolve(savedBody({turn_id:"new-history",text:"Newest history"})):new Promise(resolve=>replies.push(resolve)));
 render(<AgentProvider><Consumer/></AgentProvider>);
 try{
  fireEvent.click(screen.getByText('Load history'));fireEvent.click(screen.getByText('Load history'));
  expect(global.fetch).toHaveBeenCalledTimes(1);
  await act(async()=>{jest.advanceTimersByTime(15001);});
  expect(global.fetch.mock.calls[0][1].signal.aborted).toBe(true);
  fireEvent.click(screen.getByText('Load history'));
  await act(async()=>replies[1]({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[{turn_id:'new-history',text:'Newest history'}]})}));
  await act(async()=>replies[0]({ok:false,status:503}));
  expect(screen.getByTestId('error').textContent).toBe('');
  await act(async()=>fireEvent.click(screen.getByText('Select saved answer')));
  expect(screen.getByTestId('answer')).toHaveTextContent('Newest history');
 }finally{jest.useRealTimers();}
});

function PopulatedHistory(){
 const a=useAgent();
 return <><button onClick={()=>{for(let i=0;i<20;i++)a.pushTurn({turn_id:'local-'+i,ticker:'SPY',status:'completed',text:'Local final '+i,created_at:'2026-10-06T12:00:'+String(i).padStart(2,'0')+'Z'},a.context);}}>Seed local answers</button><button onClick={a.loadHistory}>Reload saved answers</button><button onClick={a.loadOlderHistory}>Load older saved answers</button><button onClick={a.returnToConversation}>Return local answers</button><div data-testid="saved-order">{a.turns.map(turn=>turn.turn_id).join(',')}</div><div data-testid="saved-text">{a.turns.map(turn=>turn.text).join('|')}</div></>;
}


test('newer server answers remain discoverable after twenty grounded local completions and older local questions remain reachable',async()=>{
 publishScreenContext({ticker:'SPY'});
 const locals=Array.from({length:20},(_,i)=>({turn_id:'local-'+i,ticker:'SPY',status:'completed',created_at:'2026-10-06T12:00:'+String(i).padStart(2,'0')+'Z',text:'Server text '+i}));
 const latest=[{turn_id:'other-tab-new',status:'completed',created_at:'2026-10-06T13:00:00Z',text:'New answer from another tab'},...locals.slice(1).reverse().map(turn=>turn.turn_id==='local-19'?{...turn,text:'Outdated duplicate'}:turn)];
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).includes('cursor=local-zero')?historyPage([locals[0]]):historyPage(latest,'local-zero')}));
 render(<AgentProvider><PopulatedHistory/></AgentProvider>);fireEvent.click(screen.getByText('Seed local answers'));await act(async()=>fireEvent.click(screen.getByText('Reload saved answers')));
 const ids=screen.getByTestId('saved-order').textContent.split(',');expect(ids).toHaveLength(20);expect(ids[0]).toBe('other-tab-new');expect(ids[1]).toBe('local-19');expect(ids).not.toContain('local-0');
 expect(screen.getByTestId('saved-text')).toHaveTextContent('Local final 19');expect(screen.getByTestId('saved-text')).not.toHaveTextContent('Outdated duplicate');
 await act(async()=>fireEvent.click(screen.getByText('Load older saved answers')));expect(screen.getByTestId('saved-order').textContent).toBe('local-0');expect(screen.getByTestId('saved-text')).toHaveTextContent('Local final 0');
 fireEvent.click(screen.getByText('Return local answers'));expect(screen.getByTestId('saved-order').textContent.split(',')).toHaveLength(20);expect(screen.getByTestId('saved-order')).toHaveTextContent('local-0');
});


function TimestampHistory(){const a=useAgent();return <><button onClick={a.loadHistory}>Read timestamp history</button><div data-testid="timestamp-order">{a.turns.map(turn=>turn.turn_id).join(',')}</div><div data-testid="timestamp-records">{JSON.stringify(a.turns.map(timestampFields))}</div><div data-testid="legacy-records">{JSON.stringify(a.turns.filter(turn=>turn.turn_id.startsWith('legacy')).map(timestampFields))}</div></>;}


test('server-ordered saved history preserves actual creation fields, legacy update fallback and stable ties without invented dates',async()=>{
 publishScreenContext({ticker:'SPY'});
 const supplied=[{turn_id:'old',created_at:'2026-10-06T13:00:00Z'},{turn_id:'tie-a',created_at:'2026-10-06T14:00:00+00:00'},{turn_id:'updated-fallback',created_at:'invalid',updated_at:'2026-10-06T15:00:00Z'},{turn_id:'tie-b',created_at:'2026-10-06T14:00:00Z'},{turn_id:'legacy-a'},{turn_id:'legacy-b',created_at:null}];
 const serverPage=[supplied[2],supplied[1],supplied[3],supplied[0],supplied[4],supplied[5]];
 global.fetch=jest.fn(async()=>({ok:true,json:async()=>historyPage(serverPage)}));render(<AgentProvider><TimestampHistory/></AgentProvider>);
 await act(async()=>fireEvent.click(screen.getByText('Read timestamp history')));expect(screen.getByTestId('timestamp-order')).toHaveTextContent('updated-fallback,tie-a,tie-b,old,legacy-a,legacy-b');
 expect(JSON.parse(screen.getByTestId('timestamp-records').textContent)).toEqual(serverPage);expect(JSON.parse(screen.getByTestId('legacy-records').textContent)).toEqual(supplied.slice(-2));
});


function DraftAdmissionControls(){
 const a=useAgent();
 return <>
  <button onClick={()=>a.setQuestion('Repeated question')}>Write submitted draft</button>
  <button onClick={()=>{a.setQuestion('Other typing');a.setQuestion('Repeated question');}}>Write a newer same-text draft</button>
  <button onClick={()=>a.askQuestion(a.question)}>Submit current draft</button>
  <button onClick={a.cancel}>Cancel admission</button>
  <div data-testid="remaining-draft">{a.question}</div>
  <div data-testid="admitted-answer">{a.activeTurn?.text}</div>
  <div data-testid="admitted-count">{a.turns.length}</div>
 </>;
}

test.each([false,true])('early cancellation that discovers a completed answer consumes only its owning draft: newer=%s',async newer=>{
 publishScreenContext({ticker:'SPY'});let admit;
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true}
  :String(url).endsWith('/ask')?new Promise(resolve=>{admit=resolve;})
  :{ok:true,json:async()=>({turn_id:'early-completed',status:'completed',text:'Completed before cancel'})});
 render(<AgentProvider><DraftAdmissionControls/></AgentProvider>);
 fireEvent.click(screen.getByText('Write submitted draft'));
 fireEvent.click(screen.getByText('Submit current draft'));
 await waitFor(()=>expect(admit).toBeDefined());
 await act(async()=>fireEvent.click(screen.getByText('Cancel admission')));
 if(newer)fireEvent.click(screen.getByText('Write a newer same-text draft'));
 await act(async()=>admit({ok:true,json:async()=>({turn_id:'early-completed'})}));
 await waitFor(()=>expect(screen.getByTestId('admitted-answer')).toHaveTextContent('Completed before cancel'));
 expect(screen.getByTestId('admitted-count')).toHaveTextContent('1');
 expect(screen.getByTestId('remaining-draft').textContent).toBe(newer?'Repeated question':'');
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(1);
 expect(global.fetch.mock.calls.filter(([url])=>String(url).includes('/cancel/'))).toHaveLength(1);
});

function LegacyUtcHistory(){
 const a=useAgent();
 return <><button onClick={()=>{for(let i=0;i<20;i++)a.pushTurn({turn_id:'legacy-local-'+i,status:'completed',text:'Local '+i,created_at:'2026-03-08T02:45:'+String(i).padStart(2,'0')},a.context);}}>Seed legacy UTC answers</button><button onClick={a.loadHistory}>Read legacy UTC history</button><button onClick={a.loadOlderHistory}>Read older UTC answers</button><button onClick={a.returnToConversation}>Return local UTC answers</button><div data-testid="legacy-utc-order">{a.turns.map(turn=>turn.turn_id).join(',')}</div><div data-testid="legacy-utc-records">{JSON.stringify(a.turns.map(timestampFields))}</div></>;
}


test('zone-free saved UTC dates retain the checked server order and older local answers through New York spring time change',async()=>{
 expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe('America/New_York');publishScreenContext({ticker:'SPY'});
 const locals=Array.from({length:20},(_,i)=>({turn_id:'legacy-local-'+i,status:'completed',text:'Local '+i,created_at:'2026-03-08T02:45:'+String(i).padStart(2,'0')}));
 const newest={turn_id:'newer-utc',status:'completed',created_at:'2026-03-08T03:00:00',text:'Newer saved answer'};const serverPage=[newest,...locals.slice(1).reverse()];
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).includes('cursor=utc-zero')?historyPage([locals[0]]):historyPage(serverPage,'utc-zero')}));
 render(<AgentProvider><LegacyUtcHistory/></AgentProvider>);fireEvent.click(screen.getByText('Seed legacy UTC answers'));await act(async()=>fireEvent.click(screen.getByText('Read legacy UTC history')));
 const ids=screen.getByTestId('legacy-utc-order').textContent.split(',');expect(ids).toHaveLength(20);expect(ids[0]).toBe('newer-utc');expect(ids[1]).toBe('legacy-local-19');expect(ids).not.toContain('legacy-local-0');
 expect(JSON.parse(screen.getByTestId('legacy-utc-records').textContent)).toEqual(serverPage.map(timestampFields));
 await act(async()=>fireEvent.click(screen.getByText('Read older UTC answers')));expect(screen.getByTestId('legacy-utc-order').textContent).toBe('legacy-local-0');expect(JSON.parse(screen.getByTestId('legacy-utc-records').textContent)).toEqual([timestampFields(locals[0])]);
 fireEvent.click(screen.getByText('Return local UTC answers'));expect(screen.getByTestId('legacy-utc-order').textContent.split(',')).toHaveLength(20);expect(screen.getByTestId('legacy-utc-order')).toHaveTextContent('legacy-local-0');
});



test('saved UTC legacy dates, explicit offsets, invalid dates and equal instants retain the checked server order and original fields',async()=>{
 publishScreenContext({ticker:'SPY'});
 const supplied=[{turn_id:'legacy-unknown-a'},{turn_id:'tie-a',created_at:'2026-03-08T03:00:00'},{turn_id:'older',created_at:'2026-03-08T02:45:00'},{turn_id:'offset-newest',created_at:'2026-03-07T22:30:00-05:00'},{turn_id:'tie-b',created_at:'2026-03-08T03:00:00+00:00'},{turn_id:'legacy-unknown-b',created_at:'2026-02-30T01:00:00'},{turn_id:'updated-utc-fallback',created_at:'bad',updated_at:'2026-03-08T04:00:00.123456'}];
 const serverPage=[supplied[6],supplied[3],supplied[1],supplied[4],supplied[2],supplied[0],supplied[5]];
 global.fetch=jest.fn(async()=>({ok:true,json:async()=>historyPage(serverPage)}));render(<AgentProvider><TimestampHistory/></AgentProvider>);await act(async()=>fireEvent.click(screen.getByText('Read timestamp history')));
 expect(screen.getByTestId('timestamp-order')).toHaveTextContent('updated-utc-fallback,offset-newest,tie-a,tie-b,older,legacy-unknown-a,legacy-unknown-b');
 expect(JSON.parse(screen.getByTestId('timestamp-records').textContent)).toEqual(serverPage);expect(JSON.parse(screen.getByTestId('legacy-records').textContent)).toEqual([supplied[0],supplied[5]]);
});


function SharedChoiceGuard(){const a=useAgent();return <><button onClick={()=>{a.setSettingsPending(true);a.askQuestion('Blocked from another entry');}}>Check and ask together</button><button onClick={()=>{a.setSettingsPending(false);a.askQuestion('Confirmed choice');}}>Confirm and ask together</button><div data-testid="choice-guard-error">{a.error}</div><div data-testid="choice-guard-answer">{a.activeTurn?.text}</div></>;}
test('pending or uncertain model choices block shared admission immediately, not only after the composer rerenders',async()=>{
 publishScreenContext({ticker:'SPY'});render(<AgentProvider><SharedChoiceGuard/></AgentProvider>);
 fireEvent.click(screen.getByText('Check and ask together'));expect(global.fetch).not.toHaveBeenCalled();expect(screen.getByTestId('choice-guard-error')).toHaveTextContent('Confirm your AI choice');
 fireEvent.click(screen.getByText('Confirm and ask together'));await waitFor(()=>expect(screen.getByTestId('choice-guard-answer')).toHaveTextContent('Saved final answer'));
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(1);
});

function RequestStateProbe(){const a=useAgent();return <><button onClick={()=>a.setQuestion('Explain this activity')}>Write question</button><button onClick={()=>a.askQuestion(a.question)}>Send question</button><button onClick={a.cancel}>Stop question</button><button onClick={a.loadHistory}>Read history state</button><button onClick={()=>a.retryQuestion(a.turns[0])}>Restore failed question</button><div data-testid="request-draft">{a.question}</div><div data-testid="pending-request">{JSON.stringify(a.pendingTurn)}</div><div data-testid="request-turns">{JSON.stringify(a.turns)}</div><div data-testid="request-loading">{String(a.historyLoading)}</div><div data-testid="request-error">{a.error}</div><div data-testid="request-active">{a.activeTurn?.text}</div></>;}

test('admitted pending question keeps its own frozen selection and cancelled thread entry',async()=>{
 publishScreenContext({ticker:'SPY',dte:'week',selectedExpiry:'2026-10-09'});let read;
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true}:String(url).endsWith('/ask')?{ok:true,json:async()=>({turn_id:'accepted-question'})}:String(url).includes('/cancel/')?{ok:true,json:async()=>({turn_id:'accepted-question',status:'cancelled',error:'Stopped by you'})}:new Promise(resolve=>{read=resolve;}));
 render(<AgentProvider><RequestStateProbe/></AgentProvider>);
 fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));
 await waitFor(()=>expect(read).toBeDefined());
 expect(JSON.parse(screen.getByTestId('pending-request').textContent)).toMatchObject({turn_id:'accepted-question',question:'Explain this activity',ticker:'SPY',screen:{ticker:'SPY',selectedExpiry:'2026-10-09'}});
 expect(screen.getByTestId('request-draft').textContent).toBe('');
 act(()=>publishScreenContext({ticker:'QQQ',dte:'all'}));
 expect(JSON.parse(screen.getByTestId('pending-request').textContent).screen.ticker).toBe('SPY');
 await act(async()=>{fireEvent.click(screen.getByText('Stop question'));});
 await waitFor(()=>expect(JSON.parse(screen.getByTestId('request-turns').textContent)[0]).toMatchObject({turn_id:'accepted-question',question:'Explain this activity',status:'cancelled',screen:{ticker:'SPY'}}));
 expect(JSON.parse(screen.getByTestId('pending-request').textContent)).toBeNull();
 expect(JSON.parse(screen.getByTestId('request-turns').textContent)[0].answer).toBeUndefined();
 await act(async()=>read({ok:true,json:async()=>({status:'running'})}));
 const calls=global.fetch.mock.calls.length;fireEvent.click(screen.getByText('Restore failed question'));
 expect(screen.getByTestId('request-draft')).toHaveTextContent('Explain this activity');expect(global.fetch).toHaveBeenCalledTimes(calls);
 global.fetch.mockImplementation(async url=>({ok:true,json:async()=>String(url).endsWith('/ask')?{turn_id:'retry-question'}:{turn_id:'retry-question',status:'completed',text:'Current selection answer'}}));
 fireEvent.click(screen.getByText('Send question'));
 await waitFor(()=>expect(screen.getByTestId('request-active')).toHaveTextContent('Current selection answer'));
 const submitted=global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'));
 expect(submitted).toHaveLength(2);expect(JSON.parse(submitted[1][1].body).screen.ticker).toBe('QQQ');
});

test('failed admitted questions remain in thread while the last completed reading stays visible',async()=>{
 publishScreenContext({ticker:'SPY'});let attempts=0;
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).endsWith('/session')?{}:String(url).endsWith('/ask')?{turn_id:++attempts===1?'good':'failed'}:attempts===1?{turn_id:'good',status:'completed',text:'Last completed reading'}:{turn_id:'failed',status:'failed',error:'Evidence unavailable'}}));
 render(<AgentProvider><RequestStateProbe/></AgentProvider>);fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));
 await waitFor(()=>expect(screen.getByTestId('request-active')).toHaveTextContent('Last completed reading'));
 fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));
 await waitFor(()=>expect(JSON.parse(screen.getByTestId('request-turns').textContent)[0]).toMatchObject({turn_id:'failed',question:'Explain this activity',status:'failed',error:'Evidence unavailable'}));
 expect(screen.getByTestId('request-active')).toHaveTextContent('Last completed reading');
 expect(JSON.parse(screen.getByTestId('request-turns').textContent)[0].answer).toBeUndefined();
});

test('history read is bounded, blocks overlap and ignores its late reply after a successful retry',async()=>{
 jest.useFakeTimers();publishScreenContext({ticker:'SPY'});let release;
 global.fetch=jest.fn(()=>new Promise(resolve=>{release=resolve;}));
 render(<AgentProvider><RequestStateProbe/></AgentProvider>);
 try{
  fireEvent.click(screen.getByText('Read history state'));fireEvent.click(screen.getByText('Read history state'));
  expect(global.fetch).toHaveBeenCalledTimes(1);expect(screen.getByTestId('request-loading')).toHaveTextContent('true');
  await act(async()=>{jest.advanceTimersByTime(15001);});
  expect(screen.getByTestId('request-loading')).toHaveTextContent('false');expect(screen.getByTestId('request-error')).toHaveTextContent('Saved history is unavailable');
  expect(global.fetch.mock.calls[0][1].signal.aborted).toBe(true);
  global.fetch.mockResolvedValue({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[{turn_id:'current-history',text:'Current saved history'}]})});
  await act(async()=>fireEvent.click(screen.getByText('Read history state')));
  expect(screen.getByTestId('request-error').textContent).toBe('');
  await act(async()=>release({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[{turn_id:'late-history',text:'Late private history'}]})}));
  expect(JSON.parse(screen.getByTestId('request-turns').textContent).map(turn=>turn.turn_id)).toEqual(['current-history']);
 }finally{jest.useRealTimers();}
});

test('history success clears its own old failure while preserving a newer question failure',async()=>{
 publishScreenContext({ticker:'SPY'});
 global.fetch=jest.fn(async()=>({ok:false,status:503}));render(<AgentProvider><RequestStateProbe/></AgentProvider>);
 await act(async()=>fireEvent.click(screen.getByText('Read history state')));
 expect(screen.getByTestId('request-error')).toHaveTextContent('Saved history is unavailable');
 fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));
 await waitFor(()=>expect(screen.getByTestId('request-error')).toHaveTextContent('Local session unavailable'));
 global.fetch.mockResolvedValue({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[]})});
 await act(async()=>fireEvent.click(screen.getByText('Read history state')));
 expect(screen.getByTestId('request-error')).toHaveTextContent('Local session unavailable');
});

test.each([null,{turns:null},{turns:{}},{turns:[null]},{turns:[{}]}])('malformed saved history cannot erase the current completed answer: %j',async body=>{
 publishScreenContext({ticker:'SPY'});render(<AgentProvider><RequestStateProbe/></AgentProvider>);
 fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));
 await waitFor(()=>expect(screen.getByTestId('request-active')).toHaveTextContent('Saved final answer'));
 global.fetch.mockResolvedValue({ok:true,json:async()=>body});
 await act(async()=>fireEvent.click(screen.getByText('Read history state')));
 expect(screen.getByTestId('request-error')).toHaveTextContent('Saved history is unavailable');
 expect(screen.getByTestId('request-active')).toHaveTextContent('Saved final answer');
 expect(JSON.parse(screen.getByTestId('request-turns').textContent)).toHaveLength(1);
});

test('unmount aborts an outstanding private history read',async()=>{
 publishScreenContext({ticker:'SPY'});let release;global.fetch=jest.fn(()=>new Promise(resolve=>{release=resolve;}));
 const {unmount}=render(<AgentProvider><RequestStateProbe/></AgentProvider>);fireEvent.click(screen.getByText('Read history state'));
 const signal=global.fetch.mock.calls[0][1].signal;unmount();expect(signal.aborted).toBe(true);
 await act(async()=>release({ok:true,json:async()=>({has_more:false,next_cursor:null,turns:[{turn_id:'private-late',text:'Private late answer'}]})}));
});

test('ending a session elsewhere removes the pending admitted question and ignores its later final answer',async()=>{
 publishScreenContext({ticker:'SPY'});let read;
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true}:String(url).endsWith('/ask')?{ok:true,json:async()=>({turn_id:'private-pending'})}:new Promise(resolve=>{read=resolve;}));
 render(<AgentProvider><RequestStateProbe/></AgentProvider>);fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));
 await waitFor(()=>expect(read).toBeDefined());expect(JSON.parse(screen.getByTestId('pending-request').textContent).turn_id).toBe('private-pending');
 act(()=>window.dispatchEvent(new Event('floww-research-session-ended')));
 expect(JSON.parse(screen.getByTestId('pending-request').textContent)).toBeNull();
 await act(async()=>read({ok:true,json:async()=>({turn_id:'private-pending',status:'completed',text:'Late private answer'})}));
 expect(JSON.parse(screen.getByTestId('request-turns').textContent)).toEqual([]);expect(screen.getByTestId('request-active').textContent).toBe('');
});


test('confirmed cancellation allows an immediate new ask while its older read is stalled and cannot unlock that new question',async()=>{
 publishScreenContext({ticker:'SPY'});let firstRead,secondRead,asks=0;
 global.fetch=jest.fn(async url=>{
  if(String(url).endsWith('/session'))return {ok:true};
  if(String(url).endsWith('/ask'))return {ok:true,json:async()=>({turn_id:++asks===1?'cancelled-old':'running-new'})};
  if(String(url).includes('/cancel/'))return {ok:true,json:async()=>({turn_id:'cancelled-old',status:'cancelled'})};
  return new Promise(resolve=>{if(String(url).endsWith('/cancelled-old'))firstRead=resolve;else secondRead=resolve;});
 });
 render(<AgentProvider><RequestStateProbe/></AgentProvider>);
 fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));await waitFor(()=>expect(firstRead).toBeDefined());
 await act(async()=>fireEvent.click(screen.getByText('Stop question')));
 fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));
 await waitFor(()=>expect(asks).toBe(2));await waitFor(()=>expect(secondRead).toBeDefined());
 await act(async()=>firstRead({ok:true,json:async()=>({turn_id:'cancelled-old',status:'completed',text:'Late old answer'})}));
 fireEvent.click(screen.getByText('Write question'));fireEvent.click(screen.getByText('Send question'));expect(asks).toBe(2);
 await act(async()=>secondRead({ok:true,json:async()=>({turn_id:'running-new',status:'completed',text:'New answer'})}));
 await waitFor(()=>expect(screen.getByTestId('request-active')).toHaveTextContent('New answer'));
 expect(JSON.parse(screen.getByTestId('request-turns').textContent).find(turn=>turn.turn_id==='cancelled-old').status).toBe('cancelled');
});
