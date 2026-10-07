import React from "react";
import {act,fireEvent,render,screen,waitFor} from "@testing-library/react";
import axios from "axios";
import SavedChartReadings from "./SavedChartReadings";
jest.mock("axios",()=>({get:jest.fn()}));
const row=(n,ticker="SPY")=>({decision_id:"dec_"+n,ticker,at_ts:"2026-10-06T09:26:07.754388+00:00",snapshot_id:"snap_"+n,n_quotes:20,features_status:"available",reason_codes_status:"available",review_status:"available"});
const page=(n,{ticker="SPY",order="newest",more=false}={})=>({ticker,order,decisions:[row(n,ticker)],count:1,status:"available",has_more:more,next_cursor:more?"next-position":null});
beforeEach(()=>{axios.get.mockReset();});
test("older readings load only on demand and opening a stored chart is explicit",async()=>{
 axios.get.mockResolvedValue({data:page(1,{more:true})});const open=jest.fn();render(<SavedChartReadings ticker="SPY" onOpen={open}/>);expect(axios.get).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));expect(await screen.findByText("20 saved option quotes")).toBeVisible();expect(open).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Open saved chart"}));expect(open).toHaveBeenCalledWith("snap_1");expect(axios.get).toHaveBeenCalledTimes(1);
});
test("first saved and subsequent pages keep their order and replace the current page",async()=>{
 axios.get.mockResolvedValueOnce({data:page(1,{more:true})}).mockResolvedValueOnce({data:page(2,{order:"oldest",more:true})}).mockResolvedValueOnce({data:page(3,{order:"oldest"})});
 render(<SavedChartReadings ticker="SPY"/>);fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));await screen.findByText("20 saved option quotes");
 fireEvent.click(screen.getByRole("button",{name:"First saved"}));await waitFor(()=>expect(axios.get).toHaveBeenCalledTimes(2));await screen.findByRole("button",{name:"Later readings"});
 expect(axios.get.mock.calls[1][1].params).toEqual({limit:20,order:"oldest"});
 fireEvent.click(screen.getByRole("button",{name:"Later readings"}));await waitFor(()=>expect(axios.get).toHaveBeenCalledTimes(3));await waitFor(()=>expect(screen.queryByRole("button",{name:"Later readings"})).not.toBeInTheDocument());
 expect(axios.get.mock.calls[2][1].params).toEqual({limit:20,order:"oldest",cursor:"next-position"});expect(screen.getAllByText("20 saved option quotes")).toHaveLength(1);
});
test("a delayed older stock page cannot replace the newly selected stock",async()=>{
 let finish;axios.get.mockImplementation(url=>String(url).includes("/SPY/")?new Promise(r=>{finish=r;}):Promise.resolve({data:page(2,{ticker:"QQQ"})}));
 const v=render(<SavedChartReadings ticker="SPY"/>);fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));v.rerender(<SavedChartReadings ticker="QQQ"/>);await screen.findByText(/QQQ saved readings/);
 await act(async()=>{finish({data:page(1)});});expect(screen.queryByText(/SPY saved readings/)).not.toBeInTheDocument();expect(axios.get.mock.calls[0][1].signal.aborted).toBe(true);
});
test.each(["wrong-stock","wrong-order","oversized","bad-clock","duplicate","bad-position"])("a malformed saved page remains an error without opening a chart: %s",async kind=>{
 const p=page(1);if(kind==="wrong-stock")p.ticker="QQQ";if(kind==="wrong-order")p.order="oldest";if(kind==="oversized"){p.decisions=Array.from({length:21},(_,n)=>row(n));p.count=21;}if(kind==="bad-clock")p.decisions[0].at_ts="2026-10-06T09:00:00";if(kind==="duplicate"){p.decisions.push(row(1));p.count=2;}if(kind==="bad-position"){p.has_more=true;p.next_cursor=null;}
 axios.get.mockResolvedValue({data:p});const open=jest.fn();render(<SavedChartReadings ticker="SPY" onOpen={open}/>);fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/);expect(open).not.toHaveBeenCalled();expect(screen.queryByRole("button",{name:"Open saved chart"})).not.toBeInTheDocument();
});
test("missing saved details stay readable and missing quotes do not become zero",async()=>{
 const p=page(1);p.status="partial";p.decisions[0].features_status="unavailable";p.decisions[0].n_quotes=null;p.decisions[0].snapshot_id=null;axios.get.mockResolvedValue({data:p});render(<SavedChartReadings ticker="SPY"/>);fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));expect(await screen.findByText("Saved quote details unavailable")).toBeVisible();expect(screen.getByRole("status")).toHaveTextContent(/Some saved details are missing/);expect(screen.getByRole("button",{name:"Open saved chart"})).toBeDisabled();expect(screen.queryByText("0 saved option quotes")).not.toBeInTheDocument();
});
test("closing history aborts its current read",async()=>{
 axios.get.mockReturnValue(new Promise(()=>{}));render(<SavedChartReadings ticker="SPY"/>);fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));const signal=axios.get.mock.calls[0][1].signal;fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));expect(signal.aborted).toBe(true);
});

test("a recovered summary keeps the reported count separate from missing quote details",async()=>{
 const p=page(1);p.status="partial";Object.assign(p.decisions[0],{quote_status:"summary_only",n_quotes:null,reported_n_quotes:20,snapshot_available:false});axios.get.mockResolvedValue({data:p});render(<SavedChartReadings ticker="SPY" onOpen={jest.fn()}/>);fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));expect(await screen.findByText("Saved quote details unavailable")).toBeVisible();expect(screen.getByText(/Recovered summary reported 20 quotes/)).toBeVisible();expect(screen.getByRole("button",{name:"Open saved chart"})).toBeDisabled();
});


test("the saved page reports a missing native snapshot without enabling a chart",async()=>{
 const p=page(1);p.status="partial";Object.assign(p.decisions[0],{quote_status:"available",snapshot_status:"unavailable"});axios.get.mockResolvedValue({data:p});const open=jest.fn();render(<SavedChartReadings ticker="SPY" onOpen={open}/>);fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));await screen.findByText("20 saved option quotes");expect(screen.getByRole("button",{name:"Open saved chart"})).toBeDisabled();fireEvent.click(screen.getByRole("button",{name:"Open saved chart"}));expect(open).not.toHaveBeenCalled();
});

test("a recovered summary can open its proven saved chart without claiming missing quotes",async()=>{
 const p=page(1);p.status="partial";Object.assign(p.decisions[0],{quote_status:"summary_only",n_quotes:null,reported_n_quotes:20,snapshot_status:"available"});axios.get.mockResolvedValue({data:p});const open=jest.fn();render(<SavedChartReadings ticker="SPY" onOpen={open}/>);fireEvent.click(screen.getByRole("button",{name:"Saved chart readings"}));await screen.findByText(/Recovered summary reported 20 quotes/);expect(screen.getByText("Saved quote details unavailable")).toBeVisible();fireEvent.click(screen.getByRole("button",{name:"Open saved chart"}));expect(open).toHaveBeenCalledWith("snap_1");
});
