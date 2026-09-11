import Evidence from "./Evidence";
import {THINKING_LABELS,SPEED_LABELS} from "./AgentModelSettings";
import {readableScopeText,savedChartReading} from "./chartReading";
export default function AgentPanelAnswer({turn}){
 if(!turn)return null;
 const answer=turn.answer;
 const window=answer?.snapshots?.find(s=>s.ticker===turn.ticker)?.window;
 const scope=window?.start && window?.end ? window.start===window.end ? window.start : `${window.start} to ${window.end}` : turn.horizon || "all";
 const chart=savedChartReading(answer,turn.ticker);
 const primary=answer?.summary || turn.text || "No answer available";
 const generic=["Available readings are shown below.","Available readings are shown below. Exposure estimates do not establish trade direction."].includes(primary);
 return <article className="lodestar-answer" aria-label={`Research answer for ${turn.ticker}`}>
  <h3>{turn.ticker} · {scope}</h3>
  <small>{turn.saved === false ? "Not saved" : turn.status==="completed" ? "Saved answer" : turn.status}</small>
  {chart && !generic && <p>{primary}</p>}
  {chart ? <section aria-label="Saved chart reading">{chart.map((line,i)=><p key={i}>{line.text}</p>)}</section> : <p>{primary}</p>}
  {answer?.model_status && <small>{answer.model_status}</small>}
  {(answer?.usage || []).filter(u=>u.provider).map((u,i)=><p key={`usage-${i}`} className="lodestar-ai-usage">
   {u.provider} · {u.model}{u.effort && ` · ${THINKING_LABELS[u.effort] || u.effort} thinking`}{u.speed && ` · ${SPEED_LABELS[u.speed] || u.speed} speed`}
   {u.accounting==="subscription_usage" && <small>Uses your ChatGPT allowance; dollar cost is not reported.</small>}
  </p>)}
  {(answer?.model_explanations || []).filter(item=>!chart || !["source_time","limited_comparison","no_current_readings"].includes(item.kind)).map(item=><p key={item.id}>{readableScopeText(item.text)}</p>)}
  {chart ? <details><summary>Source checks and limits</summary>
   {(answer?.model_explanations || []).filter(item=>["source_time","limited_comparison","no_current_readings"].includes(item.kind)).map(item=><p key={item.id}>{readableScopeText(item.text)}</p>)}
   {(answer?.model_relationships || []).map((text,i)=><p key={`relation-${i}`}>{readableScopeText(text)}</p>)}
   {(answer?.gaps || []).length>0 && <p>Missing: {answer.gaps.join(", ")}</p>}
  </details> : <>{(answer?.model_relationships || []).map((text,i)=><p key={`relation-${i}`}>{readableScopeText(text)}</p>)}{(answer?.gaps || []).length>0 && <p>Missing: {answer.gaps.join(", ")}</p>}</>}
  {(answer?.sections || []).map(s=><details key={s.name}><summary>{s.name}</summary><p>{readableScopeText(s.text)}</p></details>)}
  {(answer?.model_sections || []).map((s,i)=><details key={`model-${i}`}><summary>Interpretation · {s.name}</summary><p>{s.text}</p><ul>{s.fact_ids.map(id=>{
   const fact=answer.facts.find(f=>f.id===id);return fact?<li key={id}>{fact.ticker} · {fact.metric}: {Array.isArray(fact.value)?"See evidence series":String(fact.value ?? "Unavailable")} {fact.unit}</li>:null;
  })}</ul></details>)}
  <Evidence turn={turn}/>
 </article>;
}
