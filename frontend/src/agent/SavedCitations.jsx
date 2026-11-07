import {useEffect,useId,useRef,useState} from "react";
import {API} from "../config/api";
import "./SavedCitations.css";

const VERSION="agent-citation-index.v1";
const SESSION_ENDED="floww-research-session-ended";
const text=value=>typeof value==="string" && value.trim()?value:null;
const identity=row=>Boolean(text(row?.citation_id) && text(row?.turn_id) && text(row?.fact_id));
const sameReading=(row,selected)=>identity(row) && row.citation_id===selected.citation_id && row.turn_id===selected.turn_id && row.fact_id===selected.fact_id;
function stop(ref){
 const read=ref.current;ref.current=null;
 if(read){clearTimeout(read.timer);read.controller.abort();}
}
async function getSaved(path,read){
 const deadline=new Promise((_,reject)=>{read.timer=setTimeout(()=>{read.controller.abort();reject(new Error("Saved citations took too long to load. Try again."));},15000);});
 try{return await Promise.race([(async()=>{
  const result=await fetch(`${API}${path}`,{method:"GET",credentials:"include",signal:read.controller.signal});
  if(!result.ok){
   if(result.status===401){const error=new Error("Your research session is unavailable. Open Ask Flow settings to check your session, then try again.");error.sessionExpired=true;throw error;}
   if(result.status===404)throw new Error("This saved citation is no longer available.");
   throw new Error("Saved citations are unavailable. Your current answer is unchanged.");
  }
  return result.json();
 })(),deadline]);}finally{clearTimeout(read.timer);}
}
function stored(value,fallback="Unavailable"){
 if(value===null || value===undefined || value==="")return fallback;
 return typeof value==="object"?JSON.stringify(value,null,2):String(value);
}

