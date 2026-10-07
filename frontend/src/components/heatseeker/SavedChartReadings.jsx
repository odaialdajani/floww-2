import React,{useCallback,useEffect,useRef,useState} from "react";
import axios from "axios";
import {API} from "../../config/api";
const PAGE_SIZE=20;
const identity=value=>typeof value==="string"&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value);
function clock(value){
 if(typeof value!=="string"||!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(value))return false;
 const day=value.slice(0,10),[year,month,date]=day.split("-").map(Number);
 const d=new Date(Date.UTC(year,month-1,date));
 return d.toISOString().slice(0,10)===day&&Number.isFinite(Date.parse(value));
}
function checkedPage(body,ticker,order){
 if(!body||body.ticker!==ticker||body.order!==order||!["available","partial"].includes(body.status)||!Array.isArray(body.decisions)||body.decisions.length>PAGE_SIZE||body.count!==body.decisions.length||typeof body.has_more!=="boolean")throw Error("Invalid saved page");
 if(body.has_more?typeof body.next_cursor!=="string"||!body.next_cursor||body.next_cursor.length>1024:body.next_cursor!==null)throw Error("Invalid page position");
 const ids=new Set();for(const row of body.decisions){if(!row||row.ticker!==ticker||!identity(row.decision_id)||ids.has(row.decision_id)||!clock(row.at_ts))throw Error("Invalid saved reading");ids.add(row.decision_id);}
 return body;
}
function recordedTime(value){return new Date(value).toLocaleString("en-US",{timeZone:"America/New_York",month:"short",day:"numeric",year:"numeric",hour:"numeric",minute:"2-digit"});}
export default function SavedChartReadings({ticker="SPY",onOpen,disabled=false}){
 const [open,setOpen]=useState(false),[page,setPage]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const request=useRef(null),sequence=useRef(0);
 const cancel=useCallback(()=>{sequence.current++;request.current?.abort();request.current=null;},[]);
 const load=useCallback(async(order="newest",cursor=null)=>{
  cancel();const epoch=sequence.current,controller=new AbortController();request.current=controller;setBusy(true);setError("");
  try{const result=await axios.get(API+"/solstice/"+encodeURIComponent(ticker)+"/decisions/page",{params:{limit:PAGE_SIZE,order,...(cursor?{cursor}: {})},timeout:15000,signal:controller.signal,withCredentials:false});
   if(sequence.current!==epoch||controller.signal.aborted)return;
   const body=checkedPage(result?.data,ticker,order);setPage(body);
  }catch(e){if(sequence.current===epoch&&!controller.signal.aborted)setError("Saved readings could not be loaded. Reload the latest or first saved page.");}
  finally{if(sequence.current===epoch){request.current=null;setBusy(false);}}
 },[ticker,cancel]);
 useEffect(()=>{setPage(null);setError("");if(open)load("newest");else{cancel();setBusy(false);}return cancel;},[ticker,open,load,cancel]);
 const current=page?.ticker===ticker?page:null;
 return <section className="panel" data-testid="saved-chart-readings" style={{margin:"12px 0",padding:12}}>
  <button type="button" className="skylit-trade-mode-btn" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>Saved chart readings</button>
  {open&&<div style={{marginTop:12}}><strong>{ticker} saved readings</strong><p style={{fontSize:12}}>Original saved charts and option quotes. Times below use New York time. Opening one starts a read-only replay.</p>
   <div style={{display:"flex",gap:8,flexWrap:"wrap",margin:"10px 0"}}><button type="button" className="skylit-trade-mode-btn" disabled={busy} onClick={()=>load("newest")}>Latest</button><button type="button" className="skylit-trade-mode-btn" disabled={busy} onClick={()=>load("oldest")}>First saved</button>
   {current?.has_more&&<button type="button" className="skylit-trade-mode-btn" disabled={busy} onClick={()=>load(current.order,current.next_cursor)}>{current.order==="oldest"?"Later readings":"Older readings"}</button>}</div>
   {busy&&<p role="status">Loading saved readings...</p>}{error&&<p role="alert">{error}</p>}
   {current?.status==="partial"&&<p role="status">Some saved details are missing. Unknown times stay unavailable.</p>}
   {current&&!current.decisions.length&&!busy&&<p>No saved chart readings on this page.</p>}
   {disabled&&<p role="status">Close the analytical range before opening a saved chart.</p>}
   <ul style={{listStyle:"none",margin:0,padding:0,maxHeight:420,overflowY:"auto"}}>{(current?.decisions||[]).map(row=><li key={row.decision_id} style={{borderTop:"1px solid var(--border, #273144)",padding:"10px 0",display:"flex",gap:12,justifyContent:"space-between",alignItems:"center"}}>
    <div><strong>Saved {recordedTime(row.at_ts)}</strong><div style={{fontSize:12}}>{Number.isInteger(row.n_quotes)&&row.n_quotes>=0?row.n_quotes+" saved option quotes":"Saved quote details unavailable"}</div>
     {row.quote_status==="summary_only"&&Number.isSafeInteger(row.reported_n_quotes)&&row.reported_n_quotes>=0&&<small>Recovered summary reported {row.reported_n_quotes} quotes; their details are unavailable.</small>}
     {row.features_status!=="available"&&<small>Some saved details are missing.</small>}</div>
    <button type="button" className="skylit-trade-mode-btn" disabled={disabled||row.snapshot_available===false||row.snapshot_status==="unavailable"||(row.quote_status==="summary_only"&&row.snapshot_status!=="available"&&row.snapshot_available!==true)||!identity(row.snapshot_id)||typeof onOpen!=="function"} onClick={()=>onOpen(row.snapshot_id)}>Open saved chart</button>
   </li>)}</ul></div>}
 </section>;
}
