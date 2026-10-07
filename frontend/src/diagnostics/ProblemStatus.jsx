import {useEffect,useState} from "react";
import {API} from "../config/api";
const LABELS={browser_error:"Screen error",read_error:"Failed read",slow_read:"Slow read",screen_lag:"Screen lag",socket_error:"Connection error",server_log:"App warning",slow_request:"Slow reply",failed_request:"Failed reply"};
export default function ProblemStatus(){
 const [open,setOpen]=useState(false),[summary,setSummary]=useState(null),[error,setError]=useState("");
 useEffect(()=>{
  if(!open)return;
  let stopped=false,pending=false,controller=null;
  const load=async()=>{if(pending)return;pending=true;controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),5000);try{const r=await fetch(API+"/diagnostics/summary",{signal:controller.signal});if(!r.ok)throw Error();const data=await r.json();if(!stopped){setSummary(data);setError("");}}catch{if(!stopped)setError("The saved problem log is reconnecting. New screen reports stay on this computer.");}finally{clearTimeout(timeout);pending=false;}};
  load();const timer=setInterval(load,15000);
  return()=>{stopped=true;controller?.abort();clearInterval(timer);};
 },[open]);
 const successes=(summary?.recoveries||[]).reduce((n,row)=>n+(row.succeeded||0),0);
 return <aside style={{position:"fixed",right:12,bottom:84,zIndex:60,fontSize:12}} aria-label="App health">
  <button type="button" onClick={()=>setOpen(v=>!v)} aria-expanded={open}>App health</button>
  {open && <section style={{maxWidth:370,maxHeight:"60vh",overflowY:"auto",background:"#151b23",color:"#d7dce3",border:"1px solid #596171",padding:14,borderRadius:8}}>
   <h2 style={{fontSize:16,marginTop:0}}>Problem log</h2>
   <p>Errors, slow reads and screen lag are saved locally. Safe reads can retry once.</p>
   {error && <p role="status">{error}</p>}
   {summary && <><p>{summary.total_events} reports saved · {summary.recurring} repeating problems · {successes} reads recovered.</p>
    <p>A recovered read can still contain old or incomplete data. Repeated problems stay recorded for the next fix.</p>
    <ul>{summary.issues.slice(0,8).map((row,i)=><li key={i}>{LABELS[row.kind]||"App problem"} · {row.count} times{row.duration_ms?" · "+(row.duration_ms/1000).toFixed(1)+" seconds":""}</li>)}</ul></>}
  </section>}
 </aside>;
}