// The server resolves the existing HttpOnly session to an owner. These reads
// never mint a session, ask a model, update an answer or fetch market data.
export default function SavedCitations({visible=true}){
 const id=useId(),indexRead=useRef(null),detailRead=useRef(null);
 const [open,setOpen]=useState(false),[reload,setReload]=useState(0),[detailReload,setDetailReload]=useState(0);
 const [index,setIndex]=useState({status:"idle"}),[detail,setDetail]=useState({status:"idle"}),[selected,setSelected]=useState(null);
 const close=()=>{stop(indexRead);stop(detailRead);setOpen(false);setIndex({status:"idle"});setDetail({status:"idle"});setSelected(null);};
 useEffect(()=>{
  const ended=()=>{stop(indexRead);stop(detailRead);setOpen(false);setIndex({status:"idle"});setDetail({status:"idle"});setSelected(null);};
  const storage=event=>{if(event.key===SESSION_ENDED && event.newValue)ended();};
  window.addEventListener(SESSION_ENDED,ended);window.addEventListener("storage",storage);
  return()=>{stop(indexRead);stop(detailRead);window.removeEventListener(SESSION_ENDED,ended);window.removeEventListener("storage",storage);};
 },[]);
 useEffect(()=>{
  if(!visible){stop(indexRead);stop(detailRead);setOpen(false);setIndex({status:"idle"});setDetail({status:"idle"});setSelected(null);}
 },[visible]);
 useEffect(()=>{
  if(!open || !visible)return undefined;
  const read={controller:new AbortController(),timer:null};indexRead.current=read;
  stop(detailRead);setSelected(null);setDetail({status:"idle"});setIndex({status:"loading"});
  getSaved("/agent/citations?limit=30",read).then(body=>{
   if(indexRead.current!==read)return;
   if(body?.version!==VERSION || !Array.isArray(body.citations) || !body.citations.every(identity)
    || new Set(body.citations.map(row=>row.citation_id)).size!==body.citations.length)throw new Error("Saved citations could not be checked. Try again.");
   setIndex({status:"ready",rows:body.citations,scanned:body.coverage?.turns_scanned});
  }).catch(error=>{if(indexRead.current===read)setIndex({status:"error",message:error.message || "Saved citations are unavailable."});});
  return()=>{if(indexRead.current===read)stop(indexRead);};
 },[open,visible,reload]);
 useEffect(()=>{
  if(!open || !visible || !selected)return undefined;
  const read={controller:new AbortController(),timer:null};detailRead.current=read;setDetail({status:"loading"});
  // Construct only the known local route, with the exact saved answer id.
  // Never follow a response-supplied URL or use the current screen as evidence.
  const path=`/agent/citations/${encodeURIComponent(selected.citation_id)}?turn_id=${encodeURIComponent(selected.turn_id)}`;
  getSaved(path,read).then(body=>{
   if(detailRead.current!==read)return;
   if(body?.version!==VERSION || !sameReading(body.citation,selected))throw new Error("This citation could not be matched to the selected saved answer.");
   setDetail({status:"ready",row:body.citation});
  }).catch(error=>{
   if(detailRead.current!==read)return;
   if(error.sessionExpired){stop(indexRead);setIndex({status:"error",message:error.message});setSelected(null);setDetail({status:"idle"});}
   else setDetail({status:"error",message:error.message || "This saved citation is unavailable."});
  });
  return()=>{if(detailRead.current===read)stop(detailRead);};
 },[open,visible,selected,detailReload]);
 const choose=row=>{
  if(selected && sameReading(row,selected))return;
  stop(detailRead);setDetail({status:"loading"});setSelected(row);
 };
 const row=detail.status==="ready"?detail.row:null;
 return <section className="assistant-citations" aria-label="Saved citations">
  <button type="button" aria-expanded={open} aria-controls={id} onClick={()=>open?close():setOpen(true)}>{open?"Close saved citations":"Saved citations"}</button>
  {open && visible && <div id={id} className="assistant-citations-body">
   <header><h3>Saved citations</h3><p>Readings from your saved answers. These keep their original source and times.</p></header>
   {index.status==="loading" && <p role="status">Loading saved citations…</p>}
   {index.status==="error" && <div><p role="alert">{index.message}</p><button type="button" onClick={()=>setReload(n=>n+1)}>Retry saved citations</button></div>}
   {index.status==="ready" && <>
    <div className="assistant-citations-meta"><small>{Number.isInteger(index.scanned)&&index.scanned>=0?`${index.scanned} saved answers checked · `:""}Recent saved answers only</small><button type="button" onClick={()=>setReload(n=>n+1)}>Refresh citations</button></div>
    {!index.rows.length?<p>No saved citations were returned.</p>:<ul className="assistant-citations-list">{index.rows.map(item=><li key={item.citation_id}><button type="button" aria-pressed={selected?.citation_id===item.citation_id} onClick={()=>choose(item)}>
     <strong>{text(item.ticker) || "Stock unavailable"} · {text(item.metric) || "Saved reading"}</strong>
     <small>{text(item.source) || "Source unavailable"} · {text(item.status) || "Status unavailable"}</small>
    </button></li>)}</ul>}
   </>}
   {detail.status==="loading" && <p role="status">Loading saved reading…</p>}
   {detail.status==="error" && <div><p role="alert">{detail.message}</p><button type="button" onClick={()=>setDetailReload(n=>n+1)}>Retry saved reading</button></div>}
   {row && <section className="assistant-citation-reading" role="region" aria-label="Saved citation reading">
    <h4>{text(row.metric) || "Saved reading"}</h4>
    <pre>{row.value==null?"Value unavailable":stored(row.value)+(text(row.unit)?` ${row.unit}`:"")}</pre>
    <dl>{[["Stock",row.ticker],["Status",row.status],["Reason",row.reason],["Source",row.source],["Observation time",row.event_time],["Received time",row.received_at],["Saved snapshot",row.snapshot_id],["Saved answer",row.turn_id],["Fact",row.fact_id],["Contract",row.contract],["Horizon",row.horizon],["Reading version",row.version],["Parent readings",row.parents]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{stored(value)}</dd></div>)}</dl>
    <p>{row.cited===true?"Referenced in the saved answer.":row.cited===false?"Stored evidence; not referenced in the saved answer.":"Reference status unavailable."}</p>
    {Array.isArray(row.sections)&&row.sections.filter(text).length>0 && <p>Sections: {row.sections.filter(text).join(", ")}</p>}
   </section>}
  </div>}
 </section>;
}
