import React,{useEffect,useRef,useState} from "react";
import {BACKEND_URL} from "../config/api";
import './RelatedTickerPanel.css';
const validSymbol=value=>{if(typeof value!=='string')return false;const plain=value.startsWith('^')?value.slice(1):value;return /^[A-Z][A-Z0-9.-]{0,11}$/.test(plain);};
const count=value=>Number.isSafeInteger(value)&&value>=0?value.toLocaleString():'Unknown';
const readPref=(key,allowed,fallback)=>{try{const value=sessionStorage.getItem(key);return allowed.includes(value)?value:fallback;}catch{return fallback;}};
const savePref=(key,value)=>{try{sessionStorage.setItem(key,value);}catch{/* A closed comparison does not change its underlying saved prices. */}};
const reasonText=reason=>({cache_storage_unavailable:'Saved price storage is unavailable. Checking stopped.',selected_series_unavailable:'Selected stock prices are unavailable. Comparisons cannot be checked yet.',insufficient_overlap:'Not enough matching days',zero_variance:'No price changes to compare',missing_history:'Price history not loaded',selected_history_unavailable:'Selected stock history unavailable',unavailable:'Price history unavailable',unsupported_symbol:'Price history is not supported for this symbol',provider_directory_unavailable:'The provider stock list is unavailable',no_usable_comparisons:'No comparison has enough matching prices yet'}[reason]||'Reading unavailable');
export function checkedCoefficient(row){return typeof row?.coefficient==='number'&&Number.isFinite(row.coefficient)&&Math.abs(row.coefficient)<=1&&Number.isSafeInteger(row.paired_returns)&&row.paired_returns>=20?row.coefficient:null;}
function CompareRows({rows=[],onPick}){return <ul className="related-comparison-list">{rows.map(row=>{const value=checkedCoefficient(row);return <li key={row.symbol}><button type="button" onClick={()=>onPick?.(row.symbol)}>{row.symbol}</button><strong className={value===null?'unknown':value<0?'negative':'positive'}>{value===null?'Unavailable':(value>0?'+':'')+value.toFixed(2)}</strong><small>{value===null?reasonText(row.reason):row.paired_returns+' matching days · '+row.start_date+' to '+row.end_date}{row.partial?' · partial history':''}{row.stale?' · saved prices':''}</small></li>;})}</ul>;}
export default function RelatedTickerPanel({ticker='SPY',onTickerChange,onClose,layout='dock',width=380,right=12}){
 const symbol=typeof ticker==='string'?ticker.toUpperCase():'';
 const [windowDays,setWindowDays]=useState(()=>Number(readPref('floww-related-window',['30','90','252'],'90')));
 const [scope,setScope]=useState(()=>readPref('floww-related-scope',['related','all'],'related'));
 const [packet,setPacket]=useState(null),[state,setState]=useState('loading'),[notice,setNotice]=useState(''),[checking,setChecking]=useState(false),[revision,setRevision]=useState(0);
 const epoch=useRef(0),mounted=useRef(true),warmKey=useRef(null);
 const key=symbol+':'+windowDays+':'+scope;
 const packetRef=useRef(null);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;epoch.current++;};},[]);
 useEffect(()=>{savePref('floww-related-window',String(windowDays));savePref('floww-related-scope',scope);},[windowDays,scope]);
 const admit=(body,current)=>{
  if(!mounted.current||epoch.current!==current)return false;
  if(body?.ticker!==symbol||body.window!==windowDays||body.scope!==scope||!Array.isArray(body.products)||!Array.isArray(body.positive)||!Array.isArray(body.negative)||!Array.isArray(body.comparisons)||!body.coverage)throw Error('Wrong comparison context');
  if([...body.positive,...body.negative,...body.comparisons].some(row=>!validSymbol(row?.symbol)||row.coefficient!==null&&checkedCoefficient(row)===null))throw Error('Unqualified comparison');
  packetRef.current={key,data:body};setPacket(packetRef.current);setState('ready');return true;
 };
 useEffect(()=>{
  const current=++epoch.current,controller=new AbortController();packetRef.current=null;setPacket(null);setState('loading');setNotice('');setChecking(false);
  fetch(BACKEND_URL+'/api/related/'+encodeURIComponent(symbol)+'?window='+windowDays+'&scope='+scope,{signal:controller.signal}).then(async response=>{if(!response.ok)throw Error('Read unavailable');return response.json();}).then(body=>admit(body,current)).catch(error=>{if(epoch.current===current&&!controller.signal.aborted){setState('error');setNotice('Related readings could not be loaded. Try again.');}});
  return()=>{epoch.current++;controller.abort();};
 },[key,revision]);
 useEffect(()=>{
  if(!checking||warmKey.current!==key)return undefined;
  const current=epoch.current,controller=new AbortController();let timer=null,stopped=false;
  const run=async()=>{
   try{
    const response=await fetch(BACKEND_URL+'/api/related/'+encodeURIComponent(symbol)+'/warm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({window:windowDays,scope,batch_size:8}),signal:controller.signal});
    if(!response.ok)throw Error('Comparison check failed');const body=await response.json();if(stopped||epoch.current!==current)return;
    if(body?.ticker===symbol&&body.window===windowDays&&body.scope===scope&&body.batch?.reason==="cache_storage_unavailable"){setChecking(false);setState("ready");setNotice(reasonText(body.batch.reason)+" Earlier checked comparisons remain shown.");return;}
    if(!admit(body,current))return;
    if(body.batch?.reason && ["cache_storage_unavailable","selected_series_unavailable","unsupported_symbol"].includes(body.batch.reason)){setChecking(false);setNotice(reasonText(body.batch.reason));return;}
    if(body.batch?.done||body.coverage?.checked_complete){setChecking(false);return;}
    const pause=Number.isFinite(body.batch?.retry_after)?Math.max(1,Math.min(300,body.batch.retry_after)):1;
    setNotice(body.batch?.deferred?'Waiting for the data connection before checking more names.':'');timer=setTimeout(run,pause*1000);
   }catch(error){if(!stopped&&!controller.signal.aborted&&epoch.current===current){setChecking(false);setNotice('Comparison check stopped. Any saved readings keep their original dates.');}}
  };run();return()=>{stopped=true;if(timer)clearTimeout(timer);controller.abort();};
 },[checking,key]);
 const data=packet?.key===key?packet.data:null,coverage=data?.coverage;
 const pick=next=>{if(validSymbol(next))onTickerChange?.(next);};
 const samples=data?.comparisons||[];
 return <aside className={'related-ticker-panel related-'+layout} style={{'--related-width':width+'px','--related-right':right+'px'}} role="region" aria-label="Related stocks and funds">
  <div className="related-header"><div><small>RELATED TO</small><h2>{symbol||'Choose a stock'}</h2></div><button type="button" aria-label="Close related stocks" onClick={onClose}>Close</button></div>
  <div className="related-controls"><label>Compare<select aria-label="Comparison group" value={scope} onChange={e=>setScope(e.target.value)}><option value="related">Related products</option><option value="all">All available stocks</option></select></label><label>History<select aria-label="Comparison history" value={windowDays} onChange={e=>setWindowDays(Number(e.target.value))}><option value={30}>30 sessions</option><option value={90}>90 sessions</option><option value={252}>1 year</option></select></label></div>
  <div className="related-body">
   {state==='loading'&&<p role="status">Loading saved comparisons…</p>}
   {notice&&<p role={state==='error'?'alert':'status'}>{notice}</p>}
   {state==='ready'&&data?.reason&&!notice&&<p role="status">{reasonText(data.reason)}</p>}
   <section><h3>Linked funds and products</h3>{data?.products.length?<ul className="related-product-list">{data.products.map(product=><li key={product.symbol}><button type="button" disabled={product.provider_listed!==true} onClick={()=>pick(product.symbol)}>{product.symbol}</button><span>{product.issuer}{typeof product.daily_target==='number'?' · '+(product.daily_target<0?'Inverse ':'')+Math.abs(product.daily_target)+'× '+(product.reset==='daily'?'daily target':'index exposure'):''}</span><small>{product.underlying?'Linked to '+product.underlying:product.benchmark?'Benchmark: '+product.benchmark:'Relationship details unavailable'}{product.provider_listed===false?' · not in the provider list':product.provider_listed==null?' · provider access unknown':''}</small>{(product.source_urls||[]).filter(url=>typeof url==='string'&&url.startsWith('https://')).slice(0,2).map(url=><a key={url} href={url} target="_blank" rel="noreferrer">Issuer source</a>)}</li>)}</ul>:state==='ready'?<p>No verified product links are loaded for this stock yet.</p>:null}<small className="related-note">Issuer links are a checked list, not a complete list of every fund holding this stock. Daily fund targets reset daily.</small></section>
   <section><h3>Price co-movement</h3><p className="related-progress">{count(coverage?.checked)} of {count(coverage?.eligible)} names checked · {count(coverage?.usable)} usable comparisons{coverage?.pending!=null?' · '+count(coverage.pending)+' waiting':''}</p><small className="related-note">Ranked among checked names using daily price changes. Each pair shows its matching days; missing prices stay unavailable.</small><div className="related-check-actions"><button type="button" disabled={state==='loading'||!validSymbol(symbol)} onClick={()=>{setNotice('');warmKey.current=key;setChecking(value=>!value);}}>{checking?'Pause checking':scope==='all'?'Check all available stocks':'Check related products'}</button><button type="button" disabled={checking} onClick={()=>setRevision(value=>value+1)}>Reload saved</button></div>
    {samples.length>0&&<div className="related-heat-strip" aria-label="Daily price co-movement heatmap">{samples.map(row=>{const value=checkedCoefficient(row);return <button key={row.symbol} type="button" className={value===null?'unknown':value<0?'negative':value>0?'positive':'neutral'} style={{'--strength':value===null?0:Math.abs(value)}} onClick={()=>pick(row.symbol)} title={row.symbol+': '+(value===null?reasonText(row.reason):value.toFixed(2)+', '+row.paired_returns+' matched days, '+row.start_date+' to '+row.end_date)}><span>{row.symbol}</span><b>{value===null?'—':(value>0?'+':'')+value.toFixed(2)}</b></button>;})}</div>}
    <div className="related-legend"><span>−1 opposite</span><span>0 unrelated</span><span>+1 together</span></div>
    <h4>Moves together</h4>{data?.positive.length?<CompareRows rows={data.positive} onPick={pick}/>:state==='ready'?<p>No positive comparison is available in the checked names.</p>:null}
    <h4>Moves opposite</h4>{data?.negative.length?<CompareRows rows={data.negative} onPick={pick}/>:state==='ready'?<p>No negative comparison is available in the checked names.</p>:null}
    <details><summary>Dates and reading limits</summary><p>Last completed session: {data?.expected_last_close||'Unknown'}.</p><p>{count(coverage?.failed)} price reads failed · {count(coverage?.stale)} saved series · {count(coverage?.partial)} partial comparisons.</p><p>Prices use the provider's reported basis. Split and dividend adjustments are not confirmed and can affect these readings.</p><p>Past co-movement does not establish future movement.</p>{data?.comparisons_total>samples.length&&<p>The heatmap shows {samples.length} of {count(data.comparisons_total)} names in the chosen group. Rankings use only usable saved comparisons.</p>}</details>
   </section>
  </div>
 </aside>;
}
