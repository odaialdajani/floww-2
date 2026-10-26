import React,{useCallback,useEffect,useId,useMemo,useRef,useState} from 'react';
import {chartTime,checkedCandles,clampWindow,contractClosesForFrames,NODE_COLORS,NODE_LABELS,pinchFactors,priceRange,savedLevels,zoomPrice,zoomTime} from './recordedPriceChartData';
import {openingEnvelope,sessionEnvelope,sessionVwapBands,sessionVwapValues} from './chart/indicators/priceStudies';
import {volumeProfile} from './chart/indicators/profile';
import { profileConfig, tpoConfig } from './chart/indicators/paneStudies';
import './chart/stock-chrome.css';
import './RecordedPriceChart.css';
const price=value=>Number.isFinite(value)?value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'Unavailable';
const bound=(value,low,high)=>Math.max(low,Math.min(high,value));
const axisTime=value=>new Date(value).toLocaleString('en-US',{timeZone:'America/New_York',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
const closeDetails=element=>{const details=element.closest('details');if(details){details.open=false;details.querySelector('summary')?.focus();}};

export default function RecordedPriceChart({ticker,frames,revision='',onInteract,metricCoverage={},toolbarControls=null,toolbarActions=null,historyPeriodControls=null,historyControls=null,replayControls=null,dataDetails=null,readingStatus="Data details",emptyContent=null,showAtlas=true,exposureLine=null,darkLevels=null,flowBars=null,alertLines=null,cvdLine=null,contractBars=null,contractSymbol=null,contractStatus=null,fitAllFrames=null,renderDrawingLayer=null,syncSeq=0,syncView=null,syncPrice=null,syncCrosshair=null,onSync=null,studyLines=null,mappedShapes=null,volumeInstanceActive=false, overlays=null, onOverlaysChange=null, paneCfg=null, onPaneCfg=null, cvdStudy=null, cvdStudyRefusal=null}) {
 const data=useMemo(()=>checkedCandles(frames),[frames]);
 const premiumCloses=useMemo(()=>contractClosesForFrames(data,contractBars),[data,contractBars]);
 const surface=useRef(null),pointers=useRef(new Map()),gesture=useRef(null),previousLength=useRef(0);
 const [size,setSize]=useState({width:800,height:480});
 const [view,setView]=useState(()=>({start:Math.max(0,data.length-80),count:80}));
 const [manualPrice,setManualPrice]=useState(null),[hover,setHover]=useState(null),[metrics,setMetrics]=useState(['gex','vex','charm']),[allNodes,setAllNodes]=useState(false);
 // UI-05 real fit: when the caller hands a fit-all history set, the price
 // scale spans the FULL loaded history (candles + their node levels) while
 // the drawn candles stay the visible window. Without it the range comes
 // from the visible slice exactly as before — callers unaffected.
 const fitData=useMemo(()=>Array.isArray(fitAllFrames)&&fitAllFrames.length?checkedCandles(fitAllFrames):null,[fitAllFrames]);
 // S2 link dimensions: user chart actions EMIT their dim to the owning pane
 // (price/time/crosshair); an incoming sync ADOPTS view/price/crosshair
 // without re-emitting (no echo). Adoption only fires on a new syncSeq.
 const adopting=useRef(false);
 const emit=useCallback(patch=>{if(onSync&&!adopting.current)onSync(patch);},[onSync]);
 useEffect(()=>{if(!syncSeq)return;adopting.current=true;
  if(syncView&&typeof syncView==='object')setView(syncView);
  if(syncPrice&&typeof syncPrice==='object')setManualPrice(syncPrice);
  if(syncCrosshair!=null)setHover(syncCrosshair);
  adopting.current=false;},[syncSeq]); // eslint-disable-line react-hooks/exhaustive-deps
 const fitLevels=useMemo(()=>fitData?fitData.flatMap(frame=>savedLevels(frame,metrics,allNodes)):[],[fitData,metrics,allNodes]);
  const [volumeLocal,setVolumeLocal]=useState(true);
  const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState(''),[vwapOn,setVwapOn]=useState(true),[bandsOn,setBandsOn]=useState(false),[profileOn,setProfileOn]=useState(true),[envelopeOn,setEnvelopeOn]=useState(false),[cvdOn,setCvdOn]=useState(true);
  // Visual-reset: the overlay toggles can be externally controlled (one state
  // shared with the Indicators panel); standalone use keeps the internal state.
  const OVL = overlays;
  const effVwap = OVL ? !!OVL.vwap : vwapOn;
  const effVolume = OVL ? OVL.volume !== undefined ? !!OVL.volume : true : true;
  const effBands = OVL ? !!OVL.bands : bandsOn;
  const effProfile = OVL ? !!OVL.profile : profileOn;
  const effCvd = OVL ? !!OVL.cvd : cvdOn;
  const setOvl = (key, value) => { if (OVL && onOverlaysChange) onOverlaysChange({ ...OVL, [key]: value }); };
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
 const range=manualPrice||priceRange(fitData&&fitData.length?fitData:visible,fitData&&fitData.length?fitLevels:allLevels),selected=visible[hover??Math.max(0,visible.length-1)];
 const selectedLevels=savedLevels(selected,metrics,allNodes);
 const availableMetrics=useMemo(()=>Object.keys(NODE_LABELS).filter(metric=>metricCoverage?.[metric]?.checked_candles>0||data.some(frame=>savedLevels(frame,[metric],true).length)),[data,metricCoverage]);
 const left=12,right=Math.max(left+1,size.width-76),top=16,bottom=Math.max(top+1,size.height-38),plotWidth=right-left,plotHeight=bottom-top;
 const spacing=plotWidth/Math.max(1,visible.length),y=value=>bottom-(value-range.low)/(range.high-range.low)*plotHeight;
 const notify=()=>onInteract?.();
 const point=event=>{const r=surface.current.getBoundingClientRect();return {x:(event.clientX-r.left)*size.width/r.width,y:(event.clientY-r.top)*size.height/r.height};};
 const current=useRef(null);current.current={view:windowView,range,total:data.length,left,right,top,bottom,plotWidth,plotHeight,size};
 const zoom=(axis,factor,anchor=0.5)=>{notify();setHover(null);if(axis==='price'){const next=zoomPrice(range,factor,anchor);setManualPrice(next);emit({price:next});}else{const next=zoomTime(windowView,factor,anchor,data.length);setView(next);emit({time:next});}};
 useEffect(()=>{
  const element=surface.current;if(!element)return undefined;
  const wheel=event=>{const state=current.current;if(!state?.total||!(event.ctrlKey||event.metaKey||event.shiftKey))return;event.preventDefault();onInteract?.();setHover(null);
   const rect=element.getBoundingClientRect(),x=(event.clientX-rect.left)*state.size.width/rect.width,yy=(event.clientY-rect.top)*state.size.height/rect.height;
   if(event.shiftKey||x>=state.right){const next=zoomPrice(state.range,Math.exp(bound(event.deltaY,-120,120)*0.003),bound(1-(yy-state.top)/state.plotHeight,0,1));setManualPrice(next);emit({price:next});}
   else{const next=zoomTime(state.view,Math.exp(bound(event.deltaY,-120,120)*0.003),bound((x-state.left)/state.plotWidth,0,1),state.total);setView(next);emit({time:next});}
  };element.addEventListener('wheel',wheel,{passive:false});return()=>element.removeEventListener('wheel',wheel);
 },[onInteract,Boolean(data.length),emit]); // emit in deps: the listener must not keep a stale sync callback
 const begin=event=>{
  if(!data.length)return;notify();setHover(null);const p=point(event);pointers.current.set(event.pointerId,p);event.currentTarget.setPointerCapture?.(event.pointerId);
  if(pointers.current.size===2){const touch=[...pointers.current.values()];gesture.current={mode:'pinch',touch,view:windowView,range};}
  else if(pointers.current.size===1)gesture.current={mode:p.x>=right?'price':p.y>=bottom?'time':'pan',point:p,view:windowView,range,manual:Boolean(manualPrice),
   // Anchor = where the user grabbed, as a fraction of the plot, so the
   // point under the cursor stays under the cursor while the axis stretches.
   anchor:p.x>=right?bound(1-(p.y-top)/plotHeight,0,1):p.y>=bottom?bound((p.x-left)/plotWidth,0,1):0};
 };
 const move=event=>{
  const p=point(event);if(!pointers.current.has(event.pointerId)){
   if(p.x>=left&&p.x<right&&p.y>=top&&p.y<bottom){const next=bound(Math.floor((p.x-left)/spacing),0,Math.max(0,visible.length-1));if(next!==hover){setHover(next);emit({crosshair:next});}}else if(hover!=null){setHover(null);emit({crosshair:null});}return;
  }
  pointers.current.set(event.pointerId,p);const base=gesture.current;if(!base)return;
  if(base.mode==='pinch'&&pointers.current.size>=2){const touch=[...pointers.current.values()].slice(0,2),factors=pinchFactors(base.touch,touch);
   const cx=(base.touch[0].x+base.touch[1].x)/2,cy=(base.touch[0].y+base.touch[1].y)/2;
   if(factors.x!==1)setView(zoomTime(base.view,factors.x,bound((cx-left)/plotWidth,0,1),data.length));if(factors.y!==1)setManualPrice(zoomPrice(base.range,factors.y,bound(1-(cy-top)/plotHeight,0,1)));return;
  }
  const dx=p.x-base.point.x,dy=p.y-base.point.y;
  if(base.mode==='price')setManualPrice(zoomPrice(base.range,Math.exp(bound(dy,-500,500)/180),base.anchor??.5));
  else if(base.mode==='time')setView(zoomTime(base.view,Math.exp(bound(dx,-500,500)/240),base.anchor??.5,data.length));
  else {setView(clampWindow({start:base.view.start-dx/plotWidth*base.view.count,count:base.view.count},data.length));if(base.manual){const offset=dy/plotHeight*(base.range.high-base.range.low);setManualPrice({low:base.range.low+offset,high:base.range.high+offset});}}
 };
 const end=event=>{pointers.current.delete(event.pointerId);event.currentTarget.releasePointerCapture?.(event.pointerId);if(pointers.current.size===1){gesture.current={mode:'pan',point:[...pointers.current.values()][0],view:current.current.view,range:current.current.range,manual:Boolean(manualPrice)};}else gesture.current=null;};
 const downloadChart=async()=>{
  const svg=surface.current?.querySelector('svg');if(!svg||!data.length||exporting)return;
  const background=window.getComputedStyle(surface.current).backgroundColor;
  setExporting(true);setExportError('');let sourceUrl;
  try{
   // Copy the displayed drawing and its resolved styles, so saved colors and
   // text do not depend on the app stylesheet when the image opens elsewhere.
   const copy=svg.cloneNode(true),originals=[svg,...svg.querySelectorAll('*')],copies=[copy,...copy.querySelectorAll('*')];
   const properties=['color','fill','fill-opacity','stroke','stroke-opacity','stroke-width','stroke-dasharray','stroke-linecap','stroke-linejoin','opacity','font-family','font-size','font-weight','text-anchor'];
   originals.forEach((element,index)=>{const styles=window.getComputedStyle(element);properties.forEach(property=>{const value=styles.getPropertyValue(property);if(value)copies[index].style.setProperty(property,value);});});
   copy.setAttribute('xmlns','http://www.w3.org/2000/svg');copy.setAttribute('width',String(size.width));copy.setAttribute('height',String(size.height));copy.style.position='static';copy.style.width=size.width+'px';copy.style.height=size.height+'px';
   const canvas=document.createElement('canvas'),header=42,scale=2;canvas.width=Math.round(size.width*scale);canvas.height=Math.round((size.height+header)*scale);
   const context=canvas.getContext('2d');if(!context)throw new Error('Image drawing is unavailable');
   sourceUrl=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}));
   const drawing=new Image();await new Promise((resolve,reject)=>{drawing.onload=resolve;drawing.onerror=()=>reject(new Error('Chart image could not be read'));drawing.src=sourceUrl;});
   context.scale(scale,scale);context.fillStyle=background&&background!=='transparent'&&background!=='rgba(0, 0, 0, 0)'?background:'#111111';context.fillRect(0,0,size.width,size.height+header);context.fillStyle='#dce5ee';context.font='14px Consolas, monospace';
   context.fillText(ticker+' | '+chartTime(visible[0]?.time,true)+' - '+chartTime(visible.at(-1)?.time,true)+' New York',12,25);context.drawImage(drawing,0,header,size.width,size.height);
   const png=await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Chart image could not be saved')),'image/png'));
   const downloadUrl=URL.createObjectURL(png),link=document.createElement('a');link.href=downloadUrl;link.download=(String(ticker).replace(/[^a-zA-Z0-9._-]/g,'_')||'stock')+'-price-chart.png';
   document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(downloadUrl),1000);
  }catch{setExportError('Chart image could not be saved. Try again.');}
  finally{if(sourceUrl)URL.revokeObjectURL(sourceUrl);setExporting(false);}
 };
  // B08 actual study instances (C045-C048): gap-segmented overlay lines from
  // registry-computed specs — the same byTime/gap pattern as the exposure
  // path. Missing or warmup values break the segment; nothing is fabricated.
  const studyPolys=()=>{
    if(!Array.isArray(studyLines)||!studyLines.length)return null;
    return studyLines.map(spec=>{
      if(!spec||!Array.isArray(spec.points))return null;
      if(spec.pane)return null; // the momentum panes render in their OWN scales
      const byTime=new Map(spec.points.filter(p=>p&&typeof p.time==='string').map(p=>[p.time,p.value]));
      const segs=[];let cur=[];
      visible.forEach((frame,index)=>{
        const value=byTime.get(frame.time);
        if(typeof value!=='number'||!Number.isFinite(value)){if(cur.length>1)segs.push(cur);cur=[];return;}
        const py=y(value);if(py<top||py>bottom)return;
        cur.push({x:left+(index+0.5)*spacing,y:py});
      });
      if(cur.length>1)segs.push(cur);
      if(!segs.length)return null;
      return <g key={spec.id} data-instance={spec.instanceId}>
        {segs.map((seg,si)=><polyline key={si} data-testid={'study-line-'+spec.id} data-band={spec.band||''} points={seg.map(p=>p.x+','+p.y).join(' ')} fill="none" stroke={spec.color} strokeWidth={spec.band?1.2:1.6}><title>{spec.label}</title></polyline>)}
      </g>;
    });
  };
  // B09 mapped levels (contract v2): DISTINCT derived shapes — diamond ◆ /
  // triangle ▲ markers at the mapped price with a dotted level line; the
  // label + source price ride the title. Out-of-range prices render nothing.
  const mappedShapesRender=()=>{
    if(!Array.isArray(mappedShapes)||!mappedShapes.length)return null;
    return mappedShapes.filter(s=>s&&Number.isFinite(s?.price)&&s.price>=range.low&&s.price<=range.high).map((s,si)=>{
      const yy=y(s.price);
      const mx=right-14;
      const diamond=s.kind==='diamond';
      const color=diamond?'#e8bd65':'#8fd3e8';
      const d=diamond?`M ${mx} ${yy-6} L ${mx+6} ${yy} L ${mx} ${yy+6} L ${mx-6} ${yy} Z`:`M ${mx-6} ${yy+5} L ${mx+6} ${yy+5} L ${mx} ${yy-5} Z`;
      return <g key={'mapped:'+si} data-testid="mapped-level-shape" data-kind={s.kind}>
        <line x1={left} x2={right} y1={yy} y2={yy} stroke={color} strokeWidth="1" strokeDasharray="3 4" opacity="0.8" />
        <path d={d} fill={color} opacity="0.9" />
        <title>{s.label + (Number.isFinite(s.sourcePrice) ? ` · source ${s.sourcePrice}` : '')}</title>
      </g>;
    });
  };
  const exposurePolys=()=>{
    if(!showAtlas||!Array.isArray(exposureLine)||!exposureLine.length)return null;
   const byTime=new Map(exposureLine.filter(p=>p&&typeof p.time==='string').map(p=>[p.time,p]));
   const segments=(key)=>{
    const segs=[];let cur=[];
    visible.forEach((frame,index)=>{
     const entry=byTime.get(frame.time),value=entry?entry[key]:undefined;
     if(typeof value!=='number'||!Number.isFinite(value)){if(cur.length>1)segs.push(cur);cur=[];return;}
     const py=y(value);if(py<top||py>bottom)return;
     cur.push({x:left+(index+0.5)*spacing,y:py});
    });
    if(cur.length>1)segs.push(cur);return segs;
   };
   const centre=segments('centre'),upper=segments('upper'),lower=segments('lower');
   return (<g>
    {centre.map((seg,si)=><polyline data-testid="exposure-vwap-line" key={'gexvwap:'+si} points={seg.map(p=>p.x+','+p.y).join(' ')} fill="none" stroke="#72d7df" strokeWidth="2"><title>GEX VWAP centre</title></polyline>)}
    {upper.map((seg,si)=><polyline data-testid="exposure-band" key={'gexup:'+si} points={seg.map(p=>p.x+','+p.y).join(' ')} fill="none" stroke="#72d7df" strokeWidth="1" strokeDasharray="4 3" opacity="0.8"><title>GEX VWAP upper</title></polyline>)}
    {lower.map((seg,si)=><polyline data-testid="exposure-band" key={'gexlow:'+si} points={seg.map(p=>p.x+','+p.y).join(' ')} fill="none" stroke="#72d7df" strokeWidth="1" strokeDasharray="4 3" opacity="0.8"><title>GEX VWAP lower</title></polyline>)}
   </g>);
  };
  const envelopeLevels=()=>{
   if(!showAtlas||!envelopeOn||!Array.isArray(exposureLine)||!exposureLine.length)return [];
   const byTime=new Map();
   exposureLine.forEach(p=>{if(p&&typeof p.time==='string')byTime.set(p.time,p.centre);});
   const centres=visible.map(frame=>byTime.get(frame.time));
   if(!centres.some(v=>typeof v==='number'&&Number.isFinite(v)))return [];
   const sess=sessionEnvelope(centres.map(centre=>({centre})));
   const first=visible.length?new Date(visible[0].time):null;
   const anchor=first&&Number.isFinite(first.valueOf())?first.toLocaleDateString('en-CA',{timeZone:'America/New_York'}):null;
   const opening=anchor?openingEnvelope(visible.map(frame=>({time:frame.time,centre:byTime.get(frame.time)})),{anchorDate:anchor,windowMinutes:15}):{status:'unavailable'};
   const levels=[sess.high,sess.low];
   if(opening.status==='frozen'){levels.push(opening.high,opening.low);}
   return levels.filter(v=>typeof v==='number'&&Number.isFinite(v)&&v>=range.low&&v<=range.high);
  };
  const shift=amount=>{notify();setHover(null);setView(clampWindow({...windowView,start:windowView.start+amount},data.length));};
 const keyboard=event=>{const actions={ArrowLeft:()=>shift(-1),ArrowRight:()=>shift(1),PageUp:()=>shift(-Math.max(1,Math.floor(windowView.count/2))),PageDown:()=>shift(Math.max(1,Math.floor(windowView.count/2))),Home:()=>shift(-data.length),End:()=>shift(data.length),'+':()=>zoom('time',0.75),'-':()=>zoom('time',1.35)};if(actions[event.key]){event.preventDefault();event.stopPropagation();actions[event.key]();}};
 return <div className="recorded-price-chart" data-testid="recorded-price-chart" data-candles={data.length} data-visible-candles={visible.length} data-window-start={windowView.start} data-price-low={range.low} data-price-high={range.high} onKeyDown={event=>{if(event.key==='Escape'&&event.target.closest('details[open]')){event.preventDefault();event.stopPropagation();closeDetails(event.target);}}}>
  {/* 2026-10-18 visible refresh: ONE compact primary toolbar — symbol,
      interval + history summary, live price/time readout, scale, Tools and
      actions all in a single banded row. The readout keeps its testid,
      data-details popover and aria-live semantics; it simply stops being a
      separate stacked row. */}
  <div className="recorded-chart-tools" data-testid="chart-control-row">
   {toolbarControls}
   <div className="recorded-chart-scale"><button type="button" aria-label="Zoom in time" disabled={!data.length} onClick={()=>zoom('time',0.75)}>+</button><button type="button" aria-label="Zoom out time" disabled={!data.length} onClick={()=>zoom('time',1.35)}>-</button><button type="button" aria-label="Auto scale" aria-pressed={!manualPrice} disabled={!data.length} title={manualPrice?"Price scale locked; click to fit visible prices":"Fits visible prices; click to lock"} onClick={()=>setManualPrice(held=>held?null:range)}>Auto scale {manualPrice?'locked':'on'}</button></div>
   {replayControls&&<span className="recorded-chart-replay-inline" data-testid="chart-replay-row">{replayControls}</span>}
   <details className="recorded-chart-popover"><summary role="button" aria-label="Chart tools">Tools</summary><div className="recorded-chart-popover-content">
    {historyPeriodControls&&<div className="recorded-chart-period" data-testid="history-period-controls">{historyPeriodControls}</div>}
    <div className="recorded-chart-history"><button type="button" aria-label="Earlier candles" disabled={!windowView.start} onClick={()=>shift(-Math.max(1,Math.floor(windowView.count/2)))}>Earlier</button><button type="button" aria-label="Later candles" disabled={windowView.start+windowView.count>=data.length} onClick={()=>shift(Math.max(1,Math.floor(windowView.count/2)))}>Later</button><button type="button" disabled={!data.length} onClick={()=>{notify();setView({start:0,count:data.length});setManualPrice(null);}}>Fit history</button></div>
    <fieldset className="recorded-chart-layers" aria-label="Saved node lines"><legend>Saved lines</legend>{Object.entries(NODE_LABELS).map(([metric,label])=><label key={metric} style={{'--node-color':NODE_COLORS[metric]}}><input type="checkbox" checked={metrics.includes(metric)} disabled={!availableMetrics.includes(metric)} onChange={e=>{setMetrics(old=>e.target.checked?[...old,metric]:old.filter(value=>value!==metric));setManualPrice(null);}}/>{label}{!availableMetrics.includes(metric)&&<span> unavailable</span>}</label>)}<label><input type="checkbox" checked={allNodes} onChange={e=>{setAllNodes(e.target.checked);setManualPrice(null);}}/>All saved levels</label></fieldset>
    <fieldset className="recorded-chart-layers recorded-chart-overlays" aria-label="Chart overlays"><legend>Overlays</legend>
     {paneCfg&&onPaneCfg&&<span className="pane-study-settings" data-testid="profile-settings" role="group" aria-label="Volume profile and TPO settings">
      <label>Profile mode<select data-testid="profile-mode" value={paneCfg.profile?.mode??'visible'} onChange={e=>onPaneCfg({profile:{...(paneCfg.profile||{}),mode:e.target.value}})}><option value="visible">visible window</option><option value="fixed-200">fixed 200</option></select></label>
      <label>Levels<input data-testid="profile-levels" aria-label="Profile levels" type="number" min="8" max="200" value={paneCfg.profile?.levels??''} onChange={e=>{const n=Math.round(Number(e.target.value));onPaneCfg({profile:{...(paneCfg.profile||{}),levels:Number.isInteger(n)&&n>=8&&n<=200?n:null}});}}/></label>
      <label>VA%<input data-testid="profile-va-pct" aria-label="Value area pct" type="number" min="0.5" max="0.9" step="0.01" value={paneCfg.profile?.vaPct??0.68} onChange={e=>{const n=Number(e.target.value);onPaneCfg({profile:{...(paneCfg.profile||{}),vaPct:n>=0.5&&n<=0.9?n:(paneCfg.profile?.vaPct??0.68)}});}}/></label>
      <label>TPO m<input data-testid="tpo-minutes" aria-label="TPO period minutes" type="number" min="1" max="480" value={paneCfg.tpo?.periodMinutes??30} onChange={e=>{const n=Math.round(Number(e.target.value));onPaneCfg({tpo:{...(paneCfg.tpo||{}),periodMinutes:Number.isInteger(n)&&n>=1&&n<=480?n:30}});}}/></label>
      <label>TPO mode<select data-testid="tpo-mode" value={paneCfg.tpo?.mode??'bar-resolution'} onChange={e=>onPaneCfg({tpo:{...(paneCfg.tpo||{}),mode:e.target.value}})}><option value="bar-resolution">bar-resolution</option><option value="tick-true">tick-true</option></select></label>
     </span>}
     <label><input type="checkbox" aria-label="Toggle volume pane" checked={effVolume} onChange={e=>OVL?setOvl('volume',e.target.checked):setVolumeLocal(v=>!v)}/>{'Volume pane'}</label>
     <label><input type="checkbox" aria-label="Toggle VWAP" checked={effVwap} disabled={!data.some(frame=>Number.isFinite(frame.volume))} onChange={e=>OVL?setOvl('vwap',e.target.checked):setVwapOn(e.target.checked)}/>VWAP{!data.some(frame=>Number.isFinite(frame.volume))&&<span> unavailable</span>}</label>
     <label><input type="checkbox" aria-label="Toggle profile" checked={effProfile||volumeInstanceActive} disabled={!data.some(frame=>Number.isFinite(frame.volume))} onChange={e=>OVL?setOvl('profile',e.target.checked):setProfileOn(e.target.checked)}/>Profile{!data.some(frame=>Number.isFinite(frame.volume))&&<span> unavailable</span>}{volumeInstanceActive&&!effProfile&&<span> · on (volume instance)</span>}</label>
     <label><input type="checkbox" aria-label="Toggle VWAP bands" checked={effBands} disabled={!data.some(frame=>Number.isFinite(frame.volume))} onChange={e=>OVL?setOvl('bands',e.target.checked):setBandsOn(e.target.checked)}/>Bands{!data.some(frame=>Number.isFinite(frame.volume))&&<span> unavailable</span>}</label>
      <label><input type="checkbox" aria-label="Toggle exposure envelope" checked={envelopeOn} disabled={!Array.isArray(exposureLine)||!exposureLine.some(p=>typeof p?.centre==='number'&&Number.isFinite(p.centre))} onChange={e=>setEnvelopeOn(e.target.checked)}/>Envelope{(!Array.isArray(exposureLine)||!exposureLine.some(p=>typeof p?.centre==='number'&&Number.isFinite(p.centre)))&&<span> unavailable</span>}</label>
      <label><input type="checkbox" aria-label="Toggle CVD" checked={effCvd} disabled={!Array.isArray(cvdLine)||!cvdLine.some(p=>typeof p?.cvd==='number'&&Number.isFinite(p.cvd))} onChange={e=>OVL?setOvl('cvd',e.target.checked):setCvdOn(e.target.checked)}/>CVD{(!Array.isArray(cvdLine)||!cvdLine.some(p=>typeof p?.cvd==='number'&&Number.isFinite(p.cvd)))&&<span> unavailable</span>}</label>
    </fieldset>
     <button type="button" disabled={!data.length||exporting} onClick={downloadChart}>{exporting?'Saving image...':'Download chart image'}</button>{exportError&&<p role="alert">{exportError}</p>}
    {historyControls}<button type="button" onClick={event=>closeDetails(event.currentTarget)}>Close chart tools</button><small id={'chart-help-'+id}>Drag to scroll history. Pinch time and price. Drag an axis to stretch it. Ctrl + scroll zooms time; Shift + scroll zooms price. Normal scrolling moves the page.</small>
   </div></details>
   <div className="recorded-chart-actions">{toolbarActions}</div>
  </div>
  {!!data.length?<div ref={surface} className="recorded-chart-surface" role="region" aria-label={ticker+' candle chart'} aria-describedby={'chart-help-'+id} tabIndex={0} onKeyDown={keyboard} onPointerDown={begin} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onPointerLeave={()=>{if(!pointers.current.size)setHover(null);}}>
  {/* the OHLC readout rides the CANVAS top-left as an overlay — off the command row so the row stays ONE compact line. */}
        <div className="recorded-chart-readout-overlay" aria-live="off" data-testid="chart-reading-row"><strong>{selected?chartTime(selected.time,true):'Waiting for a candle'} <span>New York</span></strong>{selected&&<span>Open <b>{price(selected.open)}</b> High <b>{price(selected.high)}</b> Low <b>{price(selected.low)}</b> Close <b>{price(selected.close)}</b></span>}<details className="recorded-chart-popover recorded-chart-data"><summary role="button" aria-label="Chart data details">{readingStatus}</summary><div className="recorded-chart-popover-content">{dataDetails||<p>Prices and lines use their own stored times. Missing readings remain unavailable.</p>}<button type="button" onClick={event=>closeDetails(event.currentTarget)}>Close data details</button></div></details></div>
   <svg viewBox={'0 0 '+size.width+' '+size.height} aria-label={ticker+' recorded price candles'} role="img">
    <defs><clipPath id={'chart-clip-'+id}><rect x={left} y={top} width={plotWidth} height={plotHeight}/></clipPath></defs>
    {Array.from({length:6},(_,i)=>{const level=range.high-(range.high-range.low)*i/5,yy=y(level);return <g key={i}><line x1={left} x2={right} y1={yy} y2={yy} stroke="#27313c" strokeWidth="1"/><text x={right+10} y={yy+4} className="recorded-price-label">{price(level)}</text></g>;})}
    <g clipPath={'url(#chart-clip-'+id+')'}>
     {visible.map((frame,index)=>{const center=left+(index+0.5)*spacing,up=frame.close>=frame.open,width=Math.max(1,Math.min(14,spacing*0.65)),bodyTop=y(Math.max(frame.open,frame.close)),bodyHeight=Math.max(1,Math.abs(y(frame.open)-y(frame.close)));return <g key={frame.time} className={up?'recorded-candle-up':'recorded-candle-down'} data-testid="price-candle"><title>{chartTime(frame.time,true)+' New York. Open '+price(frame.open)+', high '+price(frame.high)+', low '+price(frame.low)+', close '+price(frame.close)}</title><line x1={center} x2={center} y1={y(frame.high)} y2={y(frame.low)} stroke="currentColor" strokeWidth="1.5"/><rect x={center-width/2} y={bodyTop} width={width} height={bodyHeight} fill="currentColor"/></g>;})}
     {visible.flatMap((frame,index)=>savedLevels(frame,metrics,allNodes).map((node,n)=>{const seconds=typeof frame.duration_seconds==='number'&&frame.duration_seconds>0?frame.duration_seconds:60,fraction=Math.min(seconds,Math.max(0,900-(node.age_seconds??frame.node_age_seconds)))/seconds;
      const xx=left+index*spacing,yy=y(node.level);return <line data-testid="saved-node-line" key={frame.time+':'+node.metric+':'+node.id+':'+n} x1={xx} x2={xx+spacing*fraction} y1={yy} y2={yy} stroke={NODE_COLORS[node.metric]} strokeWidth="2" opacity="0.88"><title>{NODE_LABELS[node.metric]+' saved level '+price(node.level)+'. Known '+chartTime(Object.hasOwn(node,'known_at')?node.known_at:frame.nodes_known_at,true)+' New York. '+(node.label||'Recorded level')}</title></line>;}))}
      {showAtlas&&visible.flatMap((frame,index)=>{
       // Orbs share saved lines' available-at and freshness gates. Legacy
       // levels without measured exposure remain markers, never ranked kings.
       const nodes=savedLevels(frame,metrics,true).filter(n=>n.status!=='unavailable');
       if(!nodes.length)return [];
       const weights=nodes.map(n=>Number.isFinite(n.signed_value)?Math.abs(n.signed_value):null);
       const kings={};
       nodes.forEach((node,ni)=>{if(weights[ni]!==null)kings[node.metric]=Math.max(kings[node.metric]||0,weights[ni]);});
       const center=left+(index+0.5)*spacing;
       return nodes.flatMap((node,ni)=>{const yy=y(node.level);
        // A strike outside the visible price range is never drawn clamped
        // to the plot edge — that would fabricate a price. Drop it and mark
        // the candle as having out-of-range nodes instead.
        if(yy<top||yy>bottom)return <title key={frame.time+':orb:'+ni+':oor'} data-testid="orb-out-of-range">Orb {price(node.level)} out of visible price range</title>;
        const king=kings[node.metric],ratio=king>0&&weights[ni]!==null?weights[ni]/king:0,r=Math.min(12,Math.max(3,4*Math.sqrt(ratio))),isKing=king>0&&weights[ni]===king;
        return <circle data-testid="chart-orb" key={frame.time+':orb:'+ni} cx={center} cy={yy} r={r} fill={isKing?'#e8bd65':'none'} stroke={NODE_COLORS[node.metric]} strokeWidth={isKing?2:1} opacity="0.75"><title>{'Orb '+price(node.level)+(isKing?' (King Node · '+NODE_LABELS[node.metric]+' · observed saved subset)':weights[ni]===null?' (exposure unavailable)':'')}</title></circle>;});})}
      {exposurePolys()}
      {studyPolys()}
      {mappedShapesRender()}
      {envelopeLevels().map((lv,li)=><line data-testid="exposure-envelope" key={'envelope:'+li} x1={left} x2={right} y1={y(lv)} y2={y(lv)} stroke="#72d7df" strokeWidth="1" strokeDasharray="2 3" opacity="0.7"><title>Exposure envelope level</title></line>)}
      {showAtlas&&Array.isArray(darkLevels)&&darkLevels.filter(l=>l&&typeof l.price==='number'&&Number.isFinite(l.price)&&l.price>=range.low&&l.price<=range.high).map((l,li)=><line data-testid="dark-pool-level" key={'dark:'+li} x1={left} x2={right} y1={y(l.price)} y2={y(l.price)} stroke="#c9a86a" strokeWidth="1.5" strokeDasharray="6 3"><title>{'Dark pool level '+price(l.price)+(l.venue?' '+l.venue:'')}</title></line>)}
      {Array.isArray(alertLines)&&alertLines.filter(a=>a&&typeof a.price==='number'&&Number.isFinite(a.price)&&a.price>=range.low&&a.price<=range.high).map((a,ai)=><line data-testid="alert-line" data-state={a.state==='stale'?'stale':'armed'} key={'alert:'+(a.id||ai)} x1={left} x2={right} y1={y(a.price)} y2={y(a.price)} stroke={a.state==='stale'?'#6b7684':'#e06c75'} strokeWidth="1.5" strokeDasharray={a.state==='stale'?'2 3':'none'}><title>{'Alert '+(a.id||ai)+' at '+price(a.price)+(a.state==='stale'?' — stale alert refused':'')}</title></line>)}
      {showAtlas&&effVwap&&data.some(frame=>Number.isFinite(frame.volume))&&(()=>{
       const all=sessionVwapValues(data),win=all.slice(windowView.start,windowView.start+windowView.count);
       const pts=win.map((v,i)=>{if(typeof v!=='number'||!Number.isFinite(v))return null;const py=y(v);if(py<top||py>bottom)return null;return {x:left+(i+0.5)*spacing,y:py};});
       const drawn=pts.filter(Boolean);if(drawn.length<2)return null;
       return <polyline data-testid="vwap-line" points={drawn.map(p=>p.x+','+p.y).join(' ')} fill="none" stroke="#e08e45" strokeWidth="2"><title>Session VWAP</title></polyline>;})()}
      {showAtlas&&effBands&&effVwap&&data.some(frame=>Number.isFinite(frame.volume))&&(()=>{
       const all=sessionVwapBands(data),maxM=3;
       return Array.from({length:maxM},(_,m)=>{const pts=[];
        for(let k=0;k<windowView.count;k+=1){const set=all[windowView.start+k];const band=set?.[m];
         if(!band||typeof band.upper!=='number'||!Number.isFinite(band.upper)||typeof band.lower!=='number'||!Number.isFinite(band.lower))continue;
         const uy=y(band.upper),ly=y(band.lower);if(uy<top||uy>bottom||ly<top||ly>bottom)continue;
         pts.push({x:left+(k+0.5)*spacing,uy,ly});}
        if(pts.length<2)return null;
        return <g key={'vwapband:'+m}><polyline data-testid="vwap-band" points={pts.map(p=>p.x+','+p.uy).join(' ')} fill="none" stroke="#e08e45" strokeWidth="1" strokeDasharray="4 3" opacity="0.8"/><polyline data-testid="vwap-band" points={pts.map(p=>p.x+','+p.ly).join(' ')} fill="none" stroke="#e08e45" strokeWidth="1" strokeDasharray="4 3" opacity="0.8"/></g>;});})()}
      {showAtlas&&(effProfile||volumeInstanceActive)&&data.some(frame=>Number.isFinite(frame.volume))&&(()=>{
       // C121: with a configuration the profile IS the configured study —
       // fixed-200/visible mode, levels 8..200, VA% 0.5..0.9, POC/VAH/VAL facts.
       const cfgP=paneCfg?.profile;
       let prof;
       if(cfgP){
         const attempted=profileConfig(visible,{mode:cfgP.mode??'visible',levels:Number.isInteger(cfgP.levels)&&cfgP.levels>=8?cfgP.levels:undefined,vaPct:typeof cfgP.vaPct==='number'?cfgP.vaPct:0.68,basis:'total'});
         if(attempted.status!=='ok')return <g data-testid="profile-study-refused"><text x={left} y={top+12} fill="#d65656" fontSize="11">{attempted.reason}</text></g>;
         prof={rows:attempted.rows,poc:attempted.poc,value_area:attempted.valueArea,status:'ok',approximation:attempted.approximation,facts:attempted.facts};
       } else {
         prof=volumeProfile(visible,{rows:Math.min(48,Math.max(8,visible.length))});
       }
       if(prof.status!=='ok')return null;
       const peak=Math.max(...prof.rows.map(r=>r.volume),1),bw=64,bx=Math.max(left,right-bw-4);
       const va=prof.value_area;
       return <g data-testid="volume-profile"><title>Volume profile (bar-range approximation)</title>{prof.rows.map((r,ri)=>{const isPoc=r.price===prof.poc.price&&r.volume===prof.poc.volume;
        const inVa=va&&r.price>=va.low&&r.price<=va.high;
        return <rect key={'vp:'+ri} data-testid={isPoc?'profile-poc':(inVa?'profile-va-row':'profile-row')} x={bx+(bw-Math.max(1,(r.volume/peak)*bw))} y={y(r.price)-2} width={Math.max(1,(r.volume/peak)*bw)} height={4} fill={isPoc?'#e8bd65':(inVa?'#72a3c9':'#5a6b7d')} opacity={isPoc?0.95:0.6}><title>{'Volume '+price(r.price)+': '+Math.round(r.volume).toLocaleString('en-US')+' shares'+(inVa&&!isPoc?' · value area':'')}</title></rect>;})}
       {prof.facts&&<g data-testid="profile-facts">
        <text x={bx} y={y(prof.facts.poc.price)-6} fill="#e8bd65" fontSize="10" data-testid="profile-fact-poc">POC {price(prof.facts.poc.price)}</text>
        <text x={bx} y={y(prof.facts.vah)-16} fill="#72a3c9" fontSize="10" data-testid="profile-fact-vah">VAH {price(prof.facts.vah)}</text>
        <text x={bx} y={y(prof.facts.val)+8} fill="#72a3c9" fontSize="10" data-testid="profile-fact-val">VAL {price(prof.facts.val)}</text>
       </g>}</g>;})()}
      {showAtlas&&paneCfg&&(()=>{ // C124-126: bar-resolution TPO — REAL plotted period boxes + typed refusals
       const cfgT=paneCfg.tpo;
       const epochBars=visible.map(f=>{const ms=Date.parse(f.time);return Number.isFinite(ms)?{...f,time:ms}:null;}).filter(Boolean);
       const tpo=tpoConfig(epochBars,{mode:cfgT?.mode??'bar-resolution',periodMinutes:cfgT?.periodMinutes??30});
       if(tpo.status!=='ok')return <g data-testid="tpo-refused"><text x={left} y={top+26} fill="#d65656" fontSize="11" data-testid="tpo-refusal-text">{tpo.reason}</text></g>;
       const colW=Math.max(3,10), tbx=Math.max(left,right-140);
       return <g data-testid="tpo-context"><title>{'Bar-resolution TPO approximation · '+tpo.note}</title>
        {tpo.periods.map((p,pi)=>{const py0=y(p.high),py1=y(p.low);
         if(!Number.isFinite(py0)||!Number.isFinite(py1))return null;
         return <rect key={'tpo:'+pi} data-testid="tpo-period-box" x={tbx+colW*pi+2} y={Math.min(py0,py1)} width={colW-2} height={Math.max(2,Math.abs(py1-py0))} fill="#7d6ac0" opacity="0.5"><title>{'Period '+p.period+' '+price(p.high)+'/'+price(p.low)+' · '+tpo.approximation}</title></rect>;})}
        {tpo.sessionFacts&&<text x={tbx} y={top+38} fill="#7d6ac0" fontSize="10" data-testid="tpo-session-facts">{'TPO '+(cfgT?.periodMinutes??30)+'m · session '+price(tpo.sessionFacts.high)+'/'+price(tpo.sessionFacts.low)+' · '+(tpo.periods.length)+' periods · bar-resolution (tick-true needs the admitted tape)'}</text>}
       </g>;})()}
      {hover!==null&&selected&&<g data-export-layer="crosshair"><line x1={left+(hover+0.5)*spacing} x2={left+(hover+0.5)*spacing} y1={top} y2={bottom} stroke="#a8b3be" strokeDasharray="3 4"/><line x1={left} x2={right} y1={y(selected.close)} y2={y(selected.close)} stroke="#a8b3be" strokeDasharray="3 4"/></g>}
    </g>
    {renderDrawingLayer && renderDrawingLayer({
      width:plotWidth,height:plotHeight,left,top,svgWidth:size.width,svgHeight:size.height,clipId:id,
      pMin:range.low,pMax:range.high,frames:visible,
      tMin:Date.parse(visible[0].time),tMax:Date.parse(visible.at(-1).time),
      // The renderer spaces bars equally across overnight/weekend gaps.
      // Drawings use that same piecewise time-to-bar transform.
      xForTime:time=>{
        const times=visible.map(f=>Date.parse(f.time));
        if(times.length===1)return plotWidth/2;
        let i=times.findIndex(v=>v>=time);if(i<0)i=times.length-1;if(i===0)i=1;
        const fraction=(time-times[i-1])/(times[i]-times[i-1]);
        return (i-0.5+fraction)*spacing;
      },
      timeForX:x=>{
        const at=x/spacing-0.5,i=bound(Math.floor(at),0,Math.max(0,visible.length-2));
        const first=Date.parse(visible[i].time),last=Date.parse(visible[Math.min(i+1,visible.length-1)].time);
        return first+(at-i)*(last-first);
      }
    })}
    <line x1={right} x2={right} y1={top} y2={bottom} stroke="#3d4853"/>
    {(()=>{
     const budget=Math.min(visible.length,5,Math.max(1,Math.floor(plotWidth/112)));
     const indices=Array.from({length:budget},(_,i)=>budget===1?Math.floor((visible.length-1)/2):Math.round(i*(visible.length-1)/(budget-1)));
     return indices.map((index,i)=>{const frame=visible[index],single=indices.length===1;
      const x=single?(left+right)/2:i===0?left:i===indices.length-1?right:left+(index+0.5)*spacing;
      return <text key={index} x={x} y={bottom+24} textAnchor={single?'middle':i===0?'start':i===indices.length-1?'end':'middle'} className="recorded-time-label">{axisTime(frame.time)}<title>{chartTime(frame.time,true)} New York</title></text>;
     });
    })()}
   </svg>
   </div>:<div className="recorded-chart-empty">{emptyContent||<p>No valid price candles are available.</p>}</div>}
   {!!data.length&&showAtlas&&Array.isArray(flowBars)&&flowBars.length===data.length&&(()=>{
    const win=flowBars.slice(windowView.start,windowView.start+windowView.count);
    const peak=Math.max(1,...win.flatMap(b=>[Math.abs(b?.call||0),Math.abs(b?.put||0)]));
    return <div className="recorded-flow-pane" data-testid="flow-pane" aria-label="Options flow per candle">{win.map((b,bi)=><div key={bi} className="recorded-flow-bar"><div className="recorded-flow-call" style={{height:(Math.abs(b?.call||0)/peak*20)+'px'}}/><div className="recorded-flow-put" style={{height:(Math.abs(b?.put||0)/peak*20)+'px'}}/></div>)}</div>;})()}
   {!!data.length&&effVolume&&(()=>{ // Volume pane: real provider volume only — never fabricated. Gated by the
    // shared Volume-pane state (chart checkbox + the Indicators panel row drive ONE state).
    const win=visible,hasVol=win.some(frame=>Number.isFinite(frame.volume)),missing=win.filter(frame=>!Number.isFinite(frame.volume)).length;
    if(!hasVol)return <div className="recorded-chart-empty recorded-volume-empty"><small>Volume unavailable for these candles.</small></div>;
    const peak=Math.max(1,...win.map(frame=>Number(frame.volume)||0));
    const h=Math.max(24,Math.min(72,Math.round(plotHeight*0.15)));
    return <svg className="recorded-volume-pane" data-testid="volume-pane" role="img" aria-label="Traded volume per candle" viewBox={'0 0 '+size.width+' '+h} preserveAspectRatio="none" style={{width:'100%',height:h}}>
      {missing>0&&<text x={left} y="11" fill="#a8b3be" fontSize="10">Volume unavailable for {missing} of {win.length} visible candles</text>}
      {win.map((frame,index)=>{const v=frame.volume;if(!Number.isFinite(v))return null;const bh=v===0?0:Math.max(1,v/peak*(h-(missing?18:4)));
       return <rect data-testid="volume-bar" key={frame.time} x={left+index*spacing+Math.max(1,spacing*0.15)} y={h-bh} width={Math.max(1,Math.min(spacing*0.7,14))} height={bh} fill={frame.close>=frame.open?'#3f8f7d':'#8f4a52'} opacity="0.85"><title>{chartTime(frame.time,true)+' — '+(Number.isFinite(v)?v.toLocaleString('en-US'):'0')+' shares'}</title></rect>;})}
    </svg>;})()}
    {(()=>{ // Owner 13:40 slice 2 — the momentum panes over H2's frozen
      // producer specs. RSI: its OWN fixed 0..100 percent scale. MACD: line +
      // signal strokes and histogram bars around zero on ONE shared
      // zero-anchored scale. ATR: its own price scale. Warmup/refused nulls
      // BREAK lines — never bridged, never zero-filled; an all-null series
      // renders the honest refusal and nothing else.
      if(!Array.isArray(studyLines)||!data.length)return null;
      const specsOf=n=>studyLines.filter(sp=>sp&&sp.pane===n&&Array.isArray(sp.points));
      const finiteVals=sp=>sp.points.filter(p=>p&&typeof p.value==='number'&&Number.isFinite(p.value)).map(p=>p.value);
      const segsOf=(sp,scale)=>{const byTime=new Map(sp.points.map(p=>[p&&p.time,p&&p.value]));const segs=[];let cur=[];
        visible.forEach((frame,index)=>{const v=byTime.get(frame.time);
          if(typeof v!=='number'||!Number.isFinite(v)){if(cur.length>1)segs.push(cur);cur=[];return;}
          cur.push({x:left+(index+0.5)*spacing,y:scale(v)});});
        if(cur.length>1)segs.push(cur);return segs;};
      const panes=[];
      for(const name of ['rsi','macd','atr']){
        const specs=specsOf(name);if(!specs.length)continue;
        const all=specs.flatMap(finiteVals);
        const refused=!all.length; // every point null: the whole series refused
        const h=name==='macd'?72:56,pad=5;
        let lo,hi;
        if(name==='rsi'){lo=0;hi=100;} // the contract's fixed percent scale
        else if(refused){lo=0;hi=1;}
        else if(name==='macd'){const m=Math.max(...all.map(Math.abs),1e-9);lo=-m;hi=m;} // zero-anchored
        else {lo=Math.min(...all);hi=Math.max(...all);if(hi===lo){lo-=1;hi+=1;}}
        const span=(hi-lo)||1,scale=v=>h-pad-((v-lo)/span)*(h-pad*2),zero=scale(0);
        panes.push(<div className={'recorded-momentum-pane'+(refused?' recorded-pane-refused':'')} data-testid={'momentum-pane-'+name} role="img" key={'mp:'+name}
          aria-label={(name==='rsi'?'RSI':name==='macd'?'MACD':'ATR')+' study pane'}>
          <svg viewBox={'0 0 '+size.width+' '+h} preserveAspectRatio="none" style={{width:'100%',height:h}}>
            {refused?null:<>{name==='rsi'&&<><line x1={left} x2={right} y1={scale(30)} y2={scale(30)} stroke="#3a4756" strokeDasharray="2 4"/><line x1={left} x2={right} y1={scale(70)} y2={scale(70)} stroke="#3a4756" strokeDasharray="2 4"/></>}{name==='macd'&&<line x1={left} x2={right} y1={zero} y2={zero} stroke="#3a4756" strokeDasharray="2 4"/>}{specs.map(sp=>{
              if(sp.band==='histogram')return null;
              return segsOf(sp,scale).map((seg,si)=><polyline data-testid={name+'-line'} key={sp.id+':'+si} points={seg.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ')} fill="none" stroke={sp.band==='signal'?'#e3c16a':'#5ec986'} strokeWidth="1.4"><title>{sp.label}</title></polyline>);})}
            {specs.filter(sp=>sp.band==='histogram').map(sp=>{const byTime=new Map(sp.points.map(p=>[p&&p.time,p&&p.value]));const bars=[];
              visible.forEach((frame,index)=>{const v=byTime.get(frame.time);if(typeof v!=='number'||!Number.isFinite(v))return;
                const vy=scale(v);bars.push(<rect data-testid="macd-histogram" key={'mh:'+index} x={left+index*spacing+Math.max(1,spacing*0.3)} y={Math.min(zero,vy)} width={Math.max(1,spacing*0.4)} height={Math.max(1,Math.abs(zero-vy))} fill={v>=0?'#57c5b0':'#e48d94'} opacity="0.7"/>);});
              return bars;})}
            </>}
            {refused&&<text x={left} y={Math.round(h/2)} fill="#d65656" fontSize="10" data-testid="momentum-refused-note">series refused — a non-finite close is in the loaded window; nothing drawn</text>}
          </svg>
          <div className="recorded-momentum-label" data-testid={'momentum-label-'+name}>
            <strong>{name.toUpperCase()}</strong>
            <span>{specs.map(sp=>sp.label).filter((v,i,a)=>a.indexOf(v)===i).join(' · ')}</span>
            {!refused&&<small>{name==='rsi'?'0–100 fixed scale':name==='macd'?'price delta · zero-anchored':'own price scale'}</small>}
          </div>
        </div>);
      }
      return panes.length?panes:null;
    })()}
        {!!data.length&&effCvd&&(()=>{ // CVD pane: BVC-estimated cumulative flow — honest gaps, never zero-filled.
     if(!showAtlas||(cvdStudy?false:!Array.isArray(cvdLine)))return null;
     // C118: with the corrected study (58815e74) the drawn path IS the
     // configured one. Holes stay null here — the segmentation below breaks
     // the polyline at every null, so nothing draws across a gap or a
     // session boundary; the raw payload path is the no-config fallback.
     const src=Array.isArray(cvdStudy?.points)?cvdStudy.points:(Array.isArray(cvdLine)?cvdLine.filter(p=>p&&typeof p.time==='string'):[]);
     const byTime=new Map(src.map(p=>[p?.time,p]));
     const known=visible.map(frame=>{const entry=byTime.get(frame.time);const v=entry?entry.cvd:undefined;return typeof v==='number'&&Number.isFinite(v)?v:null;});
     const maKnown=cvdStudy&&cvdStudy.maPeriod>1?visible.map(frame=>{const entry=byTime.get(frame.time);const v=entry?entry.ma:undefined;return typeof v==='number'&&Number.isFinite(v)?v:null;}):null;
     const maY=v=>h-pad-((v-lo)/span)*(h-pad*2);
     if(!known.some(v=>v!==null))return null;
     const vals=known.filter(v=>v!==null),lo=Math.min(...vals),hi=Math.max(...vals),span=(hi-lo)||1;
     const h=56,pad=6,cy=v=>h-pad-((v-lo)/span)*(h-pad*2);
     const segments=[];let cur=[];
     known.forEach((v,i)=>{if(v===null){if(cur.length)segments.push(cur);cur=[];return;}cur.push({x:left+(i+0.5)*spacing,y:cy(v)});});
     if(cur.length)segments.push(cur);
     const lines=segments.filter(s=>s.length>1),dots=[];
     segments.filter(s=>s.length===1).forEach(s=>dots.push(s[0]));
     const cvdCfg=paneCfg?.cvd;
     return <div className="recorded-cvd-pane" data-testid="cvd-pane" aria-label="Estimated cumulative volume delta">
       <div className="pane-study-settings" data-testid="cvd-settings" role="group" aria-label="Estimated CVD settings">
         {cvdStudyRefusal?<span className="pane-study-refusal" data-testid="cvd-study-refusal" role="note">{cvdStudyRefusal}</span>:<>
           {onPaneCfg&&<label>Anchor<select data-testid="cvd-anchor" value={paneCfg?.cvd?.anchor??'none'} onChange={e=>onPaneCfg({cvd:{...(paneCfg?.cvd||{}),anchor:e.target.value}})}><option value="none">none</option><option value="session">session</option></select></label>}
           {onPaneCfg&&<label>MA<input data-testid="cvd-ma" aria-label="CVD MA period" type="number" min="1" max="200" value={paneCfg?.cvd?.maPeriod??1} onChange={e=>{const n=Math.round(Number(e.target.value));if(Number.isInteger(n)&&n>=1&&n<=200)onPaneCfg({cvd:{...(paneCfg?.cvd||{}),maPeriod:n}});}}/></label>}
           {onPaneCfg&&<label>Zero axis<select data-testid="cvd-zero-axis" value={paneCfg?.cvd?.zeroAxis??'free'} onChange={e=>onPaneCfg({cvd:{...(paneCfg?.cvd||{}),zeroAxis:e.target.value}})}><option value="free">free</option><option value="zero-at-anchor">zero at session</option></select></label>}
         </>}
         <span className="pane-study-approx" data-testid="cvd-approx-label">estimated (BVC) — not a classified tape</span>
       </div>
       <svg viewBox={'0 0 '+size.width+' '+h} preserveAspectRatio="none" style={{width:'100%',height:h}} role="img" aria-label="CVD estimate per candle">
        {lines.map((seg,si)=><polyline data-testid="cvd-line" key={'cvd:'+si} points={seg.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ')} fill="none" stroke="#9d7bea" strokeWidth="1.5"><title>CVD estimate</title></polyline>)}
        {maKnown&&(()=>{ // C118: the MA segments exactly like the path — a hole
          // or an anchor boundary closes the run, so it never bridges either.
          const segs=[];let run=[];maKnown.forEach((v,i)=>{if(v===null){if(run.length>1)segs.push(run);run=[];return;}run.push({x:left+(i+0.5)*spacing,y:maY(v)});});if(run.length>1)segs.push(run);
          return segs.map((seg,si)=><polyline data-testid="cvd-ma-line" key={'cvdma:'+si} points={seg.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ')} fill="none" stroke="#e3c16a" strokeWidth="1" strokeDasharray="3 3"><title>{'CVD MA '+(cvdStudy?.maPeriod??1)}</title></polyline>);})()}

        {dots.map((p,di)=><circle data-testid="cvd-point" key={'cvddot:'+di} cx={p.x} cy={p.y} r="2" fill="#9d7bea" opacity="0.9"><title>CVD estimate (single known candle)</title></circle>)}
       </svg>
       <div className="recorded-cvd-summary"><span data-testid="cvd-status">Estimated CVD · shares · {vals.length}/{visible.length} known</span><details><summary role="button">CVD method</summary><p>CVD estimated via bulk volume classification (Easley, López de Prado &amp; O&apos;Hara 2012); a bar-volume estimate, not classified trade-by-trade CVD. Unknown ≠ zero; gaps are honest. Range {lo.toLocaleString('en-US')}–{hi.toLocaleString('en-US')} shares (own scale).</p></details></div>
     </div>;})()}
    {Array.isArray(alertLines)&&alertLines.some(a=>a?.state==='stale')&&<small role="note">Stale alert refused — no evaluation on stale prices.</small>}
    {!!data.length&&(()=>{ // Contract premium path: selected option's own closes on their own $ scale.
     if(contractStatus==='unavailable'||(contractSymbol&&(!Array.isArray(contractBars)||!contractBars.length)))
       return <div className="recorded-contract-empty" data-testid="contract-premium-unavailable"><small>Contract premium unavailable{contractSymbol?' for '+contractSymbol:''} in the visible candle window.</small></div>;
     if(!contractSymbol||!Array.isArray(contractBars)||!contractBars.length)return null;
     const closes=premiumCloses.slice(windowView.start,windowView.start+windowView.count);
     if(!closes.some(v=>v!==null))return <div className="recorded-contract-empty" data-testid="contract-premium-unavailable"><small>Contract premium unavailable{contractSymbol?' for '+contractSymbol:''} in the visible candle window.</small></div>;
     const vals=closes.filter(v=>v!==null),lo=Math.min(...vals),hi=Math.max(...vals),span=(hi-lo)||1;
     const h=56,pad=8,py=v=>h-pad-((v-lo)/span)*(h-pad*2);
     const segments=[];let current=[];
     closes.forEach((v,i)=>{if(v===null){if(current.length)segments.push(current);current=[];return;}current.push({x:left+(i+0.5)*spacing,y:py(v)});});
     if(current.length)segments.push(current);
     return <div className="recorded-contract-pane" data-testid="contract-premium-pane" aria-label="Selected contract premium">
       <svg viewBox={'0 0 '+size.width+' '+h} preserveAspectRatio="none" style={{width:'100%',height:h}} role="img" aria-label={contractSymbol+' premium closes'}>
        {segments.map((pts,i)=>pts.length>1?<polyline data-testid="contract-premium" key={i} points={pts.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ')} fill="none" stroke="#e8bd65" strokeWidth="1.5"><title>{contractSymbol+' premium closes'}</title></polyline>:<circle data-testid="contract-premium" key={i} cx={pts[0].x} cy={pts[0].y} r="2.5" fill="#e8bd65"><title>{contractSymbol+' premium close'}</title></circle>)}
       </svg>
       <small>{contractSymbol} premium ($) — own scale, not underlying $. Range ${lo.toFixed(2)}–${hi.toFixed(2)}. {vals.length}/{visible.length} visible candles matched. Missing prices stay gaps.</small>
     </div>;})()}
   {/* P1-5 (UX review): the candle-count footer and the selected-candle node
       legend share ONE slim line below the chart — no separate boxed strips.
       Both honest strings are unchanged. */}
   {!!data.length&&<div className="recorded-chart-below" aria-label="Chart footer and selected node legend">
     <small>{windowView.start+1}-{windowView.start+visible.length} of {data.length} loaded candles</small>
     {selected&&<span className="recorded-chart-nodes">{selectedLevels.length?selectedLevels.map((node,index)=><span key={node.metric+':'+node.id+':'+index} style={{color:NODE_COLORS[node.metric]}}>{NODE_LABELS[node.metric]} <b>{price(node.level)}</b></span>):<span>No supported saved node lines at this candle.{Object.entries(selected?.metric_status||{}).filter(([,status])=>status==="zero").map(([metric])=>" "+NODE_LABELS[metric]+" was zero; no largest level stood out.").join("")}</span>}</span>}
   </div>}
 </div>;
}
