import React from "react";
import {act,fireEvent,render,screen,waitFor} from "@testing-library/react";
import axios from "axios";
import TickerPicker,{FAVORITES_KEY} from "./TickerPicker";
jest.mock("axios",()=>({get:jest.fn()}));
beforeEach(()=>{localStorage.clear();axios.get.mockReset();});
const names=Array.from({length:650},(_,i)=>"T"+String(i).padStart(4,"0"));
test("compact dropdown searches the entire list before limiting results",()=>{
 const change=jest.fn();render(<TickerPicker value="SPY" onChange={change} tickers={["SPY",...names]}/>);
 expect(screen.getByText("Selected SPY")).toBeInTheDocument();
 const input=screen.getByRole("combobox");fireEvent.focus(input);
 expect(screen.getAllByRole("option").length).toBeLessThanOrEqual(30);
 fireEvent.change(input,{target:{value:"T0649"}});
 fireEvent.click(screen.getByRole("option",{name:"T0649"}));
 expect(change).toHaveBeenCalledWith("T0649");
 expect(axios.get).not.toHaveBeenCalled();
});
test("keyboard moves options, Enter selects, Escape closes",()=>{
 const change=jest.fn();render(<TickerPicker value="SPY" onChange={change} tickers={["SPY","QQQ","BRK.B"]}/>);
 const input=screen.getByRole("combobox");fireEvent.focus(input);fireEvent.keyDown(input,{key:"ArrowDown"});fireEvent.keyDown(input,{key:"Enter"});
 expect(change).toHaveBeenCalledWith("SPY");fireEvent.focus(input);fireEvent.keyDown(input,{key:"Escape"});
 expect(input).toHaveAttribute("aria-expanded","false");expect(screen.queryByRole("listbox")).toBeNull();
});
test("incomplete local list checks an exact provider match before loading",async()=>{
 axios.get.mockResolvedValue({data:{instruments:[{symbol:"COINBASE"},{symbol:"COIN"}]}});
 const change=jest.fn();render(<TickerPicker value="SPY" onChange={change} tickers={["SPY"]} status="incomplete"/>);
 const input=screen.getByRole("combobox");fireEvent.change(input,{target:{value:"$coin"}});fireEvent.keyDown(input,{key:"Enter"});
 await waitFor(()=>expect(change).toHaveBeenCalledWith("COIN"));
 expect(axios.get.mock.calls[0][0]).toContain("/market/catalog");expect(axios.get.mock.calls[0][1].params.q).toBe("COIN");
});
test("malformed and nonexact symbols cannot load",async()=>{
 const change=jest.fn();render(<TickerPicker value="SPY" onChange={change} tickers={["SPY"]}/>);
 const input=screen.getByRole("combobox");fireEvent.change(input,{target:{value:"SPY / bad"}});fireEvent.keyDown(input,{key:"Enter"});
 expect(await screen.findByRole("alert")).toHaveTextContent("Choose a valid stock symbol");expect(axios.get).not.toHaveBeenCalled();
 axios.get.mockResolvedValue({data:{instruments:[{symbol:"COINBASE"}],complete_provider_catalog:false}});
 fireEvent.change(input,{target:{value:"COIN"}});fireEvent.keyDown(input,{key:"Enter"});
 expect(await screen.findByRole("alert")).toHaveTextContent("could not be confirmed");expect(change).not.toHaveBeenCalled();
});
test("favorites survive remount and never filter the searchable universe",()=>{
 const change=jest.fn();const view=render(<TickerPicker value="SPY" onChange={change} tickers={["SPY","QQQ"]}/>);
 fireEvent.click(screen.getByRole("button",{name:"Add SPY to favorites"}));expect(JSON.parse(localStorage.getItem(FAVORITES_KEY))).toEqual(["SPY"]);
 view.unmount();render(<TickerPicker value="SPY" onChange={change} tickers={["SPY","QQQ"]}/>);
 expect(screen.getByRole("button",{name:"Remove SPY from favorites"})).toBeInTheDocument();
 fireEvent.change(screen.getByRole("combobox"),{target:{value:"QQQ"}});expect(screen.getByRole("option",{name:"QQQ"})).toBeInTheDocument();
});
test("failed favorite storage is explicit and cross-tab changes refresh the picker",()=>{
 const view=render(<TickerPicker value="SPY" tickers={["SPY","QQQ"]}/>);
 const set=jest.spyOn(Storage.prototype,"setItem").mockImplementation(()=>{throw new Error("full");});
 fireEvent.click(screen.getByRole("button",{name:"Add SPY to favorites"}));expect(screen.getByRole("alert")).toHaveTextContent("Favorites could not be saved");
 expect(screen.getByRole("button",{name:"Add SPY to favorites"})).toBeInTheDocument();set.mockRestore();
 localStorage.setItem(FAVORITES_KEY,JSON.stringify(["SPY"]));act(()=>window.dispatchEvent(new StorageEvent("storage",{key:FAVORITES_KEY})));
 expect(screen.getByRole("button",{name:"Remove SPY from favorites"})).toBeInTheDocument();view.unmount();
});
test("a delayed lookup cannot overwrite a newer typed choice",async()=>{
 let resolve;axios.get.mockImplementation(()=>new Promise(r=>{resolve=r;}));const change=jest.fn();
 render(<TickerPicker value="SPY" onChange={change} tickers={["SPY","QQQ"]}/>);const input=screen.getByRole("combobox");
 fireEvent.change(input,{target:{value:"COIN"}});fireEvent.keyDown(input,{key:"Enter"});
 await waitFor(()=>expect(resolve).toBeTruthy());fireEvent.change(input,{target:{value:"QQQ"}});fireEvent.click(screen.getByRole("option",{name:"QQQ"}));
 await act(async()=>resolve({data:{instruments:[{symbol:"COIN"}]}}));expect(change.mock.calls).toEqual([["QQQ"]]);
});

