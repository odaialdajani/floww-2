import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";
import RecordedPriceChart from "./RecordedPriceChart";
import DrawingRail from "./chart/drawings/DrawingRail";
import { loadPresets, savePresets, PRESET_STORAGE_VERSION } from "./chart/drawings/presetPersistence";
import { defaultPresetFor, createPreset, updatePresetStyle, deletePreset, resetPresetStyleToBuiltIn, toggleStar, setActivePreset, applyPresetToDrawing } from "./chart/drawings/presetManager";
import { buildPresetRenderSpec } from "./chart/drawings/presetRendering";
import StockInspector from "./chart/StockInspector";
import IndicatorsPanel from "./chart/indicators/IndicatorsPanel";
import { loadDrawings, saveDrawings } from "./chart/drawings/drawingPersistence";
import { reduceDrawings, createDrawing, geometryFor, magnetPoint, nudgeDrawing, canEdit, suppressesPan, unprojectPoint, viewportFor, TOOLS as REDUCER_TOOLS } from "./chart/drawings/drawingReducer";
import { barAt, sweepExtrema, visibleSnapshot } from "./chart/replay/replayReducer";
import { anchorsFor } from "./chart/drawings/toolRegistry";
import { shouldHandleShortcut } from "./chart/ChartShortcuts";
import { useChartData } from "./chart/useChartData";
import { STUDIES, getStudy, createStudyInstance, validateStudySettings, studySpecs, paneEligibility } from "./chart/indicators/registry";
import { loadStudyInstances, saveStudyInstances } from "./chart/persistence/studyStore";
import { eligibleMappedPairsFor, parseMappedLevelsResponse } from "./chart/mappedLevelsClient";
import { projectWhitespace } from "./chart/scenarioProjection";
import { chartTime } from "./recordedPriceChartData";



function savedViewLabel(scope,index){
 const text=typeof scope==="string"?scope:"",part=text.match(/\|expiries=([^|]+)/)?.[1];
 const dates=part?.split(",");
 const valid=dates?.length&&dates.every(value=>/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value+"T00:00:00Z"))&&new Date(value+"T00:00:00Z").toISOString().slice(0,10)===value)&&new Set(dates).size===dates.length;
 if(!valid)return "Saved view "+(index+1)+" - expiry dates unavailable";
 const sorted=[...dates].sort(),tokens=text.split("|")[0].split(":"),mode=tokens.includes("scalp")?"Scalp":tokens.includes("swing")?"Swing":tokens.includes("day")?"Day":"Saved";
 return mode+" | "+sorted.length+" "+(sorted.length===1?"expiry":"expiries")+" | "+sorted[0]+(sorted.length>1?" to "+sorted.at(-1):"");
}

