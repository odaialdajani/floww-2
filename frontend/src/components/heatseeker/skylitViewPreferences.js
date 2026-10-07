import {ALL_BASES} from "../../lib/solsticeMetrics";
import {mapSurface,shownMapStrikes} from "./shownMapStrikes";
export const SKYLIT_VIEW_KEY="floww-skylit-view-preferences-v1";
export const MAX_SKYLIT_VIEWS=24;
const MAX_BYTES=65536;
const METRICS=new Set(ALL_BASES.map(b=>b.id));
const LAYOUTS=new Set(["focus","profile","multi","calendar","symbols"]);
const VIEWS=new Set(["gex","skylit","vex","charm"]);
const PANES=new Set(["gex","delta","vex","charm"]);
const ZOOMS=new Set([0.75,1,1.25,1.5]);
const DEFAULTS={metric:"raw",layout:"profile",gridZoom:1,priceHistoryOpen:false,compareMode:false,comparePair:"gexvex",activePane:"gex",selection:null};

export function skylitViewScope({ticker,timeframe,expiries,dte,expiryScope,viewMode,localView}){
 if(typeof ticker!=="string" || !ticker.trim() || ticker.length>32 || typeof timeframe!=="string" || timeframe.length>32 || typeof expiryScope!=="string" || expiryScope.length>32 || (localView!=null && (typeof localView!=="string" || localView.length>32)) || !Number.isFinite(expiries) || (dte!=null && !Number.isFinite(dte)) || !VIEWS.has(viewMode))return null;
 const key=JSON.stringify([ticker,timeframe,expiries,dte??null,expiryScope,viewMode,localView??null]);return key.length<=512?key:null;
}

function queryIdentity(query){
 if(!query || typeof query!=="object" || Array.isArray(query))return null;
 const keys=Object.keys(query).sort();if(!keys.length || keys.length>32)return null;
 const entries=[];
 for(const key of keys){
  if(key.length>64 || /^(?:__proto__|constructor|prototype)$/.test(key) || /secret|password|credential|authorization|api.?key|token/i.test(key))return null;
  const value=query[key];
  if(value!==null && !["string","number","boolean"].includes(typeof value))return null;
  if(typeof value==="number" && !Number.isFinite(value))return null;
  if(typeof value==="string" && value.length>128)return null;
  entries.push([key,value]);
 }
 const text=JSON.stringify(Object.fromEntries(entries));return text.length<=2048?text:null;
}

function finiteNumber(value){
 if(typeof value!=="number" && (typeof value!=="string" || !value.trim() || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim())))return null;
 const number=Number(value);return Number.isFinite(number)?number:null;
}

function selectionIdentity(selection){
 if(!selection || typeof selection!=="object" || typeof selection.ticker!=="string" || selection.ticker.length>32 || !VIEWS.has(selection.view) || !METRICS.has(selection.metric) || typeof selection.query!=="string" || selection.query.length>2048)return null;
 let query;try{query=queryIdentity(JSON.parse(selection.query));}catch{return null;}if(!query || query!==selection.query)return null;
 const strike=selection.strike==null?null:finiteNumber(selection.strike),colKey=selection.colKey??null,wall_id=selection.wall_id??null;
 if(selection.strike!=null && strike===null)return null;
 if(colKey!==null && (typeof colKey!=="string" || !/^\d{4}-\d{2}-\d{2}$/.test(colKey)))return null;
 if(wall_id!==null && (typeof wall_id!=="string" || !wall_id.trim() || wall_id.length>128))return null;
 if((colKey!==null && strike===null) || (colKey===null && wall_id===null))return null;
 return {ticker:selection.ticker,view:selection.view,metric:selection.metric,strike,colKey,wall_id,query:selection.query};
}

function preferences(value){
 const input=value && typeof value==="object"?value:{};
 return {metric:METRICS.has(input.metric)?input.metric:DEFAULTS.metric,layout:LAYOUTS.has(input.layout)?input.layout:DEFAULTS.layout,
  gridZoom:ZOOMS.has(input.gridZoom)?input.gridZoom:1,priceHistoryOpen:input.priceHistoryOpen===true,
  compareMode:input.compareMode===true && input.layout==="focus",comparePair:input.comparePair==="rawdelta"?"rawdelta":"gexvex",
  activePane:PANES.has(input.activePane)?input.activePane:"gex",selection:selectionIdentity(input.selection)};
}

