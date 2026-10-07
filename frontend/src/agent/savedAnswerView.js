// Prepare a safe view of saved research without changing the stored evidence.
const object=value=>Boolean(value && typeof value==='object' && !Array.isArray(value));
const textFields=(row,fields)=>object(row) && fields.every(key=>row[key]==null || typeof row[key]==='string');
export function savedAnswerView(raw){
 let incomplete=false;
 if(raw==null)return {answer:null,incomplete};
 if(!object(raw))return {answer:null,incomplete:true};
 const answer={...raw};
 if(raw.history_baseline!=null){
  const day=object(raw.history_baseline)?raw.history_baseline.date:null;
  const valid=typeof day==='string' && /^\d{4}-\d{2}-\d{2}$/.test(day) && Number(day.slice(0,4))>0 && Number.isFinite(Date.parse(day+'T00:00:00Z')) && new Date(day+'T00:00:00Z').toISOString().slice(0,10)===day;
  if(!valid){answer.history_baseline=null;incomplete=true;}
 }
 const rows=(key,valid)=>{
  const value=raw[key];if(value==null)return;
  if(!Array.isArray(value)){answer[key]=[];incomplete=true;return;}
  answer[key]=value.filter(valid);if(answer[key].length!==value.length)incomplete=true;
 };
 for(const key of ['summary','model_status','mode','scope'])if(raw[key]!=null && typeof raw[key]!=='string'){answer[key]=undefined;incomplete=true;}
 rows('facts',row=>textFields(row,['id','ticker','metric','label','tool','unit','source','status','event_time','as_of']) && typeof row.id==='string');
 rows('snapshots',row=>textFields(row,['ticker']) && (row.window==null || textFields(row.window,['start','end'])));
 rows('model_sections',row=>textFields(row,['name','text']) && typeof row.text==='string');
 rows('sections',row=>textFields(row,['name','text']) && typeof row.text==='string');
 rows('model_explanations',row=>textFields(row,['id','ticker','kind','text']) && typeof row.text==='string');
 rows('model_relationships',row=>typeof row==='string');
 rows('gaps',row=>typeof row==='string');
 rows('actions',row=>textFields(row,['kind','view','ticker']) && Array.isArray(row.fact_ids) && row.fact_ids.length<=30 && row.fact_ids.every(id=>typeof id==='string'));
 rows('usage',row=>textFields(row,['provider','model','effort','speed','accounting']));
 if(answer.usage)answer.usage=answer.usage.map(row=>{
  if(row.trace==null)return row;
  if(!object(row.trace)){incomplete=true;return {...row,trace:null};}
  const trace={...row.trace};
  for(const key of ['requested','effective'])if(trace[key]!=null && !textFields(trace[key],['model','effort','speed'])){trace[key]=null;incomplete=true;}
  for(const key of ['observation_ids','evidence_ids'])if(trace[key]!=null){const values=Array.isArray(trace[key])?trace[key]:[];const safe=values.filter(value=>typeof value==='string');if(!Array.isArray(trace[key]) || safe.length!==values.length)incomplete=true;trace[key]=safe;}
  for(const key of ['correlation_id','context_hash','status'])if(trace[key]!=null && typeof trace[key]!=='string'){trace[key]=undefined;incomplete=true;}
  for(const key of ['latency_ms','actual_cost'])if(trace[key]!=null && typeof trace[key]!=='number' && typeof trace[key]!=='string'){trace[key]=undefined;incomplete=true;}
  return {...row,trace};
 });
 return {answer,incomplete};
}
