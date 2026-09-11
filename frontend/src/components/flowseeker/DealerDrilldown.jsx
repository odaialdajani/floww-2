import React, { useId } from "react";
import { finite } from "./dealerSeries";
const money = v => v == null ? "Unavailable" : new Intl.NumberFormat("en-US", {notation:"compact",maximumFractionDigits:1}).format(v);
export default function DealerDrilldown({ ticker, series, regime = {}, loading, error, stale, colorBlind, selectedExpiry }) {
 const pattern = `short-${useId().replace(/:/g,"")}`;
 const { strikes, net, cumulative, flipFraction, flip, spot } = series;
 const width = Math.max(620, strikes.length * 52), left = 42, right = width-30;
 const x = strike => left + series.xFraction(strike)*(right-left);
 const values = cumulative.filter(v=>v!=null);
 const lowerMin=Math.min(0,...values),lowerMax=Math.max(0,...values);
 const range=lowerMax-lowerMin || 1;
 const y = value => 220 - (value-lowerMin)/range*68;
 const barWidth = Math.min(24, strikes.length>1 ? Math.min(...strikes.slice(1).map((s,i)=>x(s)-x(strikes[i])))*0.65 : 24);
 const path = cumulative.map((v,i)=>v==null?"":`${i===0 || cumulative[i-1]==null ? "M":"L"}${x(strikes[i])},${y(v)}`).join(" ");
 const dist = spot != null && flip != null && flip > 0 ? (spot-flip)/flip*100 : null;
 const state = loading ? "Loading" : error ? "Unavailable" : stale ? "Stale or source time unknown" : "Available";
 return <section className="th-dealer-detail" id="dealer-drilldown" tabIndex={-1} aria-label={`Drill-down ${ticker}`} data-testid="dealer-drilldown">
  <header><h3>Drill-down <span>{ticker}</span></h3><span>{state}</span></header>
  <p>{selectedExpiry ? `Selected expiry: ${selectedExpiry}. ` : ""}Displayed expiries: {series.expiries.join(", ") || "none in the loaded data"}. Regime and flip describe the full loaded chain.</p>
  <div className="th-dealer-facts">
   <div><small>Market regime</small><strong>{regime.current_state || "Unavailable"}{regime.is_warming ? " - warming" : ""}</strong></div>
   <div><small>Gamma flip</small><strong>{flip ?? "Unavailable"}</strong><span>{dist == null ? "Spot distance unavailable" : `Spot ${Math.abs(dist).toFixed(1)}% ${dist < 0 ? "below" : dist > 0 ? "above" : "at"} flip`}</span></div>
   <div><small>Volatility</small><strong>{regime.vol_env || "Unavailable"}</strong></div>
  </div>
  {loading || !series.hasData ? <p className="th-empty">{loading ? `Loading dealer data for ${ticker}` : `Dealer chart unavailable for ${ticker}`}</p> : <>
   <div className="th-dealer-scroll"><svg viewBox={`0 0 ${width} 256`} role="img" aria-label={`Net and cumulative dealer gamma for ${ticker}`} style={{minWidth:width}}>
    <defs><pattern id={pattern} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="#c44c67"/><line x1="0" y1="0" x2="0" y2="6" stroke="#f3b8c5" strokeWidth="2"/></pattern></defs>
    <text x={left} y="15">Net dealer gamma by strike</text>
    <line x1={left} x2={right} y1="124" y2="124" className="guide"/>
    {net.map((value,i)=> {
     const h=value==null?0:Math.abs(value)/(series.maxMagnitude||1)*80;
     return <g key={strikes[i]}><title>{`${strikes[i]}: ${value==null?"Unavailable":value}`}</title>
      {value==null ? <text x={x(strikes[i])} y="115" textAnchor="middle">?</text> : <rect x={x(strikes[i])-barWidth/2} y={124-h} width={barWidth} height={Math.max(h,1)} fill={value<0 ? colorBlind?`url(#${pattern})`:"#c44c67":"#35ad94"}/>} 
      <text x={x(strikes[i])} y="139" textAnchor="middle">{value==null?"?":`${value>0?"+":""}${money(value)}`}</text>
     </g>;
    })}
    <text x={left} y="153">Cumulative signed gamma</text>
    <line x1={left} x2={right} y1={y(0)} y2={y(0)} className="guide" strokeDasharray="3 4"/>
    <path d={path} fill="none" stroke="#929ad8" strokeWidth="2"/>
    {cumulative.map((v,i)=>v==null?null:<circle key={strikes[i]} cx={x(strikes[i])} cy={y(v)} r="2" fill="#929ad8"/>)}
    {flipFraction != null && <g><line x1={left+flipFraction*(right-left)} x2={left+flipFraction*(right-left)} y1="24" y2="224" stroke="#d3ad67" strokeDasharray="4 4"/><text x={left+flipFraction*(right-left)} y="28" textAnchor="middle">Flip {flip}</text></g>}
    {strikes.map(s=><text key={s} x={x(s)} y="244" textAnchor="middle">{s}</text>)}
   </svg></div>
   {!series.complete && <p>Some displayed cells are missing. Cumulative totals stop at the first gap.</p>}
   {finite(flip) != null && flipFraction == null && <p>Flip {flip} is outside the displayed strike range.</p>}
   <footer><span>Red / minus: short gamma. Green / plus: long gamma.</span><span>Shown gamma: {money(series.total)} - displayed expiries only</span></footer>
  </>}
 </section>;
}
