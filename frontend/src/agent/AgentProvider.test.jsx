import React from "react";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import AgentProvider,{useAgent} from "./AgentProvider";
import {publishScreenContext} from "./useScreenContext";
beforeAll(()=>{Object.defineProperty(globalThis,"crypto",{value:require("crypto").webcrypto,configurable:true});});
function Consumer(){const a=useAgent();return <><button onClick={()=>a.askQuestion("What changed?")}>Ask shared</button><div data-testid="error">{a.error}</div><div data-testid="answer">{a.activeTurn?.text}</div><div data-testid="ticker">{a.activeTurn?.ticker}</div></>}
beforeEach(()=>{global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).endsWith("/session")?{}:String(url).endsWith("/ask")?{turn_id:"turn-one"}:{turn_id:"turn-one",status:"completed",ticker:"NVDA",text:"Saved final answer",ledger:{price:{value:178.4}}}}));});
test("shared request freezes screen and stores final service answer",async()=>{
 publishScreenContext({page:"flowseeker-pro",ticker:"NVDA",dte:"all",selectedContract:"NVDA-test",observedAt:"2026-09-11T15:00:00Z"});
 render(<AgentProvider><Consumer/></AgentProvider>);
 fireEvent.click(screen.getByText("Ask shared"));
 await waitFor(()=>expect(screen.getByTestId("answer").textContent).toBe("Saved final answer"));
 publishScreenContext({page:"heatseeker",ticker:"SPY",dte:"week"});
 expect(screen.getByTestId("ticker").textContent).toBe("NVDA");
 const call=global.fetch.mock.calls.find(([url])=>String(url).endsWith("/ask"));
 expect(JSON.parse(call[1].body).screen.selectedContract).toBe("NVDA-test");
 expect(call[1].credentials).toBe("include");
});
