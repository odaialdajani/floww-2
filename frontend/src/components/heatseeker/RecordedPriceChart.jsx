import React,{useEffect,useId,useMemo,useRef,useState} from 'react';
import {chartTime,checkedCandles,clampWindow,NODE_COLORS,NODE_LABELS,pinchFactors,priceRange,savedLevels,zoomPrice,zoomTime} from './recordedPriceChartData';
import {openingEnvelope,sessionEnvelope,sessionVwapBands,sessionVwapValues} from './chart/indicators/priceStudies';
import {volumeProfile} from './chart/indicators/profile';
import './RecordedPriceChart.css';
const price=value=>Number.isFinite(value)?value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'Unavailable';
const bound=(value,low,high)=>Math.max(low,Math.min(high,value));

export default function RecordedPriceChart({ticker,frames,revision='',onInteract,metricCoverage={},toolbarControls=null,toolbarActions=null,historyControls=null,dataDetails=null,readingStatus="Data details",emptyContent=null,showAtlas=true,exposureLine=null,darkLevels=null,flowBars=null,alertLines=null,cvdLine=null,contractBars=null,contractSymbol=null,contractStatus=null}) {
 const data=useMemo(()=>checkedCandles(frames),[frames]);
 const surface=useRef(null),pointers=useRef(new Map()),gesture=useRef(null),previousLength=useRef(0);
 const [size,setSize]=useState({width:800,height:480});
 const [view,setView]=useState(()=>({start:Math.max(0,data.length-80),count:80}));
 const [manualPrice,setManualPrice]=useState(null),[hover,setHover]=useState(null),[metrics,setMetrics]=useState(['gex','vex','charm']),[allNodes,setAllNodes]=useState(false);
  const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState(''),[vwapOn,setVwapOn]=useState(true),[bandsOn,setBandsOn]=useState(false),[profileOn,setProfileOn]=useState(true),[envelopeOn,setEnvelopeOn]=useState(false),[cvdOn,setCvdOn]=useState(true);
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
  else if(pointers.current.size===1)gesture.current={mode:p.x>=right?'price':p.y>=bottom?'time':'pan',point:p,view:windowView,range,manual:Boolean(manualPrice),
   // Anchor = where the user grabbed, as a fraction of the plot, so the
   // point under the cursor stays under the cursor while the axis stretches.
   anchor:p.x>=right?bound(1-(p.y-top)/plotHeight,0,1):p.y>=bottom?bound((p.x-left)/plotWidth,0,1):0};
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
 return <div className="recorded-price-chart" data-testid="recorded-price-chart" data-candles={data.length} data-visible-candles={visible.length} data-window-start={windowView.start} data-price-low={range.low} data-price-high={range.high}>
  <div className="recorded-chart-tools" data-testid="chart-control-row">
   {toolbarControls}
   <div className="recorded-chart-scale"><button type="button" aria-label="Zoom in time" disabled={!data.length} onClick={()=>zoom('time',0.75)}>+</button><button type="button" aria-label="Zoom out time" disabled={!data.length} onClick={()=>zoom('time',1.35)}>-</button><button type="button" aria-label="Auto scale" aria-pressed={!manualPrice} disabled={!data.length} title={manualPrice?"Price scale locked; click to fit visible prices":"Fits visible prices; click to lock"} onClick={()=>setManualPrice(held=>held?null:range)}>Auto scale {manualPrice?'locked':'on'}</button></div>
   <details className="recorded-chart-popover"><summary role="button" aria-label="Chart tools">Tools</summary><div className="recorded-chart-popover-content">
    <div className="recorded-chart-history"><button type="button" aria-label="Earlier candles" disabled={!windowView.start} onClick={()=>shift(-Math.max(1,Math.floor(windowView.count/2)))}>Earlier</button><button type="button" aria-label="Later candles" disabled={windowView.start+windowView.count>=data.length} onClick={()=>shift(Math.max(1,Math.floor(windowView.count/2)))}>Later</button><button type="button" disabled={!data.length} onClick={()=>{notify();setView({start:0,count:data.length});setManualPrice(null);}}>Fit history</button></div>
    <fieldset className="recorded-chart-layers" aria-label="Saved node lines"><legend>Saved lines</legend>{Object.entries(NODE_LABELS).map(([metric,label])=><label key={metric} style={{'--node-color':NODE_COLORS[metric]}}><input type="checkbox" checked={metrics.includes(metric)} disabled={!availableMetrics.includes(metric)} onChange={e=>{setMetrics(old=>e.target.checked?[...old,metric]:old.filter(value=>value!==metric));setManualPrice(null);}}/>{label}{!availableMetrics.includes(metric)&&<span> unavailable</span>}</label>)}<label><input type="checkbox" checked={allNodes} onChange={e=>{setAllNodes(e.target.checked);setManualPrice(null);}}/>All saved levels</label></fieldset>
     <label><input type="checkbox" aria-label="Toggle VWAP" checked={vwapOn} disabled={!data.some(frame=>Number.isFinite(frame.volume))} onChange={e=>setVwapOn(e.target.checked)}/>VWAP{!data.some(frame=>Number.isFinite(frame.volume))&&<span> unavailable</span>}</label>
     <label><input type="checkbox" aria-label="Toggle profile" checked={profileOn} disabled={!data.some(frame=>Number.isFinite(frame.volume))} onChange={e=>setProfileOn(e.target.checked)}/>Profile{!data.some(frame=>Number.isFinite(frame.volume))&&<span> unavailable</span>}</label>
     <label><input type="checkbox" aria-label="Toggle VWAP bands" checked={bandsOn} disabled={!data.some(frame=>Number.isFinite(frame.volume))} onChange={e=>setBandsOn(e.target.checked)}/>Bands{!data.some(frame=>Number.isFinite(frame.volume))&&<span> unavailable</span>}</label>
      <label><input type="checkbox" aria-label="Toggle exposure envelope" checked={envelopeOn} disabled={!Array.isArray(exposureLine)||!exposureLine.some(p=>typeof p?.centre==='number'&&Number.isFinite(p.centre))} onChange={e=>setEnvelopeOn(e.target.checked)}/>Envelope{(!Array.isArray(exposureLine)||!exposureLine.some(p=>typeof p?.centre==='number'&&Number.isFinite(p.centre)))&&<span> unavailable</span>}</label>
      <label><input type="checkbox" aria-label="Toggle CVD" checked={cvdOn} disabled={!Array.isArray(cvdLine)||!cvdLine.some(p=>typeof p?.cvd==='number'&&Number.isFinite(p.cvd))} onChange={e=>setCvdOn(e.target.checked)}/>CVD{(!Array.isArray(cvdLine)||!cvdLine.some(p=>typeof p?.cvd==='number'&&Number.isFinite(p.cvd)))&&<span> unavailable</span>}</label>
     <button type="button" disabled={!data.length||exporting} onClick={downloadChart}>{exporting?'Saving image...':'Download chart image'}</button>{exportError&&<p role="alert">{exportError}</p>}
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
      {showAtlas&&visible.flatMap((frame,index)=>{
       const nodes=(Array.isArray(frame.nodes)?frame.nodes:[]).filter(n=>n&&Number.isFinite(n.level)&&Object.hasOwn(NODE_COLORS,n.metric||'gex'));
       if(!nodes.length)return [];
       const weights=nodes.map(n=>{const w=n.signed_value??n.strength;return typeof w==='number'&&Number.isFinite(w)?Math.abs(w):1;});
       const king=Math.max(...weights),center=left+(index+0.5)*spacing;
       return nodes.flatMap((node,ni)=>{const yy=y(node.level);
        // A strike outside the visible price range is never drawn clamped
        // to the plot edge — that would fabricate a price. Drop it and mark
        // the candle as having out-of-range nodes instead.
        if(yy<top||yy>bottom)return <title key={frame.time+':orb:'+ni+':oor'} data-testid="orb-out-of-range">Orb {price(node.level)} out of visible price range</title>;
        const ratio=king>0?weights[ni]/king:0,r=Math.min(12,Math.max(3,4*Math.sqrt(Math.max(0,ratio)))),isKing=weights[ni]===king;
        return <circle data-testid="chart-orb" key={frame.time+':orb:'+ni} cx={center} cy={yy} r={r} fill={isKing?'#e8bd65':'none'} stroke={NODE_COLORS[node.metric||'gex']||'#e8bd65'} strokeWidth={isKing?2:1} opacity="0.75"><title>{'Orb '+price(node.level)+(isKing?' (King Node)':'')}</title></circle>;});})}
      {exposurePolys()}
      {envelopeLevels().map((lv,li)=><line data-testid="exposure-envelope" key={'envelope:'+li} x1={left} x2={right} y1={y(lv)} y2={y(lv)} stroke="#72d7df" strokeWidth="1" strokeDasharray="2 3" opacity="0.7"><title>Exposure envelope level</title></line>)}
      {showAtlas&&Array.isArray(darkLevels)&&darkLevels.filter(l=>l&&typeof l.price==='number'&&Number.isFinite(l.price)&&l.price>=range.low&&l.price<=range.high).map((l,li)=><line data-testid="dark-pool-level" key={'dark:'+li} x1={left} x2={right} y1={y(l.price)} y2={y(l.price)} stroke="#c9a86a" strokeWidth="1.5" strokeDasharray="6 3"><title>{'Dark pool level '+price(l.price)+(l.venue?' '+l.venue:'')}</title></line>)}
      {Array.isArray(alertLines)&&alertLines.filter(a=>a&&typeof a.price==='number'&&Number.isFinite(a.price)&&a.price>=range.low&&a.price<=range.high).map((a,ai)=><line data-testid="alert-line" data-state={a.state==='stale'?'stale':'armed'} key={'alert:'+(a.id||ai)} x1={left} x2={right} y1={y(a.price)} y2={y(a.price)} stroke={a.state==='stale'?'#6b7684':'#e06c75'} strokeWidth="1.5" strokeDasharray={a.state==='stale'?'2 3':'none'}><title>{'Alert '+(a.id||ai)+' at '+price(a.price)+(a.state==='stale'?' — stale alert refused':'')}</title></line>)}
      {showAtlas&&vwapOn&&data.some(frame=>Number.isFinite(frame.volume))&&(()=>{
       const all=sessionVwapValues(data),win=all.slice(windowView.start,windowView.start+windowView.count);
       const pts=win.map((v,i)=>{if(typeof v!=='number'||!Number.isFinite(v))return null;const py=y(v);if(py<top||py>bottom)return null;return {x:left+(i+0.5)*spacing,y:py};});
       const drawn=pts.filter(Boolean);if(drawn.length<2)return null;
       return <polyline data-testid="vwap-line" points={drawn.map(p=>p.x+','+p.y).join(' ')} fill="none" stroke="#e08e45" strokeWidth="2"><title>Session VWAP</title></polyline>;})()}
      {showAtlas&&bandsOn&&vwapOn&&data.some(frame=>Number.isFinite(frame.volume))&&(()=>{
       const all=sessionVwapBands(data),maxM=3;
       return Array.from({length:maxM},(_,m)=>{const pts=[];
        for(let k=0;k<windowView.count;k+=1){const set=all[windowView.start+k];const band=set?.[m];
         if(!band||typeof band.upper!=='number'||!Number.isFinite(band.upper)||typeof band.lower!=='number'||!Number.isFinite(band.lower))continue;
         const uy=y(band.upper),ly=y(band.lower);if(uy<top||uy>bottom||ly<top||ly>bottom)continue;
         pts.push({x:left+(k+0.5)*spacing,uy,ly});}
        if(pts.length<2)return null;
        return <g key={'vwapband:'+m}><polyline data-testid="vwap-band" points={pts.map(p=>p.x+','+p.uy).join(' ')} fill="none" stroke="#e08e45" strokeWidth="1" strokeDasharray="4 3" opacity="0.8"/><polyline data-testid="vwap-band" points={pts.map(p=>p.x+','+p.ly).join(' ')} fill="none" stroke="#e08e45" strokeWidth="1" strokeDasharray="4 3" opacity="0.8"/></g>;});})()}
      {showAtlas&&profileOn&&data.some(frame=>Number.isFinite(frame.volume))&&(()=>{
       const prof=volumeProfile(visible,{rows:Math.min(48,Math.max(8,visible.length))});
       if(prof.status!=='ok')return null;
       const peak=Math.max(...prof.rows.map(r=>r.volume),1),bw=64,bx=Math.max(left,right-bw-4);
       return <g data-testid="volume-profile"><title>Volume profile (bar-range approximation)</title>{prof.rows.map((r,ri)=>{const isPoc=r.price===prof.poc.price&&r.volume===prof.poc.volume;
        return <rect key={'vp:'+ri} data-testid={isPoc?'profile-poc':'profile-row'} x={bx+(bw-Math.max(1,(r.volume/peak)*bw))} y={y(r.price)-2} width={Math.max(1,(r.volume/peak)*bw)} height={4} fill={isPoc?'#e8bd65':'#5a6b7d'} opacity={isPoc?0.95:0.6}><title>{'Volume '+price(r.price)+': '+Math.round(r.volume).toLocaleString('en-US')+' shares'}</title></rect>;})}</g>;})()}
      {hover!==null&&selected&&<><line x1={left+(hover+0.5)*spacing} x2={left+(hover+0.5)*spacing} y1={top} y2={bottom} stroke="#a8b3be" strokeDasharray="3 4"/><line x1={left} x2={right} y1={y(selected.close)} y2={y(selected.close)} stroke="#a8b3be" strokeDasharray="3 4"/></>}
    </g>
    <line x1={right} x2={right} y1={top} y2={bottom} stroke="#3d4853"/>
    {Array.from({length:Math.min(5,visible.length)},(_,i)=>{const index=Math.round(i*Math.max(0,visible.length-1)/Math.max(1,Math.min(5,visible.length)-1)),frame=visible[index];return frame&&<text key={i} x={left+(index+0.5)*spacing} y={bottom+24} textAnchor={i===0?'start':i===4?'end':'middle'} className="recorded-time-label">{chartTime(frame.time)}</text>;})}
   </svg>
   </div>:<div className="recorded-chart-empty">{emptyContent||<p>No valid price candles are available.</p>}</div>}
   {!!data.length&&showAtlas&&Array.isArray(flowBars)&&flowBars.length===data.length&&(()=>{
    const win=flowBars.slice(windowView.start,windowView.start+windowView.count);
    const peak=Math.max(1,...win.flatMap(b=>[Math.abs(b?.call||0),Math.abs(b?.put||0)]));
    return <div className="recorded-flow-pane" data-testid="flow-pane" aria-label="Options flow per candle">{win.map((b,bi)=><div key={bi} className="recorded-flow-bar"><div className="recorded-flow-call" style={{height:(Math.abs(b?.call||0)/peak*20)+'px'}}/><div className="recorded-flow-put" style={{height:(Math.abs(b?.put||0)/peak*20)+'px'}}/></div>)}</div>;})()}
   {!!data.length&&(()=>{ // Volume pane: real provider volume only — never fabricated.
    const win=visible,hasVol=win.some(frame=>Number.isFinite(frame.volume));
    if(!hasVol)return <div className="recorded-chart-empty recorded-volume-empty"><small>Volume unavailable for these candles.</small></div>;
    const peak=Math.max(1,...win.map(frame=>Number(frame.volume)||0));
    const h=Math.max(24,Math.min(72,Math.round(plotHeight*0.15)));
    return <svg className="recorded-volume-pane" data-testid="volume-pane" role="img" aria-label="Traded volume per candle" viewBox={'0 0 '+size.width+' '+h} preserveAspectRatio="none" style={{width:'100%',height:h}}>
      {win.map((frame,index)=>{const v=Number(frame.volume)||0,bh=Math.max(1,v/peak*(h-4));
       return <rect data-testid="volume-bar" key={frame.time} x={left+index*spacing+Math.max(1,spacing*0.15)} y={h-bh} width={Math.max(1,Math.min(spacing*0.7,14))} height={bh} fill={frame.close>=frame.open?'#3f8f7d':'#8f4a52'} opacity="0.85"><title>{chartTime(frame.time,true)+' — '+(Number.isFinite(v)?v.toLocaleString('en-US'):'0')+' shares'}</title></rect>;})}
    </svg>;})()}
    {!!data.length&&cvdOn&&(()=>{ // CVD pane: BVC-estimated cumulative flow — honest gaps, never zero-filled.
     if(!showAtlas||!Array.isArray(cvdLine))return null;
     const byTime=new Map(cvdLine.filter(p=>p&&typeof p.time==='string').map(p=>[p.time,p]));
     const known=visible.map(frame=>{const entry=byTime.get(frame.time);const v=entry?entry.cvd:undefined;return typeof v==='number'&&Number.isFinite(v)?v:null;});
     if(!known.some(v=>v!==null))return null;
     const vals=known.filter(v=>v!==null),lo=Math.min(...vals),hi=Math.max(...vals),span=(hi-lo)||1;
     const h=56,pad=6,cy=v=>h-pad-((v-lo)/span)*(h-pad*2);
     const segments=[];let cur=[];
     known.forEach((v,i)=>{if(v===null){if(cur.length)segments.push(cur);cur=[];return;}cur.push({x:left+(i+0.5)*spacing,y:cy(v)});});
     if(cur.length)segments.push(cur);
     const lines=segments.filter(s=>s.length>1),dots=[];
     segments.filter(s=>s.length===1).forEach(s=>dots.push(s[0]));
     return <div className="recorded-cvd-pane" data-testid="cvd-pane" aria-label="Estimated cumulative volume delta">
       <svg viewBox={'0 0 '+size.width+' '+h} preserveAspectRatio="none" style={{width:'100%',height:h}} role="img" aria-label="CVD estimate per candle">
        {lines.map((seg,si)=><polyline data-testid="cvd-line" key={'cvd:'+si} points={seg.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ')} fill="none" stroke="#9d7bea" strokeWidth="1.5"><title>CVD estimate</title></polyline>)}
        {dots.map((p,di)=><circle data-testid="cvd-point" key={'cvddot:'+di} cx={p.x} cy={p.y} r="2" fill="#9d7bea" opacity="0.9"><title>CVD estimate (single known candle)</title></circle>)}
       </svg>
       <small>CVD estimated via bulk volume classification (Easley, López de Prado &amp; O&apos;Hara 2012); ≈80% bar accuracy on equities — directional, not exact. Unknown ≠ zero; gaps are honest. Range {lo.toLocaleString('en-US')}–{hi.toLocaleString('en-US')} shares (own scale).</small>
     </div>;})()}
    {Array.isArray(alertLines)&&alertLines.some(a=>a?.state==='stale')&&<small role="note">Stale alert refused — no evaluation on stale prices.</small>}
    {!!data.length&&(()=>{ // Contract premium path: selected option's own closes on their own $ scale.
     if(contractStatus==='unavailable'||(contractSymbol&&(!Array.isArray(contractBars)||!contractBars.length)))
       return <div className="recorded-contract-empty" data-testid="contract-premium-unavailable"><small>Contract premium unavailable{contractSymbol?' for '+contractSymbol:''}.</small></div>;
     if(!contractSymbol||!Array.isArray(contractBars)||!contractBars.length)return null;
     const closes=contractBars.map(b=>{const v=b?.c??b?.close;return typeof v==='number'&&Number.isFinite(v)?v:null;});
     if(!closes.some(v=>v!==null))return <div className="recorded-contract-empty" data-testid="contract-premium-unavailable"><small>Contract premium unavailable{contractSymbol?' for '+contractSymbol:''}.</small></div>;
     const vals=closes.filter(v=>v!==null),lo=Math.min(...vals),hi=Math.max(...vals),span=(hi-lo)||1;
     const h=56,pad=8,py=v=>h-pad-((v-lo)/span)*(h-pad*2);
     const pts=[];closes.forEach((v,i)=>{if(v!==null)pts.push({x:left+(closes.length===1?0.5*plotWidth:i/(closes.length-1)*plotWidth),y:py(v)});});
     if(pts.length<1)return null;
     return <div className="recorded-contract-pane" data-testid="contract-premium-pane" aria-label="Selected contract premium">
       <svg viewBox={'0 0 '+size.width+' '+h} preserveAspectRatio="none" style={{width:'100%',height:h}} role="img" aria-label={contractSymbol+' premium closes'}>
        {pts.length>1&&<polyline data-testid="contract-premium" points={pts.map(p=>p.x.toFixed(1)+','+p.y.toFixed(1)).join(' ')} fill="none" stroke="#e8bd65" strokeWidth="1.5"><title>{contractSymbol+' premium closes'}</title></polyline>}
        {pts.length===1&&<circle data-testid="contract-premium" cx={pts[0].x} cy={pts[0].y} r="2.5" fill="#e8bd65"><title>{contractSymbol+' premium close'}</title></circle>}
       </svg>
       <small>{contractSymbol} premium ($) — own scale, not underlying $. Range ${lo.toFixed(2)}–${hi.toFixed(2)}.</small>
     </div>;})()}
   {!!data.length&&<div className="recorded-chart-footer"><small>{windowView.start+1}-{windowView.start+visible.length} of {data.length} loaded candles</small></div>}
  {selected&&<div className="recorded-chart-nodes" aria-label="Selected candle saved nodes">{selectedLevels.length?selectedLevels.map((node,index)=><span key={node.metric+':'+node.id+':'+index} style={{color:NODE_COLORS[node.metric]}}>{NODE_LABELS[node.metric]} <b>{price(node.level)}</b></span>):<span>No supported saved node lines at this candle.{Object.entries(selected?.metric_status||{}).filter(([,status])=>status==="zero").map(([metric])=>" "+NODE_LABELS[metric]+" was zero; no largest level stood out.").join("")}</span>}</div>}
 </div>;
}
