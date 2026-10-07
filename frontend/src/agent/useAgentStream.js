import { useCallback, useEffect, useRef, useState } from "react";
import { API } from "../config/api";
import {requestFailureText} from "./requestFailure";
const terminal = new Set(["completed", "done", "failed", "error", "cancelled", "interrupted"]);
// Bounded waits: a hung session/admission/turn read must surface a
// recoverable error, never leave the UI hanging with no outcome.
const SESSION_TIMEOUT_MS = 15000;
const ASK_TIMEOUT_MS = 45000;
const TURN_TIMEOUT_MS = 15000;
const CANCEL_TIMEOUT_MS = 15000;
// Own each wait, including JSON bodies. Deadlines do not depend on optional
// browser AbortSignal helpers, and disposal releases hanging transports too.
async function bounded(watch,ms,operation){
 const controller=new AbortController();let timer,onAbort,abortReason;
 const abort=reason=>{abortReason=reason;controller.abort(reason);};
 watch.requests ??= new Set();watch.requests.add(controller);
 try{
  const stopped=new Promise((_,reject)=>{
   onAbort=()=>reject(abortReason || controller.signal.reason || new DOMException("Request stopped","AbortError"));
   controller.signal.addEventListener("abort",onAbort,{once:true});
   timer=setTimeout(()=>abort(new DOMException("Request timed out","TimeoutError")),ms);
  });
  return await Promise.race([operation(controller,abort),stopped]);
 }finally{
  clearTimeout(timer);controller.signal.removeEventListener("abort",onAbort);watch.requests.delete(controller);
 }
}
function releaseRequests(watch){watch.requests?.forEach(controller=>controller.abort(new DOMException("Request stopped","AbortError")));}
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
 const stop=useCallback(()=>{const w=observer.current;if(w){w.stopped=true;w.source?.close();w.releaseRejected?.();releaseRequests(w);}observer.current=null;},[]);
 useEffect(()=>stop,[stop]);
 const finish=useCallback((watch,turn)=>{
  if(watch.stopped || observer.current!==watch)return;
  watch.stopped=true;watch.source?.close();watch.releaseRejected?.();releaseRequests(watch);setState(turn.status);
  emit(turn.status==="completed" || turn.status==="done" ? "done":"error",turn);
 },[emit]);
 const cancelKnown=useCallback(async watch=>{
  if(!watch.id || watch.stopped)return;
  if(watch.cancellation)return watch.cancellation;
  watch.cancellation=(async()=>{
   try {
    const turn=await bounded(watch,CANCEL_TIMEOUT_MS,async controller=>{
     const res=await fetch(`${API}/agent/cancel/${encodeURIComponent(watch.id)}`,{method:"POST",credentials:"include",signal:controller.signal});
     if(!res.ok)throw new Error();
     const data=await res.json();return data.turn || data;
    });
    if(!terminal.has(turn.status))throw new Error();
    finish(watch,turn);
   } catch {
    if(!watch.stopped){watch.cancelRequested=false;setState("reconnecting");emit("error",{error:"Cancellation could not be confirmed; checking saved request"});}
   } finally {watch.cancellation=null;}
  })();
  return watch.cancellation;
 },[finish,emit]);
 const observeAccepted=useCallback(async watch=>{
   const turn_id=watch.id;
   const read=async()=>{
    if(watch.stopped)return true;
    const data=await bounded(watch,TURN_TIMEOUT_MS,async controller=>{
     const res=await fetch(`${API}/agent/turn/${encodeURIComponent(turn_id)}`,{credentials:"include",signal:controller.signal});
     if(!res.ok){
      if(watch.requireIdentity && [401,403,404].includes(res.status)){
       finish(watch,{turn_id,status:"interrupted",error:res.status===404?"This saved question is unavailable. No new question was sent.":"Access to this saved question has ended. No new question was sent."});return null;
      }
      throw new Error("Saved answer unavailable");
     }
     return res.json();
    });
    if(watch.stopped)return true;
    if(data===null || watch.stopped)return true;
    const turn=data.turn || data;
    if(watch.requireIdentity && turn.turn_id!==turn_id){finish(watch,{turn_id,status:"interrupted",error:"This saved question could not be checked. No new question was sent."});return true;}
    if(terminal.has(turn.status)){finish(watch,turn);return true;}
    return false;
   };
   // Admission already succeeded: retry only saved-turn reads, never the ask.
   try {if(await read())return turn_id;}catch{if(!watch.stopped)setState("reconnecting");}
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
 },[emit,finish]);
 const ask=useCallback(async body=>{
  stop();setState("asking");
  const watch={stopped:false,source:null,id:null,stage:"session",cancelRequested:false,cancellation:null};observer.current=watch;
  try {
   const session=await bounded(watch,SESSION_TIMEOUT_MS,controller=>fetch(`${API}/agent/session`,{method:"POST",credentials:"include",signal:controller.signal}));
   if(watch.stopped)return null;
   if(!session.ok)throw new Error("Local session unavailable");
   if(watch.cancelRequested){finish(watch,{status:"cancelled",error:"Cancelled before research started"});return null;}
   watch.stage="admission";
   const request_id=requestIdentity();
   const admission=await bounded(watch,ASK_TIMEOUT_MS,async(requestController,abortRequest)=>{
   watch.admissionOutcome="unknown";
   const response=await fetch(`${API}/agent/ask`,{signal:requestController.signal,method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({...body,request_id})});
   if(!response.ok){
    watch.admissionOutcome="rejected";
    let failure;
    if(response.status===422){
     // The response has rejected admission. Only now may cancellation or the
     // bounded message read abort this request without hiding a running turn.
     if(watch.stopped || watch.cancelRequested){
      requestController.abort();
      finish(watch,{status:"cancelled",error:"Cancelled before research started"});
      return null;
     }
     failure=await new Promise(resolve=>{
      let settled=false;
      const settle=(value,abort=false)=>{
       if(settled)return;
       settled=true;clearTimeout(timer);watch.releaseRejected=null;
       if(abort)abortRequest(new Error(requestFailureText(response.status)));
       resolve(value);
      };
      const timer=setTimeout(()=>settle(undefined,true),3000);
      watch.releaseRejected=()=>settle(undefined,true);
      Promise.resolve().then(()=>response.json()).then(value=>settle(value),()=>settle());
     });
     if(watch.stopped)return null;
    }
    throw new Error(requestFailureText(response.status,failure));
   }
   return response.json();
   });
   if(watch.stopped)return null;
   if(typeof admission?.turn_id!=="string" || !admission.turn_id.trim())throw new Error("Saved request identity unavailable");
   const {turn_id}=admission;watch.id=turn_id;watch.admissionOutcome="accepted";
   if(watch.stopped)return turn_id;
   // Admission consumes its owning draft even when early cancellation finds
   // a request that already completed. Emit once before any terminal path.
   emit("started",{turn_id,screen:body.screen});
   if(watch.cancelRequested){await cancelKnown(watch);if(watch.stopped)return turn_id;}
   setState("running");
   return await observeAccepted(watch);

  } catch(error){
   if(!watch.stopped){
    // Early cancellation does not confirm an admission outcome. A deadline
    // failure must still explain that a server-side question may finish.
    const timedOut=error && ["AbortError","TimeoutError"].includes(error.name);
    finish(watch,{status:"error",error:timedOut
     ? watch.stage==="session"
      ? "Connection timed out. Try asking again; no question was sent."
      : watch.admissionOutcome==="rejected"
       ? requestFailureText(0)
       : "Research request timed out. Reopen history to recover the saved request."
     : watch.admissionOutcome==="unknown"
      ? "The research request could not be confirmed. Check Saved answers before asking again; the saved question may still finish."
      : error.message});
   }
   return null;
  }
 },[stop,emit,finish,cancelKnown,observeAccepted]);
 const observeExisting=useCallback(async turn_id=>{
  if(typeof turn_id!=="string" || !/^[a-zA-Z0-9-]{1,128}$/.test(turn_id)){setState("error");emit("error",{status:"error",error:"This saved question could not be checked. No new question was sent."});return null;}
  stop();setState("reconnecting");
  const watch={stopped:false,source:null,id:turn_id,stage:"observation",cancelRequested:false,cancellation:null,requireIdentity:true};observer.current=watch;
  return observeAccepted(watch);
 },[stop,emit,observeAccepted]);
 const cancel=useCallback(async()=>{
  const watch=observer.current;if(!watch || watch.stopped)return;
  watch.cancelRequested=true;setState("cancelling");
  if(watch.releaseRejected){finish(watch,{status:"cancelled",error:"Cancelled before research started"});}
  else if(watch.id)await cancelKnown(watch);
 },[cancelKnown,finish]);
 const disconnect=useCallback(()=>{stop();setState("idle");},[stop]);
 return {state,ask,cancel,disconnect,observeExisting};
}
