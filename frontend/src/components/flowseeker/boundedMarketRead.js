const READ_TIMEOUT_MS=20000;
// Own both headers and body. Disposal/timeout releases the caller even when
// a transport does not settle, so a later poll can recover. Only GET is used.
export default async function boundedMarketRead(url,signal){
 if(signal?.aborted)throw new DOMException("Read stopped","AbortError");
 const controller=new AbortController();let timer,rejectStopped;
 const stopped=new Promise((_,reject)=>{rejectStopped=reject;});
 const stop=reason=>{controller.abort(reason);rejectStopped(reason);};
 const onAbort=()=>stop(new DOMException("Read stopped","AbortError"));
 signal?.addEventListener("abort",onAbort,{once:true});
 timer=setTimeout(()=>stop(new DOMException("Read timed out","TimeoutError")),READ_TIMEOUT_MS);
 try{return await Promise.race([(async()=>{const response=await fetch(url,{signal:controller.signal});if(!response.ok)throw new Error("HTTP "+response.status);return response.json();})(),stopped]);}
 finally{clearTimeout(timer);signal?.removeEventListener("abort",onAbort);controller.abort();}
}
