import {createContext,useCallback,useContext,useEffect,useMemo,useRef,useState} from "react";
import useScreenContext from "./useScreenContext";
import {parseChatNavigation,verifyNavigationTicker,isMarketQuestion,checkedChartAction,prepareScreenNavigation} from "./chatNavigation";
import useAgentStream from "./useAgentStream";
import {API} from "../config/api";
import {contextIdentity} from "./contextIdentity";
import {rangeResearchBlock} from '../lib/rangeAnalytics';
const AgentContext=createContext(null);
const SESSION_ENDED="floww-research-session-ended";
const HISTORY_TIMEOUT_MS=15000;
const failedStates=new Set(["failed","error","cancelled","interrupted"]);
export function useAgent(){return useContext(AgentContext);}
export default function AgentProvider({children,onNavigate}){
 const [turns,setTurns]=useState([]),[activeTurn,setActiveTurnState]=useState(null),[pendingTurn,setPendingTurn]=useState(null);
 const conversationParent=useRef(null),savedStateConflicts=useRef(new Map());
 const setActiveTurn=useCallback(turn=>{
  if(!turn)conversationParent.current=null;
  else if(!turn.localOnly)conversationParent.current=(turn._savedStateUnverified!==true && !savedStateConflicts.current.has(turn.turn_id) && ["completed","done"].includes(turn.status) && typeof turn.turn_id==="string" && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(turn.turn_id))?turn:null;
  setActiveTurnState(turn);
 },[]);
 const accepted=useRef(null),submittedRequest=useRef(null);
 const navigationEpoch=useRef(0),navigationSequence=useRef(0);const [navigating,setNavigating]=useState(false);
 useEffect(()=>()=>{navigationEpoch.current++;},[]);
 const [historyLoading,setHistoryLoading]=useState(false),historyRead=useRef(null);
 const [historyBrowsing,setHistoryBrowsing]=useState(false),historyBrowsingRef=useRef(false);
 const [historyMeta,setHistoryMeta]=useState(null),historyPage=useRef(null);
 const recentTurns=useRef([]),fullTurns=useRef(new Map());
 const [openingTurnId,setOpeningTurnId]=useState(null),savedTurnRead=useRef(null);
 const [question,setQuestionState]=useState("");
 const draft=useRef({question:"",revision:0}),submittedDraft=useRef(null),historyRequest=useRef(0);
 const setQuestion=useCallback(value=>{draft.current={question:value,revision:draft.current.revision+1};setQuestionState(value);},[]);
 const [open,setOpen]=useState(false),[barOpen,setBarOpen]=useState(false),[error,setErrorState]=useState(null),[progress,setProgress]=useState(null);
 const errorOwner=useRef(null);
 const setError=useCallback((value,owner=null)=>{errorOwner.current=owner;setErrorState(value);},[]);
 const stopHistory=useCallback(()=>{const read=historyRead.current;if(!read)return;historyRead.current=null;read.controller.abort();read.reject?.(new Error("History read cancelled"));clearTimeout(read.timer);},[]);
 const stopSavedTurn=useCallback(()=>{const read=savedTurnRead.current;if(!read)return;savedTurnRead.current=null;read.controller.abort();read.reject?.(new Error("Saved answer read cancelled"));clearTimeout(read.timer);},[]);
 useEffect(()=>()=>{stopHistory();stopSavedTurn();},[stopHistory,stopSavedTurn]);
 const [context]=useScreenContext();const frozen=useRef(null),busy=useRef(null),historyEpoch=useRef(0),ending=useRef(false);
 const [endingSession,setEndingSession]=useState(false),[sessionNotice,setSessionNotice]=useState(null);
 const [settingsOpen,setSettingsOpen]=useState(false),[settingsPending,setSettingsPendingState]=useState(false);
 const settingsGuard=useRef(false);
 const setSettingsPending=useCallback(value=>{settingsGuard.current=Boolean(value);setSettingsPendingState(Boolean(value));},[]);
 const grounding=useRef(new Map());
 const rememberFullTurn=useCallback(turn=>{
  if(!turn || turn._historySummary || turn.localOnly || typeof turn.turn_id!=="string")return;
  if(turn._savedStateUnverified!==true && ["completed","done"].includes(turn.status))savedStateConflicts.current.delete(turn.turn_id);
  fullTurns.current.delete(turn.turn_id);fullTurns.current.set(turn.turn_id,turn);
  if(fullTurns.current.size>20)fullTurns.current.delete(fullTurns.current.keys().next().value);
 },[]);
 const pushTurn=useCallback((turn,screen,select=true)=>{
  if(screen){grounding.current.set(turn.turn_id,contextIdentity(screen));if(grounding.current.size>20)grounding.current.delete(grounding.current.keys().next().value);}
  rememberFullTurn(turn);
  const recent=[turn,...recentTurns.current.filter(t=>t.turn_id!==turn.turn_id)].slice(0,20);recentTurns.current=recent;
  if(historyBrowsingRef.current)setTurns(rows=>rows.map(row=>row.turn_id===turn.turn_id?turn:row));else setTurns(recent);
  if(select){stopSavedTurn();setOpeningTurnId(null);setActiveTurn(turn);}
 },[rememberFullTurn,setActiveTurn,stopSavedTurn]);
 const answerContextStatus=!activeTurn?null:!grounding.current.has(activeTurn.turn_id)?"unverified_history":
  grounding.current.get(activeTurn.turn_id)===contextIdentity(context)?"current":"previous_selection";
 const {state:streamState,ask,cancel:cancelStream,disconnect,observeExisting}=useAgentStream({onEvent:(kind,payload)=>{
  if(kind==="started"){
   // Only accepted admission consumes the submitted draft. Later edits belong to the next question.
   const sent=submittedDraft.current;
   if(sent && draft.current.revision===sent.revision && draft.current.question===sent.question)setQuestion("");
   const progress="Checking saved evidence";
   accepted.current={...submittedRequest.current,turn_id:payload.turn_id,status:"running",progress};
   setPendingTurn(accepted.current);setProgress(progress);
  }
  else if(kind==="done"){
   stopSavedTurn();setOpeningTurnId(null);
   busy.current=null;
   pushTurn({...accepted.current,...payload,question:accepted.current?.question || payload.question,screen:accepted.current?.screen || payload.screen},frozen.current);
   accepted.current=null;setPendingTurn(null);setProgress(null);setError(null);
  }
  else if(kind==="error"){
   if(failedStates.has(payload.status))busy.current=null;
   if(accepted.current && failedStates.has(payload.status)){
    pushTurn({...accepted.current,...payload,turn_id:accepted.current.turn_id,question:accepted.current.question,screen:accepted.current.screen},frozen.current,false);
    accepted.current=null;setPendingTurn(null);setProgress(null);
   }
   if(!accepted.current && failedStates.has(payload.status))setProgress(null);
   setError(payload.error || payload.message || `Research ${payload.status || "unavailable"}`);
  }
  else {const progress=payload.message || payload.tool || "Checking saved evidence";setProgress(progress);setPendingTurn(turn=>turn?{...turn,progress}:null);}
 }});
 useEffect(()=>{if(accepted.current)setPendingTurn(turn=>turn?{...turn,status:streamState}:null);},[streamState]);
 const state=navigating?"navigating":streamState;
 const cancel=useCallback(()=>{
  if(navigating){navigationEpoch.current++;busy.current=null;setNavigating(false);setProgress(null);setError("Navigation cancelled. No page was opened.");return;}
  return cancelStream();
 },[navigating,cancelStream,setError]);
 const retryQuestion=useCallback(turn=>{
  // Restores text only. The next explicit submission uses the current selection.
  if(typeof turn?.question!=="string" || !turn.question.trim())return;
  setQuestion(turn.question);
 },[setQuestion]);
 const clearSessionView=useCallback(()=>{
  historyEpoch.current++;navigationEpoch.current++;setNavigating(false);stopHistory();stopSavedTurn();setHistoryLoading(false);setOpeningTurnId(null);busy.current=null;disconnect();
   historyBrowsingRef.current=false;setHistoryBrowsing(false);historyPage.current=null;setHistoryMeta(null);recentTurns.current=[];fullTurns.current.clear();savedStateConflicts.current.clear();
  accepted.current=null;submittedRequest.current=null;setPendingTurn(null);
  setSettingsPending(false);setSettingsOpen(false);setQuestion("");submittedDraft.current=null;setTurns([]);setActiveTurn(null);grounding.current.clear();frozen.current=null;setProgress(null);setError(null);
  setSessionNotice("Research session ended. Saved answers remain stored; reopening them requires authorized recovery.");
 },[disconnect,setQuestion,setSettingsPending,stopHistory,stopSavedTurn]);
 useEffect(()=>{
  const onStorage=e=>{if(e.key===SESSION_ENDED && e.newValue)clearSessionView();};
  window.addEventListener(SESSION_ENDED,clearSessionView);window.addEventListener("storage",onStorage);
  return ()=>{window.removeEventListener(SESSION_ENDED,clearSessionView);window.removeEventListener("storage",onStorage);};
 },[clearSessionView]);
 const checkedCachedTurn=useCallback(summary=>{
  const completed=status=>status==="completed" || status==="done";
  const cached=recentTurns.current.find(turn=>turn.turn_id===summary.turn_id && !turn._historySummary) || fullTurns.current.get(summary.turn_id) || (activeTurn?.turn_id===summary.turn_id && !activeTurn._historySummary?activeTurn:null);
  const sameUnknown=cached?.status==null && summary.status==null;
  const earlierSummary=completed(cached?.status) && (completed(summary.status) || summary.status==null || ["queued","running"].includes(summary.status));
  return cached && (cached.status===summary.status || sameUnknown || earlierSummary)?cached:null;
 },[activeTurn]);
 const readHistoryPage=useCallback(async(cursor=null)=>{
  if(ending.current || historyRead.current || savedTurnRead.current)return;
  const previous=historyPage.current;
  if(cursor!==null && (!historyBrowsingRef.current || !previous?.hasMore || previous.nextCursor!==cursor))return;
  const epoch=historyEpoch.current,request=++historyRequest.current;
  const read={controller:new AbortController(),timer:null,reject:null};historyRead.current=read;setHistoryLoading(true);
  const isCurrent=()=>epoch===historyEpoch.current && request===historyRequest.current && historyRead.current===read;
  try{
   const deadline=new Promise((_,reject)=>{read.reject=reject;read.timer=setTimeout(()=>{read.controller.abort();reject(new Error("History timed out"));},HISTORY_TIMEOUT_MS);});
   const query=new URLSearchParams({limit:"20"});if(cursor!==null)query.set("cursor",cursor);
   const data=await Promise.race([(async()=>{
    const res=await fetch(API+"/agent/history/page?"+query.toString(),{credentials:"include",signal:read.controller.signal});
    if(!res.ok)throw new Error();return res.json();
   })(),deadline]);
   if(!isCurrent())return;
   if(!Array.isArray(data?.turns) || data.turns.length>20 || data.turns.some(turn=>!turn || typeof turn.turn_id!=="string" || !turn.turn_id.trim()) || typeof data.has_more!=="boolean")throw new Error("Invalid saved history page");
   const ids=data.turns.map(turn=>turn.turn_id);if(new Set(ids).size!==ids.length)throw new Error("Repeated saved history rows");
   const next=data.next_cursor;
   if(data.has_more ? typeof next!=="string" || !next.trim() || next.length>2048 || !ids.length : next!==null)throw new Error("Invalid saved history cursor");
   if(cursor!==null && (next===cursor || previous.cursors?.includes(next) || ids.some(id=>previous.ids.has(id))))throw new Error("Saved history page did not advance");
   for(const summary of data.turns){
    const held=activeTurn?.turn_id===summary.turn_id && !activeTurn._historySummary?activeTurn:fullTurns.current.get(summary.turn_id) || recentTurns.current.find(row=>row.turn_id===summary.turn_id && !row._historySummary);
    if(held && held.status!==summary.status && ["failed","error","cancelled","interrupted"].includes(summary.status)){
     savedStateConflicts.current.set(summary.turn_id,summary.status);
     if(conversationParent.current?.turn_id===summary.turn_id)conversationParent.current=null;
    }
   }
   const retained=new Set([...fullTurns.current.keys(),...recentTurns.current.map(row=>row.turn_id),activeTurn?.turn_id]);
   for(const id of savedStateConflicts.current.keys())if(!retained.has(id))savedStateConflicts.current.delete(id);
   const rows=data.turns.map(summary=>{const cached=checkedCachedTurn(summary);return cached?{...summary,...cached,_historySummary:false}:{...summary,_historySummary:true};});
   const meta={hasMore:data.has_more,nextCursor:next,pageNumber:cursor===null?1:(previous.pageNumber || 1)+1,ids:new Set(ids),cursors:cursor===null?[]:[...(previous.cursors || []),cursor].slice(-20)};
   historyPage.current=meta;historyBrowsingRef.current=true;setHistoryBrowsing(true);setHistoryMeta({hasMore:meta.hasMore,nextCursor:meta.nextCursor,pageNumber:meta.pageNumber});setTurns(rows);
   if(errorOwner.current==="history")setError(null);return true;
  }catch{if(isCurrent())setError("Saved history is unavailable or its next page could not be checked. Your last checked page and current answer are still shown.","history");}
  finally{clearTimeout(read.timer);if(historyRead.current===read){historyRead.current=null;setHistoryLoading(false);}}
 },[checkedCachedTurn,activeTurn,setError]);
 const loadHistory=useCallback(()=>readHistoryPage(null),[readHistoryPage]);
 const loadOlderHistory=useCallback(()=>{const page=historyPage.current;if(page?.hasMore && typeof page.nextCursor==="string" && page.nextCursor.trim())return readHistoryPage(page.nextCursor);},[readHistoryPage]);
 const returnToConversation=useCallback(()=>{if(historyRead.current || savedTurnRead.current)return;historyBrowsingRef.current=false;setHistoryBrowsing(false);setTurns(recentTurns.current);},[]);
 const openSavedTurn=useCallback(async(turn,{select=true,forceRead=false}={})=>{
  if(ending.current || historyRead.current || savedTurnRead.current || !turn || typeof turn.turn_id!=="string" || !turn.turn_id.trim())return null;
  const cached=turn.localOnly || !turn._historySummary?turn:checkedCachedTurn(turn);
  if(cached && !forceRead){if(select)setActiveTurn(cached);return cached;}
  const epoch=historyEpoch.current,read={controller:new AbortController(),timer:null,reject:null};savedTurnRead.current=read;setOpeningTurnId(turn.turn_id);
  const isCurrent=()=>epoch===historyEpoch.current && savedTurnRead.current===read;
  try{
   const deadline=new Promise((_,reject)=>{read.reject=reject;read.timer=setTimeout(()=>{read.controller.abort();reject(new Error("Saved answer timed out"));},HISTORY_TIMEOUT_MS);});
   const data=await Promise.race([(async()=>{
    const res=await fetch(`${API}/agent/turn/${encodeURIComponent(turn.turn_id)}`,{credentials:"include",signal:read.controller.signal});
    if(!res.ok)throw new Error();const data=await res.json();return data?.turn || data;
   })(),deadline]);
   if(!isCurrent())return null;
   if(!data || Array.isArray(data) || data.turn_id!==turn.turn_id || data.status!=null && typeof data.status!=="string")throw new Error("Saved answer identity unavailable");
   const knownState=["completed","done","failed","error","cancelled","interrupted","queued","running"].includes(data.status);
   const answer=data.answer;
   const readable=typeof data.text==="string" && Boolean(data.text.trim()) || answer && typeof answer==="object" && !Array.isArray(answer) && (typeof answer.summary==="string" && Boolean(answer.summary.trim()) || Array.isArray(answer.sections) && answer.sections.some(section=>typeof section?.text==="string" && section.text.trim()) || Array.isArray(answer.gaps) && answer.gaps.some(gap=>typeof gap==="string" && gap.trim()) || Array.isArray(answer.facts) && answer.facts.some(fact=>fact && typeof fact.id==="string" && typeof fact.metric==="string"));
   if(!knownState && !readable)throw new Error("Older saved answer has no readable content");
   const full={...data,_historySummary:false,_savedStateUnverified:!knownState};savedStateConflicts.current.delete(full.turn_id);rememberFullTurn(full);setTurns(rows=>rows.map(row=>row.turn_id===full.turn_id?full:row));
   if(select)setActiveTurn(full);if(errorOwner.current==="saved-turn")setError(null);return full;
  }catch{if(isCurrent())setError("This saved answer is unavailable. Your current answer is still shown.","saved-turn");return null;}
  finally{clearTimeout(read.timer);if(savedTurnRead.current===read){savedTurnRead.current=null;setOpeningTurnId(null);}}
 },[checkedCachedTurn,rememberFullTurn,setActiveTurn,setError]);
 const askQuestion=useCallback(async(question,{consumeDraft=true}={})=>{
  if(busy.current || ending.current || !question.trim())return;
  const navigation=parseChatNavigation(question);
  if(navigation){
   stopSavedTurn();setOpeningTurnId(null);
   const requestOwner={};busy.current=requestOwner;const epoch=++navigationEpoch.current;
   const sent=consumeDraft && draft.current.question===question?{...draft.current}:null;
   setNavigating(true);setError(null);setProgress("Opening your selection");
   try{
    if(navigation.history){if(await loadHistory()!==true)return;}
    else {
     if(typeof onNavigate!=="function")throw new Error("Page navigation is unavailable in this view.");
     const selectedTicker=navigation.ticker || (["heatseeker","skylit","trinity","steal-three"].includes(navigation.page) && typeof context.ticker==="string" ? context.ticker.replace(/^\^/,""):null);
     const ticker=selectedTicker?await verifyNavigationTicker(selectedTicker):null;
     if(epoch!==navigationEpoch.current)return;
     prepareScreenNavigation({...navigation,ticker});
     if(ticker)window.dispatchEvent(new CustomEvent("floww:focus-ticker",{detail:{ticker}}));
     onNavigate(navigation.page);
     pushTurn({turn_id:"navigation-"+Date.now()+"-"+(++navigationSequence.current),status:"completed",localOnly:true,question,ticker:ticker || context.ticker,created_at:new Date().toISOString(),text:"Opened "+navigation.label+(ticker?" for "+ticker:"")+"."},context);
    }
    if(epoch===navigationEpoch.current && sent && draft.current.revision===sent.revision && draft.current.question===sent.question)setQuestion("");
   }catch(error){if(epoch===navigationEpoch.current)setError(error.message || "This page could not be opened.");}
   finally{if(epoch===navigationEpoch.current){setNavigating(false);setProgress(null);}if(busy.current===requestOwner)busy.current=null;}
   return;
  }
  if(settingsGuard.current){setError("Confirm your AI choice in settings before asking. Reload choices if the save was not confirmed.");return;}
  const market=isMarketQuestion(question);
  const rangeBlock=market?null:rangeResearchBlock(context);
  if(rangeBlock){setError(rangeBlock);return;}
  if(!market && !context.ticker){setError("Choose a ticker in Screener, Options map or Unusual flow before asking.");return;}
  stopSavedTurn();setOpeningTurnId(null);
  const requestOwner={};busy.current=requestOwner;setError(null);setSessionNotice(context.displayMode === 'range-replay'
   ? 'Research only · raw population and full producer integrity qualification pending. Backend resolves stored facts; no crypto/production admission or native draft permission.'
   : null);setProgress("Starting research");
  submittedDraft.current=consumeDraft && draft.current.question===question?{...draft.current}:null;
  frozen.current=market?{page:"flowseeker-pro",ticker:null,dte:"all",displayMode:"live",scope:"market"}:JSON.parse(JSON.stringify(context));
  submittedRequest.current={question,scope:market?"market":"selected",ticker:frozen.current.ticker,screen:frozen.current,created_at:new Date().toISOString()};
  const horizon=frozen.current.displayMode === 'range-replay'
   ? `range:${frozen.current.mapQuery.min_dte}:${frozen.current.mapQuery.max_dte}` : frozen.current.dte;
  try {await ask({question,ticker:frozen.current.ticker,horizon,screen:frozen.current,...(market?{scope:"market"}:{}),...(conversationParent.current?{parent_turn_id:conversationParent.current.turn_id}:{})});}
  finally{if(busy.current===requestOwner)busy.current=null;}
 },[ask,context,setError,onNavigate,pushTurn,setQuestion,loadHistory,stopSavedTurn]);
 const openChartAction=useCallback(async(action,turn)=>{
  const navigation=checkedChartAction(action,turn?.answer);
  if(!navigation){setError("This saved chart choice could not be checked. Choose a stock in the search instead.");return;}
  await askQuestion("Open "+navigation.ticker+" chart",{consumeDraft:false});
 },[askQuestion,setError]);
 const continueTurn=useCallback(async turn=>{
  if(busy.current || ending.current || !turn || !["queued","running"].includes(turn.status))return;
  const epoch=historyEpoch.current;
  const saved=turn._historySummary?await openSavedTurn(turn,{select:false}):turn;
  if(!saved || epoch!==historyEpoch.current || busy.current || ending.current)return;
  if(["completed","done"].includes(saved.status)){setActiveTurn(saved);return;}
  if(!["queued","running"].includes(saved.status))return;
  const requestOwner={};busy.current=requestOwner;setError(null);setOpen(true);setProgress("Checking your saved question");
  frozen.current=saved.spec?.screen || saved.screen || null;
  accepted.current={...saved,screen:frozen.current};setPendingTurn(accepted.current);
  try{await observeExisting(saved.turn_id);}
  finally{if(busy.current===requestOwner)busy.current=null;}
 },[observeExisting,openSavedTurn,setActiveTurn,setError]);
 const endSession=useCallback(async()=>{
  if(busy.current || ending.current)return;
  ending.current=true;setEndingSession(true);setError(null);historyEpoch.current++;stopHistory();stopSavedTurn();setHistoryLoading(false);setOpeningTurnId(null);
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),10000);
  try{
   const res=await fetch(`${API}/agent/session/logout`,{method:"POST",credentials:"include",signal:controller.signal});
   if(!res.ok)throw new Error();
   window.dispatchEvent(new Event(SESSION_ENDED));
   try{localStorage.setItem(SESSION_ENDED,`${Date.now()}-${Math.random()}`);}catch{/* Server access is revoked even when cross-tab storage is unavailable. */}
  }catch{setError("Ending this session could not be confirmed. Your answer remains visible; try again.");}
  finally{clearTimeout(timer);ending.current=false;setEndingSession(false);}
 },[setError,stopHistory,stopSavedTurn]);
 const value=useMemo(()=>({parentTurn:conversationParent.current,question,setQuestion,settingsOpen,setSettingsOpen,settingsPending,setSettingsPending,turns,activeTurn,pendingTurn,retryQuestion,continueTurn,openChartAction,openSavedTurn,openingTurnId,historyBrowsing,activeHistoryConflict:savedStateConflicts.current.get(activeTurn?.turn_id) || null,historyHasMore:Boolean(historyMeta?.hasMore),historyPageNumber:historyMeta?.pageNumber || 0,loadOlderHistory,returnToConversation,historyLoading,answerContextStatus,setActiveTurn,pushTurn,open,setOpen,barOpen,setBarOpen,askQuestion,cancel,state,error,progress,context,requestContext:frozen.current,loadHistory,endSession,endingSession,sessionNotice}),[question,setQuestion,settingsOpen,settingsPending,setSettingsPending,turns,activeTurn,pendingTurn,retryQuestion,openSavedTurn,openingTurnId,historyBrowsing,historyMeta,loadOlderHistory,returnToConversation,historyLoading,answerContextStatus,pushTurn,open,barOpen,askQuestion,cancel,state,error,progress,context,loadHistory,endSession,endingSession,sessionNotice]);
 return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}
