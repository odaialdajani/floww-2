import Evidence from "./Evidence";
export default function AgentPanelAnswer({turn}){
 if(!turn)return null;
 const answer=turn.answer;
 const window=answer?.snapshots?.find(s=>s.ticker===turn.ticker)?.window;
 const scope=window?.start && window?.end ? window.start===window.end ? window.start : `${window.start} to ${window.end}` : turn.horizon || "all";
 return <article className="lodestar-answer" aria-label={`Research answer for ${turn.ticker}`}>
  <h3>{turn.ticker} · {scope}</h3>
  <small>{turn.saved === false ? "Not saved" : turn.status==="completed" ? "Saved answer" : turn.status}</small>
  <p>{answer?.summary || turn.text || "No answer available"}</p>
  {answer?.model_status && <small>{answer.model_status}</small>}
  {(answer?.model_relationships || []).map((text,i)=><p key={`relation-${i}`}>{text}</p>)}
  {(answer?.gaps || []).length>0 && <p>Missing: {answer.gaps.join(", ")}</p>}
  {(answer?.sections || []).map(s=><details key={s.name}><summary>{s.name}</summary><p>{s.text}</p></details>)}
  {(answer?.model_sections || []).map((s,i)=><details key={`model-${i}`}><summary>Interpretation · {s.name}</summary><p>{s.text}</p><ul>{s.fact_ids.map(id=>{
   const fact=answer.facts.find(f=>f.id===id);return fact?<li key={id}>{fact.ticker} · {fact.metric}: {Array.isArray(fact.value)?"See evidence series":String(fact.value ?? "Unavailable")} {fact.unit}</li>:null;
  })}</ul></details>)}
  <Evidence turn={turn}/>
 </article>;
}
