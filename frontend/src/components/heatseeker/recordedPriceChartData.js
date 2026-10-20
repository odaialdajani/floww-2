const METRICS = {gex: 'GEX', vex: 'VEX / Vanna', charm: 'Charm'};
export const NODE_COLORS = {gex:'#e8bd65',vex:'#72d7df',charm:'#c4a1ef'};
export const NODE_LABELS = METRICS;
const positive = value => typeof value === 'number' && Number.isFinite(value) && value > 0;
// B01 canonical ingress (chartContract mirror): the mounted price-history
// consumer normalizes through the strict grammar so booleans, blanks and
// nonfinite payloads can never become chart prices, and explicit numeric
// strings become numbers (the canonical grammar). Volume keeps the stricter
// TYPED rule: only real finite numbers >= 0 are readings — a string volume
// stays unavailable rather than becoming a bar (pinned by the accepted
// RecordedPriceChart.integrity fixture "keeps '10' unavailable rather than
// inventing a zero bar"). Legacy frames semantics unchanged.
import {parsePrice} from './chart/chartContract';

export function checkedCandles(frames = []) {
  const seen = new Set();
  return (Array.isArray(frames) ? frames : []).map(frame => {
    if (!frame || typeof frame.time !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(frame.time)) return null;
    const at = Date.parse(frame.time);
    if (!Number.isFinite(at) || seen.has(at)) return null;
    const open = parsePrice(frame.open), high = parsePrice(frame.high), low = parsePrice(frame.low), close = parsePrice(frame.close);
    if (open === null || high === null || low === null || close === null) return null;
    if (high < Math.max(open, close, low) || low > Math.min(open, close, high)) return null;
    seen.add(at);
    const volume = typeof frame.volume === 'number' && Number.isFinite(frame.volume) && frame.volume >= 0 ? frame.volume : null;
    if (volume === null) { const withoutVolume = {...frame}; delete withoutVolume.volume; return {...withoutVolume, open, high, low, close}; }
    return {...frame, open, high, low, close, volume};
  }).filter(Boolean).slice().sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
}

// Match only observed contract closes at the same instant as each candle.
// Duplicate instants are ambiguous; missing/invalid readings stay gaps.
export function contractClosesForFrames(frames, bars) {
  const instant = value => {
    if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
      const ms = value < 100_000_000_000 ? value * 1000 : value;
      return Number.isFinite(new Date(ms).valueOf()) ? ms : null;
    }
    if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
    const ms = Date.parse(value);
    return Number.isFinite(ms) ? ms : null;
  };
  const byTime = new Map();
  for (const bar of Array.isArray(bars) ? bars : []) {
    const at = instant(bar?.t ?? bar?.time);
    if (at === null) continue;
    const close = bar?.c ?? bar?.close;
    byTime.set(at, byTime.has(at) ? null : typeof close === 'number' && Number.isFinite(close) && close >= 0 ? close : null);
  }
  return frames.map(frame => byTime.get(instant(frame.time)) ?? null);
}

export function savedLevels(frame, metrics = ['gex','vex','charm'], all = false) {
  const at=Date.parse(frame?.time);if(!Number.isFinite(at))return [];
  const nodes=(Array.isArray(frame?.nodes)?frame.nodes:[]).filter(node=>{
    if(!node||!positive(node.level)||!metrics.includes(node.metric||'gex')||!Object.hasOwn(METRICS,node.metric||'gex'))return false;
    const known=Date.parse(Object.hasOwn(node,'known_at')?node.known_at:frame.nodes_known_at),age=Object.hasOwn(node,'age_seconds')?node.age_seconds:frame.node_age_seconds;
    return Number.isFinite(known)&&known<=at&&typeof age==='number'&&Number.isFinite(age)&&age>=0&&age<=900;
  }).map(node=>({...node,metric:node.metric||'gex'}));
  if(all)return nodes;
  return metrics.flatMap(metric=>{
    const group=nodes.filter(node=>node.metric===metric);
    const below=group.filter(node=>node.level<=frame.close).sort((a,b)=>b.level-a.level).slice(0,2);
    const above=group.filter(node=>node.level>frame.close).sort((a,b)=>a.level-b.level).slice(0,2);
    return [...below,...above];
  });
}

export function clampWindow(view,total) {
  if(!total)return {start:0,count:0};
  const count=Math.max(1,Math.min(total,Math.round(view.count)||1));
  return {start:Math.max(0,Math.min(total-count,Math.round(view.start)||0)),count};
}
export function zoomTime(view,factor,anchor,total) {
  if(!total)return clampWindow(view,total);
  const minimum=Math.min(8,total), a=Math.max(0,Math.min(1,anchor));
  const count=Math.max(minimum,Math.min(total,Math.round(view.count*factor)));
  const point=view.start+a*Math.max(0,view.count-1);
  return clampWindow({start:point-a*Math.max(0,count-1),count},total);
}
export function zoomPrice(range,factor,anchor=0.5) {
  const a=Math.max(0,Math.min(1,anchor)),span=range.high-range.low;
  const point=range.low+span*a;
  const next=Math.max(Math.max(1,Math.abs(point))*0.000001,Math.min(Math.max(1,Math.abs(point))*20,span*factor));
  return {low:point-next*a,high:point+next*(1-a)};
}
export function pinchFactors(before,after) {
  const axis=(key)=>{const a=Math.abs(before[0][key]-before[1][key]),b=Math.abs(after[0][key]-after[1][key]);
    return a>=18 && b>=8 ? Math.max(0.125,Math.min(8,a/b)):1;};
  return {x:axis('x'),y:axis('y')};
}
export function priceRange(frames,levels=[]) {
  const values=frames.flatMap(frame=>[frame.low,frame.high]).concat(levels.map(level=>level.level)).filter(positive);
  if(!values.length)return {low:0,high:1};
  let low=Infinity,high=-Infinity;for(const value of values){low=Math.min(low,value);high=Math.max(high,value);}const pad=Math.max((high-low)*0.08,(high+low)*0.0003);
  return {low:low-pad,high:high+pad};
}
export function chartTime(time,full=false) {
  const date=new Date(time);if(!Number.isFinite(date.valueOf()))return 'Time unavailable';
  return date.toLocaleString('en-US',{timeZone:'America/New_York',month:'short',day:'numeric',...(full?{year:'numeric'}:{}),hour:'numeric',minute:'2-digit'});
}
