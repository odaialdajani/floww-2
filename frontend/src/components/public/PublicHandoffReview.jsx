import React, {useEffect, useRef, useState} from "react";
import {API} from "../../config/api";
import {useAgent} from "../../agent/AgentProvider";
import useScreenContext from "../../agent/useScreenContext";
import {contextIdentity} from "../../agent/contextIdentity";
import "./PublicReview.css";

export const POLICY_FIELDS = ["Account", "Allowed symbols / products", "Premium budget", "Daily loss limit", "Exposure limit", "Max positions", "Cash / margin", "Confirmation policy", "Quote-age limit", "Entry cutoff", "Expiry cutoff", "Protection behavior", "Rollback owner"];

function datedBrief(draft, owner) {
 const c=draft.contract,selection=draft.selection || {},wall=selection.wall_bounds;
 return [
  `FLOWW manual Public review · ${draft.created_at}`,
  "Do not activate or place orders. This research draft is not permission.",
  `Execution owner: ${owner}`,
  ...POLICY_FIELDS.map(label=>`${label}: UNSET`),
  `Recorded symbol: ${selection.ticker || "UNSET"}`,
  `Recorded contract: ${c.osi} · ${c.type} · strike ${c.strike} · expiry ${c.expiry}`,
  "Account entitlement and current broker support: UNVERIFIED. Exact recorded OSI is not executable permission; SPX support is not inferred from SPY.",
  "Limit price: UNSET. Do not derive an entry limit from the recorded bid/ask.",
  "Quantity: UNSET. Premium budget, fees and explicit cash/margin choice require operator policy and fresh preflight.",
  "Entry conditions: UNSET. Specify approach direction, owning price confirmation, invalidation and separate raw/adjusted/activity evidence; sign alone is not a trigger.",
  "Trading window: UNSET. Review exchange calendar, holidays, early closes and session boundaries in the selected execution owner.",
  "Expiry handling: UNSET. Review contract-specific close/roll/assignment deadlines and who handles uncovered or partial fills.",
  "Notifications: UNSET. Choose recipients/channels and alerts for trigger, fill, partial/reject, protection failure, expiry, pause and recovery. Delivery must be verified separately.",
  "Risks: premium loss, liquidity/spread, gap/slippage, expiration and assignment; unsupported protection, stale evidence and ownership overlap require refusal. No guaranteed outcome.",
  `Source workspace: ${selection.sourceWorkspace || selection.page || "unknown"}`,
  `Metric / basis: ${selection.metric || "unknown"} / ${selection.overlayMetric || "unknown"}`,
  `Raw wall: ${wall ? `${wall.id} · ${wall.low}–${wall.high} USD` : selection.selectedWall || "UNSET"}`,
  `Owning observation: ${c.snapshot_id} · capture/record version ${selection.mapVersion || "unknown"}`,
  `Quote-side event clocks: bid ${c.quote_clocks?.bid || "unknown"} / ask ${c.quote_clocks?.ask || "unknown"}`,
  `Recorded bid / ask: ${c.bid ?? "unavailable"} / ${c.ask ?? "unavailable"} USD. Not current executable quotes.`,
  "Request: pause NEW ENTRIES 11:30–14:00 America/New_York. Exchange holidays, early closes and DST must be enforced by the execution owner.",
  "Protection, risk exits, authenticated cancellation and reconciliation must stay active. A notification reminder is not an enforced entry rule.",
  "Native workflow/position/order ownership inventory: UNSET. Resolve overlap before any backend entry; a local lease cannot control a workflow created elsewhere.",
  "Restart: reconcile open/unknown orders before new entry. Never re-arm an expired or disarmed policy.",
  `Research correlation: ${draft.correlation_id}. Context: ${draft.context_hash}`,
  `Evidence: ${draft.evidence_ids.join(", ") || "none"}`,
  "These copied references are not remote trace ingestion. No continuous external-GEX feed is established.",
  "Public's internal agent model is separate from Lodestar. Review the full workflow in Public's builder; delivery and activation remain unverified.",
 ].join("\n");
}

export default function PublicHandoffReview({selection,turn,grounded=false}) {
 const identity=contextIdentity({selection,turn:turn?.turn_id,draft:turn?.answer?.plan_draft?.draft_id});
 return <HandoffForm key={identity} selection={selection} turn={turn} grounded={grounded}/>;
}