function readEntries(storage){
 const raw=storage.getItem(SKYLIT_VIEW_KEY);if(typeof raw!=="string" || raw.length>MAX_BYTES)return [];
 const stored=JSON.parse(raw);if(stored?.version!==1 || !Array.isArray(stored.entries))return [];
 return stored.entries.filter(row=>row && typeof row.key==="string" && row.key.length<=512).slice(0,MAX_SKYLIT_VIEWS).map(row=>({key:row.key,preferences:preferences(row.preferences)}));
}

export function readSkylitView(scope,storage){
 try{const row=scope && readEntries(storage || window.sessionStorage).find(item=>item.key===scope);return {...preferences(row?.preferences),found:Boolean(row)};}catch{return {...DEFAULTS,found:false};}
}

export function writeSkylitView(scope,value,storage){
 if(typeof scope!=="string" || scope.length>512)return false;
 try{
  const target=storage || window.sessionStorage;let previous;try{previous=readEntries(target);}catch{previous=[];}
  const safe=preferences(value);if(previous[0]?.key===scope && JSON.stringify(previous[0].preferences)===JSON.stringify(safe))return true;
  const entries=[{key:scope,preferences:safe},...previous.filter(row=>row.key!==scope)].slice(0,MAX_SKYLIT_VIEWS);
  let text=JSON.stringify({version:1,entries});while(text.length>MAX_BYTES && entries.length>1){entries.pop();text=JSON.stringify({version:1,entries});}
  if(text.length>MAX_BYTES)return false;target.setItem(SKYLIT_VIEW_KEY,text);return true;
 }catch{return false;}
}

// Revalidate identity against the current displayed payload. Build time is a
// version selector, not proof of market freshness; no saved values are reused.
export function restoreSkylitSelection(saved,{data,ticker,view,metric,spot,windowRows}){
 const identity=selectionIdentity(saved);
 if(!identity || !data || data.replay || data.stale===true || ["unavailable","stale"].includes(data.status) || ["unavailable","stale"].includes(data.quality?.state) || data.ticker!==ticker || identity.ticker!==ticker || identity.view!==view || identity.metric!==metric || typeof data.asof!=="string" || !data.asof.trim())return null;
 const query=queryIdentity(data.map_query);if(!query || identity.query!==query)return null;
 const walls=data.metrics?.walls;const wall=identity.wall_id && Array.isArray(walls)?walls.find(w=>w?.wall_id===identity.wall_id):null;
 const wallLow=finiteNumber(wall?.low),wallHigh=finiteNumber(wall?.high);
 if(identity.wall_id && (!wall || wallLow===null || wallHigh===null || wallLow>wallHigh))return null;
 if(identity.colKey!==null){
  const surface=mapSurface(data,view,metric);const section=metric!=="raw" && ["gex","skylit"].includes(view)?data.metrics?.grids?.[metric]:data.grid;
  if(["vex","charm"].includes(view) && data.grid?.[view+"_meta"]?.status==="unavailable")return null;
  if(!surface.available || section?.status==="unavailable" || !surface.expiries.includes(identity.colKey) || !shownMapStrikes(data,spot,windowRows,view,metric).includes(identity.strike))return null;
  const value=surface.matrix[identity.colKey]?.[String(identity.strike)];if(typeof value!=="number" || !Number.isFinite(value))return null;
  if(wall && (identity.strike<wallLow || identity.strike>wallHigh))return null;
  return {ticker,view,metric,strike:identity.strike,colKey:identity.colKey,wall_id:identity.wall_id,asof:data.asof,value};
 }
 if(!wall || (identity.strike!==null && (identity.strike<wallLow || identity.strike>wallHigh)))return null;
 return {ticker,view,metric,strike:identity.strike,colKey:null,wall_id:identity.wall_id,asof:data.asof,value:null};
}

export function captureSkylitSelection(selected,context){
 if(!selected || context.replay)return null;
 const query=queryIdentity(context.data?.map_query);if(!query)return null;
 const saved=selectionIdentity({...selected,view:selected.view || context.view,metric:selected.metric || context.metric,query});
 return restoreSkylitSelection(saved,context)?saved:null;
}
