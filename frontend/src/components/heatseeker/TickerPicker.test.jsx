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


const feedCounts=()=>{const now=Date.now()/1000;return {status:"available",checked_at:new Date().toISOString(),directory:{available:true,stale:false,total:3000,optionable_total:800,sectors:["Technology"],sector_classified:2},options:{received_recently:2,receipt_times:[now-2,now-3],window_seconds:300,last_scan_at:now-2},provider:{last_success_at:now-5}};};
test("global stock counts stay visible with the dropdown closed and distinguish reads from listed names",async()=>{axios.get.mockResolvedValue({data:feedCounts()});render(<TickerPicker value="SPY" tickers={["SPY","AMD"]} className="floww-header-symbol-picker"/>);await waitFor(()=>expect(screen.getByTestId("stock-feed-counts")).toHaveTextContent("3,000 listed"));expect(screen.getByTestId("stock-feed-counts")).toHaveTextContent("2 stocks checked / 800 with options in 5 min");expect(screen.queryByRole("listbox")).toBeNull();expect(screen.getByTestId("stock-feed-counts")).toBeVisible();});
test("global categories use provider options and supplied sectors without changing scanning scope",async()=>{const change=jest.fn();axios.get.mockImplementation(async(url,options)=>({data:String(url).includes("/market/status")?feedCounts():{instruments:[{symbol:"AMD",options:true,sector:"Technology"}],matches:1,stale:false}}));render(<TickerPicker value="SPY" tickers={["SPY","AMD","NOPT"]} onChange={change} className="floww-header-symbol-picker"/>);await waitFor(()=>expect(screen.getByTestId("stock-feed-counts")).toHaveTextContent("3,000 listed"));fireEvent.focus(screen.getByRole("combobox",{name:"Search stocks"}));fireEvent.change(screen.getByRole("combobox",{name:"Stock category"}),{target:{value:"options"}});await waitFor(()=>expect(screen.getByRole("option",{name:"AMD"})).toBeInTheDocument());expect(screen.queryByRole("option",{name:"NOPT"})).toBeNull();fireEvent.change(screen.getByRole("combobox",{name:"Stock sector"}),{target:{value:"Technology"}});await waitFor(()=>expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/market/catalog"),expect.objectContaining({params:expect.objectContaining({options_only:true,sector:"Technology"})})));await waitFor(()=>expect(screen.getByRole("option",{name:"AMD"})).toBeInTheDocument());fireEvent.click(screen.getByRole("option",{name:"AMD"}));expect(change).toHaveBeenCalledWith("AMD");expect(axios.get.mock.calls.every(([url])=>!String(url).includes("scan"))).toBe(true);});
test("missing sector details stay unavailable rather than guessed from a ticker",async()=>{const b=feedCounts();axios.get.mockResolvedValue({data:{...b,directory:{...b.directory,sectors:[],sector_classified:0}}});render(<TickerPicker value="SPY" tickers={["SPY","AMD"]} className="floww-header-symbol-picker"/>);await waitFor(()=>expect(screen.getByTestId("stock-feed-counts")).toHaveTextContent("3,000 listed"));fireEvent.focus(screen.getByRole("combobox",{name:"Search stocks"}));expect(screen.getByRole("combobox",{name:"Stock sector"})).toBeDisabled();expect(screen.getByRole("option",{name:"Sector details unavailable"})).toBeInTheDocument();});
test("favorite category narrows browsing without rewriting the full list",async()=>{localStorage.setItem(FAVORITES_KEY,JSON.stringify(["SPY"]));axios.get.mockImplementation(async url=>({data:String(url).includes("/market/status")?feedCounts():{instruments:[{symbol:"SPY",options:true},{symbol:"AMD",options:true}],matches:2,stale:false}}));render(<TickerPicker value="SPY" tickers={["SPY","AMD"]} className="floww-header-symbol-picker"/>);fireEvent.focus(screen.getByRole("combobox",{name:"Search stocks"}));fireEvent.change(screen.getByRole("combobox",{name:"Stock category"}),{target:{value:"favorites"}});expect(screen.getByRole("option",{name:"SPY"})).toBeInTheDocument();expect(screen.queryByRole("option",{name:"AMD"})).toBeNull();fireEvent.change(screen.getByRole("combobox",{name:"Stock category"}),{target:{value:"all"}});await waitFor(()=>expect(screen.getByRole("option",{name:"AMD"})).toBeInTheDocument());expect(JSON.parse(localStorage.getItem(FAVORITES_KEY))).toEqual(["SPY"]);});
test("changing category aborts a delayed group instead of showing old filtered results",async()=>{const pending=[];axios.get.mockImplementation((url,options)=>String(url).includes("/market/status")?Promise.resolve({data:feedCounts()}):new Promise(resolve=>pending.push({resolve,signal:options.signal,params:options.params})));render(<TickerPicker value="SPY" tickers={["SPY","AMD"]} className="floww-header-symbol-picker"/>);fireEvent.focus(screen.getByRole("combobox",{name:"Search stocks"}));fireEvent.change(screen.getByRole("combobox",{name:"Stock category"}),{target:{value:"options"}});await waitFor(()=>expect(pending).toHaveLength(1));fireEvent.change(screen.getByRole("combobox",{name:"Stock category"}),{target:{value:"all"}});expect(pending[0].signal.aborted).toBe(true);await act(async()=>pending[0].resolve({data:{instruments:[{symbol:"NOPT",options:false}],matches:1}}));expect(screen.queryByRole("option",{name:"NOPT"})).toBeNull();await waitFor(()=>expect(pending).toHaveLength(2));expect(pending[1].params.options_only).toBe(false);await act(async()=>pending[1].resolve({data:{instruments:[{symbol:"SPY",options:true}],matches:1}}));expect(screen.getByRole("option",{name:"SPY"})).toBeInTheDocument();});


test("global All listed searches provider names beyond the incomplete local fallback",async()=>{
 const change=jest.fn();axios.get.mockImplementation(async(url,options)=>({data:String(url).includes("/market/status")?feedCounts():{instruments:[{symbol:options.params.q==="BEYOND"?"BEYOND":"OUTSIDE",options:true}],matches:1,stale:false}}));
 render(<TickerPicker value="SPY" tickers={["SPY","QQQ"]} status="incomplete" className="floww-header-symbol-picker" onChange={change}/>);
 const input=screen.getByRole("combobox",{name:"Search stocks"});fireEvent.focus(input);
 await waitFor(()=>expect(screen.getByRole("option",{name:"OUTSIDE"})).toBeInTheDocument());
 fireEvent.change(input,{target:{value:"BEYOND"}});
 await waitFor(()=>expect(screen.getByRole("option",{name:"BEYOND"})).toBeInTheDocument());
 expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/market/catalog"),expect.objectContaining({params:expect.objectContaining({q:"BEYOND",page:1,limit:30,options_only:false})}));
 fireEvent.click(screen.getByRole("option",{name:"BEYOND"}));expect(change).toHaveBeenCalledWith("BEYOND");
});
test("global All listed pages use provider counts and keyboard selects the loaded page identity",async()=>{
 const batch=Array.from({length:30},(_,i)=>({symbol:"NAME"+i,options:true}));const change=jest.fn();
 axios.get.mockImplementation(async(url,options)=>({data:String(url).includes("/market/status")?feedCounts():{instruments:options.params.page===1?batch:[{symbol:"LAST",options:true}],matches:31,stale:false}}));
 render(<TickerPicker value="SPY" tickers={["SPY"]} className="floww-header-symbol-picker" onChange={change}/>);const input=screen.getByRole("combobox",{name:"Search stocks"});fireEvent.focus(input);
 await waitFor(()=>expect(screen.getByRole("option",{name:"NAME0"})).toBeInTheDocument());fireEvent.click(screen.getByRole("button",{name:"Next"}));
 await waitFor(()=>expect(screen.getByRole("option",{name:"LAST"})).toBeInTheDocument());
 fireEvent.keyDown(input,{key:"Enter"});expect(change).toHaveBeenCalledWith("LAST");expect(axios.get.mock.calls.filter(([url])=>String(url).includes("/market/catalog")).map(([,options])=>options.params.page)).toEqual([1,2]);
});
test("failed global All query keeps results unknown instead of falling back to a partial list or zero matches",async()=>{
 axios.get.mockImplementation(async url=>{if(String(url).includes("/market/status"))return {data:feedCounts()};throw Error("unavailable");});
 render(<TickerPicker value="SPY" tickers={["SPY"]} className="floww-header-symbol-picker"/>);fireEvent.focus(screen.getByRole("combobox",{name:"Search stocks"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("stock group could not be loaded");expect(screen.queryByRole("option",{name:"SPY"})).toBeNull();
 expect(document.querySelector(".ticker-picker-result-count")).toHaveTextContent("Unknown listed stocks");expect(document.querySelector(".ticker-picker-result-count")).not.toHaveTextContent("0 listed stocks");
});
test("favorite category reaches saved IDs absent from the local fallback while selection still checks the provider",async()=>{
 localStorage.setItem(FAVORITES_KEY,JSON.stringify(["BEYOND"]));const change=jest.fn();
 axios.get.mockImplementation(async url=>({data:String(url).includes("/market/status")?feedCounts():{instruments:[{symbol:"BEYOND",options:true}],matches:1,has_more:false,stale:false}}));
 render(<TickerPicker value="SPY" tickers={["SPY"]} className="floww-header-symbol-picker" onChange={change}/>);fireEvent.focus(screen.getByRole("combobox",{name:"Search stocks"}));fireEvent.change(screen.getByRole("combobox",{name:"Stock category"}),{target:{value:"favorites"}});
 expect(screen.getByRole("option",{name:"BEYOND"})).toBeInTheDocument();fireEvent.click(screen.getByRole("option",{name:"BEYOND"}));await waitFor(()=>expect(change).toHaveBeenCalledWith("BEYOND"));
});


test("a delayed global All query cannot replace the newer provider query",async()=>{
 const requests=[];axios.get.mockImplementation((url,options)=>String(url).includes("/market/status")?Promise.resolve({data:feedCounts()}):new Promise(resolve=>requests.push({resolve,params:options.params,signal:options.signal})));
 const change=jest.fn();render(<TickerPicker value="SPY" tickers={["SPY"]} className="floww-header-symbol-picker" onChange={change}/>);const input=screen.getByRole("combobox",{name:"Search stocks"});
 fireEvent.change(input,{target:{value:"OLDER"}});await waitFor(()=>expect(requests).toHaveLength(1));
 fireEvent.change(input,{target:{value:"NEWER"}});expect(requests[0].signal.aborted).toBe(true);await waitFor(()=>expect(requests).toHaveLength(2));
 await act(async()=>requests[1].resolve({data:{instruments:[{symbol:"NEWER",options:true}],matches:1,page:1,limit:30}}));
 await act(async()=>requests[0].resolve({data:{instruments:[{symbol:"OLDER",options:true}],matches:1,page:1,limit:30}}));
 expect(screen.queryByRole("option",{name:"OLDER"})).toBeNull();fireEvent.click(screen.getByRole("option",{name:"NEWER"}));expect(change.mock.calls).toEqual([["NEWER"]]);
});
test("an empty incomplete provider directory stays unknown and retries only its bounded page",async()=>{
 let attempts=0;axios.get.mockImplementation(async(url,options)=>{if(String(url).includes("/market/status"))return {data:feedCounts()};attempts++;return {data:attempts===1?{instruments:[],matches:0,complete_provider_catalog:false,page:1,limit:30}:{instruments:[{symbol:"BEYOND",options:true}],matches:1,complete_provider_catalog:true,page:1,limit:30}};});
 render(<TickerPicker value="SPY" tickers={["SPY"]} className="floww-header-symbol-picker"/>);fireEvent.focus(screen.getByRole("combobox",{name:"Search stocks"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("Matches are unavailable");expect(document.querySelector(".ticker-picker-result-count")).toHaveTextContent("Unknown listed stocks");
 fireEvent.click(screen.getByRole("button",{name:"Retry stock group"}));await waitFor(()=>expect(screen.getByRole("option",{name:"BEYOND"})).toBeInTheDocument());
 expect(axios.get.mock.calls.filter(([url])=>String(url).includes("/market/catalog")).map(([,options])=>options.params)).toEqual([{page:1,limit:30,q:"",options_only:false},{page:1,limit:30,q:"",options_only:false}]);
});
test("global All refuses a mismatched provider page or rows outside the typed query",async()=>{
 axios.get.mockImplementation(async url=>({data:String(url).includes("/market/status")?feedCounts():{instruments:[{symbol:"WRONG",options:true}],matches:1,page:2,limit:30}}));
 render(<TickerPicker value="SPY" tickers={["SPY"]} className="floww-header-symbol-picker"/>);fireEvent.change(screen.getByRole("combobox",{name:"Search stocks"}),{target:{value:"RIGHT"}});
 expect(await screen.findByRole("alert")).toHaveTextContent("Matches are unavailable");expect(screen.queryByRole("option",{name:"WRONG"})).toBeNull();
});


test("the global dropdown opens the full provider directory without losing its modal",async()=>{
 axios.get.mockImplementation(async(url,options)=>({data:String(url).includes("/market/status")?feedCounts():options.params.limit===100?{instruments:[{symbol:"NVDA",options:true}],matches:1,total:13174,optionable_total:8838,complete_provider_catalog:false,has_more:false,stale:true,asof:"2026-10-07T12:00:00Z",page:1,limit:100}:{instruments:[{symbol:"SPY",options:true}],matches:1,complete_provider_catalog:true,page:1,limit:30}}));
 function GlobalChoice(){const [ticker,setTicker]=React.useState("SPY");return <TickerPicker value={ticker} onChange={setTicker} tickers={["SPY"]} className="floww-header-symbol-picker"/>;}
 render(<GlobalChoice/>);fireEvent.click(screen.getByRole("button",{name:"Browse stock list"}));
 fireEvent.click(screen.getByRole("button",{name:"Full stock directory"}));
 const dialog=await screen.findByRole("dialog",{name:"Stocks and funds"});
 expect(screen.queryByRole("listbox")).toBeNull();expect(screen.queryByRole("button",{name:"Browse all stocks"})).toBeNull();
 await screen.findByRole("button",{name:"NVDA",exact:true});
 expect(dialog).toHaveTextContent("13,174 available");expect(dialog).toHaveTextContent("Saved list; refresh unavailable");
 expect(dialog).toHaveTextContent("2026");expect(dialog).toHaveTextContent("New York");
 expect(dialog).toHaveTextContent("full provider list is unavailable");
 act(()=>screen.getByRole("textbox",{name:"Search full stock list"}).focus());
 expect(screen.getByRole("dialog",{name:"Stocks and funds"})).toBe(dialog);
 fireEvent.click(screen.getByRole("button",{name:"NVDA",exact:true}));
 expect(screen.getByText("Selected NVDA")).toBeInTheDocument();
 expect(screen.queryByRole("dialog")).toBeNull();expect(screen.queryByRole("listbox")).toBeNull();
 expect(screen.getByRole("button",{name:"Browse stock list"})).toHaveFocus();
 expect(axios.get.mock.calls.every(([url])=>!String(url).includes("scan"))).toBe(true);
});

test("the full directory remains reachable when quick search fails and retries its own read",async()=>{
 let fullAttempts=0;axios.get.mockImplementation(async(url,options)=>{if(String(url).includes("/market/status"))return {data:feedCounts()};if(options.params.limit!==100)throw Error("quick unavailable");fullAttempts++;if(fullAttempts===1)throw Error("full unavailable");return {data:{instruments:[{symbol:"AMD",options:true}],matches:1,total:1,optionable_total:1,complete_provider_catalog:true,has_more:false,stale:false,asof:null,page:1,limit:100}};});
 render(<TickerPicker value="SPY" tickers={null} className="floww-header-symbol-picker"/>);fireEvent.click(screen.getByRole("button",{name:"Browse stock list"}));
 await screen.findByText(/stock group could not be loaded/);fireEvent.click(screen.getByRole("button",{name:"Full stock directory"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("stock list could not be loaded");
 fireEvent.click(screen.getByRole("button",{name:"Retry",exact:true}));
 await screen.findByRole("button",{name:"AMD",exact:true});expect(screen.getByRole("dialog")).toHaveTextContent("List time unknown");
 fireEvent.click(screen.getByRole("button",{name:"Close stock directory"}));expect(screen.queryByRole("dialog")).toBeNull();expect(screen.queryByRole("listbox")).toBeNull();
 expect(fullAttempts).toBe(2);
});
