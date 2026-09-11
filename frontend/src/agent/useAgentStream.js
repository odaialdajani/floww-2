import { useCallback, useEffect, useRef, useState } from "react";
import { API } from "../config/api";
const terminal = new Set(["completed", "done", "failed", "error", "cancelled", "interrupted"]);
function requestIdentity() {
 const bytes=crypto.getRandomValues(new Uint8Array(16)); bytes[6]=(bytes[6]&15)|64; bytes[8]=(bytes[8]&63)|128;
 const hex=Array.from(bytes,b=>b.toString(16).padStart(2,"0")).join("");
 return `${Date.now()}-${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export default function useAgentStream({onEvent}={}) {
 const [state,setState]=useState("idle");
 const callback=useRef(onEvent); callback.current=onEvent;
 const observer=useRef(null);
 const emit=useCallback((kind,payload)=>callback.current?.(kind,payload),[]);
 const stop=useCallback(()=>{const w=observer.current;if(w){w.stopped=true;w.source?.close();}observer.current=null;},[]);
 useEffect(()=>stop,[stop]);
 const finish=useCallback((watch,turn)=>{
  if(watch.stopped || observer.current!==watch)return;
  watch.stopped=true;watch.source?.close();setState(turn.status);
  emit(turn.status==="completed" || turn.status==="done" ? "done":"error",turn);
 },[emit]);
 const cancelKnown=useCallback(async watch=>{
  if(!watch.id || watch.stopped)return;
  if(watch.cancellation)return watch.cancellation;
  watch.cancellation=(async()=>{
   try {
    const res=await fetch(`${API}/agent/cancel/${encodeURIComponent(watch.id)}`,{method:"POST",credentials:"include"});
    if(!res.ok)throw new Error();
    const data=await res.json();const turn=data.turn || data;
    if(!terminal.has(turn.status))throw new Error();
    finish(watch,turn);
   } catch {
    if(!watch.stopped){watch.cancelRequested=false;setState("reconnecting");emit("error",{error:"Cancellation could not be confirmed; checking saved request"});}
   } finally {watch.cancellation=null;}
  })();
  return watch.cancellation;
 },[finish,emit]);
 const ask=useCallback(async body=>{
  stop();setState("asking");
  const watch={stopped:false,source:null,id:null,cancelRequested:false,cancellation:null};observer.current=watch;
  try {
   const session=await fetch(`${API}/agent/session`,{method:"POST",credentials:"include"});
   if(watch.stopped)return null;
   if(!session.ok)throw new Error("Local session unavailable");
   if(watch.cancelRequested){finish(watch,{status:"cancelled",error:"Cancelled before research started"});return null;}
   const request_id=requestIdentity();
   const response=await fetch(`${API}/agent/ask`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({...body,request_id})});
   if(!response.ok)throw new Error("Research request could not start");
   const {turn_id}=await response.json();watch.id=turn_id;
   if(watch.stopped)return turn_id;
   if(watch.cancelRequested){await cancelKnown(watch);if(watch.stopped)return turn_id;}
   setState("running");emit("started",{turn_id,screen:body.screen});
   const read=async()=>{
    if(watch.stopped)return true;
    const res=await fetch(`${API}/agent/turn/${encodeURIComponent(turn_id)}`,{credentials:"include"});
    if(watch.stopped)return true;
    if(!res.ok)throw new Error("Saved answer unavailable");
    const data=await res.json();if(watch.stopped)return true;
    const turn=data.turn || data;
    if(terminal.has(turn.status)){finish(watch,turn);return true;}
    return false;
   };
   if(await read())return turn_id;
   if(typeof EventSource!=="undefined" && !watch.stopped){
    const es=new EventSource(`${API}/agent/stream/${encodeURIComponent(turn_id)}`,{withCredentials:true});watch.source=es;
    ["step","progress"].forEach(kind=>es.addEventListener(kind,e=>{if(!watch.stopped){try{emit(kind,JSON.parse(e.data));}catch{}}}));
    es.addEventListener("done",()=>read().catch(()=>{if(!watch.stopped)setState("reconnecting");}));
    es.addEventListener("error",()=>{es.close();if(!watch.stopped)setState("reconnecting");});
   }
   const until=Date.now()+130000;
   while(!watch.stopped && Date.now()<until){
    await new Promise(resolve=>setTimeout(resolve,1000));
    if(watch.stopped)break;
    try {if(await read())break;}catch{if(!watch.stopped)setState("reconnecting");}
   }
   if(!watch.stopped)finish(watch,{status:"interrupted",error:"Connection lost. Reopen history to recover the saved request."});
   return turn_id;
  } catch(error){if(!watch.stopped)finish(watch,{status:"error",error:error.message});return null;}
 },[stop,emit,finish,cancelKnown]);
 const cancel=useCallback(async()=>{
  const watch=observer.current;if(!watch || watch.stopped)return;
  watch.cancelRequested=true;setState("cancelling");
  if(watch.id)await cancelKnown(watch);
 },[cancelKnown]);
 return {state,ask,cancel};
}
