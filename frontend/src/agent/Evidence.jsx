export default function Evidence({turn}){
 const facts=turn?.answer?.facts || Object.entries(turn?.ledger || {}).map(([id,f])=>({id,...f}));
 if(!facts.length)return null;
 return <details className="lodestar-evidence"><summary>Evidence ({facts.length})</summary>{facts.map(f=><div key={f.id}>
  <strong>{f.label || f.metric || f.tool || f.id}</strong><pre>{typeof f.value==="object" ? JSON.stringify(f.value,null,2) : String(f.value ?? "Unavailable")} {f.unit || ""}</pre>
  <small>{f.source || "Source unavailable"} · {f.status || "unknown"} · {f.event_time || f.as_of || "Observation time unavailable"}</small>
  {f.coverage && <p>{typeof f.coverage==="string"?f.coverage:JSON.stringify(f.coverage)}</p>}
 </div>)}</details>;
}
