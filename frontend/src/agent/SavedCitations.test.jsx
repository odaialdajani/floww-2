import React from "react";
import {act,render,screen,fireEvent,waitFor,within} from "@testing-library/react";
import AgentProvider,{useAgent} from "./AgentProvider";
import AgentPanel from "./AgentPanel";

const first={citation_id:"cit_first",turn_id:"saved-answer-one",fact_id:"raw",detail_path:"https://untrusted.invalid/do-not-follow",metric:"Raw GEX",value:0,unit:"USD",status:"recorded_zero",reason:null,source:"Saved options grid",snapshot_id:"snap-one",event_time:"2026-11-04T15:30:00Z",received_at:"2026-11-04T15:30:02Z",ticker:"SPY",cited:true,sections:["Wall reading"]};
const second={...first,citation_id:"cit_second",turn_id:"saved-answer-two",fact_id:"iv",metric:"Implied volatility",value:null,status:"unavailable",reason:"Greek clock unknown",ticker:"QQQ",cited:false};
const index=rows=>({version:"agent-citation-index.v1",n_turns:rows.length,n_citations:rows.length,turns:rows.map(r=>r.turn_id),citations:rows,sources:[],coverage:{turns_scanned:30,turns_indexed:rows.length}});
const response=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>body});
function Harness(){const a=useAgent();return <><button onClick={()=>a.setOpen(true)}>Open chat</button><AgentPanel/></>;}
function mount(){return render(<AgentProvider><Harness/></AgentProvider>);}
function open(){fireEvent.click(screen.getByText("Open chat"));fireEvent.click(screen.getByRole("button",{name:"Saved citations"}));}
beforeEach(()=>{global.fetch=jest.fn(async()=>response(index([first,second])));});

test("citations load only after an explicit open and preserve a stored zero and both source clocks",async()=>{
 mount();expect(global.fetch).not.toHaveBeenCalled();fireEvent.click(screen.getByText("Open chat"));expect(global.fetch).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Saved citations"}));
 await screen.findByRole("button",{name:/SPY.*Raw GEX/});
 expect(global.fetch.mock.calls[0][0]).toMatch(/\/api\/agent\/citations\?limit=30$/);
 expect(global.fetch.mock.calls[0][1]).toMatchObject({credentials:"include",method:"GET"});
 global.fetch.mockResolvedValueOnce(response({version:"agent-citation-index.v1",citation:first}));
 fireEvent.click(screen.getByRole("button",{name:/SPY.*Raw GEX/}));
 const detail=await screen.findByRole("region",{name:"Saved citation reading"});
 expect(within(detail).getByText("0 USD")).toBeInTheDocument();
 expect(detail).toHaveTextContent(first.event_time);expect(detail).toHaveTextContent(first.received_at);expect(detail).toHaveTextContent(first.turn_id);
 expect(detail).toHaveTextContent("recorded_zero");expect(detail).toHaveTextContent("Saved options grid");
 expect(global.fetch.mock.calls[1][0]).toMatch(/\/citations\/cit_first\?turn_id=saved-answer-one$/);
 expect(global.fetch.mock.calls.every(([,opts])=>opts.method==="GET")).toBe(true);
});

test("a closed citation read is aborted and its late response cannot refill the reopened view",async()=>{
 let late;global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{late=resolve;}));mount();open();
 await waitFor(()=>expect(late).toBeDefined());const signal=global.fetch.mock.calls[0][1].signal;
 fireEvent.click(screen.getByRole("button",{name:"Close saved citations"}));expect(signal.aborted).toBe(true);
 global.fetch.mockResolvedValueOnce(response(index([])));fireEvent.click(screen.getByRole("button",{name:"Saved citations"}));
 await screen.findByText("No saved citations were returned.");
 await act(async()=>late(response(index([first]))));
 expect(screen.queryByRole("button",{name:/SPY.*Raw GEX/})).toBeNull();
});

test("clicking the selected reading again keeps its in-flight request and loaded details",async()=>{
 let complete;mount();open();const selection=await screen.findByRole("button",{name:/SPY.*Raw GEX/});
 global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));fireEvent.click(selection);
 await waitFor(()=>expect(complete).toBeDefined());const signal=global.fetch.mock.calls[1][1].signal;
 fireEvent.click(selection);expect(signal.aborted).toBe(false);expect(global.fetch).toHaveBeenCalledTimes(2);
 await act(async()=>complete(response({version:"agent-citation-index.v1",citation:first})));
 const detail=await screen.findByRole("region",{name:"Saved citation reading"});expect(detail).toHaveTextContent("0 USD");
 fireEvent.click(selection);expect(screen.getByRole("region",{name:"Saved citation reading"})).toBe(detail);
 expect(screen.queryByText("Loading saved reading…")).toBeNull();expect(global.fetch).toHaveBeenCalledTimes(2);
});

test("selecting another citation cancels the previous detail and rejects late answer ownership",async()=>{
 let late;mount();open();await screen.findByRole("button",{name:/SPY.*Raw GEX/});
 global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{late=resolve;}));fireEvent.click(screen.getByRole("button",{name:/SPY.*Raw GEX/}));
 await waitFor(()=>expect(late).toBeDefined());const signal=global.fetch.mock.calls[1][1].signal;
 global.fetch.mockResolvedValueOnce(response({version:"agent-citation-index.v1",citation:second}));fireEvent.click(screen.getByRole("button",{name:/QQQ.*Implied volatility/}));
 const detail=await screen.findByRole("region",{name:"Saved citation reading"});expect(signal.aborted).toBe(true);expect(detail).toHaveTextContent("Greek clock unknown");expect(detail).toHaveTextContent("Value unavailable");
 await act(async()=>late(response({version:"agent-citation-index.v1",citation:first})));
 expect(detail).toHaveTextContent("saved-answer-two");expect(detail).not.toHaveTextContent("saved-answer-one");expect(detail).not.toHaveTextContent("0 USD");
});