test("exact provider lookup reaches later directory pages",async()=>{
 axios.get.mockResolvedValueOnce({data:{instruments:[{symbol:"AZ"}],has_more:true,asof:"one"}}).mockResolvedValueOnce({data:{instruments:[{symbol:"Z"}],has_more:false,asof:"one"}});
 const change=jest.fn();render(<TickerPicker value="SPY" tickers={["SPY"]} onChange={change}/>);const input=screen.getByRole("combobox");
 fireEvent.change(input,{target:{value:"Z"}});fireEvent.keyDown(input,{key:"Enter"});await waitFor(()=>expect(change).toHaveBeenCalledWith("Z"));expect(axios.get.mock.calls.map(([,options])=>options.params.page)).toEqual([1,2]);
});
test("favorite changes update another mounted picker without touching other settings",()=>{
 localStorage.setItem("th-prefs-v1",JSON.stringify({universe:["QQQ"]}));render(<><TickerPicker value="SPY" tickers={["SPY"]} ariaLabel="First stocks"/><TickerPicker value="SPY" tickers={["SPY"]} ariaLabel="Second stocks"/></>);
 fireEvent.click(screen.getAllByRole("button",{name:"Add SPY to favorites"})[0]);expect(screen.getAllByRole("button",{name:"Remove SPY from favorites"})).toHaveLength(2);
 expect(JSON.parse(localStorage.getItem("th-prefs-v1"))).toEqual({universe:["QQQ"]});
});
test("a changed provider page cannot confirm a different generation",async()=>{
 axios.get.mockResolvedValueOnce({data:{instruments:[{symbol:"AZ"}],has_more:true,asof:"old"}}).mockResolvedValueOnce({data:{instruments:[{symbol:"Z"}],has_more:false,asof:"new"}});
 const change=jest.fn();render(<TickerPicker value="SPY" tickers={["SPY"]} onChange={change}/>);const input=screen.getByRole("combobox");
 fireEvent.change(input,{target:{value:"Z"}});fireEvent.keyDown(input,{key:"Enter"});expect(await screen.findByRole("alert")).toHaveTextContent("could not be confirmed");expect(change).not.toHaveBeenCalled();
});

test("changing the owning selection invalidates an older provider lookup",async()=>{
 let resolve;axios.get.mockImplementation(()=>new Promise(r=>{resolve=r;}));const change=jest.fn();const tickers=["SPY","QQQ"];
 const view=render(<TickerPicker value="SPY" tickers={tickers} onChange={change}/>);const input=screen.getByRole("combobox");fireEvent.change(input,{target:{value:"COIN"}});fireEvent.keyDown(input,{key:"Enter"});
 await waitFor(()=>expect(resolve).toBeTruthy());view.rerender(<TickerPicker value="QQQ" tickers={tickers} onChange={change}/>);
 await act(async()=>resolve({data:{instruments:[{symbol:"COIN"}]}}));expect(change).not.toHaveBeenCalled();expect(screen.getByText("Selected QQQ")).toBeInTheDocument();
});

test("unreadable favorites are visible and never replaced by a blind save",()=>{
 const get=jest.spyOn(Storage.prototype,"getItem").mockImplementation(()=>{throw new Error("unavailable");});const set=jest.spyOn(Storage.prototype,"setItem");
 render(<TickerPicker value="SPY" tickers={["SPY"]}/>);expect(screen.getByRole("alert")).toHaveTextContent("favorites could not be read");
 fireEvent.click(screen.getByRole("button",{name:"Add SPY to favorites"}));expect(set).not.toHaveBeenCalled();get.mockRestore();set.mockRestore();
});
test("clicking a dropdown option returns focus to the search field",()=>{
 render(<TickerPicker value="SPY" tickers={["SPY","QQQ"]}/>);const input=screen.getByRole("combobox");fireEvent.focus(input);fireEvent.click(screen.getByRole("option",{name:"QQQ"}));expect(input).toHaveFocus();expect(input).toHaveAttribute("aria-expanded","false");
});

test("moving focus outside closes the dropdown and aborts a pending lookup",async()=>{
 let resolve;axios.get.mockImplementation(()=>new Promise(r=>{resolve=r;}));const change=jest.fn();render(<><TickerPicker value="SPY" tickers={["SPY"]} onChange={change}/><button type="button">Other task</button></>);
 const input=screen.getByRole("combobox");fireEvent.change(input,{target:{value:"COIN"}});fireEvent.keyDown(input,{key:"Enter"});await waitFor(()=>expect(resolve).toBeTruthy());
 act(()=>screen.getByRole("button",{name:"Other task"}).focus());expect(input).toHaveAttribute("aria-expanded","false");expect(axios.get.mock.calls[0][1].signal.aborted).toBe(true);
 await act(async()=>resolve({data:{instruments:[{symbol:"COIN"}]}}));expect(change).not.toHaveBeenCalled();
});
