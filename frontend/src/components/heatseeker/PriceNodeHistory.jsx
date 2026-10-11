import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";
import RecordedPriceChart from "./RecordedPriceChart";
import DrawingRail from "./chart/drawings/DrawingRail";
import { loadDrawings, saveDrawings } from "./chart/drawings/drawingPersistence";
import { reduceDrawings } from "./chart/drawings/drawingReducer";
import { chartTime } from "./recordedPriceChartData";



function savedViewLabel(scope,index){
 const text=typeof scope==="string"?scope:"",part=text.match(/\|expiries=([^|]+)/)?.[1];
 const dates=part?.split(",");
 const valid=dates?.length&&dates.every(value=>/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value+"T00:00:00Z"))&&new Date(value+"T00:00:00Z").toISOString().slice(0,10)===value)&&new Set(dates).size===dates.length;
 if(!valid)return "Saved view "+(index+1)+" - expiry dates unavailable";
 const sorted=[...dates].sort(),tokens=text.split("|")[0].split(":"),mode=tokens.includes("scalp")?"Scalp":tokens.includes("swing")?"Swing":tokens.includes("day")?"Day":"Saved";
 return mode+" | "+sorted.length+" "+(sorted.length===1?"expiry":"expiries")+" | "+sorted[0]+(sorted.length>1?" to "+sorted.at(-1):"");
}

