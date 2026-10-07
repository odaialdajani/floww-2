import React,{useEffect,useId,useMemo,useRef,useState} from 'react';
import {chartTime,checkedCandles,clampWindow,NODE_COLORS,NODE_LABELS,pinchFactors,priceRange,savedLevels,zoomPrice,zoomTime} from './recordedPriceChartData';
import './RecordedPriceChart.css';
const price=value=>Number.isFinite(value)?value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'Unavailable';
const bound=(value,low,high)=>Math.max(low,Math.min(high,value));

export default function RecordedPriceChart({ticker,frames,revision='',onInteract,metricCoverage={},toolbarControls=null,toolbarActions=null,historyControls=null,dataDetails=null,readingStatus="Data details",emptyContent=null}) {
 const data=useMemo(()=>checkedCandles(frames),[frames]);
 const surface=useRef(null),pointers=useRef(new Map()),gesture=useRef(null),previousLength=useRef(0);
 const [size,setSize]=useState({width:800,height:480});
 const [view,setView]=useState(()=>({start:Math.max(0,data.length-80),count:80}));
 const [manualPrice,setManualPrice]=useState(null),[hover,setHover]=useState(null),[metrics,setMetrics]=useState(['gex','vex','charm']),[allNodes,setAllNodes]=useState(false);
 const id=useId().replace(/[^a-zA-Z0-9_-]/g,'');
 useEffect(()=>{
  const element=surface.current;if(!element)return undefined;
  const measure=()=>{const r=element.getBoundingClientRect();if(r.width>0&&r.height>0)setSize({width:r.width,height:r.height});};
  measure();const observer=typeof ResizeObserver==='function'?new ResizeObserver(measure):null;observer?.observe(element);
  window.addEventListener('resize',measure);return()=>{observer?.disconnect();window.removeEventListener('resize',measure);};
 },[Boolean(data.length)]);
 useEffect(()=>{setView({start:Math.max(0,data.length-80),count:80});setManualPrice(null);setHover(null);pointers.current.clear();gesture.current=null;},[revision]); // scope owns the view
 useEffect(()=>{const old=previousLength.current;setView(current=>{const count=current.count||80;const next=clampWindow(!old||current.start+Math.min(count,old)>=old?{start:Math.max(0,data.length-count),count}:current,data.length);return {...next,count};});previousLength.current=data.length;setHover(null);},[data.length]);
 const windowView=clampWindow(view,data.length),visible=data.slice(windowView.start,windowView.start+windowView.count);
 const allLevels=useMemo(()=>visible.flatMap(frame=>savedLevels(frame,metrics,allNodes)),[visible,metrics,allNodes]);
 const range=manualPrice||priceRange(visible,allLevels),selected=visible[hover??Math.max(0,visible.length-1)];
 const selectedLevels=savedLevels(selected,metrics,allNodes);
 const availableMetrics=useMemo(()=>Object.keys(NODE_LABELS).filter(metric=>metricCoverage?.[metric]?.checked_candles>0||data.some(frame=>savedLevels(frame,[metric],true).length)),[data,metricCoverage]);
 const left=12,right=Math.max(left+1,size.width-76),top=16,bottom=Math.max(top+1,size.height-38),plotWidth=right-left,plotHeight=bottom-top;
 const spacing=plotWidth/Math.max(1,visible.length),y=value=>bottom-(value-range.low)/(range.high-range.low)*plotHeight;
 const notify=()=>onInteract?.();
 const point=event=>{const r=surface.current.getBoundingClientRect();return {x:(event.clientX-r.left)*size.width/r.width,y:(event.clientY-r.top)*size.height/r.height};};
 const current=useRef(null);current.current={view:windowView,range,total:data.length,left,right,top,bottom,plotWidth,plotHeight,size};
 const zoom=(axis,factor,anchor=0.5)=>{notify();setHover(null);if(axis==='price')setManualPrice(zoomPrice(range,factor,anchor));else setView(zoomTime(windowView,factor,anchor,data.length));};
 useEffect(()=>{
  const element=surface.current;if(!element)return undefined;
  const wheel=event=>{const state=current.current;if(!state?.total||!(event.ctrlKey||event.metaKey||event.shiftKey))return;event.preventDefault();onInteract?.();setHover(null);
   const rect=element.getBoundingClientRect(),x=(event.clientX-rect.left)*state.size.width/rect.width,yy=(event.clientY-rect.top)*state.size.height/rect.height;
   if(event.shiftKey||x>=state.right)setManualPrice(zoomPrice(state.range,Math.exp(bound(event.deltaY,-120,120)*0.003),bound(1-(yy-state.top)/state.plotHeight,0,1)));
   else setView(zoomTime(state.view,Math.exp(bound(event.deltaY,-120,120)*0.003),bound((x-state.left)/state.plotWidth,0,1),state.total));
  };element.addEventListener('wheel',wheel,{passive:false});return()=>element.removeEventListener('wheel',wheel);
 },[onInteract,Boolean(data.length)]);
 const begin=event=>{
  if(!data.length)return;notify();setHover(null);const p=point(event);pointers.current.set(event.pointerId,p);event.currentTarget.setPointerCapture?.(event.pointerId);
  if(pointers.current.size===2){const touch=[...pointers.current.values()];gesture.current={mode:'pinch',touch,view:windowView,range};}
  else if(pointers.current.size===1)gesture.current={mode:p.x>=right?'price':p.y>=bottom?'time':'pan',point:p,view:windowView,range,manual:Boolean(manualPrice)};
 };
 const move=event=>{
  const p=point(event);if(!pointers.current.has(event.pointerId)){
   if(p.x>=left&&p.x<right&&p.y>=top&&p.y<bottom)setHover(bound(Math.floor((p.x-left)/spacing),0,Math.max(0,visible.length-1)));else setHover(null);return;
  }
  pointers.current.set(event.pointerId,p);const base=gesture.current;if(!base)return;
  if(base.mode==='pinch'&&pointers.current.size>=2){const touch=[...pointers.current.values()].slice(0,2),factors=pinchFactors(base.touch,touch);
   const cx=(base.touch[0].x+base.touch[1].x)/2,cy=(base.touch[0].y+base.touch[1].y)/2;
   if(factors.x!==1)setView(zoomTime(base.view,factors.x,bound((cx-left)/plotWidth,0,1),data.length));if(factors.y!==1)setManualPrice(zoomPrice(base.range,factors.y,bound(1-(cy-top)/plotHeight,0,1)));return;
  }
  const dx=p.x-base.point.x,dy=p.y-base.point.y;
  if(base.mode==='price')setManualPrice(zoomPrice(base.range,Math.exp(bound(dy,-500,500)/180),0.5));
  else if(base.mode==='time')setView(zoomTime(base.view,Math.exp(bound(dx,-500,500)/240),0.5,data.length));
  else {setView(clampWindow({start:base.view.start-dx/plotWidth*base.view.count,count:base.view.count},data.length));if(base.manual){const offset=dy/plotHeight*(base.range.high-base.range.low);setManualPrice({low:base.range.low+offset,high:base.range.high+offset});}}
 };
 const end=event=>{pointers.current.delete(event.pointerId);event.currentTarget.releasePointerCapture?.(event.pointerId);if(pointers.current.size===1){gesture.current={mode:'pan',point:[...pointers.current.values()][0],view:current.current.view,range:current.current.range,manual:Boolean(manualPrice)};}else gesture.current=null;};
 const shift=amount=>{notify();setHover(null);setView(clampWindow({...windowView,start:windowView.start+amount},data.length));};
 const keyboard=event=>{const actions={ArrowLeft:()=>shift(-1),ArrowRight:()=>shift(1),PageUp:()=>shift(-Math.max(1,Math.floor(windowView.count/2))),PageDown:()=>shift(Math.max(1,Math.floor(windowView.count/2))),Home:()=>shift(-data.length),End:()=>shift(data.length),'+':()=>zoom('time',0.75),'-':()=>zoom('time',1.35)};if(actions[event.key]){event.preventDefault();event.stopPropagation();actions[event.key]();}};
 return <div className="recorded-price-chart" data-testid="recorded-price-chart" data-candles={data.length} data-visible-candles={visible.length} data-window-start={windowView.start} data-price-low={range.low} data-price-high={range.high}>
  <div className="recorded-chart-tools" data-testid="chart-control-row">
   {toolbarControls}
   <div className="recorded-chart-scale"><button type="button" aria-label="Zoom in time" disabled={!data.length} onClick={()=>zoom('time',0.75)}>+</button><button type="button" aria-label="Zoom out time" disabled={!data.length} onClick={()=>zoom('time',1.35)}>-</button><button type="button" aria-label="Auto scale" aria-pressed={!manualPrice} disabled={!data.length} title={manualPrice?"Price scale locked; click to fit visible prices":"Fits visible prices; click to lock"} onClick={()=>setManualPrice(held=>held?null:range)}>Auto scale {manualPrice?'locked':'on'}</button></div>
   <details className="recorded-chart-popover"><summary role="button" aria-label="Chart tools">Tools</summary><div className="recorded-chart-popover-content">
    <div className="recorded-chart-history"><button type="button" aria-label="Earlier candles" disabled={!windowView.start} onClick={()=>shift(-Math.max(1,Math.floor(windowView.count/2)))}>Earlier</button><button type="button" aria-label="Later candles" disabled={windowView.start+windowView.count>=data.length} onClick={()=>shift(Math.max(1,Math.floor(windowView.count/2)))}>Later</button><button type="button" disabled={!data.length} onClick={()=>{notify();setView({start:0,count:data.length});setManualPrice(null);}}>Fit history</button></div>
    <fieldset className="recorded-chart-layers" aria-label="Saved node lines"><legend>Saved lines</legend>{Object.entries(NODE_LABELS).map(([metric,label])=><label key={metric} style={{'--node-color':NODE_COLORS[metric]}}><input type="checkbox" checked={metrics.includes(metric)} disabled={!availableMetrics.includes(metric)} onChange={e=>{setMetrics(old=>e.target.checked?[...old,metric]:old.filter(value=>value!==metric));setManualPrice(null);}}/>{label}{!availableMetrics.includes(metric)&&<span> unavailable</span>}</label>)}<label><input type="checkbox" checked={allNodes} onChange={e=>{setAllNodes(e.target.checked);setManualPrice(null);}}/>All saved levels</label></fieldset>
    {historyControls}<small id={'chart-help-'+id}>Drag to scroll history. Pinch time and price. Drag an axis to stretch it. Ctrl + scroll zooms time; Shift + scroll zooms price. Normal scrolling moves the page.</small>
   </div></details>
   <div className="recorded-chart-actions">{toolbarActions}</div>
  </div>
  <div className="recorded-chart-readout" aria-live="off" data-testid="chart-reading-row"><strong>{selected?chartTime(selected.time,true):'Waiting for a candle'} <span>New York</span></strong>{selected&&<span>Open <b>{price(selected.open)}</b> High <b>{price(selected.high)}</b> Low <b>{price(selected.low)}</b> Close <b>{price(selected.close)}</b></span>}<details className="recorded-chart-popover recorded-chart-data"><summary role="button" aria-label="Chart data details">{readingStatus}</summary><div className="recorded-chart-popover-content">{dataDetails||<p>Prices and lines use their own stored times. Missing readings remain unavailable.</p>}</div></details></div>
  {!!data.length?<div ref={surface} className="recorded-chart-surface" role="region" aria-label={ticker+' candle chart'} aria-describedby={'chart-help-'+id} tabIndex={0} onKeyDown={keyboard} onPointerDown={begin} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onPointerLeave={()=>{if(!pointers.current.size)setHover(null);}}>
   <svg viewBox={'0 0 '+size.width+' '+size.height} aria-label={ticker+' recorded price candles'} role="img">
    <defs><clipPath id={'chart-clip-'+id}><rect x={left} y={top} width={plotWidth} height={plotHeight}/></clipPath></defs>
    {Array.from({length:6},(_,i)=>{const level=range.high-(range.high-range.low)*i/5,yy=y(level);return <g key={i}><line x1={left} x2={right} y1={yy} y2={yy} stroke="#27313c" strokeWidth="1"/><text x={right+10} y={yy+4} className="recorded-price-label">{price(level)}</text></g>;})}
    <g clipPath={'url(#chart-clip-'+id+')'}>
     {visible.map((frame,index)=>{const center=left+(index+0.5)*spacing,up=frame.close>=frame.open,width=Math.max(1,Math.min(14,spacing*0.65)),bodyTop=y(Math.max(frame.open,frame.close)),bodyHeight=Math.max(1,Math.abs(y(frame.open)-y(frame.close)));return <g key={frame.time} className={up?'recorded-candle-up':'recorded-candle-down'} data-testid="price-candle"><title>{chartTime(frame.time,true)+' New York. Open '+price(frame.open)+', high '+price(frame.high)+', low '+price(frame.low)+', close '+price(frame.close)}</title><line x1={center} x2={center} y1={y(frame.high)} y2={y(frame.low)} stroke="currentColor" strokeWidth="1.5"/><rect x={center-width/2} y={bodyTop} width={width} height={bodyHeight} fill="currentColor"/></g>;})}
     {visible.flatMap((frame,index)=>savedLevels(frame,metrics,allNodes).map((node,n)=>{const seconds=typeof frame.duration_seconds==='number'&&frame.duration_seconds>0?frame.duration_seconds:60,fraction=Math.min(seconds,Math.max(0,900-(node.age_seconds??frame.node_age_seconds)))/seconds;
      const xx=left+index*spacing,yy=y(node.level);return <line data-testid="saved-node-line" key={frame.time+':'+node.metric+':'+node.id+':'+n} x1={xx} x2={xx+spacing*fraction} y1={yy} y2={yy} stroke={NODE_COLORS[node.metric]} strokeWidth="2" opacity="0.88"><title>{NODE_LABELS[node.metric]+' saved level '+price(node.level)+'. Known '+chartTime(Object.hasOwn(node,'known_at')?node.known_at:frame.nodes_known_at,true)+' New York. '+(node.label||'Recorded level')}</title></line>;}))}
     {hover!==null&&selected&&<><line x1={left+(hover+0.5)*spacing} x2={left+(hover+0.5)*spacing} y1={top} y2={bottom} stroke="#a8b3be" strokeDasharray="3 4"/><line x1={left} x2={right} y1={y(selected.close)} y2={y(selected.close)} stroke="#a8b3be" strokeDasharray="3 4"/></>}
    </g>
    <line x1={right} x2={right} y1={top} y2={bottom} stroke="#3d4853"/>
    {Array.from({length:Math.min(5,visible.length)},(_,i)=>{const index=Math.round(i*Math.max(0,visible.length-1)/Math.max(1,Math.min(5,visible.length)-1)),frame=visible[index];return frame&&<text key={i} x={left+(index+0.5)*spacing} y={bottom+24} textAnchor={i===0?'start':i===4?'end':'middle'} className="recorded-time-label">{chartTime(frame.time)}</text>;})}
   </svg>
  </div>:<div className="recorded-chart-empty">{emptyContent||<p>No valid price candles are available.</p>}</div>}
  {!!data.length&&<div className="recorded-chart-footer"><small>{windowView.start+1}-{windowView.start+visible.length} of {data.length} loaded candles</small></div>}
  {selected&&<div className="recorded-chart-nodes" aria-label="Selected candle saved nodes">{selectedLevels.length?selectedLevels.map((node,index)=><span key={node.metric+':'+node.id+':'+index} style={{color:NODE_COLORS[node.metric]}}>{NODE_LABELS[node.metric]} <b>{price(node.level)}</b></span>):<span>No supported saved node lines at this candle.{Object.entries(selected?.metric_status||{}).filter(([,status])=>status==="zero").map(([metric])=>" "+NODE_LABELS[metric]+" was zero; no largest level stood out.").join("")}</span>}</div>}
 </div>;
}
