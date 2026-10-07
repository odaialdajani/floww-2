import React from "react";
import {render,screen,fireEvent,act} from "@testing-library/react";
import "@testing-library/jest-dom";
import StealThreePreview from "./StealThreePreview";
import useScreenContext, { publishScreenContext } from "../../agent/useScreenContext";
function ReadContext() { const [context] = useScreenContext(); return <output data-testid="screen-context">{JSON.stringify(context)}</output>; }
function readContext() { return JSON.parse(screen.getByTestId("screen-context").textContent); }

jest.mock("./DualGEXBadge",()=>({ticker})=><div data-testid="extra-exposure">{ticker} exposure reading</div>);
jest.mock("./IVMidBadge",()=>({ticker})=><div data-testid="extra-volatility">{ticker} volatility reading</div>);
jest.mock("./TickerPicker",()=>({value,onChange})=><button onClick={()=>onChange("QQQ")}>Choose stock {value}</button>);
jest.mock("./WheelIncomeScreenerPanel",()=>{
 const React=require("react");
 return function MockIncome({ticker}) {
  const [value,setValue]=React.useState("Put income");
  return <div data-testid="extra-income">{ticker} income reading<button onClick={()=>setValue("Call income")}>{value}</button></div>;
 };
});

test("one visible study preserves every original study and control choice",()=>{
 render(<StealThreePreview ticker="SPY" onTickerChange={()=>{}}/>);
 const selector=screen.getByRole("combobox",{name:"Study"});
 expect(screen.getByTestId("extra-income")).toBeVisible();
 expect(screen.queryByRole("button",{name:/Choose stock/})).toBeNull();
 fireEvent.click(screen.getByRole("button",{name:"Put income"}));
 fireEvent.change(selector,{target:{value:"exposure"}});
 expect(screen.getByTestId("extra-exposure")).toBeVisible();
 expect(screen.getByTestId("extra-income")).not.toBeVisible();
 fireEvent.change(selector,{target:{value:"volatility"}});
 expect(screen.getByTestId("extra-volatility")).toBeVisible();
 expect(screen.getByTestId("extra-exposure")).not.toBeVisible();
 fireEvent.change(selector,{target:{value:"income"}});
 expect(screen.getByRole("button",{name:"Call income"})).toBeVisible();
 expect(document.querySelectorAll('.extra-study-family:not([hidden])')).toHaveLength(1);
 expect(screen.queryByText(/journal-validated|endpoint base|ranks #/i)).not.toBeInTheDocument();
});

test("shared stock changes reach already opened studies without a duplicate picker",()=>{
 const view=render(<StealThreePreview ticker="SPY" onTickerChange={()=>{}}/>);
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"exposure"}});
 view.rerender(<StealThreePreview ticker="QQQ" onTickerChange={()=>{}}/>);
 expect(screen.getByTestId("extra-exposure")).toHaveTextContent("QQQ exposure reading");
 expect(screen.getByTestId("extra-income")).toHaveTextContent("QQQ income reading");
 expect(screen.queryByRole("button",{name:/Choose stock/})).toBeNull();
});

test("standalone preview keeps one verified stock control",()=>{
 render(<StealThreePreview defaultTicker="SPY"/>);
 fireEvent.click(screen.getByRole("button",{name:"Choose stock SPY"}));
 expect(screen.getByTestId("extra-income")).toHaveTextContent("QQQ income reading");
});

test("standalone stock choice updates the preview and reports the choice",()=>{
 const change=jest.fn();
 render(<StealThreePreview defaultTicker="SPY" onTickerChange={change}/>);
 fireEvent.click(screen.getByRole("button",{name:"Choose stock SPY"}));
 expect(change).toHaveBeenCalledWith("QQQ");
 expect(screen.getByTestId("extra-income")).toHaveTextContent("QQQ income reading");
});


test("Extra replaces an old Options reading with the current stock and chosen study",()=>{
 let releaseOld; act(()=>{releaseOld=publishScreenContext({page:"heatseeker",ticker:"SPY",dte:7,displayMode:"historical",observedAt:"2026-10-01T14:00:00Z",reading:{netGex:123}});});
 const view=render(<><StealThreePreview ticker="NVDA"/><ReadContext/></>);
 expect(readContext()).toMatchObject({contextVersion:1,page:"steal-three",ticker:"NVDA",study:"Options income",observedAt:null});
 expect(readContext().reading).toBeUndefined();
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"exposure"}});
 expect(readContext().study).toBe("Exposure comparison");
 act(()=>releaseOld());
 expect(readContext().ticker).toBe("NVDA");
 view.rerender(<><StealThreePreview ticker="QQQ"/><ReadContext/></>);
 expect(readContext().ticker).toBe("QQQ");
 view.rerender(<ReadContext/>);
 expect(readContext().ticker).toBeNull();
});

test("Extra unmount leaves a later screen owner intact",()=>{
 const view=render(<><StealThreePreview ticker="NVDA"/><ReadContext/></>);
 let release; act(()=>{release=publishScreenContext({page:"flowseeker-pro",ticker:"QQQ"});});
 view.rerender(<ReadContext/>);
 expect(readContext()).toMatchObject({page:"flowseeker-pro",ticker:"QQQ"});
 act(()=>release());
});


test("Extra selection survives StrictMode and clears only its own choice",()=>{
 const view=render(<React.StrictMode><StealThreePreview ticker="NVDA"/><ReadContext/></React.StrictMode>);
 expect(readContext()).toMatchObject({page:"steal-three",ticker:"NVDA",observedAt:null});
 view.rerender(<React.StrictMode><StealThreePreview ticker="QQQ"/><ReadContext/></React.StrictMode>);
 expect(readContext()).toMatchObject({page:"steal-three",ticker:"QQQ",observedAt:null});
 view.rerender(<React.StrictMode><ReadContext/></React.StrictMode>);
 expect(readContext().ticker).toBeNull();
});
