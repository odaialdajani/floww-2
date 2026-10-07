import {BUILTIN_SCREENS,applyScreenToScans,TICKER_FACTS,SCAN_FACT_LABELS,TICKER_FACT_LABELS} from './tideFeed';
import {spreadStockAlerts} from './stockAlertOverview';

const finite=value=>value!==null && value!==undefined && typeof value!=='boolean' && (typeof value==='number' || typeof value==='string' && value.trim()) && Number.isFinite(Number(value))?Number(value):null;
const nonnegative=value=>{const number=finite(value);return number!==null && number>=0?number:null;};
const object=value=>value && typeof value==='object' && !Array.isArray(value)?value:{};
const has=(value,key)=>Object.prototype.hasOwnProperty.call(value,key);
const COLUMNS=['underlying_ticker','ticker','contract_type','strike_price','expiration_date','day_volume','open_interest','implied_volatility','delta','underlying_price'];

export function savedClock(value,now=Date.now()){
 if(value===null || value===undefined || value==='')return {state:'unknown',reason:'missing',ms:null};
 let ms=null;
 if(typeof value==='number' && Number.isFinite(value) && value>0)ms=value*1000;
 else if(typeof value==='string' && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) && dayNumber(value.slice(0,10))!==null)ms=Date.parse(value);
 if(!Number.isFinite(ms) || ms<=0)return {state:'unknown',reason:'invalid',ms:null};
 if(ms>now)return {state:'unknown',reason:'future',ms:null};
 return {state:'known',reason:null,ms,iso:new Date(ms).toISOString()};
}

