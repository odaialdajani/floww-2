import React from "react";
import {act,render,screen,fireEvent,waitFor} from "@testing-library/react";
import PublicHandoffReview from "./PublicHandoffReview";

const selection={page:"trinity",ticker:"SPY",snapshotId:"record-1",mapVersion:"2026-10-02T14:45:00Z",selectedWall:"wall-1",selectedExpiry:"2026-10-02",overlayMetric:"delta",selectedContract:{osi:"SPY261002C00500000"},displayMode:"live"};
const turn={turn_id:"turn-1",status:"completed",answer:{context:selection,plan_draft:{version:"trade-plan-draft.v1",draft_id:"draft-1",context_hash:"a".repeat(64),created_at:"2026-10-02T14:45:00Z",correlation_id:"turn-1",selection:{...selection,metric:"gex",wall_bounds:{id:"wall-1",low:499,high:501}},contract:{osi:selection.selectedContract.osi,strike:"500",expiry:"2026-10-02",type:"call",snapshot_id:"record-1",bid:1,ask:1.1,quote_usage:"recorded_research_only"},evidence_ids:["evidence-1"],observation_ids:["record-1"],executable:false,blockers:["PREFLIGHT_REQUIRED","COMMISSIONING_POLICY_UNSET"]}}};
beforeEach(()=>{
 global.fetch=jest.fn(async()=>({ok:true,json:async()=>({handoff_id:"saved-report",broker_verified:false,activation:"unverified"})}));
 Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText:jest.fn(async()=>{})}});
});

test("native brief requires explicit owner; copy is not activation and policy stays UNSET",async()=>{
 render(<PublicHandoffReview selection={selection} turn={turn} grounded/>);
 expect(screen.getByRole("button",{name:"Prepare dated brief"})).toBeDisabled();
 fireEvent.change(screen.getByLabelText("Execution owner"),{target:{value:"PUBLIC_NATIVE_AGENT"}});
 fireEvent.click(screen.getByRole("button",{name:"Prepare dated brief"}));
 const brief=screen.getByLabelText("Editable Public brief");
 expect(brief.value).toContain("Account: UNSET");
 expect(brief.value).toContain("Premium budget: UNSET");
 expect(brief.value).toContain("SPY261002C00500000");
 expect(brief.value).toContain("Raw wall: wall-1 · 499–501 USD");
 expect(brief.value).toContain("Metric / basis: gex / delta");
 expect(brief.value).toContain("Source workspace: trinity");
 expect(brief.value).toContain("11:30–14:00 America/New_York");
 expect(brief.value).toContain("not remote trace ingestion");
 await act(async()=>fireEvent.click(screen.getByRole("button",{name:"Copy brief"})));
 expect(screen.getByText(/Copied only — delivery and activation are unverified/)).toBeVisible();
 expect(global.fetch).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText("Reviewed workflow reference"),{target:{value:"operator-reference"}});
 fireEvent.change(screen.getByLabelText("Operator-reported workflow status"),{target:{value:"reviewed"}});
 await act(async()=>fireEvent.click(screen.getByRole("button",{name:"Save manual handoff report"})));
 const [url,opts]=global.fetch.mock.calls[0];
 expect(url).toMatch(/\/agent\/handoffs$/);
 expect(opts.credentials).toBe("include");
 expect(JSON.parse(opts.body)).toMatchObject({turn_id:"turn-1",context_hash:"a".repeat(64),execution_owner:"PUBLIC_NATIVE_AGENT",reported_status:"reviewed",workflow_reference:"operator-reference"});
 expect(JSON.parse(opts.body)).not.toHaveProperty("approved");
 expect(screen.getByText(/Saved operator report — broker status and activation remain unverified/)).toBeVisible();
});

test('manual draft contains explicit unresolved entry, expiry, notification and risk instructions without inventing a limit',()=>{
 render(<PublicHandoffReview selection={selection} turn={turn} grounded/>);
 fireEvent.change(screen.getByLabelText('Execution owner'),{target:{value:'PUBLIC_NATIVE_AGENT'}});
 fireEvent.click(screen.getByRole('button',{name:'Prepare dated brief'}));
 const brief=screen.getByLabelText('Editable Public brief').value;
 for(const field of ['Limit price: UNSET','Quantity: UNSET','Entry conditions: UNSET','Trading window: UNSET','Expiry handling: UNSET','Notifications: UNSET'])expect(brief).toContain(field);
 expect(brief).toContain('Recorded symbol: SPY');
 expect(brief).toContain('Account entitlement and current broker support: UNVERIFIED');
 expect(brief).toContain('Risks: premium loss, liquidity/spread, gap/slippage, expiration and assignment');
 expect(brief).not.toContain('Limit price: 1.1');
 expect(global.fetch).not.toHaveBeenCalled();
});

test("backend owner refuses without immutable preflight, policy, approval and overlap inventory",()=>{
 render(<PublicHandoffReview selection={selection} turn={turn} grounded/>);
 fireEvent.change(screen.getByLabelText("Execution owner"),{target:{value:"FLOWW_BACKEND"}});
 expect(screen.getByRole("button",{name:"Prepare dated brief"})).toBeDisabled();
 expect(screen.getByText(/unresolved native ownership overlap/)).toBeVisible();
 expect(global.fetch).not.toHaveBeenCalled();
});

test.each(["snapshotId","selectedWall","overlayMetric","selectedExpiry","selectedContract"])("changing %s invalidates the brief and a late report",async field=>{
 let release;
 global.fetch.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
 const view=render(<PublicHandoffReview selection={selection} turn={turn} grounded/>);
 fireEvent.change(screen.getByLabelText("Execution owner"),{target:{value:"PUBLIC_NATIVE_AGENT"}});
 fireEvent.click(screen.getByRole("button",{name:"Prepare dated brief"}));
 fireEvent.click(screen.getByRole("button",{name:"Save manual handoff report"}));
 await waitFor(()=>expect(release).toBeTruthy());
 view.rerender(<PublicHandoffReview selection={{...selection,[field]:field==="selectedContract"?{osi:"OTHER"}:"changed"}} turn={turn} grounded/>);
 await act(async()=>release({ok:true,json:async()=>({handoff_id:"old",broker_verified:false})}));
 expect(screen.queryByLabelText("Editable Public brief")).not.toBeInTheDocument();
 expect(screen.queryByText(/Saved operator report/)).not.toBeInTheDocument();
 expect(screen.getByRole("button",{name:"Prepare dated brief"})).toBeDisabled();
});

test("revocation clears a prepared brief and refuses a late saved report",async()=>{
 const view=render(<PublicHandoffReview selection={selection} turn={turn} grounded/>);
 fireEvent.change(screen.getByLabelText("Execution owner"),{target:{value:"PUBLIC_NATIVE_AGENT"}});
 fireEvent.click(screen.getByRole("button",{name:"Prepare dated brief"}));
 act(()=>window.dispatchEvent(new Event("floww-research-session-ended")));
 expect(screen.queryByLabelText("Editable Public brief")).not.toBeInTheDocument();
 view.unmount();
});
