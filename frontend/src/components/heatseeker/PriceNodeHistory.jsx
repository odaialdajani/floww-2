import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";
import RecordedPriceChart from "./RecordedPriceChart";
import DrawingRail from "./chart/drawings/DrawingRail";
import { loadDrawings, saveDrawings } from "./chart/drawings/drawingPersistence";
import { reduceDrawings, createDrawing, geometryFor, magnetPoint, nudgeDrawing, canEdit, suppressesPan, unprojectPoint, viewportFor, TOOLS as DRAWING_TOOLS_6 } from "./chart/drawings/drawingReducer";
import { barAt, sweepExtrema, visibleSnapshot } from "./chart/replay/replayReducer";
import { anchorsFor } from "./chart/drawings/toolRegistry";
import { shouldHandleShortcut } from "./chart/ChartShortcuts";
import { chartTime } from "./recordedPriceChartData";



function savedViewLabel(scope,index){
 const text=typeof scope==="string"?scope:"",part=text.match(/\|expiries=([^|]+)/)?.[1];
 const dates=part?.split(",");
 const valid=dates?.length&&dates.every(value=>/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value+"T00:00:00Z"))&&new Date(value+"T00:00:00Z").toISOString().slice(0,10)===value)&&new Set(dates).size===dates.length;
 if(!valid)return "Saved view "+(index+1)+" - expiry dates unavailable";
 const sorted=[...dates].sort(),tokens=text.split("|")[0].split(":"),mode=tokens.includes("scalp")?"Scalp":tokens.includes("swing")?"Swing":tokens.includes("day")?"Day":"Saved";
 return mode+" | "+sorted.length+" "+(sorted.length===1?"expiry":"expiries")+" | "+sorted[0]+(sorted.length>1?" to "+sorted.at(-1):"");
}