export default function PriceNodeHistory({ ticker = "SPY", open: controlledOpen, onOpenChange, primary = false, toolbarActions = null, exposureLine = null, darkLevels = null, flowBars = null, showAtlas = true, forcedScope = null, onRecordNodes = null, cvdLine = null }) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? (primary || localOpen);
  const setOpen = value => { setLocalOpen(value); onOpenChange?.(value); };
  const [days, setDays] = useState(5);
  const [minutes, setMinutes] = useState(30);
  const [scope, setScope] = useState("");
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState("idle");
  const [reload, setReload] = useState(0);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordNote, setRecordNote] = useState("");
  // M3 contract premium path: user-picked OSI symbol loads the contract's
  // own OHLCV beside the underlying candles (own $ scale, never mixed).
  const [contractInput, setContractInput] = useState("");
  const [contract, setContract] = useState("");
  // G10c drawings mount: rail over per-symbol persisted drawings (registry +
  // persistence landed in PR122; this mount shows them on the chart page).
  // Rail manages list/select/delete/lock/hide only — no canvas editing.
  const [drawings, setDrawings] = useState(() => loadDrawings(ticker));
  const [selectedDrawing, setSelectedDrawing] = useState(null);
  const persistDrawings = next => {
    setDrawings(next);
    try { saveDrawings(ticker, next); } catch { /* quota: in-memory only */ }
  };
  const recordNodes = useCallback(async () => {
    if (!onRecordNodes || recording) return;
    setRecording(true); setRecordNote("Recording nodes… (uses market reads)");
    try {
      const result = await onRecordNodes();
      if (result?.recorded) { setRecordNote(""); setReload(n => n + 1); }
      else setRecordNote("Recording did not land — try again.");
    } catch { setRecordNote("Recording did not land — try again."); }
    finally { setRecording(false); }
  }, [onRecordNodes, recording]);
  useEffect(() => { setScope(""); setPayload(null); setPlaying(false); setDrawings(loadDrawings(ticker)); setSelectedDrawing(null); setContractInput(""); setContract(""); }, [ticker]);
  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    let active = true;
    setPayload(null); setStatus("loading"); setPlaying(false);
    const activeScope = forcedScope ?? scope;
    axios.get(`${API}/heatseeker/price-history/${encodeURIComponent(ticker)}`, {
      params: { days, interval_minutes: minutes, include_metric_lines: true, ...(activeScope ? { query_key: activeScope } : {}), ...(contract ? { contract_symbol: contract } : {}) },
      timeout: 30000, signal: controller.signal,
    }).then(({ data }) => {
      if (!active) return;
      if (data?.ticker !== ticker.toUpperCase() || !Array.isArray(data.frames)) { setStatus("error"); return; }
      setPayload(data); setPosition(Math.max(0, (data.frames?.length || 0) - 1)); setStatus("ready");
    }).catch(() => { if (active) setStatus("error"); });
    return () => { active = false; controller.abort(); };
  }, [ticker, days, minutes, scope, forcedScope, open, reload, contract]);
  const frames = payload?.ticker === ticker.toUpperCase() ? payload.frames || [] : [];
  useEffect(() => {
    if (!playing || !open || frames.length < 2) return undefined;
    const id = setInterval(() => setPosition(p => {
      if (p >= frames.length - 1) { setPlaying(false); return p; }
      return p + 1;
    }), 250);
    return () => clearInterval(id);
  }, [playing, open, frames.length]);
  const pauseInteraction = useCallback(() => setPlaying(false), []);
  const controls = <><strong className="price-chart-symbol">{ticker}</strong>
    <select aria-label="Candle interval" title="Candle interval" value={minutes} onChange={e=>setMinutes(Number(e.target.value))}><option value={1}>1 min</option><option value={5}>5 min</option><option value={15}>15 min</option><option value={30}>30 min</option><option value={60}>1 hour</option></select>
    <select aria-label="History sessions" title="History period" value={days} onChange={e=>setDays(Number(e.target.value))}><option value={1}>1 session</option><option value={5}>1 week</option><option value={20}>1 month</option></select></>;
  const historyControls = <>
    {forcedScope==null&&payload?.scopes?.length>1&&<label className="price-history-view">Saved view<select aria-label="Saved node view" value={scope||payload.query_key||""} onChange={e=>setScope(e.target.value)}>{payload.scopes.map((saved,i)=><option key={saved} value={saved}>{savedViewLabel(saved,i)}</option>)}</select></label>}
    {forcedScope!=null&&<span className="price-history-view price-history-external-scope">Screener scope active</span>}
    <button type="button" onClick={()=>setReload(n=>n+1)}>Reload history</button>
    {onRecordNodes&&<button type="button" disabled={recording||status==="loading"} onClick={recordNodes}>{recording?"Recording…":"Record nodes"}</button>}
    {recordNote&&<span role="status">{recordNote}</span>}
    <label className="price-history-contract">Option contract<input aria-label="Option contract symbol" placeholder="OSI, e.g. SPY261017C00650000" value={contractInput} onChange={e=>setContractInput(e.target.value)} /></label>
    <button type="button" disabled={!contractInput.trim()} onClick={()=>setContract(contractInput.trim().toUpperCase())}>Load contract</button>
    {contract&&<button type="button" onClick={()=>{setContract("");setContractInput("");}}>Clear contract</button>}
    {!!frames.length&&<div className="price-history-replay"><button type="button" onClick={()=>{if(!playing&&position>=frames.length-1)setPosition(0);setPlaying(value=>!value);}}>{playing?"Pause replay":"Play replay"}</button><input aria-label="Replay position" type="range" min={0} max={frames.length-1} value={position} onChange={e=>{setPosition(Number(e.target.value));setPlaying(false);}}/><span>{chartTime(frames[position]?.time,true)} New York</span><button type="button" onClick={()=>{setPosition(frames.length-1);setPlaying(false);}}>Show all</button></div>}
  </>;
  const details = <div className="price-history-details">
    {payload?.recording&&<p>{payload.recording.status==="unavailable"?"Saved recording details are unavailable.":payload.recording.durable?"New node readings are saved across restarts.":"Warning: node readings are temporary and may be lost on restart."}{payload.recording.first_at?" First saved reading for "+ticker+": "+chartTime(payload.recording.first_at,true)+" New York.":payload.recording.status==="available"?" No node readings have been saved for "+ticker+" yet.":""} Readings are captured when this symbol's heatmap refreshes.</p>}
    {!!frames.length&&<p>{payload?.price_sessions_returned!=null?payload.price_sessions_returned+" sessions returned. ":""}{payload.candles_with_recorded_nodes} of {frames.length} candles have saved nodes. {payload.bar_seconds?payload.bar_seconds/60+"-minute candles. ":""}Gaps mean no recent saved reading. Chart times use New York.{payload.node_status==="unavailable"?" Saved node history is currently unavailable.":""}{payload.records_truncated?" This period contains more saved readings than can be loaded; use a shorter period.":""}{payload.node_status==="available"&&!payload.candles_with_recorded_nodes?" No recorded nodes match these candles. Earlier missing readings cannot be recreated from today's data.":""}</p>}
    {Object.entries(payload?.metric_line_coverage||{}).map(([metric,coverage])=><p key={metric}>{metric==="vex"?"VEX / Vanna":"Charm"}: {coverage.checked_candles} of {frames.length} candles have qualified saved readings.</p>)}
    {payload?.metric_details_truncated&&<p>Use a shorter period to load older saved lines; this request reached its history limit.</p>}
  </div>;
  const empty = status==="loading"?<p role="status">Loading recorded history...</p>:status==="error"?<p role="alert">History could not be loaded. Try reloading.</p>:<p role="alert">{payload?.price_status==="unavailable"?"Price history is unavailable right now. Reload history to try again.":"No valid price candles were returned for this period."}</p>;
  const readingStatus = !frames.length?"Data details":payload?.node_status==="unavailable"?"Saved lines unavailable":(payload.candles_with_recorded_nodes??"Unknown")+"/"+frames.length+" saved";
  return <section className="panel price-node-history" data-open={open} style={{margin:"12px 0",padding:12}} data-testid="price-node-history">
    {!primary&&<button type="button" className="skylit-trade-mode-btn" aria-expanded={open} onClick={()=>{setOpen(!open);setPlaying(false);}}>Price chart + historical nodes</button>}
    {open&&<RecordedPriceChart ticker={ticker} frames={frames.slice(0,position+1)} revision={ticker+":"+days+":"+minutes+":"+payload?.query_key+":"+reload} onInteract={pauseInteraction} metricCoverage={payload?.metric_line_coverage} toolbarControls={controls} toolbarActions={toolbarActions} historyControls={historyControls} dataDetails={details} readingStatus={readingStatus} emptyContent={empty} showAtlas={showAtlas} exposureLine={exposureLine??payload?.exposure_line??null} darkLevels={darkLevels} cvdLine={cvdLine??payload?.cvd_line??null} contractBars={payload?.contract_bars??null} contractSymbol={payload?.contract_symbol??(contract||null)} contractStatus={payload?.contract_status??null} flowBars={Array.isArray(flowBars)&&flowBars.length===frames.length?flowBars.slice(0,position+1):flowBars}/>}
    {open&&<DrawingRail drawings={drawings} selectedId={selectedDrawing}
      onSelect={setSelectedDrawing}
      onDelete={id => { if (selectedDrawing === id) setSelectedDrawing(null); persistDrawings(reduceDrawings(drawings, { type: "delete", id })); }}
      onToggleLock={id => persistDrawings(drawings.map(d => d.id === id ? { ...d, locked: !d.locked } : d))}
      onToggleHide={id => persistDrawings(drawings.map(d => d.id === id ? { ...d, visible: d.visible === false } : d))} />}
  </section>;
}
