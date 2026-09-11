import {createContext,useCallback,useContext,useEffect,useMemo,useRef,useState} from "react";
import useScreenContext from "./useScreenContext";
import useAgentStream from "./useAgentStream";
import {API} from "../config/api";
const AgentContext=createContext(null);
const SESSION_ENDED="floww-research-session-ended";
export function useAgent(){return useContext(AgentContext);}
export default function AgentProvider({children}){
 const [turns,setTurns]=useState([]),[activeTurn,setActiveTurn]=useState(null);
 const [open,setOpen]=useState(false),[barOpen,setBarOpen]=useState(false),[error,setError]=useState(null),[progress,setProgress]=useState(null);
 const [context]=useScreenContext();const frozen=useRef(null),busy=useRef(false),historyEpoch=useRef(0),ending=useRef(false);
 const [endingSession,setEndingSession]=useState(false),[sessionNotice,setSessionNotice]=useState(null);
 const pushTurn=useCallback(turn=>{setTurns(rows=>[turn,...rows.filter(t=>t.turn_id!==turn.turn_id)].slice(0,20));setActiveTurn(turn);},[]);
 const {state,ask,cancel,disconnect}=useAgentStream({onEvent:(kind,payload)=>{
  if(kind==="done"){pushTurn(payload);setError(null);}
  else if(kind==="error"){setError(payload.error || payload.message || `Research ${payload.status || "unavailable"}`);}
  else setProgress(payload.message || payload.tool || "Checking saved evidence");
 }});
 const clearSessionView=useCallback(()=>{
  historyEpoch.current++;busy.current=false;disconnect();
  setTurns([]);setActiveTurn(null);frozen.current=null;setProgress(null);setError(null);
  setSessionNotice("Research session ended. Saved answers remain stored; reopening them requires authorized recovery.");
 },[disconnect]);
 useEffect(()=>{
  const onStorage=e=>{if(e.key===SESSION_ENDED && e.newValue)clearSessionView();};
  window.addEventListener(SESSION_ENDED,clearSessionView);window.addEventListener("storage",onStorage);
  return ()=>{window.removeEventListener(SESSION_ENDED,clearSessionView);window.removeEventListener("storage",onStorage);};
 },[clearSessionView]);
 const askQuestion=useCallback(async(question)=>{
  if(busy.current || ending.current || !question.trim())return;
  if(!context.ticker){setError("Select a ticker first.");return;}
  busy.current=true;setError(null);setSessionNotice(null);setProgress("Starting research");
  frozen.current=JSON.parse(JSON.stringify(context));
  const epoch=historyEpoch.current;
  try {await ask({question,ticker:frozen.current.ticker,horizon:frozen.current.dte,screen:frozen.current});}
  finally{if(epoch===historyEpoch.current)busy.current=false;}
 },[ask,context]);
 const loadHistory=useCallback(async()=>{
  if(ending.current)return;
  const epoch=historyEpoch.current;
  try{const res=await fetch(`${API}/agent/history`,{credentials:"include"});if(!res.ok)throw new Error();const data=await res.json();if(epoch===historyEpoch.current)setTurns(data.turns || []);}
  catch{if(epoch===historyEpoch.current)setError("Saved history is unavailable. Your current answer is still shown.");}
 },[]);
 const endSession=useCallback(async()=>{
  if(busy.current || ending.current)return;
  ending.current=true;setEndingSession(true);setError(null);historyEpoch.current++;
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),10000);
  try{
   const res=await fetch(`${API}/agent/session/logout`,{method:"POST",credentials:"include",signal:controller.signal});
   if(!res.ok)throw new Error();
   window.dispatchEvent(new Event(SESSION_ENDED));
   try{localStorage.setItem(SESSION_ENDED,`${Date.now()}-${Math.random()}`);}catch{/* Server access is revoked even when cross-tab storage is unavailable. */}
  }catch{setError("Ending this session could not be confirmed. Your answer remains visible; try again.");}
  finally{clearTimeout(timer);ending.current=false;setEndingSession(false);}
 },[]);
 const value=useMemo(()=>({turns,activeTurn,setActiveTurn,pushTurn,open,setOpen,barOpen,setBarOpen,askQuestion,cancel,state,error,progress,context,requestContext:frozen.current,loadHistory,endSession,endingSession,sessionNotice}),[turns,activeTurn,pushTurn,open,barOpen,askQuestion,cancel,state,error,progress,context,loadHistory,endSession,endingSession,sessionNotice]);
 return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}
