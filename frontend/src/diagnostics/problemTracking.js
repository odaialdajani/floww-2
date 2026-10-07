import {API, BACKEND_URL} from "../config/api";
const KEY="floww.problemQueue";
const SAFE_READS=new Set(["/api/flowseeker/scan","/api/flowseeker/scan/history","/api/flowseeker/alerts/feed","/api/agent/models","/api/agent/prefs","/api/health"]);
const NAMES=new Set(["Error","TypeError","ReferenceError","RangeError","SyntaxError","AbortError","NetworkError"]);
let queue=[],installed=false,nativeFetch=null,flushing=false;
try {const saved=JSON.parse(localStorage.getItem(KEY)||"[]");if(Array.isArray(saved))queue=saved.slice(-30).map(clean);}catch{}
function clean(event) {
 const row={kind:event.kind};
 row.event_id=(typeof event.event_id==="string" && /^[a-f0-9-]{36}$/.test(event.event_id)?event.event_id:null) || (window.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g,c=>{const r=Math.floor(Math.random()*16);return (c==="x"?r:(r&3)|8).toString(16);}));
 if(typeof event.route==="string" && event.route.startsWith("/"))row.route=event.route.split(/[?#]/)[0].slice(0,200);
 if(["GET","POST","PUT","PATCH","DELETE","HEAD"].includes(event.method))row.method=event.method;
 if(NAMES.has(event.name))row.name=event.name;
 for(const key of ["status","duration_ms"])if(Number.isFinite(event[key]) && event[key]>=0)row[key]=Math.round(Math.min(event[key],3600000));
 if(["attempted","succeeded","failed"].includes(event.result))row.result=event.result;
 return row;
}
export function reportProblem(event) {
 try {queue.push(clean(event));queue=queue.slice(-30);localStorage.setItem(KEY,JSON.stringify(queue));}catch{}
}
export async function flushProblems() {
 if(!nativeFetch || !queue.length || flushing)return;
 flushing=true;
 const batch=queue.slice(0,30);
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),4000);
 try {
  const response=await nativeFetch(API+"/diagnostics/events",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({events:batch}),signal:controller.signal});
  if(response.ok){queue=queue.filter(row=>!batch.includes(row));try{localStorage.setItem(KEY,JSON.stringify(queue));}catch{}}
 }catch{}finally{clearTimeout(timeout);flushing=false;}
}
export function startProblemTracking() {
 if(installed || typeof window.fetch!=="function")return ()=>{};
 installed=true;nativeFetch=window.fetch.bind(window);
 const prior=window.fetch,retried=new Map();
 const wrapped=async(input,options={})=>{
  let url;try{url=new URL(typeof input==="string" || input instanceof URL?input:input.url,window.location.href);}catch{return nativeFetch(input,options);}
  const method=String(options.method || input?.method || "GET").toUpperCase(),signal=options.signal || input?.signal;
  const local=url.origin===new URL(BACKEND_URL,window.location.href).origin && url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/diagnostics");
  if(!local)return nativeFetch(input,options);
  const start=performance.now();
  let response,error;
  try {response=await nativeFetch(input,options);}catch(e){error=e;}
  const aborted=signal?.aborted || error?.name==="AbortError";
  if(aborted)throw error || new DOMException("Aborted","AbortError");
  const duration=performance.now()-start;
  if(error || !response.ok)reportProblem({kind:"read_error",route:url.pathname,method,status:response?.status,name:error?.name});
  else if(duration>=2000)reportProblem({kind:"slow_read",route:url.pathname,method,duration_ms:duration});
  const retryable=method==="GET" && SAFE_READS.has(url.pathname) && (!response || [502,503,504].includes(response.status));
  if(retryable && Date.now()-(retried.get(url.pathname)||0)>30000){
   retried.set(url.pathname,Date.now());
   reportProblem({kind:"recovery",route:url.pathname,method,result:"attempted"});
   await new Promise(resolve=>setTimeout(resolve,750));
   if(signal?.aborted)throw error || new DOMException("Aborted","AbortError");
   try {
    const recovered=await nativeFetch(input,options);
    reportProblem({kind:"recovery",route:url.pathname,method,result:recovered.ok?"succeeded":"failed"});
    return recovered;
   }catch(e){if(e.name!=="AbortError")reportProblem({kind:"recovery",route:url.pathname,method,result:"failed"});throw e;}
  }
  if(error)throw error;
  return response;
 };
 window.fetch=wrapped;
 const onError=e=>reportProblem({kind:"browser_error",name:e.error?.name || "Unknown"});
 const onReject=e=>reportProblem({kind:"browser_error",name:e.reason?.name || "Unknown"});
 window.addEventListener("error",onError,true);window.addEventListener("unhandledrejection",onReject);
 let last=performance.now(),lagAt=0;
 const heartbeat=setInterval(()=>{
  const now=performance.now(),lag=now-last-1000;last=now;
  if(document.visibilityState==="visible" && lag>=1000 && now-lagAt>30000){lagAt=now;reportProblem({kind:"screen_lag",duration_ms:lag});}
 },1000);
 const xhr=window.XMLHttpRequest?.prototype,oldOpen=xhr?.open,oldSend=xhr?.send,tag=Symbol("flowwRead");
 const watchedOpen=function(method,url,...args){try{const parsed=new URL(url,window.location.href);this[tag]={method:String(method).toUpperCase(),route:parsed.pathname,local:parsed.origin===new URL(BACKEND_URL,window.location.href).origin && parsed.pathname.startsWith("/api/") && !parsed.pathname.startsWith("/api/diagnostics")};}catch{this[tag]=null;}return oldOpen.call(this,method,url,...args);};
 const watchedSend=function(...args){const info=this[tag];if(info?.local){const started=performance.now();let aborted=false;const onAbort=()=>{aborted=true;};this.addEventListener("abort",onAbort,{once:true});this.addEventListener("loadend",()=>{this.removeEventListener("abort",onAbort);if(aborted)return;const duration=performance.now()-started;if(this.status===0 || this.status>=400)reportProblem({kind:"read_error",route:info.route,method:info.method,status:this.status});else if(duration>=2000)reportProblem({kind:"slow_read",route:info.route,method:info.method,duration_ms:duration});},{once:true});}return oldSend.apply(this,args);};
 if(xhr){xhr.open=watchedOpen;xhr.send=watchedSend;}
 const OriginalSocket=window.WebSocket;
 const TrackedSocket=OriginalSocket && new Proxy(OriginalSocket,{construct(Target,args,newTarget){
  const socket=Reflect.construct(Target,args,newTarget);
  try{const url=new URL(args[0],window.location.href);if(url.origin.replace(/^ws/,"http")===new URL(BACKEND_URL,window.location.href).origin){
   let reported=false;const report=()=>{if(!reported){reported=true;reportProblem({kind:"socket_error",route:url.pathname});}};
   socket.addEventListener("error",report);socket.addEventListener("close",event=>{if(!event.wasClean)report();},{once:true});
  }}catch{}
  return socket;
 }});
 if(TrackedSocket)window.WebSocket=TrackedSocket;
 const flush=setInterval(flushProblems,5000);
 flushProblems();
 return ()=>{if(TrackedSocket && window.WebSocket===TrackedSocket)window.WebSocket=OriginalSocket;if(xhr?.open===watchedOpen)xhr.open=oldOpen;if(xhr?.send===watchedSend)xhr.send=oldSend;if(window.fetch===wrapped)window.fetch=prior;installed=false;clearInterval(heartbeat);clearInterval(flush);window.removeEventListener("error",onError,true);window.removeEventListener("unhandledrejection",onReject);};
}
