import React from "react";
import {act,render,screen,fireEvent,waitFor,within} from "@testing-library/react";
import AgentProvider,{useAgent} from "./AgentProvider";
import {publishScreenContext} from "./useScreenContext";
beforeAll(()=>{Object.defineProperty(globalThis,"crypto",{value:require("crypto").webcrypto,configurable:true});});
function Consumer(){const a=useAgent();return <><button onClick={()=>a.askQuestion("What changed?")}>Ask shared</button><button onClick={a.loadHistory}>Load history</button><button onClick={a.endSession}>End session</button><div data-testid="error">{a.error}</div><div data-testid="notice">{a.sessionNotice}</div><div data-testid="history-count">{a.turns.length}</div><div data-testid="answer">{a.activeTurn?.text}</div><div data-testid="ticker">{a.activeTurn?.ticker}</div></>}
beforeEach(()=>{global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).endsWith("/session")?{}:String(url).endsWith("/ask")?{turn_id:"turn-one"}:{turn_id:"turn-one",status:"completed",ticker:"NVDA",text:"Saved final answer",ledger:{price:{value:178.4}}}}));});
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
