import React from "react";
import {act,render,screen,fireEvent,waitFor,within} from "@testing-library/react";
import AgentProvider,{useAgent} from "./AgentProvider";
import {publishScreenContext} from "./useScreenContext";
import {rangeSelectionContext} from '../lib/rangeAnalytics';
import rangeComplete from '../fixtures/integration/range-analytics.v1/complete.json';
import rangePartial from '../fixtures/integration/range-analytics.v1/partial.json';
beforeAll(()=>{Object.defineProperty(globalThis,"crypto",{value:require("crypto").webcrypto,configurable:true});});
function Consumer(){const a=useAgent();return <><button onClick={()=>a.askQuestion("What changed?")}>Ask shared</button><button onClick={a.loadHistory}>Load history</button><button onClick={a.endSession}>End session</button><button onClick={()=>a.setActiveTurn(a.turns[0])}>Select saved answer</button><div data-testid="error">{a.error}</div><div data-testid="notice">{a.sessionNotice}</div><div data-testid="history-count">{a.turns.length}</div><div data-testid="answer">{a.activeTurn?.text}</div><div data-testid="ticker">{a.activeTurn?.ticker}</div><div data-testid="grounding">{a.answerContextStatus}</div></>}
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
 publishScreenContext(storedRangeContext());
 global.fetch=jest.fn(async()=>({ok:true,json:async()=>({turns:[{turn_id:'history-range',ticker:'SPY',text:'Historical range answer'}]})}));
 render(<AgentProvider><Consumer/></AgentProvider>);fireEvent.click(screen.getByText('Load history'));
 await waitFor(()=>expect(screen.getByTestId('history-count')).toHaveTextContent('1'));
 fireEvent.click(screen.getByText('Select saved answer'));
 expect(screen.getByTestId('grounding')).toHaveTextContent('unverified_history');
 act(()=>publishScreenContext(storedRangeContext(rangePartial)));
 expect(screen.getByTestId('grounding')).toHaveTextContent('unverified_history');expect(global.fetch).toHaveBeenCalledTimes(1);
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
 global.fetch.mockImplementation(async url=>String(url).endsWith("/history")?await new Promise(resolve=>{release=resolve;}):{ok:true,json:async()=>({status:"signed-out"})});
 fireEvent.click(screen.getByText("Load history"));
 fireEvent.click(screen.getByText("End session"));
 await waitFor(()=>expect(screen.getByTestId("notice").textContent).toMatch(/session ended/));
 expect(screen.getByTestId("answer").textContent).toBe("");
 await act(async()=>release({ok:true,json:async()=>({turns:[{turn_id:"old",text:"Private"}]})}));
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
 global.fetch.mockImplementation(async url=>String(url).endsWith("/history")?await new Promise(resolve=>{release=resolve;}):{ok:true,json:async()=>({})});
 fireEvent.click(second.getByText("Load history"));
 fireEvent.click(first.getByText("End session"));
 await waitFor(()=>expect(second.getByTestId("answer").textContent).toBe(""));
 await act(async()=>release({ok:true,json:async()=>({turns:[{turn_id:"late-private"}]})}));
 expect(second.getByTestId("history-count").textContent).toBe("0");
 expect(second.getByTestId("notice").textContent).toMatch(/session ended/);
 act(()=>window.dispatchEvent(new StorageEvent("storage",{key:"floww-research-session-ended",newValue:"another-tab"})));
 expect(second.getByTestId("answer").textContent).toBe("");
});
