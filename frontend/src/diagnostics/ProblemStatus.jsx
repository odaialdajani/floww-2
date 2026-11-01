import {useEffect,useState} from "react";
import {API} from "../config/api";
import {isLocalProblemPage} from "./problemTracking";
import {permanentRefusal,retryDelay} from "./retryPolicy";
const LABELS={browser_error:"Screen error",read_error:"Failed read",slow_read:"Slow read",screen_lag:"Screen lag",socket_error:"Connection error",server_log:"App warning",slow_request:"Slow reply",failed_request:"Failed reply"};
export default function ProblemStatus(){
 const [open,setOpen]=useState(false),[summary,setSummary]=useState(null),[error,setError]=useState("");
 const local=isLocalProblemPage();
 useEffect(()=>{
  if(!open || !local)return;
  let stopped=false,pending=false,controller=null,timer=null,failures=0,nextAt=0;
  const schedule=()=>{if(!stopped)timer=setTimeout(load,Math.min(Math.max(0,nextAt-Date.now()),2147483647));};
  const load=async()=>{
   if(stopped || pending)return;
   if(Date.now()<nextAt){schedule();return;}
   pending=true;controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),5000);
   let delay=15000,blocked=false;
   try{
    const r=await fetch(API+"/diagnostics/summary",{signal:controller.signal});
    if(!r.ok){
     blocked=permanentRefusal(r);delay=retryDelay(r,++failures,15000);
     if(!stopped)setError(blocked?"The local problem log is unavailable for this connection.":"The problem log is unavailable. The next check will wait before trying again.");
    }else{
     const data=await r.json();
     if(!data || !Array.isArray(data.issues) || !Array.isArray(data.recoveries)
       || !Number.isFinite(data.total_events) || !Number.isFinite(data.recurring))throw Error("Invalid summary");
     if(!stopped){setSummary(data);setError("");}failures=0;
    }
   }catch{
    delay=retryDelay(null,++failures,15000);
    if(!stopped)setError("The problem log is unavailable. The next check will wait before trying again.");
   }finally{
    clearTimeout(timeout);pending=false;
    if(!blocked){nextAt=Date.now()+delay;schedule();}
   }
  };
  load();
  return()=>{stopped=true;controller?.abort();clearTimeout(timer);};
 },[open,local]);
 const successes=(summary?.recoveries||[]).reduce((n,row)=>n+(row.succeeded||0),0);
 return <aside style={{position:"fixed",right:12,bottom:84,zIndex:60,fontSize:12}} aria-label="App health">
  <button type="button" onClick={()=>setOpen(v=>!v)} aria-expanded={open}>App health</button>
  {open && <section style={{maxWidth:370,maxHeight:"60vh",overflowY:"auto",background:"#151b23",color:"#d7dce3",border:"1px solid #596171",padding:14,borderRadius:8}}>
   <h2 style={{fontSize:16,marginTop:0}}>Problem log</h2>
   {!local?<p>Problem reports are available in the Mac's local browser. This device does not upload or queue screen reports.</p>:<>
   <p>Errors, slow reads and screen lag are saved locally. Safe reads can retry once.</p>
   {error && <p role="status">{error}</p>}
   {summary && <>{error && <p>Last received summary</p>}<p>{summary.total_events} reports saved · {summary.recurring} repeating problems · {successes} reads recovered.</p>
    <p>A recovered read can still contain old or incomplete data. Repeated problems stay recorded for the next fix.</p>
    <ul>{summary.issues.slice(0,8).map((row,i)=><li key={i}>{LABELS[row.kind]||"App problem"} · {row.count} times{row.duration_ms?" · "+(row.duration_ms/1000).toFixed(1)+" seconds":""}</li>)}</ul></>}</>}
  </section>}
 </aside>;
}
