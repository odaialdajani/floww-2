import {useEffect,useState} from "react";
import axios from "axios";
import {API} from "../../config/api";
const count=value=>Number.isSafeInteger(value)&&value>=0;
export function checkMarketCoverage(body){
 if(!body||!["available","not_checked"].includes(body.status)||typeof body.checked_at!=="string"||!Number.isFinite(Date.parse(body.checked_at))||!body.directory||!body.options||!body.provider)throw Error("Invalid feed counts");
 const directory=body.directory,options=body.options;
 if(typeof directory.available!=="boolean"||typeof directory.stale!=="boolean"||(directory.available&&(!count(directory.total)||!count(directory.optionable_total)||directory.optionable_total>directory.total)))throw Error("Invalid listed counts");
 if(options.received_recently!==null&&(!count(options.received_recently)||!Array.isArray(options.receipt_times)||options.receipt_times.length!==options.received_recently||!Number.isFinite(options.window_seconds)||options.window_seconds<=0||options.receipt_times.some(value=>!Number.isFinite(value)||value<0)))throw Error("Invalid option reads");
 if(body.provider.last_success_at!==null&&(!Number.isFinite(body.provider.last_success_at)||body.provider.last_success_at<0))throw Error("Invalid feed clock");
 return body;
}
export default function useMarketCoverage(enabled){
 const [state,setState]=useState({data:null,status:"loading"}),[now,setNow]=useState(()=>Date.now()/1000);
 useEffect(()=>{
  if(!enabled)return undefined;
  let active=true,controller=null;
  const load=async()=>{
   controller?.abort();const request=new AbortController();controller=request;
   try{const {data}=await axios.get(API+"/market/status",{signal:request.signal,timeout:15000,withCredentials:false});
    if(active&&controller===request&&!request.signal.aborted){setState({data:checkMarketCoverage(data),status:"ready"});setNow(Date.now()/1000);}
   }catch{if(active&&controller===request&&!request.signal.aborted)setState(previous=>({data:previous.data,status:"unavailable"}));}
  };
  load();const poll=setInterval(load,30000),clock=setInterval(()=>setNow(Date.now()/1000),5000);
  return()=>{active=false;controller?.abort();clearInterval(poll);clearInterval(clock);};
 },[enabled]);
 const data=state.data,window=data?.options.window_seconds;
 const fresh=state.status==="ready"&&data?.options.received_recently!==null&&Array.isArray(data?.options.receipt_times)
  ?data.options.receipt_times.filter(time=>now-time>=-30&&now-time<=window).length:null;
 const last=data?.provider.last_success_at;
 return {...state,fresh,now,lastSuccessAge:state.status==="ready"&&Number.isFinite(last)&&now-last>=-30?Math.max(0,now-last):null};
}
