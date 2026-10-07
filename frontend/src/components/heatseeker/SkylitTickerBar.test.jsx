import React from "react";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import axios from "axios";
import SkylitTickerBar from "./SkylitTickerBar";
jest.mock("axios",()=>({get:jest.fn()}));
beforeEach(()=>{localStorage.clear();axios.get.mockReset();});
test("browse keeps quick selection without a horizontal button tape",()=>{
 const change=jest.fn();render(<SkylitTickerBar activeTicker="SPY" onTickerChange={change}/>);
 fireEvent.click(screen.getByRole("button",{name:"Browse stock list"}));fireEvent.click(screen.getByRole("option",{name:"QQQ"}));
 expect(change).toHaveBeenCalledWith("QQQ");expect(axios.get).not.toHaveBeenCalled();
});
test("typing a valid missing name checks the provider before loading",async()=>{
 axios.get.mockResolvedValue({data:{instruments:[{symbol:"HOOD"}]}});const change=jest.fn();
 render(<SkylitTickerBar activeTicker="SPY" onTickerChange={change}/>);const input=screen.getByRole("combobox");
 fireEvent.change(input,{target:{value:"hood"}});fireEvent.keyDown(input,{key:"Enter"});
 expect(change).not.toHaveBeenCalled();await waitFor(()=>expect(change).toHaveBeenCalledWith("HOOD"));
});
test("blank and malformed names never load or query the provider",()=>{
 const change=jest.fn();render(<SkylitTickerBar activeTicker="SPY" onTickerChange={change}/>);const input=screen.getByRole("combobox");
 fireEvent.keyDown(input,{key:"Enter"});fireEvent.change(input,{target:{value:"SPY/QQQ"}});fireEvent.keyDown(input,{key:"Enter"});
 expect(change).not.toHaveBeenCalled();expect(axios.get).not.toHaveBeenCalled();expect(screen.getByRole("alert")).toHaveTextContent("valid stock symbol");
});
