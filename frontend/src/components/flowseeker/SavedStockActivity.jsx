import React,{useEffect,useMemo,useRef,useState} from 'react';
import {API} from '../../config/api';
import {BUILTIN_SCREENS} from './tideFeed';
import {filterSavedActivity,formatSavedClock,readSavedActivity,savedActivityQuery} from './savedStockActivityData';
import './SavedStockActivity.css';

const PAGE_SIZE=12,READ_TIMEOUT_MS=15000,CACHED_GROUP_LIMIT=5;
const number=value=>value===null || value===undefined?'Unknown':new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(value);
const estimate=value=>value===null?'Unknown':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(value)+' estimate';
const screenIdentity=screen=>({id:screen?.id,custom:screen?.custom,copyOf:screen?.copyOf,rule:screen?.rule,conditions:screen?.conditions,ruleUnitsVersion:screen?.ruleUnitsVersion});

function SavedDetails({row}){
 return <details className="saved-stock-details"><summary>Saved row details</summary>
  <dl><dt>Saved receipt</dt><dd>{formatSavedClock(row.receiptClock)}</dd><dt>Volume source time</dt><dd>{formatSavedClock(row.volumeClock)}</dd>
   <dt>Quote source time</dt><dd>{formatSavedClock(row.quoteClock)}</dd><dt>Chain source time</dt><dd>{formatSavedClock(row.eventClock)}</dd>
   <dt>Stored scope</dt><dd>{row.meta.scope || row.stockMeta.scope || 'Unknown'}</dd>
   <dt>Original examples</dt><dd>{row.stockMeta.original_retained_rows ?? row.stockMeta.retained_rows ?? 'Unknown'}</dd></dl>
  <p>Original saved values. Missing units and readings remain unknown.</p>
  <pre aria-label="Original saved row">{JSON.stringify({row:row.raw,quote:row.extra,observation:row.meta,stock:row.stockMeta},null,2)}</pre>
 </details>;
}

