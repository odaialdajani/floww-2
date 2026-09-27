import {useState} from "react";
import {useAgent} from "./AgentProvider";
import AgentPanelAnswer from "./AgentPanelAnswer";
import AgentModelSettings from "./AgentModelSettings";
export default function AgentConversation(){
 const a=useAgent();const [question,setQuestion]=useState("");
 const [savingAI,setSavingAI]=useState(false);
 const busy=["asking","running","reconnecting","cancelling"].includes(a.state);
 const ctx=busy ? a.requestContext || a.context : a.context;
 return <div className="lodestar-conversation">
  <p className="lodestar-context">Selected: {ctx?.ticker || "choose a ticker"} · {ctx?.dte || "all"}</p>
  <AgentModelSettings disabled={busy || a.endingSession} onSaving={setSavingAI}/>
  <form onSubmit={e=>{e.preventDefault();if(question.trim() && !savingAI){a.askQuestion(question);setQuestion("");}}}>
   <label htmlFor="lodestar-question">Ask about the selected market</label>
   <textarea id="lodestar-question" autoFocus value={question} onChange={e=>setQuestion(e.target.value)} placeholder="What changed, and what supports it?" maxLength={2000}/>
   <div><button type="submit" disabled={busy || savingAI || a.endingSession || !question.trim()}>Ask</button>{busy && <button type="button" onClick={a.cancel}>Cancel</button>}<button type="button" disabled={a.endingSession} onClick={a.loadHistory}>Saved answers</button>
   <button type="button" disabled={busy || savingAI || a.endingSession} onClick={a.endSession} title="Ends this browser's access. Saved answers remain stored; reopening them requires authorized recovery.">{a.endingSession?"Ending session…":"End research session"}</button></div>
  </form>
  {busy && <p role="status">{a.state==="reconnecting"?"Reconnecting to your saved request":a.progress || "Checking evidence"}</p>}
  {a.error && <p role="alert">{a.error}</p>}
  {a.sessionNotice && <p role="status">{a.sessionNotice}</p>}
  <AgentPanelAnswer turn={a.activeTurn}/>
  {a.turns.length>0 && <details><summary>History ({a.turns.length})</summary>{a.turns.map(t=><button key={t.turn_id} onClick={()=>a.setActiveTurn(t)}>{t.ticker} · {t.question || "Saved answer"}</button>)}</details>}
 </div>;
}
