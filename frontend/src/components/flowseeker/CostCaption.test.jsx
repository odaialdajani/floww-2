/** @jest-environment jsdom */
import React from "react";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import FlowseekerProBlademap from "./FlowseekerProBlademap";
beforeEach(()=>{localStorage.clear();global.fetch=jest.fn(async()=>({ok:true,json:async()=>({})}));});
test("missing quote history displays no invented cost",async()=>{
 render(<FlowseekerProBlademap active/>);
 fireEvent.click(screen.getByText("Open drill"));
 await waitFor(()=>expect(screen.getByText("No contracts match for SPY")).toBeInTheDocument());
 expect(screen.getByTestId("spread-cost-state")).toHaveTextContent("Spread-cost history unavailable");
 expect(screen.getByTestId("spread-cost-state")).toHaveTextContent("mid-quote estimates are not executable costs");
 expect(screen.queryByText(/COST ~\$/)).not.toBeInTheDocument();
});
test("static quote snapshot cannot manufacture a historical cost estimate",async()=>{
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).includes("/public/chain/")?{ok:true,spot:452,contracts:[{strike:450,type:"call",expiry:"2026-12-18",volume:500,oi:500,iv:.2,bid:4,ask:4.2}]}:{}}));
 render(<FlowseekerProBlademap active/>);
 fireEvent.click(screen.getByText("Open drill"));
 await waitFor(()=>expect(document.querySelectorAll(".th-dtab tbody tr")).toHaveLength(1));
 expect(screen.getByTestId("spread-cost-state")).toHaveTextContent("history unavailable");
 expect(screen.queryByText(/COST ~\$0/)).not.toBeInTheDocument();
});
