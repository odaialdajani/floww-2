import React, {useEffect,useRef,useState} from 'react';
import {API} from '../../config/api';
import {storedAppKeyHeaders} from '../../utils/appKey';
import {usePublishScreenContext} from '../../agent/useScreenContext';
import {admitRangeEnvelope,rangeSelectionContext,RANGE_METRICS} from '../../lib/rangeAnalytics';
import {cellPalette,fmtK} from './SkylitHeatmapGrid';
import RangeReplayControls from './RangeReplayControls';
import AskLodestar from './AskLodestar';
import './RangeAnalyticsWorkspace.css';

/** An explicit non-writing analytical read; no browser Greeks, contract or permission. */
export default function RangeAnalyticsWorkspace({ticker,onReplayModeChange}) {
 const [minDte,setMinDte]=useState('14'),[maxDte,setMaxDte]=useState('60');
 const [metric,setMetric]=useState('raw_oi'),[result,setResult]=useState(null),[loading,setLoading]=useState(false);
 const [selection,setSelection]=useState(null),[expanded,setExpanded]=useState(false),[follow,setFollow]=useState(false);
 const [replayOpen,setReplayOpen]=useState(false),[replayMode,setReplayMode]=useState(false);
 const [copyStatus,setCopyStatus]=useState(null),[approach,setApproach]=useState('awaiting'),[reviewOpen,setReviewOpen]=useState(false);
 const epoch=useRef(0),controller=useRef(null),cellRefs=useRef(new Map());
 const clear=()=>{epoch.current++;controller.current?.abort();setResult(null);setSelection(null);setLoading(false);setReplayMode(false);};
 const acceptStored=record=>{epoch.current++;controller.current?.abort();setResult(record?{envelope:record}:null);setSelection(null);setLoading(false);if(record)setReplayMode(true);};
 const validWindow=minDte.trim() && maxDte.trim() && Number.isInteger(Number(minDte)) && Number.isInteger(Number(maxDte)) && Number(minDte)>=0 && Number(maxDte)<=365 && Number(minDte)<=Number(maxDte);
 useEffect(()=>{
  clear();setExpanded(false);setFollow(false);setReplayOpen(false);
  return()=>{epoch.current++;controller.current?.abort();};
  // The owning symbol invalidates every field; no automatic data/model request.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[ticker]);
 useEffect(()=>{onReplayModeChange?.(replayMode);},[replayMode,onReplayModeChange]);
 useEffect(()=>()=>{onReplayModeChange?.(false);},[onReplayModeChange]);
 const candidate=result?.envelope;
 const envelope=candidate?.symbol===ticker && candidate.query.min_dte===Number(minDte) && candidate.query.max_dte===Number(maxDte)?candidate:null,section=envelope?.grids[metric];
 const context=rangeSelectionContext(envelope,metric,selection,replayMode?'replay':'live');
 usePublishScreenContext({...context,ticker});
 const read=async()=>{
  clear();const id=++epoch.current,ctrl=new AbortController();controller.current=ctrl;
  const min=Number(minDte),max=Number(maxDte);
  if(!minDte.trim() || !maxDte.trim() || !Number.isInteger(min) || !Number.isInteger(max) || min<0 || max>365 || min>max){setResult({reason:min>max?'REVERSED_WINDOW':'WINDOW_OUT_OF_RANGE'});return;}
  const timer=setTimeout(()=>ctrl.abort(),20000);setLoading(true);
  try{
   const response=await fetch(`${API}/heatmap/${encodeURIComponent(ticker)}/range-analytics?min_dte=${min}&max_dte=${max}&persist=false`,
    {headers:storedAppKeyHeaders() || {},credentials:'include',signal:ctrl.signal});
   const data=await response.json();
   if(id!==epoch.current || ctrl.signal.aborted)return;
   const admitted=admitRangeEnvelope(data,{symbol:ticker,minDte:min,maxDte:max});
   setResult(!response.ok && !admitted.reason?{reason:`RANGE_HTTP_${response.status}`} : admitted);
  }catch(error){if(id===epoch.current)setResult({reason:ctrl.signal.aborted?'RANGE_READ_TIMEOUT':'RANGE_READ_FAILED'});}
  finally{clearTimeout(timer);if(id===epoch.current)setLoading(false);}
 };
 const queryChange=(setter,value)=>{clear();setter(value);};
 const copyContext=async()=>{
  if(!envelope){setCopyStatus('Nothing to copy: load a range or stored record first.');return;}
  const payload={kind:'range-lodestar-context',version:1,ticker,symbol:envelope.symbol,record_id:envelope.record_id||null,content_digest:envelope.content_digest||null,query:envelope.query,metric,selection,replay:replayMode,received_at:envelope.clocks?.received_at,synthetic:!!envelope.synthetic,note:'research-only frozen context; not an execution permission'};
  try{await navigator.clipboard.writeText(JSON.stringify(payload));setCopyStatus('Context copied.');}
  catch(error){setCopyStatus('Copy failed: clipboard unavailable.');}
 };
 const scenarioText=()=>{
  if(!selection)return 'Select a cell first; reaction review needs a selected strike and expiry.';
  if(approach==='awaiting')return 'No reaction measured yet — choose an approach only after observing price action. Sign alone is not an entry or proven dealer position.';
  if(typeof selectedRaw!=='number'||selectedRaw===0)return 'Raw wall direction unknown for this cell; approach noted without a directional read.';
  if(approach==='above')return selectedRaw>0?'Positive raw: approach from above → review bounce. Owning price confirmation is required.':'Negative raw: approach from above → review flush. Owning price confirmation is required.';
  return selectedRaw>0?'Positive raw: approach from below → review rejection. Owning price confirmation is required.':'Negative raw: approach from below → review squeeze. Owning price confirmation is required.';
 };
 const rows=envelope?.axes.strike_keys || [],expiries=envelope?.axes.expiries || [];
 const values=section && section.status!=='unavailable'?Object.values(section.cells).flatMap(row=>Object.values(row)).filter(v=>typeof v==='number'):[];
 const extent=Math.max(1,...values.map(Math.abs));
 const focusCell=(event,row,column)=>{
  const movement={ArrowUp:[-1,0],ArrowDown:[1,0],ArrowLeft:[0,-1],ArrowRight:[0,1]}[event.key];
  if(!movement)return;
  const target=cellRefs.current.get(`${row+movement[0]}:${column+movement[1]}`);
  if(target){event.preventDefault();target.focus();}
 };
 const followSpot=()=>{
  setFollow(value=>!value);
  const spot=envelope?.clocks.spot.price;
  if(typeof spot!=='number' || !rows.length)return;
  const nearest=rows.reduce((a,b)=>Math.abs(Number(a)-spot)<=Math.abs(Number(b)-spot)?a:b);
  cellRefs.current.get(`${rows.indexOf(nearest)}:0`)?.scrollIntoView?.({block:'center',inline:'nearest'});
 };
 const selectedRaw=selection?envelope?.grids.raw_oi.cells[selection.expiry]?.[selection.strike]:null;
 return <section className={`range-workspace${expanded?' range-workspace-expanded':''}`} aria-label="Solstice analytical range">
  <header className="range-toolbar">
   <h2>{ticker} · Analytical range</h2>
   <label>Minimum DTE<input aria-label="Minimum DTE" type="number" min="0" max="365" value={minDte} onChange={e=>queryChange(setMinDte,e.target.value)}/></label>
   <label>Maximum DTE<input aria-label="Maximum DTE" type="number" min="0" max="365" value={maxDte} onChange={e=>queryChange(setMaxDte,e.target.value)}/></label>
   <button type="button" onClick={read} disabled={loading || replayOpen} title={replayOpen?'Exit stored replay with Live before requesting a current analytical range':undefined}>{loading?'Loading range…':'Load analytical range'}</button>
   <label>Metric<select aria-label="Range metric" value={metric} onChange={e=>{setSelection(null);setMetric(e.target.value);}}>{Object.entries(RANGE_METRICS).map(([key,value])=><option key={key} value={key}>{value.label}</option>)}</select></label>
   <button type="button" disabled={!envelope} aria-pressed={follow} onClick={followSpot}>Follow</button>
   <button type="button" disabled={!envelope} aria-pressed={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?'Return layout':'Expand range'}</button>
   <button type="button" disabled={!validWindow} aria-pressed={replayOpen} title={!validWindow?'WINDOW_OUT_OF_RANGE: choose an integer owning window first':'Stored rga1 research frames; full integrity/production qualification remain pending'} onClick={()=>{clear();setReplayOpen(value=>!value);}}>{replayOpen?'Close range replay':'Range replay'}</button>
  </header>
  {replayOpen && <RangeReplayControls ticker={ticker} minDte={minDte.trim()?Number(minDte):NaN} maxDte={maxDte.trim()?Number(maxDte):NaN} onRecord={acceptStored} onLive={()=>{setReplayOpen(false);clear();}}/>}
  {replayMode && <p className="range-note" role="status">Stored rga1 replay · no current-chain reconstruction; producer-reported integrity, full qualification pending.</p>}
  <p className="range-note">Research only · no execution eligibility. Listed dates are not trading permission; volume is not trade direction.</p>
  {loading && <p role="status">Reading the requested range; prior selection cleared.</p>}
  {result?.reason && <p role="status">Analytical range unavailable · {result.reason}</p>}
  {envelope && <>
   <p>{envelope.query.as_of_ny} America/New_York · {envelope.query.min_dte}–{envelope.query.max_dte} DTE · {envelope.synthetic?'Synthetic fixture · ':''}{envelope.provenance.data_source}{envelope.provenance.stale?' · STALE source':''}</p>
   <p>{envelope.coverage.complete?'Producer reports complete expiry coverage':'Partial expiry coverage'} · {envelope.coverage.n_returned_expiries}/{envelope.coverage.n_admitted} admitted expiries returned · {envelope.coverage.complete_reason || 'listing edges observed'}.</p>
   {envelope.coverage.skipped.length>0 && <ul>{envelope.coverage.skipped.map((row,i)=><li key={i}>{row.expiry} · reason {row.reason}</li>)}</ul>}
   <p>{section.basis} · {section.unit} · {section.formula_version} · {section.model} · metric {section.status}</p>
   <details><summary>Clocks and coverage</summary>
    <p>Received {envelope.clocks.received_at} · fetched {envelope.clocks.fetched_at || 'unknown'} · {envelope.clocks.chain_event_time?`chain event ${envelope.clocks.chain_event_time}`:'Chain event time unknown'}.</p>
    <p>OI effective dates: {envelope.clocks.oi_effective_dates.join(', ') || 'unknown'}. Missing per-contract dates remain unknown.</p>
    <p>Spot {envelope.clocks.spot.price ?? 'unknown'} · {envelope.clocks.spot.source || 'source unknown'} · event {envelope.clocks.spot.event_time || 'unknown'}.</p>
    <p>Producer-reported usable {section.usable ?? 'unknown'}; missing delta {section.missing_delta ?? 'unknown'}, invalid delta {section.invalid_delta ?? 'unknown'}, quarantined {section.quarantined ?? 'unknown'}. Population acceptance is separate from cell counts.</p>
    <p>Record {envelope.record_id} · digest {envelope.content_digest}. Shape admission is not cryptographic replay integrity; stored evidence validation awaits the producer repair.</p>
   </details>
   <div className="range-desk">
    <div className="range-matrix-scroll">
     {section.status==='unavailable'?<p role="status">{RANGE_METRICS[metric].label} unavailable · {section.reason || 'NO_COVERAGE'}</p>:
      <table role="grid" aria-label={`${RANGE_METRICS[metric].label} · strike by expiry`} className="range-matrix">
       <thead><tr><th scope="col">Strike USD</th>{expiries.map(row=><th scope="col" key={row.expiry}>{row.expiry}<small>{row.dte} DTE</small></th>)}</tr></thead>
       <tbody>{rows.map((strike,r)=><tr key={strike}><th scope="row">{strike}</th>{expiries.map(({expiry},c)=>{
        const value=section.cells[expiry][strike],color=value===null?null:cellPalette((value/extent+1)/2);
        const selected=selection?.strike===strike && selection.expiry===expiry;
        return <td key={expiry} role="gridcell" aria-selected={selected} className={selected?'range-selected':''}>
         <button type="button" ref={node=>{if(node)cellRefs.current.set(`${r}:${c}`,node);else cellRefs.current.delete(`${r}:${c}`);}}
          aria-label={`${strike} · ${expiry} · ${value===null?'Unavailable':value+' USD per 1% spot move'}`}
          style={color?{background:color.background,color:color.foreground}:undefined}
          onKeyDown={event=>focusCell(event,r,c)} onClick={()=>setSelection(value===null?null:{strike,expiry})}>
          {value===null?'Unavailable':fmtK(value)}
         </button></td>;
       })}</tr>)}</tbody>
      </table>}
    </div>
    <aside className="range-inspector" aria-label="Range selection review">
     <h3>Selected strike</h3>
     <p>{selection?`${selection.strike} USD · ${selection.expiry}`:'Select an available cell'}</p>
     <p>Wall bounds/ID unavailable in this range envelope; a cell is not a classified structural wall.</p>
      <h3>Evidence / scenario</h3>
      <label>Price approach<select aria-label="Price approach" value={approach} onChange={e=>setApproach(e.target.value)}>
       <option value="awaiting">Awaiting measured reaction</option>
       <option value="above">From above · falling into wall</option>
       <option value="below">From below · rising into wall</option>
      </select></label>
      <p>{scenarioText()}</p>
      <h3>Handoff trace</h3>
      <p>{selection?`Wall context attached · ${ticker} · ${selection.strike} USD · ${selection.expiry}`:'No cell selected — nothing attached.'}</p>
      <p>{envelope?`Record ${envelope.record_id||'unidentified'} · digest ${envelope.content_digest||'unknown'} · received ${envelope.clocks?.received_at||'unknown'} · ${replayMode?'stored replay':'live read'} · ${envelope.synthetic?'synthetic fixture':'observed source'}`:'No envelope loaded.'}</p>
      <p>Execution owner: unselected — choosing an owner labels a future draft only and never authorizes entry.</p>
      <h3>Review trade</h3>
      <button type="button" disabled={!envelope} onClick={()=>setReviewOpen(value=>!value)}>{reviewOpen?'Close trade review':'Review trade'}</button>
      {reviewOpen && envelope && <div role="region" aria-label="Trade review">
       <p>{selection?`Reviewing ${selection.strike} USD · ${selection.expiry} · ${ticker}`:'No cell selected.'} Record {envelope.record_id||'unidentified'} · {replayMode?'stored replay':'live read'}.</p>
       <p>Contract: RANGE_CONTRACT_UNAVAILABLE · no exact OSI, population or quote clocks. Risks explicit and unset: limit, budget, conditions, window, expiry, notifications.</p>
       <p>No execution path: this review cannot place, approve, or route any order. Backend entry unavailable; copied references do not activate Public.</p>
      </div>}
      <h3>Lodestar context</h3>
      <button type="button" disabled={!envelope} onClick={copyContext}>Copy Lodestar context</button>
      {copyStatus && <p role="status">{copyStatus}</p>}
     <h3>Supported contract</h3><p>RANGE_CONTRACT_UNAVAILABLE · owning OSI, contract population and quote clocks are not supplied. No current-chain substitution.</p>
     <h3>Lodestar</h3><p>{replayMode?'Select a stored cell for research-only interpretation. Full production integrity and raw population qualification remain pending; no contract or execution permission.':'Live range reads are not persisted research evidence. Select a stored replay record first; no current-chain or old answer substitute.'}</p>
     <AskLodestar subject={`${ticker} recorded range`} overlayMetric={metric} displayMode={replayMode?'range-replay':'range-live'} compact testId="range-ask-lodestar" starters={['Explain the recorded cells','What limits this observation?','What confirms or invalidates?']}/>
     <h3>Public route</h3><p>Backend entry unavailable. Native drafts need an exact supported contract; copied references do not activate Public.</p>
    </aside>
   </div>
  </>}
 </section>;
}