export default function SavedStockActivity({active=true,screen=BUILTIN_SCREENS[0],universe=[],tickerFacts={},filters={},onPickTicker}){
 const [offset,setOffset]=useState(0),[localPage,setLocalPage]=useState(0),[refresh,setRefresh]=useState(0),[clock,setClock]=useState(()=>Date.now());
 const [read,setRead]=useState({key:null,data:null,status:'idle',error:null});
 const cache=useRef(new Map()),epoch=useRef(0);
 const filterKey=JSON.stringify({screen:screenIdentity(screen),filters,universe});
 const oldFilter=useRef(filterKey);
 const requestedOffset=oldFilter.current===filterKey?offset:0;
 const query=savedActivityQuery(filters,requestedOffset),url=API+'/flowseeker/scan-public/observations?'+query;
 useEffect(()=>{
  if(oldFilter.current!==filterKey){oldFilter.current=filterKey;setOffset(0);setLocalPage(0);}
 },[filterKey]);
 useEffect(()=>{
  if(!active)return;
  setClock(Date.now());const timer=setInterval(()=>setClock(Date.now()),60000);
  return ()=>clearInterval(timer);
 },[active]);
 useEffect(()=>{
  const generation=++epoch.current;
  if(!active)return;
  const cached=cache.current.get(url);
  if(cached){setRead({key:url,data:cached,status:'ready',error:null});return;}
  const controller=new AbortController();let timeout,expired=false;
  setRead(previous=>({key:url,data:previous.key===url?previous.data:null,status:'loading',error:null}));
  const current=()=>generation===epoch.current;
  const deadline=new Promise((_,reject)=>{timeout=setTimeout(()=>{expired=true;controller.abort();reject(new Error('Saved read timed out.'));},READ_TIMEOUT_MS);});
  const request=(async()=>{
   const response=await fetch(url,{method:'GET',signal:controller.signal});
   if(!response.ok)throw new Error('Saved read unavailable.');
   const payload=await response.json();readSavedActivity(payload,{now:Date.now()});
   if(payload.offset!==requestedOffset)throw new Error('Saved group identity could not be checked.');return payload;
  })();
  Promise.race([request,deadline]).then(payload=>{
   if(!current() || controller.signal.aborted)return;
   cache.current.delete(url);cache.current.set(url,payload);
   while(cache.current.size>CACHED_GROUP_LIMIT)cache.current.delete(cache.current.keys().next().value);
   setRead({key:url,data:payload,status:'ready',error:null});
  }).catch(()=>{
   if(current() && (expired || !controller.signal.aborted))setRead(previous=>({...previous,status:'error',error:'Saved activity is unavailable. Try reading saved pages again.'}));
  }).finally(()=>clearTimeout(timeout));
  return ()=>{epoch.current++;clearTimeout(timeout);controller.abort();};
 },[active,url,filterKey,refresh,requestedOffset]);
 const decoded=useMemo(()=>read.data?readSavedActivity(read.data,{now:clock}):null,[read.data,clock]);
 const visible=useMemo(()=>decoded?filterSavedActivity(decoded.rows,{screen,filters,universe,tickerFacts,now:clock}):{rows:[],warnings:[]},[decoded,screen,filterKey,tickerFacts,clock]);
 const pages=Math.max(1,Math.ceil(visible.rows.length/PAGE_SIZE)),page=Math.min(localPage,pages-1);
 const pageRows=visible.rows.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);
 const stockCount=new Set(visible.rows.map(row=>row.under)).size;
 const meta=read.data?.coverage || {},warnings=[...new Set([...(decoded?.warnings || []),...visible.warnings])];
 const reload=()=>{cache.current.delete(url);setRefresh(value=>value+1);};
 const nextGroup=()=>{if(read.data?.next_offset!==null && Number.isInteger(read.data?.next_offset)){setOffset(read.data.next_offset);setLocalPage(0);}};
 if(!active)return null;
 return <section className="saved-stock-activity" aria-label="Saved stock activity">
  <header className="saved-stock-heading"><div><h3>Saved stock activity</h3><span className="saved-stock-state">Dated records{decoded?.partial?' · Partial':''}</span></div>
   <button type="button" onClick={reload} disabled={read.status==='loading'}>Read saved pages again</button></header>
  <p className="saved-stock-clock-note">Saved receipts are not market times. Unknown source clocks stay unknown.</p>
  {read.status==='loading' && <p role="status">Reading saved rows...</p>}
  {read.error && <p className="saved-stock-error" role="alert">{read.error}{read.data?' The earlier checked saved group remains shown.':''}</p>}
  {read.data && <>
   <div className="saved-stock-counts"><b>{stockCount} stocks</b><span>{visible.rows.length} rows match this loaded group</span><span>{read.data.total} saved rows match the stock, type and volume search</span></div>
   {decoded?.discarded>0 && <p className="saved-stock-quality-note">{decoded.warnings[0]}</p>}
   {visible.rows.length===0 && Number(filters.minScore)>0 && <p className="saved-stock-quality-note">Saved scores were not recorded. Remove the score filter to see saved rows.</p>}
   {warnings.length>0 && <details className="saved-stock-filter-notes"><summary>Some filters need unavailable readings</summary>{warnings.map(text=><p key={text}>{text}</p>)}</details>}
   {pageRows.length>0?<div className="saved-stock-table-wrap"><table><thead><tr>
    <th>Stock</th><th>Type</th><th>Strike</th><th>Expiry</th><th>Volume</th><th>Open interest</th><th>Volume / open interest</th><th>Quote estimate</th><th>Saved receipt</th><th>Volume time</th><th>Details</th>
   </tr></thead><tbody>{pageRows.map((row,index)=><tr key={row.key+':'+index}>
    <td><button type="button" className="saved-stock-symbol" aria-label={'Open current stock '+row.under} disabled={typeof onPickTicker!=='function'} onClick={()=>onPickTicker?.(row.under)} title="Opens the current stock view. This saved contract remains separate.">{row.under}</button></td>
    <td>{row.type==='call'?'Call':'Put'}</td><td>{number(row.strike)}</td><td>{row.exp}</td><td>{number(row.vol)}</td><td>{number(row.oi)}</td><td>{row.volOI===null?'Unknown':number(row.volOI)}</td>
    <td className="saved-stock-money">{estimate(row.premium)}</td><td>{formatSavedClock(row.receiptClock)}</td><td>{formatSavedClock(row.volumeClock)}</td><td><SavedDetails row={row}/></td>
   </tr>)}</tbody></table></div>:read.status!=='error' && <p className="saved-stock-empty">{read.data.status==='missing'?'No saved rows have been recorded for this selection.':'No saved rows match this loaded group. Other saved groups may still contain matches.'}</p>}
   <nav className="saved-stock-paging" aria-label="Saved row pages">
    <div><button type="button" disabled={page===0} onClick={()=>setLocalPage(value=>Math.max(0,value-1))}>Previous rows</button><span>Page {page+1} of {pages}</span>
     <button type="button" disabled={page>=pages-1} onClick={()=>setLocalPage(value=>Math.min(pages-1,value+1))}>Next rows</button>
     <button type="button" disabled={page>=pages-1} onClick={()=>setLocalPage(pages-1)}>Last rows page</button></div>
    <div><button type="button" disabled={offset===0 || read.status==='loading'} onClick={()=>{setOffset(Math.max(0,offset-100));setLocalPage(0);}}>Previous saved group</button>
     <span>Group {Math.floor(offset/100)+1}</span><button type="button" disabled={page<pages-1 || read.data.next_offset===null || read.status==='loading' || read.status==='error'} onClick={nextGroup}>Load next saved group</button></div>
   </nav>
   <p className="saved-stock-legacy-note">Legacy records keep at most three original examples. Pruned history is unavailable.</p>
   <details className="saved-stock-coverage"><summary>Saved coverage and limits</summary><p>{number(meta.observed_tickers)} stocks have retained observations; {number(meta.missing_tickers)} have no retained observation. Latest failed checks: {number(meta.latest_failed_tickers)}.</p>
    <p>The saved selection keeps at most {number(meta.rows_per_ticker_cap)} rows per stock and {number(meta.symbol_limit)} stocks. Legacy records have their separate {number(meta.legacy_retention_ticker_limit)}-stock limit. Whole chains and pruned records are unavailable.</p>
    <p>Times are shown in New York time. Expiry filters compare calendar dates today. Saved lists may change between groups; this is not a frozen market snapshot.</p></details>
  </>}
 </section>;
}