function HandoffForm({selection,turn,grounded}) {
 const [owner,setOwner]=useState(""),[brief,setBrief]=useState(""),[reference,setReference]=useState("");
 const [reported,setReported]=useState("prepared"),[notice,setNotice]=useState(""),[saving,setSaving]=useState(false),[revoked,setRevoked]=useState(false);
 const epoch=useRef(0),controller=useRef(null);
 const draft=turn?.answer?.plan_draft;
 const matches=grounded && !revoked && turn?.status==="completed" && draft?.version==="trade-plan-draft.v1"
  && draft.contract?.osi && contextIdentity(turn.answer.context)===contextIdentity(selection);
 const canPrepare=Boolean(matches && owner==="PUBLIC_NATIVE_AGENT");
 useEffect(()=>{
  const clear=()=>{epoch.current++;controller.current?.abort();setRevoked(true);setBrief("");setReference("");setNotice("");setSaving(false);};
  const storage=e=>{if(e.key==="floww-research-session-ended" && e.newValue)clear();};
  window.addEventListener("floww-research-session-ended",clear);window.addEventListener("storage",storage);
  return()=>{epoch.current++;controller.current?.abort();window.removeEventListener("floww-research-session-ended",clear);window.removeEventListener("storage",storage);};
 },[]);
 const copy=async()=>{
  const current=epoch.current;
  try{await navigator.clipboard.writeText(brief);if(epoch.current===current)setNotice("Copied only — delivery and activation are unverified.");}
  catch{if(epoch.current===current)setNotice("Clipboard unavailable. Select the dated brief to copy it manually.");}
 };
 const save=async()=>{
  if(!canPrepare || !brief || saving)return;
  const current=++epoch.current,ctrl=new AbortController();controller.current=ctrl;
  const timer=setTimeout(()=>ctrl.abort(),15000);setSaving(true);setNotice("");
  try{
   const response=await fetch(`${API}/agent/handoffs`,{method:"POST",credentials:"include",signal:ctrl.signal,
    headers:{"Content-Type":"application/json"},body:JSON.stringify({turn_id:turn.turn_id,context_hash:draft.context_hash,
     execution_owner:owner,brief,workflow_reference:reference,reported_status:reported})});
   if(!response.ok)throw new Error(response.status===401?"SESSION_EXPIRED":"REPORT_UNCONFIRMED");
   const saved=await response.json();
   if(!saved.handoff_id || saved.broker_verified!==false || saved.activation!=="unverified")throw new Error("REPORT_UNCONFIRMED");
   if(epoch.current===current)setNotice("Saved operator report — broker status and activation remain unverified.");
  }catch(e){if(epoch.current===current)setNotice(e.message==="SESSION_EXPIRED"?"Research session expired. No report was confirmed.":"Manual handoff report was not confirmed. No approval or activation occurred.");}
  finally{clearTimeout(timer);if(epoch.current===current)setSaving(false);}
 };
 return <section className="public-handoff-review" aria-label="Public agent review">
  <h3>Public agent</h3>
  <p>Manual reviewed bridge · no order or activation from this panel.</p>
  <label>Execution owner<select value={owner} onChange={e=>{epoch.current++;controller.current?.abort();setOwner(e.target.value);setBrief("");setNotice("");setSaving(false);}}>
   <option value="">Choose one owner</option><option value="PUBLIC_NATIVE_AGENT">Public native agent · manual builder</option><option value="FLOWW_BACKEND">FLOWW backend · separately gated</option>
  </select></label>
  {owner==="FLOWW_BACKEND" && <p role="status">Backend entry unavailable: immutable preflight, account policy, authenticated intent approval and unresolved native ownership overlap must be validated on the server. This panel does not submit orders.</p>}
  {!matches && <p role="status">Resolve an exact listed contract and ask Lodestar for this owning observation. Saved research from a different selection cannot prepare a current brief.</p>}
  <button type="button" disabled={!canPrepare || saving} onClick={()=>{setBrief(datedBrief(draft,owner));setNotice("");}}>Prepare dated brief</button>
  <details><summary>Commissioning policy · UNSET</summary><dl>{POLICY_FIELDS.map(field=><React.Fragment key={field}><dt>{field}</dt><dd>UNSET</dd></React.Fragment>)}</dl>
   <p>Policy text is not server permission. Local trading state is not proof of remote native-workflow ownership.</p></details>
  {brief && <div className="public-manual-brief">
   <label>Editable Public brief<textarea value={brief} disabled={saving} maxLength={10000} rows={12} onChange={e=>{setBrief(e.target.value);setNotice("");}}/></label>
   <button type="button" disabled={saving || !matches} onClick={copy}>Copy brief</button>
   <a href="https://public.com/ai-agents/trading-strategies" target="_blank" rel="noopener noreferrer">Public builder guidance ↗</a>
   <label>Reviewed workflow reference<input value={reference} disabled={saving} maxLength={256} onChange={e=>setReference(e.target.value)} placeholder="Operator reference, not an API receipt"/></label>
   <label>Operator-reported workflow status<select value={reported} disabled={saving} onChange={e=>setReported(e.target.value)}>
    <option value="prepared">Prepared, not reviewed</option><option value="reviewed">Reviewed in builder</option><option value="reported_active">Operator reports active · unverified</option><option value="reported_paused">Operator reports paused · unverified</option>
   </select></label>
   <button type="button" disabled={!matches || saving || !brief.trim()} onClick={save}>{saving?"Saving private report…":"Save manual handoff report"}</button>
   <small>Private research history only. Never enter broker credentials here.</small>
  </div>}
  {notice && <p role="status">{notice}</p>}
 </section>;
}

export function GroundedPublicReview() {
 const agent=useAgent();const [selection]=useScreenContext();
 return <PublicHandoffReview selection={selection} turn={agent?.activeTurn} grounded={agent?.answerContextStatus==="current"}/>;
}
