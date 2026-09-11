import {createContext,useCallback,useContext,useMemo,useRef,useState} from "react";
import useScreenContext from "./useScreenContext";
import useAgentStream from "./useAgentStream";
import {API} from "../config/api";
const AgentContext=createContext(null);
export function useAgent(){return useContext(AgentContext);}
export default function AgentProvider({children}){
 const [turns,setTurns]=useState([]),[activeTurn,setActiveTurn]=useState(null);
 const [open,setOpen]=useState(false),[barOpen,setBarOpen]=useState(false),[error,setError]=useState(null),[progress,setProgress]=useState(null);
 const [context]=useScreenContext();const frozen=useRef(null),busy=useRef(false);
 const pushTurn=useCallback(turn=>{setTurns(rows=>[turn,...rows.filter(t=>t.turn_id!==turn.turn_id)].slice(0,20));setActiveTurn(turn);},[]);
 const {state,ask,cancel}=useAgentStream({onEvent:(kind,payload)=>{
  if(kind==="done"){pushTurn(payload);setError(null);}
  else if(kind==="error"){setError(payload.error || payload.message || `Research ${payload.status || "unavailable"}`);}
  else setProgress(payload.message || payload.tool || "Checking saved evidence");
 }});
 const askQuestion=useCallback(async(question)=>{
  if(busy.current || !question.trim())return;
  if(!context.ticker){setError("Select a ticker first.");return;}
  busy.current=true;setError(null);setProgress("Starting research");
  frozen.current=JSON.parse(JSON.stringify(context));
  try {await ask({question,ticker:frozen.current.ticker,horizon:frozen.current.dte,screen:frozen.current});}
  finally{busy.current=false;}
 },[ask,context]);
 const loadHistory=useCallback(async()=>{
  try{const res=await fetch(`${API}/agent/history`,{credentials:"include"});if(!res.ok)throw new Error();const data=await res.json();setTurns(data.turns || []);}
  catch{setError("Saved history is unavailable. Your current answer is still shown.");}
 },[]);
 const value=useMemo(()=>({turns,activeTurn,setActiveTurn,pushTurn,open,setOpen,barOpen,setBarOpen,askQuestion,cancel,state,error,progress,context,requestContext:frozen.current,loadHistory}),[turns,activeTurn,pushTurn,open,barOpen,askQuestion,cancel,state,error,progress,context,loadHistory]);
 return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}