export default function PriceNodeHistory({ ticker = "SPY", open: controlledOpen, onOpenChange, primary = false, toolbarActions = null, exposureLine = null, darkLevels = null, flowBars = null, alertLines = null, showAtlas = true, forcedScope = null, onRecordNodes = null, cvdLine = null, onQuality = null, onReplayState = null }) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? (primary || localOpen);
  const setOpen = value => { setLocalOpen(value); onOpenChange?.(value); };
  const [days, setDays] = useState(5);
  const [minutes, setMinutes] = useState(30);
  const [sessions, setSessions] = useState("regular");
  const [savedView, setSavedView] = useState({ticker,scope:"",followMap:true});
  const scope = savedView.ticker === ticker ? savedView.scope : "";
  const followMap = savedView.ticker === ticker ? savedView.followMap : true;
  const usingMapScope = forcedScope != null && followMap;
  const setScope = value => setSavedView(current => ({ticker,scope:value,followMap:current.ticker===ticker?current.followMap:true}));
  const setFollowMap = value => setSavedView(current => ({ticker,scope:current.ticker===ticker?current.scope:"",followMap:value}));
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState("idle");
  const [reload, setReload] = useState(0);
  const [retryUntil, setRetryUntil] = useState(0);
  const [clock, setClock] = useState(Date.now);
  const retryRemaining = Math.max(0, Math.ceil((retryUntil-clock)/1000));
  const reloadHistory = () => { if(status!=="loading" && !retryRemaining) setReload(n=>n+1); };
  useEffect(()=>{
    if(!retryUntil) return undefined;
    const timer=setInterval(()=>{const now=Date.now();setClock(now);if(now>=retryUntil)setRetryUntil(0);},1000);
    return ()=>clearInterval(timer);
  },[retryUntil]);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordNote, setRecordNote] = useState("");
  // M3 contract premium path: user-picked OSI symbol loads the contract's
  // own OHLCV beside the underlying candles (own $ scale, never mixed).
  const [contractInput, setContractInput] = useState("");
  const [contract, setContract] = useState("");
  // Node velocity: fastest-moving recorded nodes over the last snapshot
  // pair (read-only compare output). Unavailable stays explicit.
  const [velocity, setVelocity] = useState(null);
  const velocityDtText = seconds => {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) return 'unknown window';
    if (seconds >= 3600) return `${+(seconds / 3600).toFixed(2)} h`;
    if (seconds >= 60) return `${+(seconds / 60).toFixed(1)} min`;
    return `${+seconds.toFixed(1)} s`;
  };
  // G10c drawings mount: rail over per-symbol persisted drawings (registry +
  // persistence landed in PR122; this mount shows them on the chart page).
  // Rail manages list/select/delete/lock/hide only — no canvas editing.
  const [drawings, setDrawings] = useState(() => loadDrawings(ticker));
  const [selectedDrawing, setSelectedDrawing] = useState(null);
  // B16 creation/drag/keyboard geometry state: a draft collects logical
  // anchors from pointer events; a drag carries the selected drawing with
  // pan-arbitration; arrow keys nudge. Anchors stay logical {t,p} —
  // projection is derived, so they survive zoom/resize.
  const [draftTool, setDraftTool] = useState(null);
  const [draftAnchors, setDraftAnchors] = useState([]);
  const [dragState, setDragState] = useState(null);
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
  useEffect(() => { setScope(""); setPayload(null); setPlaying(false); setDrawings(loadDrawings(ticker)); setSelectedDrawing(null); setContractInput(""); setContract(""); setVelocity(null); }, [ticker]);
  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    let active = true;
    setPayload(null); setStatus("loading"); setPlaying(false); setRetryUntil(0);
    const activeScope = usingMapScope ? forcedScope : scope;
    axios.get(`${API}/heatseeker/price-history/${encodeURIComponent(ticker)}`, {
      params: { days, interval_minutes: minutes, include_metric_lines: true, sessions, ...(activeScope ? { query_key: activeScope } : {}), ...(contract ? { contract_symbol: contract } : {}) },
      timeout: 30000, signal: controller.signal,
    }).then(({ data }) => {
      if (!active) return;
      if (data?.ticker !== ticker.toUpperCase() || !Array.isArray(data.frames)) { setStatus("error"); return; }
      const seconds=data?.price_failure?.retry_after_seconds;
      if(typeof seconds==="number"&&Number.isFinite(seconds)&&seconds>0&&seconds<=3600){const now=Date.now();setClock(now);setRetryUntil(now+Math.ceil(seconds)*1000);}
      setPayload(data); setPosition(Math.max(0, (data.frames?.length || 0) - 1)); setStatus("ready");
    }).catch(() => { if (active) setStatus("error"); });
    return () => { active = false; controller.abort(); };
  }, [ticker, days, minutes, sessions, scope, forcedScope, usingMapScope, open, reload, contract]);
  const frames = payload?.ticker === ticker.toUpperCase() ? payload.frames || [] : [];
  // B16 pointer/keyboard geometry: the drawing layer projects LOGICAL anchors
  // through the real loaded frames' time/price domain. Zoom/resize changes
  // pixels, never anchor meaning.
  const drawingViewport = viewportFor(frames, 600, 320);
  const nudgeStep = drawingViewport
    ? { dt: (drawingViewport.tMax - drawingViewport.tMin) / 100, dp: (drawingViewport.pMax - drawingViewport.pMin) / 100 }
    : { dt: 60000, dp: 0.5 };
  const layerPoint = event => {
    const rect = event.currentTarget.getBoundingClientRect();
    // jsdom reports zero rects; fall back to viewBox coords so the geometry
    // path stays testable. Real browsers always have non-zero rects.
    const x = rect.width ? event.clientX - rect.left : event.clientX;
    const y = rect.height ? event.clientY - rect.top : event.clientY;
    return unprojectPoint({ x, y }, drawingViewport);
  };
  const commitDraft = point => {
    const nextAnchors = [...draftAnchors, point];
    if (nextAnchors.length >= anchorsFor(draftTool)) {
      persistDrawings(reduceDrawings(drawings, { type: "add", drawing: createDrawing(draftTool, nextAnchors) }));
      setDraftTool(null); setDraftAnchors([]);
    } else setDraftAnchors(nextAnchors);
  };
  const onDrawingLayerPointerDown = event => {
    if (!drawingViewport) return;
    // While dragging a selected drawing, pointer events never start a pan:
    // the layer owns the gesture (arbitration contract: suppressesPan).
    if (dragState) { event.stopPropagation(); return; }
    const raw = layerPoint(event);
    if (!raw) return;
    const point = magnetPoint(raw, frames, 0.25, drawingViewport);
    if (draftTool) { event.stopPropagation(); commitDraft(point); }
  };
  const onDrawingElementPointerDown = (event, drawing) => {
    if (!drawingViewport || !canEdit(drawing)) { if (drawing) setSelectedDrawing(drawing.id); return; }
    event.stopPropagation();
    setSelectedDrawing(drawing.id);
    const start = layerPoint(event);
    if (!start) return;
    setDragState({ id: drawing.id, anchors: drawing.anchors.map(a => ({ ...a })), start, suppressPan: true });
  };
  const onDrawingLayerPointerMove = event => {
    if (!dragState || !drawingViewport) return;
    event.stopPropagation();
    const now = layerPoint(event);
    if (!now) return;
    const dt = now.t - dragState.start.t, dp = now.p - dragState.start.p;
    persistDrawings(reduceDrawings(drawings, { type: "update", id: dragState.id,
      anchors: dragState.anchors.map(a => ({ t: a.t + dt, p: a.p + dp })) }));
  };
  const onDrawingLayerPointerUp = event => {
    if (!dragState) return;
    event.stopPropagation();
    setDragState(null);
  };
  // Keyboard geometry: Escape cancels an active draft; arrows nudge the
  // selected (unlocked) drawing by one logical step. Typing fields never
  // trigger drawing keys.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = event => {
      if (!shouldHandleShortcut(event)) return;
      if (event.key === "Escape" && draftTool) { setDraftTool(null); setDraftAnchors([]); return; }
      if (!selectedDrawing) return;
      const drawing = drawings.find(d => d.id === selectedDrawing);
      if (!canEdit(drawing)) return;
      const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] }[event.key];
      if (!dir) return;
      event.preventDefault();
      persistDrawings(reduceDrawings(drawings, { type: "nudge", id: selectedDrawing, dt: dir[0] * nudgeStep.dt, dp: dir[1] * nudgeStep.dp }));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, drawings, selectedDrawing, draftTool, nudgeStep]);
  const comparisonScope = typeof payload?.query_key === "string" ? payload.query_key : "";
  // B06 workspace quality contract (inert without a listener): the pane
  // reports its own data-quality truth — latest observed reading time,
  // saved-node coverage, truncation (partial bars), capability reason and
  // the manual-retry state. Unknowns stay unknown; nothing is invented.
  useEffect(() => {
    if (!onQuality) return;
    onQuality({
      status,
      sourceTime: frames.length ? frames[frames.length - 1].time : null,
      coverage: frames.length ? `${payload?.candles_with_recorded_nodes ?? 0} of ${frames.length} candles carry saved nodes` : "no candles loaded",
      partialBars: payload?.records_truncated ? "period contains more saved readings than can be loaded" : null,
      capability: payload?.node_status ?? null,
      retry: retryRemaining > 0 ? `manual retry in ${retryRemaining}s` : "manual retry available",
    });
  }, [onQuality, status, frames.length, payload, retryRemaining]);
  // B15 replay algebra reporting (inert without a listener, like onQuality):
  // the pane reports its REAL frames through the replay algebra — cursor,
  // partial/completed bar (a bar completes only once its window closes past
  // the cursor), extrema swept strictly at-or-before the cursor (future bars
  // can never extend the historical range), newest known-at snapshot, and the
  // provenance of the newest visible frame (live at the advancing head,
  // replay when scrubbing/rewinding). Replay-derived events never enter live
  // caches — the consumer routes them through replayReducer's caches.
  const lastReportedPosition = useRef(-1);
  useEffect(() => {
    if (!onReplayState) return undefined;
    if (!frames.length) { onReplayState(null); return undefined; }
    const cursorFrame = frames[Math.min(position, frames.length - 1)];
    const cursor = Date.parse(cursorFrame.time);
    const windowEnd = frames[position + 1] ? Date.parse(frames[position + 1].time) : null;
    const events = frames.map(f => ({ id: f.time, event_time: Date.parse(f.time), available_at: Date.parse(f.time), open: f.open, close: f.close }));
    const bar = barAt(events, cursor, windowEnd);
    const visible = frames.slice(0, position + 1).map(f => ({ time: Date.parse(f.time), high: f.high, low: f.low }));
    const extrema = sweepExtrema(visible, cursor);
    const snapshot = visibleSnapshot(frames.map(f => ({ id: f.time, known_at: Date.parse(f.time), close: f.close })), cursor);
    const wentBack = position < lastReportedPosition.current;
    const origin = (playing || wentBack) ? "replay" : "live";
    const delta = position === lastReportedPosition.current
      ? []
      : [{ id: cursorFrame.time, symbol: ticker.toUpperCase(), value: cursorFrame.close, time: cursor, origin }];
    lastReportedPosition.current = position;
    onReplayState({
      cursor, cursorTime: cursorFrame.time, playing, bar, extrema,
      snapshotKnownAt: snapshot ? snapshot.known_at : null,
      visibleBars: position + 1, totalBars: frames.length, delta,
    });
    return undefined;
  }, [onReplayState, frames, position, playing]); // eslint-disable-line react-hooks/exhaustive-deps
  const comparisonTime = frames[position]?.time;
  const awareTime = value => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    ? Date.parse(value) : NaN;
  const cutoff = awareTime(comparisonTime);
  // Include view controls so the old result disappears on the first render
  // of a new request, before effects can clear the old history payload.
  const velocityRequestKey = JSON.stringify([ticker, comparisonScope, comparisonTime,
    days, minutes, sessions, scope, forcedScope, usingMapScope, reload, contract]);
  const comparable = !playing && status === "ready" && !!comparisonScope && Number.isFinite(cutoff);
  useEffect(() => {
    if (!open || !comparable) return undefined;
    const controller = new AbortController();
    let active = true;
    setVelocity(null);
    // A scrub or replay must not send an attribute request per animation tick.
    const timer = setTimeout(() => {
      Promise.resolve(axios.get(`${API}/solstice/attribute/${encodeURIComponent(ticker)}`, {
        params: { query_key: comparisonScope, as_of: comparisonTime },
        timeout: 15000, signal: controller.signal,
      })).then(({ data }) => {
        if (active) setVelocity({ requestKey: velocityRequestKey, data });
      }).catch(() => { if (active) setVelocity({ requestKey: velocityRequestKey, data: { status: "unavailable" } }); });
    }, 150);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [ticker, open, comparable, comparisonScope, comparisonTime, velocityRequestKey]);
  const comparison = comparable && velocity?.requestKey === velocityRequestKey ? velocity.data : null;
  const pair = [comparison?.from, comparison?.to];
  const pairMatches = comparison?.ticker === ticker.toUpperCase()
    && comparison?.query_key === comparisonScope
    && pair.every(observation => typeof observation?.id === "string" && observation.id
      && observation.query_key === comparisonScope
      && Number.isFinite(awareTime(observation.asof)) && awareTime(observation.asof) <= cutoff
      && Number.isFinite(awareTime(observation.received_at)) && awareTime(observation.received_at) <= cutoff)
    && pair[0].id !== pair[1].id && awareTime(pair[0].asof) < awareTime(pair[1].asof)
    && typeof comparison.velocity_dt_seconds === "number" && Number.isFinite(comparison.velocity_dt_seconds)
    && comparison.velocity_dt_seconds > 0;
  const velocityRows = pairMatches && comparison?.status === "ok" && Array.isArray(comparison.velocities)
    ? comparison.velocities.filter(row => row?.status === "retained"
      && typeof row.strike === "number" && Number.isFinite(row.strike) && row.strike > 0
      && typeof row.velocity === "number" && Number.isFinite(row.velocity)).slice(0, 5) : [];
  const velocityReasons = {
    CUTOFF_INVALID: "the candle time could not be verified.",
    DAY_INVALID: "the recorded comparison day could not be verified.",
    DAY_MISMATCH: "comparison day does not match the candle time.",
    SCOPE_UNVERIFIED: "saved scope or source details could not be verified.",
    NO_MATCHING_OBSERVATIONS: "no recorded observations match this saved view at this candle.",
    OBSERVATION_STALE: "the latest recorded observation is older than 15 minutes.",
    COMPARABLE_PAIR_MISSING: "need 2+ comparable recorded snapshots at this candle.",
  };
  const velocityNote = playing ? "paused during replay."
    : !comparable ? "saved scope or candle time is unavailable."
    : !comparison ? "checking this saved view and candle time."
    : comparison.status === "history_unavailable"
      ? velocityReasons[comparison.reason_code] || velocityReasons.COMPARABLE_PAIR_MISSING
    : pairMatches && comparison.status === "ok" ? "no comparable nodes in this recorded window."
    : "no verified comparison matches this saved view and candle time.";
  useEffect(() => {
    if (!playing || !open || frames.length < 2) return undefined;
    const id = setInterval(() => setPosition(p => {
      if (p >= frames.length - 1) { setPlaying(false); return p; }
      return p + 1;
    }), 250);
    return () => clearInterval(id);
  }, [playing, open, frames.length]);
  const pauseInteraction = useCallback(() => setPlaying(false), []);
  // 2026-10-18 compact toolbar: symbol/interval stay prominent; the loaded
  // history range AND session coverage stay visible as text, while their two
  // picker selects live inside Chart tools. Labels mirror the option text so
  // the summary never claims a different basis than the picker serves.
  const historyDayLabel = { 1: "1 session", 5: "1 week", 20: "1 month", 60: "3 months", 260: "1 year", 2600: "5 years" }[days]
    ?? `${days} sessions`;
  const historySessionLabel = sessions === "all" ? "all sessions" : "regular hours";
  const controls = <><strong className="price-chart-symbol">{ticker}</strong>
    <select aria-label="Candle interval" title="Candle interval" value={minutes} onChange={e=>setMinutes(Number(e.target.value))}><option value={1}>1 min</option><option value={5}>5 min</option><option value={15}>15 min</option><option value={30}>30 min</option><option value={60}>1 hour</option></select>
    <span className="price-history-summary" data-testid="price-history-summary" title="Selected history period and session coverage">{historyDayLabel} · {historySessionLabel}</span></>;
  const historyPeriodControls = <>
    <label className="price-history-view">History period<select aria-label="History sessions" title="History period" value={days} onChange={e=>setDays(Number(e.target.value))}><option value={1}>1 session</option><option value={5}>1 week</option><option value={20}>1 month</option><option value={60}>3 months</option><option value={260}>1 year</option><option value={2600}>5 years</option></select></label>
    <label className="price-history-view">Session coverage<select aria-label="Session coverage" title="Which trading sessions to load" value={sessions} onChange={e=>setSessions(e.target.value)}><option value="regular">Regular hours</option><option value="all">All sessions</option></select></label>
  </>;
  const historyControls = <>
    {!usingMapScope&&payload?.scopes?.length>1&&<label className="price-history-view">Saved view<select aria-label="Saved node view" value={scope||payload.query_key||""} onChange={e=>setScope(e.target.value)}>{payload.scopes.map((saved,i)=><option key={saved} value={saved}>{savedViewLabel(saved,i)}</option>)}</select></label>}
    {forcedScope!=null&&<label className="price-history-view"><input type="checkbox" aria-label="Follow map scope" checked={followMap} onChange={event=>setFollowMap(event.target.checked)}/>Follow map scope</label>}
    {usingMapScope&&<span className="price-history-view price-history-external-scope">Map scope active</span>}
    <button type="button" disabled={status==="loading"||retryRemaining>0} onClick={reloadHistory}>Reload history</button>
    {onRecordNodes&&<button type="button" disabled={recording||status==="loading"} onClick={recordNodes}>{recording?"Recording…":"Record nodes"}</button>}
    {recordNote&&<span role="status">{recordNote}</span>}
    <label className="price-history-contract">Option contract<input aria-label="Option contract symbol" placeholder="OSI, e.g. SPY261017C00650000" value={contractInput} onChange={e=>setContractInput(e.target.value)} /></label>
    <button type="button" disabled={!contractInput.trim()} onClick={()=>setContract(contractInput.trim().toUpperCase())}>Load contract</button>
    {contract&&<button type="button" onClick={()=>{setContract("");setContractInput("");}}>Clear contract</button>}
  </>;
  // Replay affordances stay visible while Chart tools is closed: pause state
  // and candle time must remain readable during an active replay.
  const replayControls = !!frames.length&&<div className="price-history-replay"><button type="button" onClick={()=>{if(!playing&&position>=frames.length-1)setPosition(0);setPlaying(value=>!value);}}>{playing?"Pause replay":"Play replay"}</button><input aria-label="Replay position" type="range" min={0} max={frames.length-1} value={position} onChange={e=>{setPosition(Number(e.target.value));setPlaying(false);}}/><span>{chartTime(frames[position]?.time,true)} New York</span><button type="button" onClick={()=>{setPosition(frames.length-1);setPlaying(false);}}>Latest candle</button></div>;
  const missingMapScope=usingMapScope&&payload?.node_status!=="unavailable"&&Array.isArray(payload?.scopes)&&!payload.scopes.includes(forcedScope);
  const details = <div className="price-history-details">
    {payload?.recording&&<p>{payload.recording.status==="unavailable"?"Saved recording details are unavailable.":payload.recording.durable?"New node readings are saved across restarts.":"Warning: node readings are temporary and may be lost on restart."}{payload.recording.first_at?" First saved reading for "+ticker+": "+chartTime(payload.recording.first_at,true)+" New York.":payload.recording.status==="available"?" No node readings have been saved for "+ticker+" yet.":""} Readings are captured when this symbol's heatmap refreshes.</p>}
    {!!frames.length&&<p>{payload?.price_sessions_returned!=null?payload.price_sessions_returned+" sessions returned. ":""}{payload.candles_with_recorded_nodes} of {frames.length} candles have saved nodes. {payload.bar_seconds?payload.bar_seconds/60+"-minute candles. ":""}Gaps mean no recent saved reading. Chart times use New York.{payload.node_status==="unavailable"?" Saved node history is currently unavailable.":""}{payload.records_truncated?" This period contains more saved readings than can be loaded; use a shorter period.":""}{payload.node_status==="available"&&!payload.candles_with_recorded_nodes?" No recorded nodes match these candles. Earlier missing readings cannot be recreated from today's data.":""}</p>}
    {payload?.node_status!=="unavailable"&&payload?.node_coverage?.gap_counts&&<p>Saved-node gaps: {payload.node_coverage.gap_counts.no_prior_observation} with no earlier observation; {payload.node_coverage.gap_counts.observation_too_old} older than the saved-reading limit; {payload.node_coverage.gap_counts.recorded_without_nodes} recorded without node levels. Other scopes are not substituted.</p>}
    {Object.entries(payload?.metric_line_coverage||{}).map(([metric,coverage])=><p key={metric}>{metric==="vex"?"VEX / Vanna":"Charm"}: {coverage.checked_candles} of {frames.length} candles have qualified saved readings.</p>)}
    {payload?.metric_details_truncated&&<p>Use a shorter period to load older saved lines; this request reached its history limit.</p>}
    {missingMapScope&&<p>No saved readings match the map scope at these candle times. Open Chart tools and turn off Follow map scope to choose an older saved view. No other scope was substituted.</p>}
    {status==="ready"&&!velocityRows.length&&<p data-testid="velocity-unavailable">Node velocity unavailable — {velocityNote}</p>}
  </div>;
  const failureMessages = {inflight_cap:"Price history is waiting for a free provider slot.",host_cooldown:"Public is cooling down after a request limit.",token_bucket:"The price-history request allowance is temporarily used up.",budget_unavailable:"Price-history allowance could not be checked. No provider request was made.",provider_unavailable:"Price history could not be read from Public. No old prices were substituted.",invalid_price_bars:"Returned price bars failed validation; no candles were invented."};
  const failure = failureMessages[payload?.price_failure?.reason];
  const retryNote = retryRemaining>0?` Retry is available in ${retryRemaining} seconds.`:"";
  const empty = status==="loading"?<p role="status">Loading recorded history...</p>:<div><p role="alert">{status==="error"?"History could not be loaded.":payload?.price_status==="unavailable"?(failure?failure+retryNote:"Price history is unavailable right now."):"No valid price candles were returned for this period."}</p><button type="button" aria-label="Retry price history" disabled={retryRemaining>0} onClick={reloadHistory}>{retryRemaining?`Retry in ${retryRemaining}s`:"Retry history"}</button></div>;
  const readingStatus = !frames.length?"Data details":payload?.node_status==="unavailable"?"Saved lines unavailable":missingMapScope?"Saved map scope missing":(payload.candles_with_recorded_nodes??"Unknown")+"/"+frames.length+" saved";
  return <section className="panel price-node-history" data-open={open} style={{margin:"12px 0",padding:12}} data-testid="price-node-history">
    {!primary&&<button type="button" className="skylit-trade-mode-btn" aria-expanded={open} onClick={()=>{setOpen(!open);setPlaying(false);}}>Price chart + historical nodes</button>}
    {open&&<RecordedPriceChart ticker={ticker} frames={frames.slice(0,position+1)} revision={ticker+":"+days+":"+minutes+":"+payload?.query_key+":"+reload} onInteract={pauseInteraction} metricCoverage={payload?.metric_line_coverage} toolbarControls={controls} toolbarActions={toolbarActions} historyPeriodControls={historyPeriodControls} historyControls={historyControls} replayControls={replayControls} dataDetails={details} readingStatus={readingStatus} emptyContent={empty} showAtlas={showAtlas} exposureLine={exposureLine??payload?.exposure_line??null} darkLevels={darkLevels} alertLines={alertLines??null} cvdLine={cvdLine??payload?.cvd_line??null} contractBars={payload?.contract_bars??null} contractSymbol={payload?.contract_symbol??(contract||null)} contractStatus={payload?.contract_status??null} flowBars={Array.isArray(flowBars)&&flowBars.length===frames.length?flowBars.slice(0,position+1):flowBars}/>}
    {open&&forcedScope!=null&&!followMap&&<p role="note">Saved-view review — these recorded expiry dates are not the current map scope.</p>}
    {/* P1-5 (UX review): secondary strips below the chart collapse into slim
        lines — drawings behind a one-line disclosure, velocity as an inline
        hairline row. Rail testids and interactions are unchanged. */}
    {open&&<details className="price-history-drawings" data-testid="drawings-disclosure">
      <summary role="button" aria-label="Drawings">Drawings{drawings.length ? ` · ${drawings.length}` : ""}</summary>
      {/* B16: real coordinate conversion + pointer/keyboard geometry. The
          layer renders every visible drawing through the live frames'
          time/price domain; creation picks a tool then places anchors
          (OHLC-magnet); a selected drawing drags with pan suppressed;
          arrows nudge; Escape cancels; Undo pops. */}
      {drawingViewport&&<svg className="drawing-layer" data-testid="drawing-layer" viewBox="0 0 600 320" width="600" height="320"
        data-arbitration={dragState ? "drawing-drag" : "idle"} role="img" aria-label="Drawing layer"
        onPointerDown={onDrawingLayerPointerDown} onPointerMove={onDrawingLayerPointerMove} onPointerUp={onDrawingLayerPointerUp} onPointerLeave={onDrawingLayerPointerUp}>
        <rect x="0" y="0" width="600" height="320" fill="#0d151d" stroke="#232c36" />
        {drawings.filter(d=>d.visible!==false).map(d=>{const g=geometryFor(d.tool,d.anchors,drawingViewport);
          if(!g)return null;
          const common={"data-testid":"drawing-shape","data-drawing-id":d.id,"data-selected":d.id===selectedDrawing,stroke:d.id===selectedDrawing?"#e3c16a":"#7fa6c0",strokeWidth:d.id===selectedDrawing?2:1.2,fill:"none",onPointerDown:e=>onDrawingElementPointerDown(e,d)};
          if(g.kind==="rect")return <rect key={d.id} {...common} x={g.x} y={g.y} width={Math.max(g.width,2)} height={Math.max(g.height,2)} />;
          if(g.kind==="label")return <text key={d.id} {...common} x={g.x} y={g.y} fontSize="12" fill="#dce8f2">{d.text||"text"}</text>;
          return <polyline key={d.id} {...common} points={g.points.map(pt=>`${pt.x},${pt.y}`).join(" ")} />;})}
        {draftAnchors.map((a,i)=>{const pt=geometryFor("text",[a],drawingViewport);
          return pt?<circle key={"draft-"+i} data-testid="draft-anchor" cx={pt.x} cy={pt.y} r="4" fill="#e3c16a" />:null;})}
      </svg>}
      <DrawingRail drawings={drawings} selectedId={selectedDrawing}
      tools={DRAWING_TOOLS_6.map(id=>({id,anchors:anchorsFor(id)}))} draftTool={draftTool}
      onToolPick={id=>{setDraftTool(draftTool===id?null:id);setDraftAnchors([]);}}
      onUndo={()=>persistDrawings(reduceDrawings(drawings,{type:"undo"}))}
      onCancelDraft={()=>{setDraftTool(null);setDraftAnchors([]);}}
      onSelect={setSelectedDrawing}
      onDelete={id => { if (selectedDrawing === id) setSelectedDrawing(null); persistDrawings(reduceDrawings(drawings, { type: "delete", id })); }}
      onToggleLock={id => persistDrawings(drawings.map(d => d.id === id ? { ...d, locked: !d.locked } : d))}
      onToggleHide={id => persistDrawings(drawings.map(d => d.id === id ? { ...d, visible: d.visible === false } : d))} />
    </details>}
    {open&&velocityRows.length>0&&(
      <div className="price-history-velocity" data-testid="velocity-strip" aria-label="Fastest-moving nodes">
        <strong>Node velocity</strong><span> over {velocityDtText(comparison.velocity_dt_seconds)}</span>
        <small> · {chartTime(comparison.from.asof,true)} to {chartTime(comparison.to.asof,true)} New York · same saved scope</small>
        <ul>{velocityRows.map(row=>{
          const rate = typeof row.velocity==="number"&&Number.isFinite(row.velocity)
            ? (row.velocity>=0?"+":"")+row.velocity.toLocaleString("en-US",{maximumFractionDigits:1})+"/s" : "n/a";
          const growth = typeof row.growth==="number"&&Number.isFinite(row.growth)
            ? `${(row.growth*100).toFixed(1)}%` : "n/a";
          return <li key={row.strike} data-testid="velocity-row">strike {row.strike}: {rate} ({growth})</li>;})}</ul>
      </div>)}

  </section>;
}