export default function PriceNodeHistory({ ticker = "SPY", open: controlledOpen, onOpenChange, primary = false, toolbarActions = null, exposureLine = null, darkLevels = null, flowBars = null, alertLines = null, showAtlas = true, forcedScope = null, onRecordNodes = null, cvdLine = null, onQuality = null, onEnvelopes = null, fitMode = "fit-visible", onReplayState = null, onReplayController = null, replaySourceId = null, replayEpoch = null, sync = null, onSyncEvent = null }) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? (primary || localOpen);
  const setOpen = value => { setLocalOpen(value); onOpenChange?.(value); };
  const [days, setDays] = useState(5);
  const [minutes, setMinutes] = useState(30);
  const [sessions, setSessions] = useState("regular");
  // S2 link dimensions: the pane adopts a synced interval/session when the
  // sync sequence advances (adoption never re-emits — no echo loop).
  const lastSyncSeq = useRef(0);
  useEffect(() => {
    if (!sync || typeof sync !== 'object' || !sync.seq || sync.seq === lastSyncSeq.current) return;
    lastSyncSeq.current = sync.seq;
    if (sync.interval != null && sync.interval !== minutes) setMinutes(Number(sync.interval));
    if (sync.session != null && sync.session !== sessions) setSessions(String(sync.session));
  }, [sync]); // eslint-disable-line react-hooks/exhaustive-deps
  const [savedView, setSavedView] = useState({ticker,scope:"",followMap:true});
  const scope = savedView.ticker === ticker ? savedView.scope : "";
  const followMap = savedView.ticker === ticker ? savedView.followMap : true;
  const usingMapScope = forcedScope != null && followMap;
  const setScope = value => setSavedView(current => ({ticker,scope:value,followMap:current.ticker===ticker?current.followMap:true}));
  const setFollowMap = value => setSavedView(current => ({ticker,scope:current.ticker===ticker?current.scope:"",followMap:value}));
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
  // CHART-C090: Alt+L/Alt+S arm the risk box's side; the rail pick keeps the last side.
  const [draftSide, setDraftSide] = useState("long");
  const [draftAnchors, setDraftAnchors] = useState([]);
  const [dragState, setDragState] = useState(null);
  const persistDrawings = next => {
    setDrawings(next);
    try { saveDrawings(ticker, next); } catch { /* quota: in-memory only */ }
  };
  // ── B17 preset production adoption (C091/C129/C130/C131) ──────────────────
  // The caller state for the delivered preset manager: ONE scoped list bound
  // to this pane's ticker, loaded per scope, persisted only through complete
  // successful whole-store operations. Local only — no cloud/account sync.
  const [presetList, setPresetList] = useState([]);
  const [presetError, setPresetError] = useState(null);
  useEffect(() => {
    setPresetError(null);
    // future storage envelopes are not ours to interpret: refuse to load AND
    // to overwrite — surfaced honestly, never a silent empty
    try {
      const raw = window.localStorage.getItem('floww.drawing.presets.' + String(ticker || '').toUpperCase());
      const env = raw ? JSON.parse(raw) : null;
      if (env && typeof env.v === 'number' && env.v > PRESET_STORAGE_VERSION) {
        setPresetList([]);
        setPresetError('newer preset storage version (' + env.v + ') — presets not loaded; nothing overwritten');
        return;
      }
    } catch { /* fall through to the delivered loader */ }
    setPresetList(loadPresets(ticker));
  }, [ticker]);
  const commitPresets = next => {
    // whole-store write; on ANY refusal the operation is dropped and the
    // error is surfaced — the in-memory list never drifts from the store
    try { savePresets(ticker, next); setPresetList(next); setPresetError(null); return true; }
    catch (err) { setPresetError(String(err && err.message ? err.message : err)); return false; }
  };
  const requestPresetOp = result => {
    if (!result || result.ok === false) { setPresetError(result && result.error ? result.error : 'preset operation refused'); return false; }
    return commitPresets(result.list);
  };
  // Visual-reset-20261025: the contextual right workspace — one dock, three
  // stable tabs (Indicators / Data / Review), explicit close, authoritative
  // selection stays with this pane. Open by default on desktop entry so the
  // studies/catalog discovery is never buried under Tools→another disclosure.
  const [chartOverlays, setChartOverlays] = useState({ vwap: true, bands: false, profile: true, cvd: true, volume: true });
  const [dockOpen, setDockOpen] = useState(true);
  const [dockTab, setDockTab] = useState("indicators");
  const openDock = tab => { setDockTab(tab); setDockOpen(true); };
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
  useEffect(() => { setScope(""); setPlaying(false); setDrawings(loadDrawings(ticker)); setSelectedDrawing(null); setContractInput(""); setContract(""); setVelocity(null); }, [ticker]);
  const activeScope = usingMapScope ? forcedScope : scope;
  // B05 mount (C2-PRODUCER-CONTRACTS-20261024.json): the pane's price-history
  // read goes through the shared useChartData hook — one PRIVATE session per
  // pane, superseded identities aborted, identical in-flight reads shared.
  // The hook's dedupeKey slots carry the contract's four dimensions; the
  // remaining request dimensions (days, contract, the manual reload counter)
  // ride the scope slot so a change ABORTS the superseded in-flight query
  // instead of sharing it. The wire params themselves come from the fetcher.
  const paneIdentity = `${activeScope}|days=${days}|contract=${contract || "-"}|reload=${reload}`;
  const fetchHistory = useCallback(({ signal }) => axios.get(
    `${API}/heatseeker/price-history/${encodeURIComponent(ticker)}`, {
      params: { days, interval_minutes: minutes, include_metric_lines: true, include_envelopes: true, sessions, ...(activeScope ? { query_key: activeScope } : {}), ...(contract ? { contract_symbol: contract } : {}) },
      timeout: 30000, signal,
    }
  ).then(({ data }) => {
    // Served truth -> badge truth: the route's typed price_failure vocabulary
    // carries the budget/outage reasons; nothing else is inferred (the route
    // never stale-serves, so cached/stale stay unflagged).
    const reason = data?.price_failure?.reason;
    const budget = reason === "inflight_cap" || reason === "host_cooldown" || reason === "token_bucket" || reason === "budget_unavailable";
    const outage = reason === "provider_unavailable" || reason === "invalid_price_bars";
    const valid = data?.ticker === ticker.toUpperCase() && Array.isArray(data.frames);
    // The pane-owned pieces arm HERE — the same place the incumbent's single
    // .then armed them — so the hook's [status, badge, data] commit renders
    // together with the replay cursor and the retry gate (a typed refusal and
    // its retry note can never render apart). The signal guard keeps an
    // aborted/superseded query from arming anything; the consumer effect
    // below re-applies both from the ACTIVE read, so a superseded arming
    // self-heals one commit later.
    if (valid && !signal?.aborted) {
      setPosition(Math.max(0, (data.frames?.length || 0) - 1));
      const seconds = data?.price_failure?.retry_after_seconds;
      if (typeof seconds === "number" && Number.isFinite(seconds) && seconds > 0 && seconds <= 3600) {
        const now = Date.now(); setClock(now); setRetryUntil(now + Math.ceil(seconds) * 1000);
      }
    }
    if (!valid) {
      return { data: null, error: true, budgetExhausted: budget, outage };
    }
    return { data, budgetExhausted: budget, outage };
  }).catch(error => {
    // A transport rejection is an unreachable read, never a live one.
    throw Object.assign(error instanceof Error ? error : new Error("history read failed"), { outage: true });
  }), [ticker, days, minutes, sessions, activeScope, contract]);
  const { data: readData, status, badge: readBadge } = useChartData({
    symbol: ticker, interval: minutes, session: sessions, scope: paneIdentity,
    fetcher: fetchHistory, enabled: open,
  });
  // Single-commit application: the payload is DERIVED from the hook's own
  // state (status ready ⇒ this read's data, anything else ⇒ none), so the
  // pane renders data exactly when the hook commits it — no intermediate
  // ready-without-payload frame, no extra commit for consumers to await.
  const payload = status === "ready" && readData ? readData : null;
  // Generation-gated corrector: re-apply the replay cursor and the retry
  // gate from the ACTIVE read (heals any superseded arming), and stop replay
  // plus clear the retry clock the moment a new request starts loading.
  useEffect(() => {
    if (status === "ready" && readData) {
      setPosition(Math.max(0, (readData.frames?.length || 0) - 1));
      const seconds = readData?.price_failure?.retry_after_seconds;
      if (typeof seconds === "number" && Number.isFinite(seconds) && seconds > 0 && seconds <= 3600) {
        const now = Date.now(); setClock(now); setRetryUntil(now + Math.ceil(seconds) * 1000);
      } else if (readData && !readData.price_failure?.retry_after_seconds) {
        setRetryUntil(0);
      }
    } else if (status === "loading") {
      setPlaying(false); setRetryUntil(0);
    }
  }, [status, readData]);
  const frames = payload?.ticker === ticker.toUpperCase() ? payload.frames || [] : [];
  // B08 ACTUAL STUDY INSTANCES (C045-C048): per-pane instances through the ONE
  // registry, persisted per symbol (versioned store, quota-capped). Two
  // differently configured studies compute independent series from THIS pane's
  // own frames via the existing priceStudies primitives — no second engine.
  const [studyInstances, setStudyInstances] = useState(() => loadStudyInstances(ticker));
  const [studyAddPeriod, setStudyAddPeriod] = useState("20");
  const [studyAddMultiple, setStudyAddMultiple] = useState("2");
  const [studyRefusal, setStudyRefusal] = useState(null);
  useEffect(() => { setStudyInstances(loadStudyInstances(ticker)); setStudyRefusal(null); }, [ticker]);
  const commitStudies = next => {
    try { saveStudyInstances(ticker, next); setStudyInstances(next); setStudyRefusal(null); }
    catch (error) { setStudyRefusal(error?.message === "study quota exceeded" ? "Study limit reached — remove one first." : "Study settings refused — check period and multiple."); }
  };
  const addStudy = (kind, settingsOverride) => {
    // pane source-eligibility first — a pane without the required source
    // refuses creation with the typed reason (contract v2), never a zero render
    const eligible = paneEligibility(kind, frames);
    if (!eligible.ok) { setStudyRefusal(eligible.reason); return; }
    const settings = settingsOverride ? { ...settingsOverride }
      : kind === "bollinger" ? { period: Number(studyAddPeriod), multiple: Number(studyAddMultiple) }
      : kind === "vwap" ? { source: "hlc3", bandBasis: "std", multipliers: [1, 2, 3], bands: false, anchor: "session" }
      : kind === "volume" ? {}
      : kind === "exposure-vwap" ? null
      : { period: Number(studyAddPeriod) };
    if (settings === null || !validateStudySettings(kind, settings)) {
      setStudyRefusal(kind === "exposure-vwap" ? "Exposure VWAP needs an eligible board source — not creatable on the price pane."
        : kind === "bollinger" ? "Bollinger needs a whole period 10..500 and a multiple 0.5..5."
        : kind === "vwap" ? "VWAP settings refused." : "Period must be a whole number 1..500.");
      return;
    }
    commitStudies([...studyInstances, createStudyInstance(kind, settings, ticker)]);
  };
  const updateStudy = (id, patch) => {
    const inst = studyInstances.find(s => s.instanceId === id);
    if (!inst) return;
    const settings = { ...inst.settings, ...patch };
    if (!validateStudySettings(inst.kind, settings)) { setStudyRefusal("Refused — invalid settings; the previous value stays."); return; }
    commitStudies(studyInstances.map(s => (s.instanceId === id ? { ...s, settings } : s)));
  };
  const removeStudy = id => commitStudies(studyInstances.filter(s => s.instanceId !== id));
  const toggleStudyVisible = id => commitStudies(studyInstances.map(s => s.instanceId === id ? { ...s, visible: s.visible === false } : s));
  const togglePane = paneKey => {
    // the REAL pane states: volume-pane gates the measured-volume BARS pane
    // (70 real rects), profile/cvd their own plots — one shared state
    setChartOverlays(o => ({ ...o, [paneKey === "volume-pane" ? "volume" : paneKey]: !(o[paneKey === "volume-pane" ? "volume" : paneKey]) }));
  };
  const STUDY_COLORS = ["#e8bd65", "#5ec986", "#72d7df", "#c4a1ef", "#e06c75", "#8fd3e8"];
  const studyLineSpecs = useMemo(() => studyInstances.filter(inst => inst.visible !== false).flatMap((inst, i) => studySpecs(inst, frames).map(spec => ({ ...spec, color: STUDY_COLORS[i % STUDY_COLORS.length] }))), [studyInstances, frames]);
  // B09 mapped levels (b09_mapped_levels_contract v2): cross-instrument
  // source->target mapping through the contract route — the backend is the ONE
  // ratio authority; this caller never computes a ratio and never substitutes
  // naked-levels claims. Only validated-family sources are selectable; the
  // cursor is the pane's replay position (review-mode ratio lock).
  const [mappedSource, setMappedSource] = useState(null);
  const [mapped, setMapped] = useState(null);
  useEffect(() => {
    if (!mappedSource || !eligibleMappedPairsFor(ticker).includes(mappedSource)) { setMapped(null); return undefined; }
    let cancelled = false;
    const cursorFrame = frames[position];
    const cursorSeconds = cursorFrame ? Math.floor(Date.parse(cursorFrame.time) / 1000) : null;
    if (!cursorSeconds) { setMapped({ status: 'unavailable', reason: 'no cursor', shapes: [], legend: null, ratio: null }); return undefined; }
    setMapped({ status: 'loading', shapes: [], legend: null, ratio: null });
    axios.get(`${API}/heatseeker/mapped-levels/${encodeURIComponent(ticker.toUpperCase())}`, { params: { source: mappedSource, cursor: cursorSeconds, scope: payload?.query_key || '' } })
      .then(res => { if (!cancelled) setMapped(parseMappedLevelsResponse(res?.data, cursorSeconds)); })
      .catch(() => { if (!cancelled) setMapped({ status: 'unavailable', reason: 'route unavailable', shapes: [], legend: null, ratio: null }); });
    return () => { cancelled = true; };
  }, [mappedSource, ticker, position, payload?.query_key]);
  // B10 future whitespace (b10_projection_contract v2, H3 PASS; CHART-C044):
  // the future axis extends in exact interval multiples of THIS pane's grid;
  // the scenario zone is sessionZones at its own known-at — recorded context
  // only, high/low never extended into the future; the source age is ALWAYS
  // rendered with the zone. Refusals render as the typed one-liner.
  const GRID_MINUTES = [1, 5, 15, 30, 60];
  const projection = useMemo(() => {
    if (!frames.length || !GRID_MINUTES.includes(minutes)) return null;
    const cursorFrame = frames[position];
    if (!cursorFrame) return null;
    return projectWhitespace(frames, {
      intervalMinutes: minutes,
      horizonMinutes: minutes * 8,
      supportedGrid: GRID_MINUTES,
      cursorMs: Date.parse(cursorFrame.time),
    });
  }, [frames, minutes, position]);
  // B16 pointer/keyboard geometry: the drawing layer projects LOGICAL anchors
  // through the real loaded frames' time/price domain. Zoom/resize changes
  // pixels, never anchor meaning.
  const drawingViewportRef = useRef(null);
  const layerPoint = event => {
    const vp=drawingViewportRef.current;
    if(!vp)return null;
    const svg=event.currentTarget.ownerSVGElement || event.currentTarget;
    const rect=svg.getBoundingClientRect();
    const x=(rect.width?(event.clientX-rect.left)*vp.svgWidth/rect.width:event.clientX)-vp.left;
    const y=(rect.height?(event.clientY-rect.top)*vp.svgHeight/rect.height:event.clientY)-vp.top;
    return unprojectPoint({x,y},vp);
  };
  const commitDraft = point => {
    const nextAnchors = [...draftAnchors, point];
    if (nextAnchors.length >= anchorsFor(draftTool)) {
      // C091: a NEW drawing gets this tool's preset default — starred >
      // active > built-in — and records the link so dirty tracking is honest
      const base = createDrawing(draftTool, nextAnchors, draftTool === "risk" ? { side: draftSide } : null);
      const creationPreset = defaultPresetFor(presetList, draftTool);
      persistDrawings(reduceDrawings(drawings, { type: "add", drawing: creationPreset ? applyPresetToDrawing(base, creationPreset) : base }));
      setDraftTool(null); setDraftAnchors([]);
    } else setDraftAnchors(nextAnchors);
  };
  const onDrawingLayerPointerDown = event => {
    const drawingViewport=drawingViewportRef.current;
    if (!drawingViewport) return;
    // While dragging a selected drawing, pointer events never start a pan:
    // the layer owns the gesture (arbitration contract: suppressesPan).
    if (dragState) { event.stopPropagation(); return; }
    const raw = layerPoint(event);
    if (!raw) return;
    // B17: brush is a FREE draw — the registry says magnet:false, so its
    // anchors never snap to OHLC. The six basics keep their incumbent path.
    const point = draftTool === "brush" ? raw : magnetPoint(raw, drawingViewport.frames, 0.25, drawingViewport);
    if (draftTool) { event.stopPropagation(); commitDraft(point); }
  };
  const onDrawingElementPointerDown = (event, drawing) => {
    const drawingViewport=drawingViewportRef.current;
    if (!drawingViewport || !canEdit(drawing)) { if (drawing) setSelectedDrawing(drawing.id); return; }
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setSelectedDrawing(drawing.id);
    const start = layerPoint(event);
    if (!start) return;
    setDragState({ id: drawing.id, anchors: drawing.anchors.map(a => ({ ...a })), start, suppressPan: true });
  };
  const onDrawingLayerPointerMove = event => {
    const drawingViewport=drawingViewportRef.current;
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
      // CHART-C090: Alt+L/Alt+S arm the analysis risk box (long/short) — the
      // shell's plain-key dispatch ignores modifier combos (actionFor guard).
      if (event.altKey && !event.ctrlKey && !event.metaKey) {
        const k = String(event.key || "").toLowerCase();
        if (k === "l" || k === "s") {
          event.preventDefault();
          setDraftTool("risk");
          setDraftSide(k === "l" ? "long" : "short");
          setDraftAnchors([]);
          return;
        }
      }
      if (event.key === "Escape" && draftTool) { setDraftTool(null); setDraftAnchors([]); return; }
      if (!selectedDrawing) return;
      const drawing = drawings.find(d => d.id === selectedDrawing);
      if (!canEdit(drawing)) return;
      const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] }[event.key];
      if (!dir) return;
      event.preventDefault();
      // The renderer can zoom without rerendering its parent. Read its
      // current domain at the gesture, rather than a parent-render snapshot.
      const vp=drawingViewportRef.current;
      if(!vp)return;
      const nudgeStep={dt:(vp.tMax-vp.tMin)/100,dp:(vp.pMax-vp.pMin)/100};
      persistDrawings(reduceDrawings(drawings, { type: "nudge", id: selectedDrawing, dt: dir[0] * nudgeStep.dt, dp: dir[1] * nudgeStep.dp }));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, drawings, selectedDrawing, draftTool]);
  const comparisonScope = typeof payload?.query_key === "string" ? payload.query_key : "";
  // B06 workspace quality contract (inert without a listener): the pane
  // reports its own data-quality truth — latest observed reading time,
  // saved-node coverage, truncation (partial bars), capability reason and
  // the manual-retry state. Unknowns stay unknown; nothing is invented.
  useEffect(() => {
    if (!onQuality) return;
    onQuality({
      status,
      badge: readBadge,
      sourceTime: frames.length ? frames[frames.length - 1].time : null,
      coverage: frames.length ? `${payload?.candles_with_recorded_nodes ?? 0} of ${frames.length} candles carry saved nodes` : "no candles loaded",
      partialBars: payload?.records_truncated ? "period contains more saved readings than can be loaded" : null,
      capability: payload?.node_status ?? null,
      retry: retryRemaining > 0 ? `manual retry in ${retryRemaining}s` : "manual retry available",
    });
  }, [onQuality, status, readBadge, frames.length, payload, retryRemaining]);
  // R21-03/04 supply wiring (inert without a listener, like onQuality): the
  // pane publishes the recorded admission envelopes that arrived alongside
  // this read's own bars. A payload without an envelopes key — or this
  // pane's reset to no payload — publishes null, so the workspace never
  // renders a previous read's truth.
  useEffect(() => {
    if (!onEnvelopes) return;
    onEnvelopes(status === "ready" && payload?.ticker === ticker.toUpperCase() && payload.envelopes
      && typeof payload.envelopes === "object" ? {...payload.envelopes, owner:{ticker:payload.ticker,scope:payload.query_key || ""}} : null);
  }, [onEnvelopes, payload, status, ticker]);
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
    // R21-02: the owning bar is the bar_seconds bucket of this pane's own
    // resolution (minutes prop — the same one the read requested), and a
    // frame's availability is the server-emitted end_time (its window close)
    // — never invented from the candle's own open time. Without a real
    // emission (older backend) availability is honestly unknown: null.
    const barSeconds = [60, 300, 900, 1800, 3600].includes(minutes * 60) ? minutes * 60 : null;
    const events = frames.map(f => ({ id: f.time, event_time: Date.parse(f.time), available_at: f.end_time ? Date.parse(f.end_time) : null, open: f.open, close: f.close }));
    const bar = barSeconds ? barAt(events, cursor, barSeconds * 1000) : null;
    const visible = frames.slice(0, position + 1).map(f => ({ time: Date.parse(f.time), high: f.high, low: f.low }));
    const extrema = sweepExtrema(visible, cursor);
    const snapshot = visibleSnapshot(frames.map(f => ({ id: f.time, known_at: Date.parse(f.time), close: f.close })), cursor);
    // R21-02: live ONLY at the advancing head — a paused or scrubbed cursor
    // anywhere behind the newest frame is replay, whichever way it moved.
    const origin = position === frames.length - 1 ? "live" : "replay";
    const delta = position === lastReportedPosition.current
      ? []
      : [{ id: cursorFrame.time, symbol: ticker.toUpperCase(), value: cursorFrame.close, time: cursor, origin }];
    lastReportedPosition.current = position;
    onReplayState({
      cursor, cursorTime: cursorFrame.time, playing, bar, extrema,
      snapshotKnownAt: snapshot ? snapshot.known_at : null,
      visibleBars: position + 1, totalBars: frames.length, delta,
      // B23: the REAL visible bars at the cursor (epoch time, observed range)
      // feed bar-resolution reads — never a fabricated volume-at-price.
      visible: frames.slice(0, position + 1).map(f => ({ time: Date.parse(f.time), low: f.low, high: f.high })),
      // B24: the pane's real scope/generation identity — the focused-chart
      // ask gate binds and resolves against exactly this (server-owned facts).
      scope: payload?.query_key || "",
      generation: ticker + ":" + days + ":" + minutes + ":" + (payload?.query_key || "") + ":" + reload,
      // R21-03: the pane's REAL resolution, so flow/profile consumers key
      // their bucket identities on the owning interval, never a guess.
      barSeconds,
      // R21-06: the reporting pane's identity — the consumer validates the
      // report against the LIVE focused pane, so a late report from a pane
      // that lost focus can never re-admit.
      source: replaySourceId,
    });
    return undefined;
  }, [onReplayState, frames, position, playing, replayEpoch]); // eslint-disable-line react-hooks/exhaustive-deps
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
  useEffect(() => {
    if(!onReplayController)return undefined;
    onReplayController({source:replaySourceId,
      toggle:()=>{if(!frames.length)return;if(!playing&&position>=frames.length-1)setPosition(0);setPlaying(!playing);},
      pause:()=>setPlaying(false)});
    return ()=>onReplayController(null);
  },[onReplayController,replaySourceId,frames.length,playing,position]);
  const pauseInteraction = useCallback(() => setPlaying(false), []);
  // 2026-10-18 compact toolbar: symbol/interval stay prominent; the loaded
  // history range AND session coverage stay visible as text, while their two
  // picker selects live inside Chart tools. Labels mirror the option text so
  // the summary never claims a different basis than the picker serves.
  const historyDayLabel = { 1: "1 session", 5: "1 week", 20: "1 month", 60: "3 months", 260: "1 year", 2600: "5 years" }[days]
    ?? `${days} sessions`;
  const historySessionLabel = sessions === "all" ? "all sessions" : "regular hours";
  const controls = <><strong className="price-chart-symbol">{ticker}</strong>
    <select aria-label="Candle interval" title="Candle interval" value={minutes} onChange={e=>{setMinutes(Number(e.target.value));onSyncEvent?.({interval:Number(e.target.value)});}}><option value={1}>1 min</option><option value={5}>5 min</option><option value={15}>15 min</option><option value={30}>30 min</option><option value={60}>1 hour</option></select>
    <span className="price-history-summary" data-testid="price-history-summary" title="Selected history period and session coverage">{historyDayLabel} · {historySessionLabel}</span>
    <span className="stock-dock-actions" data-testid="stock-dock-actions">
      <button type="button" className="stock-dock-btn" aria-pressed={dockOpen&&dockTab==="indicators"} data-testid="stock-dock-open-indicators" title="Indicators: studies and measured-pane controls" onClick={()=>openDock("indicators")}>Indicators{studyInstances.length?` · ${studyInstances.length}`:""}</button>
      <button type="button" className="stock-dock-btn" aria-pressed={dockOpen&&dockTab==="data"} data-testid="stock-dock-open-data" title="Data: saved views, reload, node recording, option contract" onClick={()=>openDock("data")}>Data</button>
      <button type="button" className="stock-dock-btn" aria-pressed={dockOpen&&dockTab==="review"} data-testid="stock-dock-open-review" title="Review: the Wall→Contract→AskFlow→Public brief workflow" onClick={()=>openDock("review")}>Review</button>
    </span></>;
  const historyPeriodControls = <>
    <label className="price-history-view">History period<select aria-label="History sessions" title="History period" value={days} onChange={e=>setDays(Number(e.target.value))}><option value={1}>1 session</option><option value={5}>1 week</option><option value={20}>1 month</option><option value={60}>3 months</option><option value={260}>1 year</option><option value={2600}>5 years</option></select></label>
    <label className="price-history-view">Session coverage<select aria-label="Session coverage" title="Which trading sessions to load" value={sessions} onChange={e=>{setSessions(e.target.value);onSyncEvent?.({session:e.target.value});}}><option value="regular">Regular hours</option><option value="all">All sessions</option></select></label>
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
  // Visual-reset: the studies catalog and mapped-levels panels now live in
  // the right workspace Indicators tab — same testids, no discovery dead end.
  const studiesPanelContent = <>    <details className="price-studies-panel" data-testid="studies-panel">
      <summary data-testid="studies-panel-summary" role="button" aria-label="Indicators">Indicators{studyInstances.length ? ` · ${studyInstances.length}` : ""}</summary>
      <div className="price-studies-content">
        <IndicatorsPanel
          instances={studyInstances}
          frames={frames}
          builtinVwapOn={chartOverlays.vwap}
          paneState={{"volume-pane": chartOverlays.volume, cvd: chartOverlays.cvd, profile: chartOverlays.profile}}
          availability={{cvd: Array.isArray(cvdLine ?? payload?.cvd_line) && (cvdLine ?? payload?.cvd_line).some(p => typeof p?.cvd === "number" && Number.isFinite(p.cvd)), profile: frames.some(f => Number.isFinite(f?.volume))}}
          onCreate={addStudy}
          onUpdateSettings={(id, settings) => updateStudy(id, settings)}
          onRemove={removeStudy}
          onToggleVisible={toggleStudyVisible}
          onTogglePane={togglePane}
        />
        {studyRefusal && <p role="alert" data-testid="studies-refusal">{studyRefusal}</p>}
      </div>
    </details>
    <details className="price-mapped-levels" data-testid="mapped-levels-panel">
      <summary data-testid="mapped-levels-summary" role="button" aria-label="Mapped levels">Mapped levels{mapped?.status === 'available' ? ` · ${mapped.shapes.length}` : ''}</summary>
      <div className="price-mapped-content">
        {eligibleMappedPairsFor(ticker).length ? <>
          <p className="price-mapped-hint">Cross-instrument levels mapped through the validated-family route — the ratio, its provenance and eligibility come from the backend.</p>
          <label>Source
            <select data-testid="mapped-levels-source" aria-label="Mapped-levels source" value={mappedSource || ''} onChange={e => setMappedSource(e.target.value || null)}>
              <option value="">Off</option>
              {eligibleMappedPairsFor(ticker).map(source => <option key={source} value={source}>{source} → {ticker.toUpperCase()}</option>)}
            </select>
          </label>
          {mapped && mapped.status !== 'loading' && <p data-testid="mapped-levels-status" role={mapped.status === 'available' ? 'status' : 'note'}>{mapped.status === 'available' ? 'Available' : mapped.status === 'refused' ? `Refused — ${mapped.reason}` : `Unavailable — ${mapped.reason}`}</p>}
          {mapped?.status === 'loading' && <p data-testid="mapped-levels-status" role="status">Loading mapped levels…</p>}
          {mapped?.status === 'available' && <>
            <p data-testid="mapped-levels-legend">◆ {mapped.legend.diamond} · ▲ {mapped.legend.triangle}</p>
            <p data-testid="mapped-levels-ratio" title={JSON.stringify(mapped.ratio?.provenance || {})}>Ratio {mapped.ratio.value} · known at {mapped.ratio.knownAt}</p>
          </>}
        </> : <p data-testid="mapped-levels-status">No validated mapped-level family for {ticker.toUpperCase()} — futures and other pairs stay refused until a validated mapping exists.</p>}
      </div>
    </details>
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
  const renderDrawingLayer = drawingViewport => {
    drawingViewportRef.current=drawingViewport;
      return <g className="drawing-layer" data-testid="drawing-layer" data-domain="renderer" transform={`translate(${drawingViewport.left},${drawingViewport.top})`} clipPath={`url(#drawings-${drawingViewport.clipId})`}
        data-arbitration={dragState ? "drawing-drag" : "idle"} role="img" aria-label="Drawing layer"
        onPointerDown={onDrawingLayerPointerDown} onPointerMove={onDrawingLayerPointerMove} onPointerUp={onDrawingLayerPointerUp} onPointerLeave={onDrawingLayerPointerUp}>
        <defs><clipPath id={`drawings-${drawingViewport.clipId}`}><rect width={drawingViewport.width} height={drawingViewport.height}/></clipPath><marker id={`arrow-${drawingViewport.clipId}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#7fa6c0"/></marker></defs>
        <rect x="0" y="0" width={drawingViewport.width} height={drawingViewport.height} fill="transparent" pointerEvents={draftTool ? "all" : "none"} />
        {drawings.filter(d=>d.visible!==false).map(d=>{const g=geometryFor(d.tool,d.anchors,drawingViewport,d);
          if(!g)return null;
          // B17/C130 ADAPTER MOUNT: non-risk drawings render through the
          // frozen preset rendering adapter (buildPresetRenderSpec) — the
          // same geometryFor transform, now consuming the FULL family style
          // (fib ratios/levelColors/visibility/extensions/labels/reverse/log,
          // line extensions, shape fillOpacity, label fontSize). Refusals
          // fall back to the incumbent rendering so a drawing is never lost
          // or unhit-testable; the risk box keeps its C090 semantic renderer.
          const renderSpecPrimitive=(pr,pi,tidOverride)=>{
            const part=pr.meta?.part;
            const tid=tidOverride||(part==="level"?"fib-level":(part?"preset-"+part:"drawing-shape"));
            if(pr.kind==="polyline")return <polyline key={pi} data-testid={tid} data-drawing-id={d.id} data-selected={d.id===selectedDrawing} data-ratio={pr.meta?.ratio} points={pr.points.map(pt=>`${pt.x},${pt.y}`).join(" ")} stroke={pr.stroke} strokeWidth={pr.strokeWidth} strokeDasharray={pr.dash} fill="none" pointerEvents="stroke" markerEnd={pr.marker==="arrow"?`url(#arrow-${drawingViewport.clipId})`:undefined} onPointerDown={e=>onDrawingElementPointerDown(e,d)} />;
            if(pr.kind==="text")return <text key={pi} data-testid={tid} data-drawing-id={d.id} x={pr.x} y={pr.y} fontSize={pr.fontSize} fill={pr.fill} pointerEvents="none">{pr.text}</text>;
            if(pr.kind==="rect"||pr.kind==="band")return <rect key={pi} data-testid={tid} data-drawing-id={d.id} x={pr.x} y={pr.y} width={Math.max(pr.width,2)} height={Math.max(pr.height,2)} fill={pr.fill||"none"} stroke={pr.stroke||"none"} strokeWidth={pr.strokeWidth} strokeDasharray={pr.dash} pointerEvents={pr.kind==="rect"&&pr.stroke!=="none"?"stroke":"none"} onPointerDown={pr.kind==="rect"?e=>onDrawingElementPointerDown(e,d):undefined} />;
            return null;
          };
          if(d.tool!=="risk"){
            const spec=buildPresetRenderSpec({tool:d.tool,anchors:d.anchors,viewport:drawingViewport,style:d.style,selected:d.id===selectedDrawing});
            if(spec.status==="ok"&&Array.isArray(spec.primitives)&&spec.primitives.length){
              const main=spec.primitives.find(p=>p.kind!=="text")||spec.primitives[0];
              if(spec.primitives.length===1)return renderSpecPrimitive(spec.primitives[0],0,"drawing-shape");
              return <g key={d.id} data-testid="drawing-shape" data-drawing-id={d.id} data-selected={d.id===selectedDrawing} fill="none" stroke={main.stroke} strokeWidth={main.strokeWidth} strokeDasharray={main.dash} pointerEvents="stroke" onPointerDown={e=>onDrawingElementPointerDown(e,d)}>
                {spec.primitives.map((pr,pi)=>renderSpecPrimitive(pr,pi))}
              </g>;
            }
          }
          const common={"data-testid":"drawing-shape","data-drawing-id":d.id,"data-selected":d.id===selectedDrawing,stroke:d.style?.color||(d.id===selectedDrawing?"#e3c16a":"#7fa6c0"),strokeWidth:d.style?.width||(d.id===selectedDrawing?2:1.2),strokeDasharray:d.style?.dash?"6 3":undefined,fill:"none",pointerEvents:"stroke",onPointerDown:e=>onDrawingElementPointerDown(e,d)};
          if(g.kind==="risk"){
            // CHART-C090: analysis-only entry/stop/target box — shaded stop->entry
            // (risk) and entry->target (reward) zones, three role lines and the
            // R-multiple; never a broker intent.
            const roles=Object.fromEntries(g.levels.map(l=>[l.role,l]));
            const zone=(a,b,testid,fill)=>a&&b&&Number.isFinite(a.y)&&Number.isFinite(b.y)?<rect key={testid} data-testid={testid} x={g.x0} width={Math.max(1,g.x1-g.x0)} y={Math.min(a.y,b.y)} height={Math.abs(a.y-b.y)} fill={fill} stroke="none" pointerEvents="none"/>:null;
            return <g key={d.id} {...common} data-testid="risk-shape" fill="none">
              {zone(roles.entry,roles.stop,"risk-zone-stop","rgba(214,86,86,0.14)")}
              {zone(roles.entry,roles.target,"risk-zone-target","rgba(94,201,134,0.10)")}
              {g.levels.map(l=><line key={l.role} data-testid={"risk-line-"+l.role} x1={g.x0} x2={g.x1} y1={l.y} y2={l.y} stroke={l.role==="entry"?"#e3c16a":l.role==="stop"?"#d65656":"#5ec986"} strokeWidth={common.strokeWidth} pointerEvents="stroke" onPointerDown={e=>onDrawingElementPointerDown(e,d)}/>)}
              {g.levels.map(l=><text key={l.role+"-lbl"} x={g.x1+4} y={l.y} fontSize="9" fill="#8fa6ba" pointerEvents="none">{l.role} {l.price}</text>)}
              <text data-testid="risk-label" x={g.x0} y={Math.min(...g.levels.map(l=>l.y))-4} fontSize="10" fill={d.id===selectedDrawing?"#e3c16a":"#8fa6ba"} pointerEvents="none">R {g.rMultiple.toFixed(1)} · {g.side} · analysis only</text>
            </g>;}
          if(g.kind==="rect")return <rect key={d.id} {...common} x={g.x} y={g.y} width={Math.max(g.width,2)} height={Math.max(g.height,2)} />;
          if(g.kind==="label")return <text key={d.id} {...common} x={g.x} y={g.y} fontSize="12" fill="#dce8f2">{d.text||"text"}</text>;
          if(g.kind==="fib")return <g key={d.id} {...common} fill="none">{g.levels.map((level,li)=>(<g key={d.id+":"+li} data-testid="fib-level" data-ratio={level.ratio}>
            <polyline {...common} points={level.points.map(pt=>`${pt.x},${pt.y}`).join(" ")} />
            <text x={level.points[1].x+4} y={level.points[1].y} fontSize="9" fill={d.id===selectedDrawing?"#e3c16a":"#8fa6ba"}>{level.ratio}</text>
          </g>))}</g>;
          return <polyline key={d.id} {...common} markerEnd={d.tool==="arrow"?`url(#arrow-${drawingViewport.clipId})`:undefined} points={g.points.map(pt=>`${pt.x},${pt.y}`).join(" ")} />;})}
        {draftAnchors.map((a,i)=>{const pt=geometryFor("text",[a],drawingViewport);
          return pt?<circle key={"draft-"+i} data-testid="draft-anchor" cx={pt.x} cy={pt.y} r="4" fill="#e3c16a" />:null;})}
      </g>;
  };
  return <section className="panel price-node-history" data-open={open} data-read-badge={readBadge} style={{margin:"12px 0",padding:12}} data-testid="price-node-history">
    {!primary&&<button type="button" className="skylit-trade-mode-btn" aria-expanded={open} onClick={()=>{setOpen(!open);setPlaying(false);}}>Price chart + historical nodes</button>}
    {open&&<div className="stock-pane-row" data-testid="stock-pane-row">
    <div className="stock-pane-main">
    {open&&<RecordedPriceChart renderDrawingLayer={renderDrawingLayer} ticker={ticker} frames={frames.slice(0,position+1)} fitAllFrames={fitMode==="fit-all"?frames:null} revision={ticker+":"+days+":"+minutes+":"+payload?.query_key+":"+reload} onInteract={pauseInteraction} metricCoverage={payload?.metric_line_coverage} toolbarControls={controls} toolbarActions={null} historyPeriodControls={historyPeriodControls} historyControls={null} replayControls={replayControls} dataDetails={details} readingStatus={readingStatus} emptyContent={empty} showAtlas={showAtlas} exposureLine={exposureLine??payload?.exposure_line??null} darkLevels={darkLevels} alertLines={alertLines??null} cvdLine={cvdLine??payload?.cvd_line??null} contractBars={payload?.contract_bars??null} contractSymbol={payload?.contract_symbol??(contract||null)} contractStatus={payload?.contract_status??null} flowBars={Array.isArray(flowBars)&&flowBars.length===frames.length?flowBars.slice(0,position+1):flowBars} syncSeq={sync?.seq||0} syncView={sync?.time||null} syncPrice={sync?.price||null} syncCrosshair={sync?.crosshair!=null?sync.crosshair:null} onSync={onSyncEvent} studyLines={studyLineSpecs} mappedShapes={mapped?.status === 'available' ? mapped.shapes : null} volumeInstanceActive={studyInstances.some(i=>i&&i.kind==="volume")} overlays={chartOverlays} onOverlaysChange={setChartOverlays}/>}
    {open&&forcedScope!=null&&!followMap&&<p role="note">Saved-view review — these recorded expiry dates are not the current map scope.</p>}
    {/* B10 (C044): interval future whitespace + typed scenario zone. The
        slots are EMPTY CANVAS markers — no forecasts; the zone is recorded
        context at its own known-at; the source age is always visible. */}
    {open&&projection?.status === 'ok'&&<div className="price-future-whitespace" data-testid="future-whitespace-strip" title="Future whitespace — empty canvas in interval multiples; the scenario zone describes only what was knowable at the cursor">
      <span className="pw-slots" data-testid="future-whitespace-slots">{projection.segments.map((seg,i)=><i key={i} data-testid="future-whitespace-slot" aria-hidden="true"></i>)}</span>
      <span data-testid="scenario-zone-label">Session zone {projection.zone.high}/{projection.zone.low} · {projection.zone.bars} bars</span>
      <span data-testid="scenario-source-age" title="Age of the zone source at the cursor — how far the cursor is past the last known bar">age {projection.sourceAgeSeconds}s</span>
      <span className="pw-note">{projection.zone.note}</span>
    </div>}
    {open&&projection?.status === 'refused'&&<p className="price-future-whitespace-refused" data-testid="future-whitespace-refusal" role="note">Future whitespace unavailable — {projection.reason}{projection.zone&&projection.zone.reason?` (${projection.zone.reason})`:''}</p>}
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

      <DrawingRail drawings={drawings} selectedId={selectedDrawing}
      tools={REDUCER_TOOLS.map(id=>({id,anchors:anchorsFor(id)}))} draftTool={draftTool} onStyle={(id,style)=>persistDrawings(reduceDrawings(drawings,{type:"style",id,style}))}
      onToolPick={id=>{setDraftTool(draftTool===id?null:id);setDraftAnchors([]);}}
      onUndo={()=>persistDrawings(reduceDrawings(drawings,{type:"undo"}))}
      onCancelDraft={()=>{setDraftTool(null);setDraftAnchors([]);}}
      onSelect={setSelectedDrawing}
      onDelete={id => { if (selectedDrawing === id) setSelectedDrawing(null); persistDrawings(reduceDrawings(drawings, { type: "delete", id })); }}
      onToggleLock={id => persistDrawings(drawings.map(d => d.id === id ? { ...d, locked: !d.locked } : d))}
      onToggleHide={id => persistDrawings(drawings.map(d => d.id === id ? { ...d, visible: d.visible === false } : d))}
      presets={presetList}
      presetScope={ticker}
      onPresetCreate={request => requestPresetOp(createPreset(presetList, request))}
      onPresetUpdate={(id, style) => requestPresetOp(updatePresetStyle(presetList, id, style))}
      onPresetApply={id => {
        // the SELECTED drawing only — never a silent restyle of many
        const preset = presetList.find(p => p && p.id === id);
        const target = drawings.find(d => d && d.id === selectedDrawing);
        if (!preset || !target || target.locked) return;
        persistDrawings(drawings.map(d => d.id === target.id ? applyPresetToDrawing(d, preset) : d));
      }}
      onPresetToggleStar={id => requestPresetOp(toggleStar(presetList, id))}
      onPresetSetActive={id => requestPresetOp(setActivePreset(presetList, id))}
      onPresetReset={id => requestPresetOp(resetPresetStyleToBuiltIn(presetList, id))}
      onPresetDelete={id => requestPresetOp(deletePreset(presetList, id))} />
      {presetError && <p className="price-preset-error" data-testid="preset-error" role="note">{presetError}</p>}
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

    </div>
    <StockInspector open={dockOpen} activeTab={dockTab} onTabChange={setDockTab} onClose={()=>setDockOpen(false)}
      counts={{indicators:studyInstances.length||null,data:null,review:null}}
      indicators={studiesPanelContent}
      data={historyControls}
      review={<div className="stock-review-tab" data-testid="stock-review-context">
        <strong className="stock-review-head">Current selection</strong>
        {(() => { const sel = drawings.find(d => d && d.id === selectedDrawing);
          if (!sel) return <p className="stock-review-empty">No drawing selected — pick one in the Drawings list below the chart.</p>;
          const linked = presetList.find(p => p && p.id === sel.presetId);
          return <p className="stock-review-selection" data-testid="stock-review-selection">
            {sel.tool} drawing{sel.style?.color ? ` · ${sel.style.color}` : ""}{sel.style?.width ? ` · w${sel.style.width}` : ""}{sel.locked ? " · locked" : ""}{sel.visible === false ? " · hidden" : ""}
            {linked ? ` · preset ${linked.name}${linked.kind === "built-in" ? " (built-in)" : linked.starred ? " · starred" : linked.active ? " · active" : ""}` : " · unlinked"}
          </p>; })()}
        {(() => { const inst = studyInstances[0];
          return <p className="stock-review-note" data-testid="stock-review-study">{studyInstances.length
            ? `${studyInstances.length} active stud${studyInstances.length === 1 ? "y" : "ies"} — first: ${inst.kind}${inst.settings?.period ? " " + inst.settings.period : ""}`
            : "No active studies — add one in the Indicators tab."}</p>; })()}
        <p className="stock-review-families" data-testid="stock-review-families">Analytics families — levels, patterns, income, history, moves, structure, exposure, briefing — live on the options desk; the Wall→Contract→AskFlow→Public brief workflow stays in the action band above the chart.</p>
      </div>} />
    </div>}
  </section>;
}
