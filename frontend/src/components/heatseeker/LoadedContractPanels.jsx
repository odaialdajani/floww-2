import React,{useState} from 'react';
import './LoadedContractPanels.css';

const finite=v=>typeof v==='number'&&Number.isFinite(v);
const count=v=>finite(v)&&Number.isSafeInteger(v)&&v>=0?v.toLocaleString('en-US'):'—';
const money=v=>finite(v)?v.toLocaleString('en-US',{maximumFractionDigits:2}):'—';

function BoundedRows({rows,spot,children}) {
 const [offset,setOffset]=useState(null);
 const nearest=finite(spot)?rows.reduce((best,row,i)=>Math.abs(row.strike-spot)<Math.abs(rows[best].strike-spot)?i:best,0):0;
 const end=Math.max(0,rows.length-21),start=Math.min(end,offset??Math.max(0,nearest-10));
 return <div className="loaded-contract-panel">
  <div className="loaded-contract-window"><span>{rows.length?`${start+1}–${Math.min(start+21,rows.length)} of ${rows.length} strikes`:'No loaded strikes'}</span>
   <button type="button" disabled={start===0} onClick={()=>setOffset(Math.max(0,start-21))}>Lower strikes</button>
   <button type="button" disabled={start>=end} onClick={()=>setOffset(Math.min(end,start+21))}>Higher strikes</button>
   <button type="button" disabled={!finite(spot)} onClick={()=>setOffset(null)}>Center on spot</button>
  </div><div className="loaded-contract-scroll">{children(rows.slice(start,start+21))}</div>
 </div>;
}

export function OpenInterestPanel({data}) {
 const [chosen,setChosen]=useState(null);
 const surface=data?.grid?.oi_surface;
 if(surface?.version!=='oi-counts.v1'||surface.units!=='contracts')
  return <p role="status">Open interest was not recorded in this observation. No counts are reconstructed.</p>;
 const expiries=Array.isArray(surface.expiries)?surface.expiries:[];
 const expiry=expiries.includes(chosen)?chosen:expiries[0]||'';
 const column=surface.cells?.[expiry]||{};
 const rows=[...new Set(surface.strikes||[])].filter(s=>finite(s)&&s>0).sort((a,b)=>a-b).map(strike=>({...column[String(strike)],strike,loaded:Object.prototype.hasOwnProperty.call(column,String(strike))}));
 const dates=Array.isArray(surface.oi_effective_dates)?surface.oi_effective_dates:[];
 return <section aria-label="Open interest counts">
  <p>Open interest · contracts · loaded scope · {surface.status||'unknown coverage'}. Calls plus puts; no positioning sign or dollar multiplier.</p>
  <p>{dates.length?`OI effective dates: ${dates.join(', ')}`:'OI effective date unknown'}. Source: {(surface.sources||[]).join(', ')||'unknown'}.</p>
  <label>Expiry <select aria-label="Open interest expiry" value={expiry} onChange={e=>setChosen(e.target.value)}>{expiries.map(e=><option key={e}>{e}</option>)}</select></label>
  <BoundedRows rows={rows} spot={data?.spot}>{visible=><table aria-label="Loaded open interest"><thead><tr><th>Strike</th><th>Calls</th><th>Puts</th><th>Total</th><th>Coverage</th></tr></thead>
   <tbody>{visible.map(row=><tr key={row.strike}><th scope="row">{row.strike}</th><td>{count(row.call)}</td><td>{count(row.put)}</td><td>{count(row.total)}</td>
    <td>{!row.loaded?'No loaded contracts for this expiry':(row.missing||row.invalid||row.quarantined)?`${row.missing||0} missing · ${row.invalid||0} invalid · ${row.quarantined||0} excluded`:'loaded readings'}</td></tr>)}</tbody></table>}</BoundedRows>
  <small>Missing or invalid constituents withhold the total. This is the loaded contract universe, not full-market coverage.</small>
 </section>;
}

export function CallPutLadder({data}) {
 const rows=(Array.isArray(data?.strikes)?data.strikes:[]).filter(r=>finite(r?.strike)&&r.strike>0).slice().sort((a,b)=>a.strike-b.strike);
 const maximum=Math.max(0,...rows.flatMap(r=>[r.call_gex,r.put_gex].filter(finite).map(Math.abs)));
 if(!rows.length)return <p role="status">Call and put exposure was not recorded in this observation.</p>;
 const leg=(row,side)=>finite(row[side+'_gex'])?<><span className="loaded-exposure-bar" aria-label={`${side==='call'?'Call':'Put'} exposure ${row.strike}`}
  style={{width:`${maximum?Math.abs(row[side+'_gex'])/maximum*100:0}%`}}/>{money(row[side+'_gex'])}</>:<span>{side==='call'?'Call':'Put'} exposure unavailable</span>;
 return <section aria-label="Call and put exposure ladder"><p>Loaded call / put exposure · {data?.formula_version==='gex.v2'?'USD per 1% spot move':'source units not recorded'} · one magnitude scale for both legs.</p>
  <BoundedRows rows={rows} spot={data?.spot}>{visible=><table aria-label="Loaded call and put exposure"><thead><tr><th>Calls</th><th>Strike</th><th>Puts</th></tr></thead>
   <tbody>{visible.map(row=><tr key={row.strike}><td>{leg(row,'call')}</td><th scope="row">{row.strike}</th><td>{leg(row,'put')}</td></tr>)}</tbody></table>}</BoundedRows>
  <small>Recorded/supplied leg values only. A missing leg is unknown; it is never drawn as zero.</small>
 </section>;
}

export default function LoadedContractPanels({data}) {
 const [active,setActive]=useState(null);
 return <section className="loaded-contract-details" aria-label="Loaded contract details">
  <div className="loaded-contract-window">{[['interest','Open interest'],['ladder','Call / put ladder']].map(([id,label])=><button type="button" key={id}
   aria-expanded={active===id} onClick={()=>setActive(active===id?null:id)}>{label}</button>)}</div>
  {active==='interest'&&<OpenInterestPanel data={data}/>} {active==='ladder'&&<CallPutLadder data={data}/>}
 </section>;
}
