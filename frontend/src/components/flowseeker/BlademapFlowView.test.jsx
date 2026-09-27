/** @jest-environment jsdom */
import React from "react";
import {render,screen,fireEvent,waitFor,within} from "@testing-library/react";
import FlowseekerProBlademap from "./FlowseekerProBlademap";
const expiry=new Date(Date.now()+14*86400000).toISOString().slice(0,10);
const contracts=[{strike:450,type:"call",expiry,volume:500,oi:500,iv:.2,bid:4,ask:4.2},{strike:450,type:"put",expiry,volume:600,oi:600,iv:.25,bid:3.9,ask:4.1}];
beforeEach(()=>{
 localStorage.clear();
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).includes("/public/chain/SPY")?{ok:true,contracts,spot:452}:{}}));
});
async function openDrill(){
 render(<FlowseekerProBlademap active/>);
 fireEvent.click(screen.getByText("Open drill"));
 await waitFor(()=>expect(document.querySelectorAll(".th-dtab tbody tr")).toHaveLength(2));
 return screen.getByTestId("drill");
}
test("free-text ticker scope filters Pulse and reset restores the scope",async()=>{
 render(<FlowseekerProBlademap active/>);
 fireEvent.click(screen.getByRole("button",{name:/^Filters/}));
 const input=screen.getByPlaceholderText(/Ticker/);
 fireEvent.change(input,{target:{value:"ZZZ"}});
 expect(screen.getByTestId("filters-panel")).toHaveTextContent("Reset");
 expect(JSON.parse(localStorage.getItem("th-prefs-v1")).knobQ).toBe("ZZZ");
 fireEvent.click(screen.getByRole("button",{name:/Reset/}));
 expect(input.value).toBe("");
});
test("drill expiry bands are exclusive",async()=>{
 const drill=await openDrill();
 fireEvent.click(within(drill).getByRole("button",{name:"Mo"}));
 expect(document.querySelectorAll(".th-dtab tbody tr")).toHaveLength(2);
 fireEvent.click(within(drill).getByRole("button",{name:"0DTE"}));
 expect(within(drill).getByText("No contracts match for SPY")).toBeInTheDocument();
});
test("single page retains section navigation and removes retired tabs",async()=>{
 await openDrill();
 expect(screen.getByRole("complementary",{name:"Sections"})).toBeInTheDocument();
 for(const text of ["WTI Crude","Stat-Arb Pairs","Smart Order Flow"])expect(screen.queryByText(text)).not.toBeInTheDocument();
});
test("selected signal stays below the tape and missing chart values stay unavailable",async()=>{
 await openDrill();
 fireEvent.click(document.querySelector(".th-dtab tbody tr"));
 const detail=document.querySelector(".th-sel"),table=document.querySelector(".th-dtab");
 expect(detail).toHaveTextContent("SPY");
 expect(table.compareDocumentPosition(detail)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
 expect(screen.getByTestId("dealer-drilldown")).toHaveTextContent("Dealer chart unavailable for SPY");
});
