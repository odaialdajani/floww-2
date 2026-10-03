import React,{useState} from "react";
import {act,render,screen,fireEvent,waitFor} from "@testing-library/react";
import axios from "axios";
import useScreenContext,{usePublishScreenContext} from "../../agent/useScreenContext";
import TidehunterPublicBridge from "./TidehunterPublicBridge";

jest.mock("axios",()=>({get:jest.fn()}));
const source={page:"flowseeker-pro",ticker:"SPY",selectedContract:"pro-display-ckey",selectedStrike:500,selectedExpiry:"2026-10-02",selectedType:"call",observedAt:"2026-10-02T14:30:00Z"};
const packet={ticker:"SPY",snapshotId:"separate-record",asof:"2026-10-02T14:45:00Z",data_source:"fixture",formula_version:"gex.v2",map_query:{mode:"day",expiries:4,dte:null},grid:{strikes:[500],expiries:["2026-10-02"]}};
const identity={osi:"SPY261002C00500000",strike:"500",expiry:"2026-10-02",type:"call",series:"SPY"};
function Publisher({context}){usePublishScreenContext(context);return null;}
function Current(){const[c]=useScreenContext();return <output data-testid="published-bridge">{JSON.stringify(c)}</output>;}
function Scene({selection=source}){const[review,setReview]=useState(false);return <><Publisher context={review?null:selection}/><TidehunterPublicBridge onReviewActive={setReview}/><Current/></>;}
beforeEach(()=>axios.get.mockImplementation(async url=>String(url).includes("/contract")?{data:{status:"ok",ticker:"SPY",snapshot_id:"separate-record",matched_identity:identity,quote:{bid:1,ask:1.1},multiplier:{value:100,source:"fixture"}}}:{data:packet}));

test("Pro ckey is display-only; exact identity resolves before a separate, dated Public review",async()=>{
 render(<Scene/>);
 expect(axios.get).not.toHaveBeenCalled();
 await act(async()=>fireEvent.click(screen.getByRole("button",{name:"Resolve a separate Public review"})));
 expect(screen.getByRole("dialog",{name:"Separate Public contract review"})).toBeInTheDocument();
 const params=axios.get.mock.calls.find(([url])=>String(url).includes("/contract"))[1].params;
 expect(params).toEqual({strike:"500",expiry:"2026-10-02",type:"call",snapshot_id:"separate-record"});
 expect(params.osi).toBeUndefined();
 expect(screen.getByText(/New owning observation: separate-record/)).toBeVisible();
 expect(screen.getByText(/Pro source time: 2026-10-02T14:30:00Z/)).toBeVisible();
 expect(JSON.parse(screen.getByTestId("published-bridge").textContent)).toMatchObject({page:"flowseeker-pro",bridgeVersion:"tidehunter-public-review.v1",snapshotId:"separate-record",selectedContract:identity,contractResolution:"resolved"});
 fireEvent.click(screen.getByRole("button",{name:"Close separate Public review"}));
 expect(JSON.parse(screen.getByTestId("published-bridge").textContent).selectedContract).toBe("pro-display-ckey");
 expect(axios.get.mock.calls.some(([url])=>/order|preflight|approval/.test(String(url)))).toBe(false);
});

test("conflicting symbol or incomplete contract refuses; no nearest substitute",async()=>{
 axios.get.mockResolvedValue({data:{...packet,ticker:"QQQ"}});
 render(<Scene/>);
 await act(async()=>fireEvent.click(screen.getByRole("button",{name:"Resolve a separate Public review"})));
 expect(screen.getByText(/OBSERVATION_IDENTITY_MISMATCH/)).toBeVisible();
 expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
 expect(axios.get).toHaveBeenCalledTimes(1);
});

test("symbol changes abort the owned request and cannot publish its late exact result",async()=>{
 let release,signal;
 axios.get.mockImplementation((url,opts)=>{signal=opts.signal;return new Promise(resolve=>{release=resolve;});});
 const view=render(<Scene/>);
 fireEvent.click(screen.getByRole("button",{name:"Resolve a separate Public review"}));
 await waitFor(()=>expect(release).toBeTruthy());
 view.rerender(<Scene selection={{...source,ticker:"QQQ"}}/>);
 expect(signal.aborted).toBe(true);
 await act(async()=>release({data:packet}));
 expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
 expect(JSON.parse(screen.getByTestId("published-bridge").textContent).ticker).toBe("QQQ");
});
