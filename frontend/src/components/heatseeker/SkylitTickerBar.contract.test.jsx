import React from "react";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import axios from "axios";
import SkylitTickerBar from "./SkylitTickerBar";
jest.mock("axios",()=>({get:jest.fn()}));
beforeEach(()=>{localStorage.clear();axios.get.mockReset();});
const bigUniverse=()=>({trinity:["^SPX","SPY","QQQ"],default:["IWM"],popular:Array.from({length:600},(_,i)=>"T"+String(i).padStart(4,"0"))});
test("compact browsing bounds rows but reports the full loaded count",()=>{
 render(<SkylitTickerBar activeTicker="SPY" tickers={bigUniverse()}/>);expect(screen.getByTestId("skylit-ticker-count")).toHaveTextContent("604 loaded tickers");
 expect(screen.queryByRole("listbox")).toBeNull();fireEvent.focus(screen.getByRole("combobox"));expect(screen.getAllByRole("option")).toHaveLength(30);
});
test("search reaches a name beyond the browsing page",()=>{
 const change=jest.fn();render(<SkylitTickerBar activeTicker="SPY" onTickerChange={change} tickers={bigUniverse()}/>);
 fireEvent.change(screen.getByRole("combobox"),{target:{value:"T0559"}});fireEvent.click(screen.getByRole("option",{name:"T0559"}));expect(change).toHaveBeenCalledWith("T0559");
});
test("active selection remains clear even outside the current dropdown page",()=>{
 render(<SkylitTickerBar activeTicker="T0559" tickers={bigUniverse()}/>);expect(screen.getByText("Selected T0559")).toBeInTheDocument();
});
test("provider-confirmed free text remains reachable outside the loaded list",async()=>{
 const change=jest.fn();axios.get.mockResolvedValue({data:{instruments:[{symbol:"VSAT"}]}});
 render(<SkylitTickerBar activeTicker="SPY" onTickerChange={change} tickers={bigUniverse()}/>);const input=screen.getByRole("combobox");
 fireEvent.change(input,{target:{value:"vsat"}});fireEvent.keyDown(input,{key:"Enter"});await waitFor(()=>expect(change).toHaveBeenCalledWith("VSAT"));
});
test("share classes and loaded index symbols preserve spelling",()=>{
 const change=jest.fn();render(<SkylitTickerBar activeTicker="SPY" onTickerChange={change} tickers={["SPY","BRK.B","^SPX"]}/>);
 const input=screen.getByRole("combobox");fireEvent.change(input,{target:{value:"brk.b"}});fireEvent.keyDown(input,{key:"Enter"});
 fireEvent.change(input,{target:{value:"^spx"}});fireEvent.keyDown(input,{key:"Enter"});expect(change.mock.calls).toEqual([["BRK.B"],["^SPX"]]);
});
