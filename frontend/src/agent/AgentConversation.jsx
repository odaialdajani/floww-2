import {memo,useCallback,useEffect,useMemo,useRef,useState,useId} from "react";
import {ArrowDown,ArrowUp,Settings} from "lucide-react";
import {useAgent} from "./AgentProvider";
import AgentPanelAnswer from "./AgentPanelAnswer";
import AssistantSettingsDialog from "./AssistantSettingsDialog";
import {followUpQuestions,starterQuestions} from "./chatQuestions";
import "./AssistantWorkspace.css";
const SavedAnswer=memo(AgentPanelAnswer);
const FAILED=new Set(["failed","error","cancelled","interrupted"]);
export default function AgentConversation({visible=true}){
 const a=useAgent();const {question,setQuestion}=a;
 const busy=["asking","running","reconnecting","cancelling","navigating"].includes(a.state);
 const ctx=busy ? a.requestContext || a.context : a.context;
 const thread=useMemo(()=>{
  const turns=a.turns || [];
  return turns.slice(0,20).filter(turn=>turn.turn_id!==a.pendingTurn?.turn_id).reverse();
 },[a.turns,a.activeTurn,a.pendingTurn?.turn_id]);
 const keptAnswer=a.activeTurn && !a.activeTurn._historySummary && a.activeTurn.turn_id!==a.pendingTurn?.turn_id && !thread.some(turn=>turn.turn_id===a.activeTurn.turn_id)?a.activeTurn:null;
 const displayedTurns=keptAnswer?[...thread,keptAnswer]:thread;
 const scroller=useRef(null),composer=useRef(null),stick=useRef(true),signature=useRef("");
 const [newAnswer,setNewAnswer]=useState(false);
 const jump=useCallback(()=>{const node=scroller.current;if(node){const last=node.querySelector(".assistant-turn:last-child");node.scrollTop=last?last.offsetTop:node.scrollHeight;stick.current=true;setNewAnswer(false);}},[]);
 const latestSignature=displayedTurns.map(t=>t.turn_id+":"+t.status).join("|")+":"+(a.pendingTurn?.turn_id || "")+":"+(a.pendingTurn?.status || "");
 useEffect(()=>{if(signature.current===latestSignature)return;signature.current=latestSignature;if(stick.current)jump();else setNewAnswer(true);},[latestSignature,jump]);
 useEffect(()=>{if(visible && stick.current)jump();},[visible,jump]);
 useEffect(()=>{if(a.historyBrowsing && scroller.current){scroller.current.scrollTop=0;stick.current=false;setNewAnswer(false);}},[a.historyBrowsing,a.historyPageNumber]);
 const fill=text=>{setQuestion(text);composer.current?.focus();};
 const suggestions=starterQuestions(ctx),followups=followUpQuestions(ctx?.ticker);
 const disabled=busy || a.settingsPending || a.endingSession;
 const send=()=>{if(question.trim() && !disabled)a.askQuestion(question);};
 const [savedDate,setSavedDate]=useState("");const dateId=useId();
 const marketDateParts=new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
 const marketDay=kind=>marketDateParts.find(part=>part.type===kind)?.value;const today=marketDay("year")+"-"+marketDay("month")+"-"+marketDay("day");
 const validSavedDate=/^\d{4}-\d{2}-\d{2}$/.test(savedDate) && Number(savedDate.slice(0,4))>0 && savedDate<=today && Number.isFinite(Date.parse(savedDate+"T00:00:00Z")) && new Date(savedDate+"T00:00:00Z").toISOString().slice(0,10)===savedDate;
 const dateUnavailable=ctx?.scope==="market"?"Choose one stock. Saved-date comparisons are unavailable for a market-wide question.":!ctx?.ticker || typeof ctx.ticker!=="string"?"Choose one stock to compare a saved date.":["replay","range-replay","range-live"].includes(ctx.displayMode)?"Saved-date comparisons are unavailable in replay or range views. Return to the live stock chart.":null;
 const fillSavedDate=()=>{if(disabled || dateUnavailable || !validSavedDate)return;fill("For "+ctx.ticker+", compare the currently selected reading with the latest compatible saved observation on "+savedDate+" in New York market time. Keep missing data unknown; do not substitute another date.");};
 const historyReadBusy=a.historyLoading || Boolean(a.openingTurnId) || a.endingSession;
 return <div className="lodestar-conversation assistant-conversation">
  <div className="assistant-context-row"><div><p className="lodestar-context">{ctx?.scope==="market"?"Market scan":ctx?.ticker ? "Selected: "+ctx.ticker+" · "+(ctx.dte || "all"):"Choose a stock or ask about all stocks"}</p><small>{busy?"This question keeps the selection it started with.":a.parentTurn?"Your next question can refer to your last opened answer and this selection.":"Your next question uses the current selection."}</small></div><button type="button" className="assistant-icon-button" aria-label="Ask FLOWW settings" aria-haspopup="dialog" aria-expanded={a.settingsOpen} onClick={e=>{e.currentTarget.focus();a.setSettingsOpen(true);}}><Settings size={17} aria-hidden="true"/></button></div>
  {a.historyBrowsing && <div className="assistant-history-controls" aria-label="Saved answer pages"><small>{a.historyPageNumber>1?"Older saved answers":"Latest saved answers"}</small><div><button type="button" disabled={historyReadBusy} onClick={a.loadHistory}>Latest answers</button>{a.historyHasMore && <button type="button" disabled={historyReadBusy} onClick={a.loadOlderHistory}>Older answers</button>}<button type="button" disabled={historyReadBusy} onClick={a.returnToConversation}>Current questions</button></div></div>}
  <div ref={scroller} className="assistant-thread" aria-label="Questions and saved answers" onScroll={e=>{const n=e.currentTarget;stick.current=n.scrollHeight-n.scrollTop-n.clientHeight<80;if(stick.current)setNewAnswer(false);}}>
   {a.historyBrowsing && !thread.length && <p className="assistant-selection-note">No saved answers were returned for this page.</p>}
   {!a.historyBrowsing && !thread.length && !keptAnswer && !a.pendingTurn && <section className="assistant-welcome"><small>MAKE SENSE OF THE READING</small><h3>What do you want to understand?</h3><p>Ask FLOWW explains stock readings and checks unusual activity across the available market scan. It shows what is missing and what has changed.</p>{suggestions.length?<div className="assistant-starters">{suggestions.map(s=><button key={s.label} type="button" disabled={disabled} onClick={()=>fill(s.question)}>{s.label}</button>)}</div>:<p>Open Stock chart or Screener and choose a stock first.</p>}<p className="assistant-welcome-note">Try “open NVDA chart” or “open screener”, or ask about unusual activity across all stocks. Nothing is sent until you press Ask.</p></section>}
   {displayedTurns.map(row=>{
    const conflict=a.activeHistoryConflict && a.activeTurn?.turn_id===row.turn_id && !a.activeTurn._historySummary?a.activeHistoryConflict:null;
    const turn=conflict?{...a.activeTurn,_savedStateUnverified:true}:row;
    const active=!turn._historySummary && turn.turn_id===a.activeTurn?.turn_id;
    const ticker=typeof turn.ticker==="string"?turn.ticker:"";
    const summary=(typeof turn.answer?.summary==="string"?turn.answer.summary:"") || (typeof turn.preview==="string"?turn.preview:"") || (typeof turn.text==="string"?turn.text:"") || "Saved answer preview is unavailable.";
    const failed=FAILED.has(turn.status),unfinished=["queued","running"].includes(turn.status);
    return <section className="assistant-turn" key={turn.turn_id} aria-label={ticker ? ticker+" question and answer":"Saved question and answer"}>
     {keptAnswer?.turn_id===turn.turn_id && <small className="assistant-kept-answer">Current answer kept open</small>}
     <div className="assistant-question"><small>You</small><p>{typeof turn.question==="string" && turn.question?turn.question:"The saved question is unavailable."}</p></div>
     <div className="assistant-response"><small>Ask FLOWW{turn.answer?.scope==="market" || turn.spec?.scope==="market" || turn.scope==="market"?" · Market scan":ticker ? " · "+ticker:""}</small>
      {conflict && <div className="assistant-selection-note" role="status"><p>The earlier answer is kept here. The latest saved state reports this question {conflict==='failed'?'failed':conflict==='cancelled'?'was cancelled':conflict==='interrupted'?'was interrupted':'had an error'}. Its saved state is unverified until checked.</p><button type="button" disabled={historyReadBusy} onClick={()=>a.openSavedTurn?.(row,{forceRead:true})}>Check saved details</button></div>}
      {unfinished?<div className="assistant-failed"><p>This saved question is still in progress.</p><button type="button" disabled={disabled} onClick={()=>a.continueTurn?.(turn)}>Check progress</button><small>This opens the same question; it does not ask again.</small></div>:failed?<div className="assistant-failed"><p>{turn.status==="cancelled"?"Question cancelled. No answer was created.":turn.status==="interrupted"?"Connection lost. The saved question may still finish; check Saved answers before asking again.":"This question could not be completed."}</p>{turn.error && <p>{typeof turn.error==="string"?turn.error:"The saved failure message is unavailable."}</p>}<button type="button" disabled={disabled} onClick={()=>{a.retryQuestion?.(turn);composer.current?.focus();}}>Retry question</button><small>Review the draft first. A retry uses your current selection.</small></div>:<>
       {active && !turn.localOnly && turn.answer?.scope!=="market" && a.answerContextStatus!=="current" && <p className="assistant-selection-note" role="status">{a.answerContextStatus==="previous_selection"?"This answer uses the selection saved when you asked. The screen may now show a different or newer reading.":"Saved answer. Its selection has not been checked against the current screen."}</p>}
       {active?<><SavedAnswer turn={turn} onChartAction={action=>a.openChartAction?.(action,turn)}/>{!turn.localOnly && turn.answer?.scope!=="market" && (ticker && ctx?.ticker===ticker?<div className="assistant-followups" aria-label="Follow-up questions">{followups.map(s=><button key={s.label} type="button" disabled={disabled} onClick={()=>fill(s.question)}>{s.label}</button>)}</div>:<p className="assistant-selection-note">Select {ticker || "the saved stock"} to ask a follow-up about this answer.</p>)}</>:<><p className="assistant-answer-preview">{summary.length>180?summary.slice(0,180)+"…":summary}</p><button type="button" disabled={historyReadBusy} onClick={()=>a.openSavedTurn?a.openSavedTurn(turn):a.setActiveTurn(turn)}>{a.openingTurnId===turn.turn_id?"Opening saved answer…":"Open full answer"}</button></>}
      </>}
     </div>
    </section>;
   })}
   {a.pendingTurn && <section className="assistant-turn assistant-pending" aria-label="Question in progress"><div className="assistant-question"><small>You</small><p>{typeof a.pendingTurn.question==="string"?a.pendingTurn.question:"The saved question is unavailable."}</p></div><div className="assistant-response"><small>Ask FLOWW · {a.pendingTurn.scope==="market"?"Market scan":typeof a.pendingTurn.ticker==="string"?a.pendingTurn.ticker:"Stock unavailable"}</small><p role="status">{a.state==="reconnecting"?"Reconnecting to your saved question…":a.state==="cancelling"?"Checking cancellation…":typeof a.pendingTurn.progress==="string" && a.pendingTurn.progress?a.pendingTurn.progress:typeof a.progress==="string" && a.progress?a.progress:"Checking the saved data…"}</p><div className="assistant-thinking" aria-hidden="true"><span/><span/><span/></div></div></section>}
  </div>
  {!a.historyBrowsing && thread.length>=20 && <p className="assistant-selection-note">Showing up to 20 recent questions. Open Saved answers to browse older questions.</p>}
  {newAnswer && <button type="button" className="assistant-new-answer" onClick={jump}><ArrowDown size={14} aria-hidden="true"/>New answer</button>}
  <div className="assistant-notices" aria-live="polite">
   {busy && !a.pendingTurn && <p role="status">{a.state==="reconnecting"?"Reconnecting to your saved request":a.state==="cancelling"?"Checking cancellation":typeof a.progress==="string" && a.progress?a.progress:"Checking evidence"}</p>}
   {a.historyLoading && <p role="status">Loading saved answers…</p>}
   {a.openingTurnId && <p role="status">Opening the full saved answer…</p>}
   {a.error && <p role="alert">{typeof a.error==="string"?a.error:"The saved problem description is unavailable."}</p>}
   {a.sessionNotice && <p role="status">{a.sessionNotice}</p>}
   {a.settingsPending && <p role="status">Confirm your AI choice in settings before asking.</p>}
  </div>
  <form className="assistant-composer" onSubmit={e=>{e.preventDefault();send();}}>
   <label htmlFor="lodestar-question">Ask about the selected market</label>
   <textarea ref={composer} id="lodestar-question" value={question} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if(e.key==="Enter" && !e.shiftKey && !e.nativeEvent.isComposing){e.preventDefault();send();}}} placeholder={ctx?.ticker?"Ask about "+ctx.ticker+", or choose a question above…":"Ask about all stocks, or open a stock chart…"} maxLength={2000}/>
   <details className="assistant-history-date"><summary>Compare a saved date</summary><p>Dates use New York market time. Use the latest matching saved reading that day; a closing reading must be verified. Missing data stays missing.</p>{dateUnavailable && <p role="status">{dateUnavailable}</p>}<label htmlFor={dateId}>Saved date</label><div className="assistant-history-date-actions"><input id={dateId} type="date" value={savedDate} min="0001-01-01" max={today} onChange={event=>setSavedDate(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();event.stopPropagation();}}}/><button type="button" disabled={disabled || Boolean(dateUnavailable) || !validSavedDate} onClick={fillSavedDate}>Use this date</button></div><small>This adds a draft. Press Ask to send it.</small></details>
   <div className="assistant-composer-actions"><button type="button" disabled={historyReadBusy} onClick={a.loadHistory}>{a.historyLoading?"Loading answers…":"Saved answers"}</button><span/>{busy && <button type="button" onClick={a.cancel}>Cancel</button>}<button type="submit" className="assistant-send" disabled={disabled || !question.trim()}><ArrowUp size={15} aria-hidden="true"/>Ask</button></div><small className="assistant-composer-hint">Enter to ask · Shift + Enter for a new line</small>
  </form>
  <AssistantSettingsDialog open={Boolean(a.settingsOpen && visible)} onClose={()=>a.setSettingsOpen(false)} disabled={busy || a.endingSession} onSaving={a.setSettingsPending} endSession={a.endSession} endingSession={a.endingSession} settingsPending={a.settingsPending}/>
 </div>;
}
