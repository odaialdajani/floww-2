import Evidence from "./Evidence";
import {checkedChartAction} from "./chatNavigation";
import {savedAnswerView} from "./savedAnswerView";
import {readableGap,sectionLabel} from "./chatQuestions";
import {THINKING_LABELS,SPEED_LABELS} from "./AgentModelSettings";
import {readableScopeText,savedChartReading} from "./chartReading";
export default function AgentPanelAnswer({turn,onChartAction}){
 if(!turn)return null;
 if(turn.localOnly)return <article className="lodestar-answer" aria-label="App navigation"><p>{typeof turn.text==="string"?turn.text:"Navigation details are unavailable."}</p><small>Page opened in this chat. This is not a saved market reading.</small></article>;
 const {answer,incomplete}=savedAnswerView(turn.answer);
 const completed=["completed","done"].includes(turn.status) && turn._savedStateUnverified!==true;
 const date=answer?.history_baseline?.date;
 const dateSection=date?(answer?.sections || []).find(section=>section.name==="What changed"):null;
 const ticker=typeof turn.ticker==="string"?turn.ticker:"Stock unavailable";
 const unsupported=(answer?.model_sections || []).some(s=>!Array.isArray(s.fact_ids) || !s.fact_ids.length || s.fact_ids.some(id=>!(answer?.facts || []).some(f=>f.id===id)));
 const window=answer?.snapshots?.find(s=>s.ticker===ticker)?.window;
 const scope=window?.start && window?.end ? window.start===window.end ? window.start : `${window.start} to ${window.end}` : typeof turn.horizon==="string"?turn.horizon:"Scope unavailable";
 const chart=savedChartReading(answer,ticker);
 const primary=answer?.summary || (typeof turn.text==="string"?turn.text:"") || "No answer available";
 const explanations=(answer?.model_explanations || []).map(item=>({...item,text:readableScopeText(item.text).replace((item.ticker===ticker?ticker:"__none__")+" (scope all): ","")}));
 const assessment=[...new Set((answer?.model_sections || []).map(s=>s.text))];
 const generic=["Available readings are shown below.","Available readings are shown below. Exposure estimates do not establish trade direction."].includes(primary);
 return <article className="lodestar-answer" aria-label={`Research answer for ${ticker}`}>
  <h3>{answer?.scope==="market"?"Market scan":ticker+" · "+scope}</h3>
  <small>{turn.saved === false ? "Not saved" : completed?"Saved answer":"Saved answer status unknown"}</small>
  {date && <section className="assistant-date-result assistant-gaps" aria-label="Saved date comparison"><h4>Saved date comparison · {date}</h4><small>Requested date in New York market time.</small><p>{dateSection?readableScopeText(dateSection.text):"The dated comparison details are unavailable. The other saved readings remain below."}</p></section>}
  {chart && !generic && <p>{primary}</p>}
  {chart ? <section aria-label="Saved chart reading">{chart.map((line,i)=><p key={i}>{line.text}</p>)}</section> : <p>{generic && (answer?.facts || []).length?"The saved reading has important limits. Here is what can be checked.":primary}</p>}
  {incomplete && <p className="assistant-selection-note" role="status">Some saved answer details are incomplete. The readable parts are shown below.</p>}
  {unsupported && <p className="assistant-selection-note" role="status">Source references are unavailable for this saved section. Treat its interpretation as unverified.</p>}
  {answer?.model_status && <small className="assistant-answer-status">{!completed?"Saved explanation · completion unverified":unsupported || incomplete?"Saved interpretation · source support unverified":answer.mode==="model-assisted"?"AI explanation checked":/not supported|unavailable|limit reached/i.test(answer.model_status)?"Saved readings shown · AI explanation withheld":answer.model_status}</small>}
  {explanations.filter(item=>!chart || !["source_time","limited_comparison","no_current_readings"].includes(item.kind)).map(item=><p key={item.id} className="assistant-insight">{readableScopeText(item.text)}</p>)}
  {(answer?.model_sections || []).length>0 && <section className="assistant-assessment" aria-label={!completed || incomplete || unsupported?"Saved interpretation":"Checked assessment"}><h4>{!completed || incomplete || unsupported?"Saved interpretation":"What this means"}</h4>{assessment.slice(0,3).map((text,i)=><p key={i}>{text}</p>)}</section>}
  {(answer?.gaps || []).length>0 && <section className="assistant-gaps" aria-label="Missing and limited data"><h4>What is missing</h4><ul>{[...new Set(answer.gaps.map(readableGap))].slice(0,3).map((gap,i)=><li key={i}>{gap}</li>)}</ul><p>A stronger reading needs compatible, dated observations. Saving a value does not make it current.</p></section>}
  {answer?.scope==="market" && <section className="assistant-market-actions" aria-label="Stock charts from this scan">{(answer.actions || []).filter(action=>checkedChartAction(action,answer)).slice(0,3).map(action=><button key={action.ticker} type="button" disabled={!onChartAction} onClick={()=>onChartAction?.(action)}>Open {action.ticker} live chart</button>)}<p>Chart buttons open the current chart. This saved scan keeps its original times and coverage.</p></section>}
  <details className="assistant-answer-details"><summary>Source and answer details</summary>
  {(answer?.usage || []).filter(u=>u.provider).map((u,i)=>u.trace ? <section key={`usage-${i}`} className="lodestar-ai-usage" aria-label="Grounded model dispatch">
   <p>Requested: {u.trace.requested?.model || "Unverified"} · {THINKING_LABELS[u.trace.requested?.effort] || u.trace.requested?.effort || "Unverified"}</p>
   <p>{u.trace.effective ? `Effective: ${u.trace.effective.model} · ${THINKING_LABELS[u.trace.effective.effort] || u.trace.effective.effort}` : "Effective dispatch unverified — no fallback claimed."}</p>
   <details><summary>Dispatch trace</summary>
    <dl><dt>Correlation</dt><dd>{u.trace.correlation_id}</dd><dt>Context hash</dt><dd>{u.trace.context_hash}</dd>
     <dt>Observations</dt><dd>{(u.trace.observation_ids || []).join(", ") || "None"}</dd><dt>Evidence</dt><dd>{(u.trace.evidence_ids || []).join(", ") || "None"}</dd>
     <dt>Status / latency</dt><dd>{u.trace.status} · {u.trace.latency_ms} ms</dd>
     <dt>Speed</dt><dd>{u.trace.effective?.speed || "Unverified"}</dd>
    </dl><p>Dollar cost: {u.trace.actual_cost == null ? "unknown" : u.trace.actual_cost}. Uses your ChatGPT allowance.</p>
   </details>
  </section> : <p key={`usage-${i}`} className="lodestar-ai-usage">
   {u.provider} · {u.model}{u.effort && ` · ${THINKING_LABELS[u.effort] || u.effort} thinking`}{u.speed && ` · ${SPEED_LABELS[u.speed] || u.speed} speed`}
   {u.accounting==="subscription_usage" && <small>Uses your ChatGPT allowance; dollar cost is not reported.</small>}
  </p>)}

  {chart ? <details><summary>Source checks and limits</summary>
   {(answer?.model_explanations || []).filter(item=>["source_time","limited_comparison","no_current_readings"].includes(item.kind)).map(item=><p key={item.id}>{readableScopeText(item.text)}</p>)}
   {(answer?.model_relationships || []).map((text,i)=><p key={`relation-${i}`}>{readableScopeText(text)}</p>)}
   {(answer?.gaps || []).length>0 && <p>Missing: {answer.gaps.join(", ")}</p>}
  </details> : <>{(answer?.model_relationships || []).map((text,i)=><p key={`relation-${i}`}>{readableScopeText(text)}</p>)}{(answer?.gaps || []).length>0 && <p>Missing: {answer.gaps.join(", ")}</p>}</>}
  {(answer?.sections || []).map(s=><details key={s.name}><summary>{sectionLabel(s.name)}</summary><p>{readableScopeText(s.text)}</p></details>)}
  {(answer?.model_sections || []).map((s,i)=>{
   const ids=Array.isArray(s.fact_ids)?s.fact_ids:[],facts=Array.isArray(answer?.facts)?answer.facts:[];
   const missing=!Array.isArray(s.fact_ids) || !ids.length || ids.some(id=>!facts.some(f=>f?.id===id));
   return <details key={`model-${i}`}><summary>Interpretation · {sectionLabel(s.name)}</summary><p>{s.text}</p>{missing && <p>This section has incomplete source references.</p>}<ul>{ids.map(id=>{
    const fact=facts.find(f=>f?.id===id);return fact?<li key={id}>{fact.ticker} · {fact.metric}: {Array.isArray(fact.value)?"See evidence series":String(fact.value ?? "Unavailable")} {fact.unit}</li>:null;
   })}</ul></details>;
  })}
  <Evidence turn={{...turn,answer}}/>
  </details>
 </article>;
}