export function savedToday(now=Date.now()){
 try{const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);const value=kind=>parts.find(part=>part.type===kind)?.value;return value('year')+'-'+value('month')+'-'+value('day');}catch{return null;}
}
function dayNumber(value){
 if(typeof value!=='string' || !/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
 const date=new Date(value+'T00:00:00Z');
 return Number.isFinite(date.getTime()) && date.toISOString().slice(0,10)===value?date.getTime()/86400000:null;
}
export function savedExpiryDays(expiry,today){const exp=dayNumber(expiry),day=dayNumber(today);return exp!==null && day!==null?exp-day:null;}
export const savedContractKey=row=>row.under+'|'+row.type+'|'+row.strike+'|'+row.exp;

export function savedActivityQuery(filters={},offset=0){
 const query=new URLSearchParams({offset:String(offset),limit:'100',order:'stocks'});
 const ticker=typeof filters.q==='string'?filters.q.trim().toUpperCase():'';
 if(ticker)query.set('ticker',ticker);
 if(['call','put'].includes(filters.type))query.set('contract_type',filters.type);
 const volume=nonnegative(filters.minVolume);if(volume!==null && volume>0)query.set('min_volume',String(volume));
 return query.toString();
}

export function readSavedActivity(payload,{now=Date.now()}={}){
 if(!payload || !Array.isArray(payload.columns) || payload.columns.length!==COLUMNS.length || payload.columns.some((name,index)=>name!==COLUMNS[index]) || !Array.isArray(payload.rows) || payload.rows.length>100 || !Number.isInteger(payload.count) || payload.count!==payload.rows.length
  || !Number.isInteger(payload.offset) || payload.offset<0 || !Number.isInteger(payload.total) || payload.total<0
  || payload.next_offset!==null && (!Number.isInteger(payload.next_offset) || payload.next_offset<=payload.offset || payload.next_offset>payload.total))throw new Error('Saved page could not be checked.');
 const quotes=object(payload.quote_truth),rowMeta=object(payload.row_observations),stocks=object(payload.observations_by_ticker);
 const today=savedToday(now);let discarded=0;const rows=[];
 for(const raw of payload.rows){
  const under=Array.isArray(raw) && typeof raw[0]==='string'?raw[0].trim().toUpperCase():null;
  const type=Array.isArray(raw)?raw[2]:null,strike=Array.isArray(raw)?finite(raw[3]):null,exp=Array.isArray(raw)?raw[4]:null;
  if(!Array.isArray(raw) || raw.length<7 || raw.length>10 || !under || !/^[A-Z][A-Z0-9.-]{0,11}$/.test(under) || !['call','put'].includes(type) || strike===null || strike<=0 || dayNumber(exp)===null){discarded++;continue;}
  const identity=under+'|'+type+'|'+strike+'|'+exp;
  const extra=object(quotes[identity]),meta=object(rowMeta[identity]),stock=object(stocks[under]);
  const clock=(key,fallback)=>savedClock(has(meta,key)?meta[key]:has(extra,key)?extra[key]:fallback,now);
  const receiptClock=clock('received_at',stock.received_at);
  const volumeClock=clock('volume_source_time',null),quoteClock=clock('quote_source_time',null);
  const vol=nonnegative(raw[5]),oi=nonnegative(raw[6]);
  const premium=nonnegative(extra.premium_true);
  rows.push({under,ticker:under,type,strike,exp,vol,oi,volOI:vol!==null && oi!==null && oi>0?vol/oi:null,
   spot:nonnegative(raw[9]),delta:finite(raw[8]),iv:extra.iv_unit==='fraction'?nonnegative(raw[7]):null,
   dte:savedExpiryDays(exp,today),premium,premiumLabel:premium!==null?'Quote estimate':null,
   score:null,oiChgPct:null,notional:null,ftype:null,arch:null,regime:null,
   receiptClock,volumeClock,quoteClock,eventClock:clock('event_time',stock.event_time),
   dataStatus:meta.data_status || stock.data_status || 'partial',tradeEligible:false,
   key:identity,raw:raw.slice(),extra:{...extra},meta:{...meta},stockMeta:{...stock},
  });
 }
 const warnings=[];if(discarded)warnings.push(discarded+' unreadable saved '+(discarded===1?'row was':'rows were')+' left out.');
 return {rows:spreadStockAlerts(rows),discarded,warnings,partial:payload.status==='partial' || discarded>0 || rows.some(row=>row.dataStatus!=='available' || row.receiptClock.state!=='known' || row.volumeClock.state!=='known'),payload};
}
function checkedTickerFacts(row,tickerFacts,now){
 const facts=object(tickerFacts?.[row.under]);
 const receipt=savedClock(facts.received_at ?? facts.received,now);
 if(row.receiptClock.state!=='known' || receipt.state!=='known' || row.receiptClock.ms!==receipt.ms)return {};
 return Object.fromEntries(TICKER_FACTS.map(key=>[key,finite(facts[key])]));
}
function conditionsOf(screen){return (screen?.conditions || []).flatMap(condition=>Array.isArray(condition.conditions)?conditionsOf(condition):[condition]);}

export function filterSavedActivity(rows,{screen=BUILTIN_SCREENS[0],filters={},universe=[],tickerFacts={},now=Date.now()}={}){
 const today=savedToday(now),names=new Set(universe.map(name=>String(name).trim().toUpperCase()));
 const chosen=screen?.custom?screen:typeof screen?.matchScan==='function'?screen:BUILTIN_SCREENS.find(item=>item.id===screen?.id) || BUILTIN_SCREENS[0];
 const warnings=new Set();
 if(finite(filters.minScore)>0)warnings.add('Saved scores are unavailable. Rows without a saved score do not pass this filter.');
 const inherited=chosen.custom?BUILTIN_SCREENS.find(item=>item.id===chosen.copyOf):chosen;
 if(inherited?.id==='oiconf')warnings.add('Saved open interest changes are unavailable.');
 if(inherited?.id==='whale')warnings.add('Large activity uses only a recorded quote estimate; unknown values do not pass.');
 if(chosen.custom && chosen.rule && chosen.rule!=='ANY')warnings.add('The chosen signal rule was not recorded with these saved rows.');
 const unknown=new Set();
 const eligible=rows.filter(original=>{
  const row={...original,dte:savedExpiryDays(original.exp,today)};
  const facts=checkedTickerFacts(row,tickerFacts,now);
  for(const condition of conditionsOf(chosen)){const value=TICKER_FACTS.includes(condition.fact)?facts[condition.fact]:row[condition.fact];if(value===null || value===undefined)unknown.add(TICKER_FACT_LABELS[condition.fact] || SCAN_FACT_LABELS[condition.fact] || 'Chosen reading');}
  if(filters.universeOnly && !names.has(row.under))return false;
  if(filters.type && filters.type!=='all' && row.type!==filters.type)return false;
  const query=typeof filters.q==='string'?filters.q.trim().toUpperCase():'';if(query && !row.under.includes(query))return false;
  const minVolume=finite(filters.minVolume);if(minVolume>0 && (row.vol===null || row.vol<minVolume))return false;
  const minScore=finite(filters.minScore);if(minScore>0 && (row.score===null || row.score<minScore))return false;
  const low=finite(filters.dteMin),high=finite(filters.dteMax);
  if(low!==null && (row.dte===null || row.dte<low))return false;
  if(high!==null && (row.dte===null || row.dte>high))return false;
  return applyScreenToScans([row],chosen,{universe:[...names],tickerFacts:{[row.under]:facts},alerts:[]}).length>0;
 });
 if(unknown.size)warnings.add('Some chosen filters need readings that were not recorded or are unavailable: '+[...unknown].join(', ')+'.');
 if((filters.dteMin!==null && filters.dteMin!==undefined || filters.dteMax!==null && filters.dteMax!==undefined || inherited?.id==='zerodte' || inherited?.id==='hedge'))warnings.add('Expiry filters use the actual calendar date today. Older expired options stay expired.');
 return {rows:spreadStockAlerts(eligible),warnings:[...warnings]};
}

export function formatSavedClock(clock){
 if(clock?.state!=='known')return 'Unknown';
 try{return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(clock.ms);}catch{return 'Unknown';}
}