test("a mismatched detail answer is refused instead of attributing another saved fact to the selection",async()=>{
 mount();open();await screen.findByRole("button",{name:/SPY.*Raw GEX/});
 global.fetch.mockResolvedValueOnce(response({version:"agent-citation-index.v1",citation:{...first,turn_id:"foreign-answer"}}));
 fireEvent.click(screen.getByRole("button",{name:/SPY.*Raw GEX/}));
 expect(await screen.findByRole("alert")).toHaveTextContent("could not be matched");
 expect(screen.queryByRole("region",{name:"Saved citation reading"})).toBeNull();
});

test("failed storage and empty history stay distinct and retry performs one deliberate read",async()=>{
 global.fetch.mockResolvedValueOnce(response({detail:"Saved research storage is unavailable"},503));mount();open();
 expect(await screen.findByRole("alert")).toHaveTextContent("Saved citations are unavailable");expect(screen.queryByText("No saved citations were returned.")).toBeNull();
 global.fetch.mockResolvedValueOnce(response(index([])));fireEvent.click(screen.getByRole("button",{name:"Retry saved citations"}));
 await screen.findByText("No saved citations were returned.");expect(global.fetch).toHaveBeenCalledTimes(2);
});

test("session end clears private citations and invalidates a detail even when transport ignores abort",async()=>{
 let late;mount();open();await screen.findByRole("button",{name:/SPY.*Raw GEX/});
 global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{late=resolve;}));fireEvent.click(screen.getByRole("button",{name:/SPY.*Raw GEX/}));await waitFor(()=>expect(late).toBeDefined());
 const signal=global.fetch.mock.calls[1][1].signal;act(()=>window.dispatchEvent(new Event("floww-research-session-ended")));
 expect(signal.aborted).toBe(true);expect(screen.queryByRole("button",{name:/SPY.*Raw GEX/})).toBeNull();
 await act(async()=>late(response({version:"agent-citation-index.v1",citation:first})));
 expect(screen.queryByRole("region",{name:"Saved citation reading"})).toBeNull();expect(screen.queryByText(first.source)).toBeNull();
});

test("an expired owner session is reported without creating a new session or asking the model",async()=>{
 global.fetch.mockResolvedValueOnce(response({detail:"Research session expired"},401));mount();open();
 expect(await screen.findByRole("alert")).toHaveTextContent("research session");
 expect(global.fetch).toHaveBeenCalledTimes(1);expect(global.fetch.mock.calls[0][1].method).toBe("GET");expect(screen.queryByText("No saved citations were returned.")).toBeNull();
});

test("an expired session during detail lookup removes the old owner's citation list",async()=>{
 mount();open();await screen.findByRole("button",{name:/SPY.*Raw GEX/});
 global.fetch.mockResolvedValueOnce(response({detail:"Research session expired"},401));fireEvent.click(screen.getByRole("button",{name:/SPY.*Raw GEX/}));
 expect(await screen.findByRole("alert")).toHaveTextContent("research session");
 expect(screen.queryByRole("button",{name:/SPY.*Raw GEX/})).toBeNull();expect(screen.queryByRole("button",{name:/QQQ.*Implied volatility/})).toBeNull();
});

test("another tab ending the session clears already loaded private citation details",async()=>{
 mount();open();await screen.findByRole("button",{name:/SPY.*Raw GEX/});
 global.fetch.mockResolvedValueOnce(response({version:"agent-citation-index.v1",citation:first}));fireEvent.click(screen.getByRole("button",{name:/SPY.*Raw GEX/}));await screen.findByRole("region",{name:"Saved citation reading"});
 act(()=>window.dispatchEvent(new StorageEvent("storage",{key:"floww-research-session-ended",newValue:"another-session-ended"})));
 expect(screen.queryByRole("region",{name:"Saved citation reading"})).toBeNull();expect(screen.queryByRole("button",{name:/SPY.*Raw GEX/})).toBeNull();
});

test("hiding chat cancels its read and keeps no citation content mounted when reopened",async()=>{
 let late;global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{late=resolve;}));mount();open();await waitFor(()=>expect(late).toBeDefined());
 const signal=global.fetch.mock.calls[0][1].signal;fireEvent.click(screen.getByRole("button",{name:"Close Ask Flow"}));expect(signal.aborted).toBe(true);
 await act(async()=>late(response(index([first]))));fireEvent.click(screen.getByText("Open chat"));
 expect(screen.queryByRole("button",{name:/SPY.*Raw GEX/})).toBeNull();expect(global.fetch).toHaveBeenCalledTimes(1);
});

test("a stuck saved read times out visibly and never retries itself",async()=>{
 jest.useFakeTimers();global.fetch.mockImplementation(()=>new Promise(()=>{}));const view=mount();
 try{
  open();const signal=global.fetch.mock.calls[0][1].signal;
  await act(async()=>jest.advanceTimersByTime(15000));
  expect(screen.getByRole("alert")).toHaveTextContent("took too long");expect(signal.aborted).toBe(true);
  await act(async()=>jest.advanceTimersByTime(60000));expect(global.fetch).toHaveBeenCalledTimes(1);
 }finally{view.unmount();jest.useRealTimers();}
});
