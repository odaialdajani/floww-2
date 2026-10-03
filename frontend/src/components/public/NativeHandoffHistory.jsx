import React,{useEffect,useRef,useState} from 'react';
import {API} from '../../config/api';

export default function NativeHandoffHistory(){
 const [records,setRecords]=useState(null),[notice,setNotice]=useState(''),[loading,setLoading]=useState(false);
 const epoch=useRef(0),controller=useRef(null);
 useEffect(()=>{
  const clear=()=>{epoch.current++;controller.current?.abort();setRecords(null);setNotice('Private history cleared from this view.');setLoading(false);};
  const storage=e=>{if(e.key==='floww-research-session-ended' && e.newValue)clear();};
  window.addEventListener('floww-research-session-ended',clear);window.addEventListener('storage',storage);
  return()=>{epoch.current++;controller.current?.abort();window.removeEventListener('floww-research-session-ended',clear);window.removeEventListener('storage',storage);};
 },[]);
 const load=async()=>{
  if(loading)return;
  const current=++epoch.current,ctrl=new AbortController();controller.current=ctrl;
  setLoading(true);setNotice('');const timer=setTimeout(()=>ctrl.abort(),15000);
  try{
   const response=await fetch(`${API}/agent/handoffs`,{credentials:'include',signal:ctrl.signal});
   if(!response.ok)throw new Error();
   const body=await response.json();
   if(epoch.current===current)setRecords(body.handoffs || []);
  }catch{if(epoch.current===current)setNotice('Private handoff history unavailable; the research session may have expired. No broker status was inferred.');}
  finally{clearTimeout(timer);if(epoch.current===current)setLoading(false);}
 };
 return <section className="public-handoff-review panel p-4" aria-label="Private manual Public handoff history">
  <h3>Manual Public handoffs</h3><p>Operator reports, not executions or verified remote ownership. Actual Public orders and option P&amp;L are separate.</p>
  <button type="button" onClick={load} disabled={loading}>{loading?'Loading private history…':'Load private handoff history'}</button>
  {records?.length===0 && <p>No saved handoff reports in this research session.</p>}
  {records?.map(record=><article key={record.handoff_id}>
   <strong>{record.workflow_reference || 'No workflow reference supplied'}</strong>
   <p>{record.reported_status} · broker state / activation unverified · {record.created_at}</p>
   <details><summary>Dated brief · reference {record.handoff_id}</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{record.brief}</pre></details>
  </article>)}
  {notice && <p role="status">{notice}</p>}
 </section>;
}
