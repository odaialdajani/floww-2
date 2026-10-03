import React,{useEffect,useRef,useState} from "react";
import axios from "axios";
import {API} from "../../config/api";
import useScreenContext,{usePublishScreenContext} from "../../agent/useScreenContext";
import {contextIdentity} from "../../agent/contextIdentity";
import AskLodestar from "../heatseeker/AskLodestar";
import {GroundedPublicReview} from "./PublicHandoffReview";
import "./PublicReview.css";

const VERSION="tidehunter-public-review.v1";
const OSI=/^[A-Z0-9.]{1,12}\d{6}[CP]\d{8}$/;

/** Separate explicit current record read; never upgrades Pro estimates into broker facts. */
export default function TidehunterPublicBridge({onReviewActive=()=>{}}) {
 const [published]=useScreenContext();
 const [review,setReview]=useState(null),[pending,setPending]=useState(false),[error,setError]=useState("");
 const epoch=useRef(0),controller=useRef(null),sourceRef=useRef(null),callback=useRef(onReviewActive);callback.current=onReviewActive;
 const source=published.bridgeVersion===VERSION?sourceRef.current:published;
 const sourceKey=contextIdentity(source);
 usePublishScreenContext(review?.context || null);
 useEffect(()=>{
  if(review)return;
  epoch.current++;controller.current?.abort();setPending(false);setError("");
 },[sourceKey,review]);
 useEffect(()=>()=>{epoch.current++;controller.current?.abort();callback.current(false);},[]);
 const side=String(source?.selectedType || "").toLowerCase();
 const osi=typeof source?.selectedContract==="string" && OSI.test(source.selectedContract)?source.selectedContract:null;
 const hasSelector=source?.page==="flowseeker-pro" && source?.ticker && (osi ||
  (typeof source.selectedStrike==="number" && Number.isFinite(source.selectedStrike) && source.selectedExpiry && ["call","put"].includes(side)));
 const resolve=async()=>{
  if(!hasSelector || pending)return;
  const frozen=JSON.parse(JSON.stringify(source));sourceRef.current=frozen;
  const current=++epoch.current,ctrl=new AbortController();controller.current=ctrl;setPending(true);setError("");
  try{
   // Deliberately a NEW owning observation. Pro does not publish a record ID;
   // claiming this is the old Pro observation would be false.
   const {data}=await axios.get(`${API}/heatmap/${encodeURIComponent(frozen.ticker)}`,{params:{mode:"day",expiries:4},signal:ctrl.signal,timeout:20000});
   if(epoch.current!==current || ctrl.signal.aborted)return;
   if(data?.ticker!==frozen.ticker || !data.snapshotId || !data.asof || !data.data_source || !data.formula_version || !data.map_query)throw new Error("OBSERVATION_IDENTITY_MISMATCH");
   const selector=osi?{osi}:{strike:String(frozen.selectedStrike),expiry:frozen.selectedExpiry,type:side};
   const {data:body}=await axios.get(`${API}/solstice/${encodeURIComponent(frozen.ticker)}/contract`,{params:{...selector,snapshot_id:data.snapshotId},signal:ctrl.signal,timeout:20000});
   if(epoch.current!==current || ctrl.signal.aborted)return;
   const matched=body?.matched_identity;
   const strikes=data.grid?.strikes || [],expiries=data.grid?.expiries || [];
   if(body?.status!=="ok" || body.ticker!==frozen.ticker || body.snapshot_id!==data.snapshotId || !matched?.osi || !OSI.test(matched.osi)
    || !matched.strike || !matched.expiry || !["call","put"].includes(matched.type) || !strikes.includes(Number(matched.strike)) || !expiries.includes(matched.expiry)
    || (osi && osi!==matched.osi) || (!osi && (String(matched.expiry)!==frozen.selectedExpiry || Number(matched.strike)!==frozen.selectedStrike || matched.type!==side)))throw new Error("EXACT_CONTRACT_UNAVAILABLE");
   const context={contextVersion:2,page:"flowseeker-pro",bridgeVersion:VERSION,ticker:frozen.ticker,dte:"all",mode:"day",
    selectedContract:matched,contractResolution:"resolved",selectedStrike:Number(matched.strike),selectedExpiry:matched.expiry,selectedWall:null,
    metric:"gex",overlayMetric:"raw",activePane:"gex",displayMode:"live",snapshotId:data.snapshotId,mapVersion:data.asof,
    provider:data.data_source,formula:data.formula_version,mapQuery:data.map_query,mapStrikes:strikes,mapExpiries:expiries,
    observedAt:data.event_time || data.observed_at || null,sourceWorkspace:"flowseeker-pro",sourceObservedAt:frozen.observedAt || null};
   setReview({context,body,source:frozen});callback.current(true);
  }catch(e){if(epoch.current===current && !ctrl.signal.aborted)setError(["OBSERVATION_IDENTITY_MISMATCH","EXACT_CONTRACT_UNAVAILABLE"].includes(e.message)?e.message:"READ_UNAVAILABLE — no Pro estimate or nearby contract substituted");}
  finally{if(epoch.current===current)setPending(false);}
 };
 const close=()=>{epoch.current++;controller.current?.abort();setReview(null);setPending(false);setError("");callback.current(false);};
 const closeRef=useRef(null);
 useEffect(()=>{if(!review)return;const previous=document.activeElement;closeRef.current?.focus();const escape=e=>{if(e.key==="Escape")close();};window.addEventListener("keydown",escape);return()=>{window.removeEventListener("keydown",escape);previous?.focus?.();};},[review]);
 return <section className="tidehunter-public-bridge" aria-label="Tidehunter Public boundary">
  <strong>Separate Public review</strong>
  <p>Pro ckey, estimated premium and conviction are display inputs, not executable identity, current quotes or probability. Public chain OI/volume is not a trade-print or aggressor feed.</p>
  {!review && <><button type="button" disabled={!hasSelector || pending} onClick={resolve}>{pending?"Resolving exact current record…":"Resolve a separate Public review"}</button>
   {!hasSelector && <p role="status">SELECTED_CONTRACT_INCOMPLETE — choose a published exact strike, expiry and type; ckey alone is not sufficient.</p>}
   <p>This explicit read loads a new owning observation; it does not replace or recalculate the friend-owned Pro feed.</p></>}
  {error && <p role="alert">{error}</p>}
  {review && <div role="dialog" aria-label="Separate Public contract review">
   <button ref={closeRef} type="button" onClick={close}>Close separate Public review</button>
   <p>Pro source time: {review.source.observedAt || "unknown"}</p>
   <p>New owning observation: {review.context.snapshotId} · {review.context.mapVersion} · {review.context.provider}</p>
   <strong>{review.body.matched_identity.osi}</strong>
   <p>Recorded bid / ask: {review.body.quote?.bid ?? "unknown"} / {review.body.quote?.ask ?? "unknown"} USD · ages: {review.body.quote?.ages_s?.bid ?? "unknown"} / {review.body.quote?.ages_s?.ask ?? "unknown"} s</p>
   <p>Multiplier: {review.body.multiplier?.value ?? "unknown"} · {review.body.multiplier?.source || "provenance unavailable"}. Read-only, not preflight.</p>
   <AskLodestar subject={`${review.context.ticker} · separate exact contract review`} compact/>
   <GroundedPublicReview/>
  </div>}
 </section>;
}
