import {useCallback,useMemo,useSyncExternalStore} from "react";
import axios from "axios";
import {fetchFullUniverse} from "./tickerUniverse";
const CACHE_MS=5*60*1000,entries=new Map();
function publish(entry,patch){entry.snapshot={...entry.snapshot,...patch};entry.listeners.forEach(fn=>fn());}
function entryFor(api){
 if(entries.has(api))return entries.get(api);
 for(const [key,item] of entries){if(entries.size<4)break;if(!item.listeners.size && !item.request)entries.delete(key);}
 const entry={listeners:new Set(),request:null,lastCompleted:0,snapshot:{tickers:null,status:"loading"},revision:0};
 entries.set(api,entry);return entry;
}
async function load(entry,api,force=false){
 if(entry.request && !force)return;
 if(!force && entry.lastCompleted && Date.now()-entry.lastCompleted<CACHE_MS)return;
 entry.request?.abort();const controller=new AbortController(),revision=++entry.revision;entry.request=controller;
 publish(entry,{status:"loading"});const current=()=>entry.request===controller && entry.revision===revision && !controller.signal.aborted;
 const get=url=>axios.get(url,{signal:controller.signal,timeout:30000});
 try{
  let base=null;
  try{const response=await get(api+"/tickers");base=response.data || null;if(current() && base && !entry.snapshot.tickers)publish(entry,{tickers:base});}catch{/* Prior full list is kept, with incomplete status below. */}
  if(!current())return;
  const full=await fetchFullUniverse(get,api);
  if(!current())return;
  const tickers=full.symbols.length?{trinity:base?.trinity || [],default:base?.default || [],popular:full.symbols}:entry.snapshot.tickers;
  entry.lastCompleted=Date.now();publish(entry,{tickers,status:!full.complete?"incomplete":full.stale?"saved":"complete"});
 }finally{if(entry.request===controller)entry.request=null;}
}
// Share only a dated stock directory, never market readings or account state.
export default function useTickerDirectory(api){
 const entry=useMemo(()=>entryFor(api),[api]);
 const subscribe=useCallback(listener=>{
  entry.listeners.add(listener);load(entry,api);
  return ()=>{entry.listeners.delete(listener);if(!entry.listeners.size && entry.request){entry.request.abort();entry.request=null;entry.revision++;publish(entry,{status:"incomplete"});}};
 },[entry,api]);
 const snapshot=useSyncExternalStore(subscribe,()=>entry.snapshot,()=>entry.snapshot);
 const retry=useCallback(()=>load(entry,api,true),[entry,api]);
 return {...snapshot,retry};
}

// Explicit reset starts a new catalogue check; normal tab changes reuse it.
export function clearTickerDirectoryCache(){
 for(const [api,entry] of entries){
  entry.request?.abort();entry.request=null;entry.revision++;entry.lastCompleted=0;
  if(entry.listeners.size){publish(entry,{tickers:null,status:"loading"});load(entry,api,true);}
  else entries.delete(api);
 }
}
