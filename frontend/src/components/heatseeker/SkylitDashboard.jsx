import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";
import SkylitTickerBar from "./SkylitTickerBar";
import SkylitControlBar from "./SkylitControlBar";
import SkylitHeatmapGrid from "./SkylitHeatmapGrid";
import SkylitMetricsSidebar from "./SkylitMetricsSidebar";
import SolsticeStatusStrip from "./SolsticeStatusStrip";
import WallInspector from "./WallInspector";
import ScenarioStrip from "./ScenarioStrip";
import ExposureStrip from "./ExposureStrip";
import { publishScreenContext } from "../../agent/useScreenContext";
import ReplayStrip from "./ReplayStrip";
import AlertEngineStrip from "../flowseeker/AlertEngineStrip";
import { shownMapStrikes, mapSurface } from "./shownMapStrikes";

import { resolveSelectedWall, wallPositionOf } from "../../lib/solsticeSelection";

/**
 * SelectedCellReadout — R6-1 + R7-03: the banner resolves its value from the
 * CURRENT displayed snapshot's ACTIVE surface (viewMode + metric identity).
 * A cell that is absent there is unavailable — never the number stored at
 * click time (stale across refreshes) and never another metric's value
 * (GEX under a VEX view).
 */
function SelectedCellReadout({ selectedCell, displayData, metric, viewMode }) {
  const surface = mapSurface(displayData, viewMode, metric).matrix;
  const _sn = Number(selectedCell.strike);
  const sk = Number.isFinite(_sn) && Math.floor(_sn) === _sn ? String(Math.trunc(_sn)) : String(selectedCell.strike);
  const current = surface[selectedCell.colKey]?.[sk];
  const value = typeof current === "number" && Number.isFinite(current) ? current : null;
  return (
    <span
      className="skylit-selected-cell-readout"
      data-testid="skylit-selected-cell"
      title={`Selected cell (${viewMode.toUpperCase()} pane) — current snapshot value`}
    >
      {selectedCell.strike} · {selectedCell.colKey} · {value == null ? "unavailable" : value.toFixed(1)}
    </span>
  );
}

/**
 * SelectedWallBlock — identity selection resolved against the CURRENT
 * snapshot (P05/R4-06). Retains by wall_id across compatible refreshes
 * (asof/metric/expand); cross-symbol clears; missing walls explain
 * WALL_GONE instead of substituting the nearest different wall.
 */
function SelectedWallBlock({ data, spot, selectedCell, metric = "raw", replay = false }) {
  const res = resolveSelectedWall(data, selectedCell);
  if (res.status === "empty" || res.status === "cleared") return null;
  if (res.status === "gone") {
    return (
      <>
        <WallInspector wall={null} interaction={null} metrics={data?.metrics} grids={data?.metrics?.grids} quality={data?.quality} scenario={null} goneReason={res.reason} lastWallId={res.lastWallId} />
        <ScenarioStrip scenarios={[]} />
      </>
    );
  }
  const { wall, interaction } = res;
  let scenarios = res.scenarios && res.scenarios.length ? res.scenarios : [];
  if (!scenarios.length && wall) {
    // Compat fallback only (backend now attaches scoped scenarios): derive
    // from wall position (wall below spot = support/bounce, wall above =
    // resistance/rejection). Never scenarios[0] of a different wall.
    const wpos = wallPositionOf(wall, spot);
    const side = wpos === "inside" ? "below" : wpos;
    scenarios = [
      { wall_id: wall.wall_id, wall_position: wpos,
        name: side === "below" ? "Bounce watch" : "Rejection watch", type: "reversal_watch",
        confirmation: `reclaim and hold ${side === "below" ? "above " + wall.low : "below " + wall.high}`,
        invalidation: `sustained acceptance ${side === "below" ? "below " + wall.low : "above " + wall.high}` },
      { wall_id: wall.wall_id, wall_position: wpos,
        name: side === "below" ? "Breakdown continuation" : "Breakout continuation", type: "continuation",
        confirmation: "acceptance beyond zone + follow-through/retest",
        invalidation: `reclaim and hold ${side === "below" ? "above " + wall.low : "below " + wall.high}` },
    ];
  }
  return (
    <>
      <WallInspector
        wall={wall} interaction={interaction} metrics={data.metrics} grids={data.metrics?.grids}
        quality={data.quality} scenario={scenarios[0]}
        scout={data.scout} patterns={data.patterns_v1} regime={data.gamma_regime_v1}
        vanna={data.vanna_v1} moneyness={data.moneyness} metric={metric}
        snapshotId={data.snapshotId || null} replay={replay}
      />
      <ScenarioStrip scenarios={scenarios} />
    </>
  );
}

/**
 * CompareWorkspace — R7-04 synchronized GEX+VEX desk. Two instances of the
 * REAL grid over ONE snapshot/request: GEX left, VEX right (stacked on
 * narrow widths via CSS). Shared ticker/observation/spot/scope/selection/
 * live-replay/generation; independent per-pane scales; scroll synced by
 * strike/expiry identity with a loop guard. The VEX pane ignores weighting
 * controls (delta weighting is N/A for VEX) and shows explicit unavailable
 * when its surface is missing. Own scroll refs per instance so inline and
 * expanded desks never cross-sync.
 */
function CompareWorkspace({ data, spot, ticker, metric, gridZoom,
                            density, windowRows, onPaneCellClick,
                            onStrikeClick, onPaneScale, compareLock }) {
  const gexRef = useRef(null);
  const vexRef = useRef(null);
  const guard = useRef(false);
  const syncFrom = (from) => (e) => {
    if (guard.current) return;
    guard.current = true;
    try {
      const other = from === "gex" ? vexRef.current : gexRef.current;
      const self = from === "gex" ? gexRef.current : vexRef.current;
      if (other && self) {
        other.scrollTop = self.scrollTop;
        other.scrollLeft = self.scrollLeft;
      }
    } finally {
      guard.current = false;
    }
  };
  const metricLabel = metric === "delta" ? "Δ-weighted" : metric === "activity" ? "Session activity" : "Raw GEX";
  const pane = (side, view, title, units, scale) => (
    <div
      className="skylit-compare-pane"
      data-testid={`skylit-pane-${side}`}
      ref={side === "gex" ? gexRef : vexRef}
      onScroll={syncFrom(side)}
    >
      <div className="skylit-compare-pane-header" data-testid={`skylit-pane-${side}-header`} title={title}>
        {side === "gex" ? `GEX · ${metricLabel}` : "VEX"} · {units}
      </div>
      <SkylitHeatmapGrid
        data={data}
        spot={spot}
        ticker={ticker}
        viewMode={view}
        metric={side === "gex" ? metric : "raw"}
        scale={scale ? { ...scale, locked: true } : null}
        onScaleReady={(s) => onPaneScale && onPaneScale(side, s)}
        onCellClick={(s, c, v) => onPaneCellClick && onPaneCellClick(side, s, c, v)}
        onStrikeClick={onStrikeClick}
        windowRows={windowRows}
        density={density}
      />
    </div>
  );
  return (
    <div className="skylit-compare-workspace" data-testid="skylit-compare-desk" style={{ zoom: gridZoom }}>
      {pane("gex", "gex", "Raw structural wall anchor; weighting changes cells, not walls",
        "USD/1% move", compareLock?.gex || null)}
      {pane("vex", "vex", "Vanna exposure; delta weighting N/A here",
        "USD/+1 vol pt · local-bs-vanna.v1", compareLock?.vex || null)}
    </div>
  );
}

/**
 * SkylitDashboard — Full Zenith-style trading dashboard
 *
 * Layout:
 *   1. TickerBar (top ticker tape)
 *   2. ControlBar (GEX/VEX, price, timeframe)
 *   3. Main area: HeatmapGrid + MetricsSidebar
 *
 * Matches Zenith reference from screenshots:
 * - Dark background (#0a0e1a)
 * - Ticker buttons at top
 * - GEX/VEX toggle + LIVE badge
 * - Strike price column on left
 * - Color-coded heatmap cells
 * - Current price row highlighted
 * - POC (highest value) with yellow + star
 * - Right sidebar with KING, |GEX|, TOP FLOOR, etc.
 */

function SkylitDashboard({
  ticker = "SPY",
  spot = null,
  change = null,
  changePct = null,
  data = null,
  viewMode = "gex",
  dte = null,
  onViewModeChange,
  timeframe = "5m",
  onTimeframeChange,
  expiries = 4,
  onExpiriesChange,
  onTickerChange,
  onRefresh,
  onCellClick,
  onStrikeClick,
  onReplayChange,
  isLive = false,
  regime = null,
  loading = false,
  // Full ticker universe from App.js ({trinity, default, popular} with the
  // /api/tickers/all list merged into popular). Wired through to the bar +
  // control bar so arrows/buttons/search traverse everything, not fallbacks.
  tickers = null,
}) {
  const [tradeMode, setTradeMode] = useState(false);
  const [selectedCell, setSelectedCell] = useState(null);
  // T04: metric overlay state — same snapshot, raw wall identity locked while
  // viewing activity (walls come from the payload, never recomputed per tab).
  const [metric, setMetric] = useState("raw");
  // F15 display-scale control: freeze the live auto range into a locked
  // comparison scale for replay. Cleared on any scope change so a stale
  // scale can never color a new symbol/metric/view.
  const [liveScale, setLiveScale] = useState(null);
  const [scaleLock, setScaleLock] = useState(null);
  // R7-04 compare desk: Single (default, unchanged) vs GEX+VEX. One
  // snapshot/request drives both panes; the active pane owns the readout
  // while wall identity stays raw-anchored. Per-pane scales lock together.
  const [compareMode, setCompareMode] = useState(false);
  const [activePane, setActivePane] = useState("gex");
  const [compareScales, setCompareScales] = useState({ gex: null, vex: null });
  const [compareLock, setCompareLock] = useState(null);
  // R8-02: "Follow this wall" — keep the same wall_id selected across
  // compatible live refreshes. Cleared on ticker change or scope change.
  const [followWall, setFollowWall] = useState(false);
  const [followWallId, setFollowWallId] = useState(null);
  // R8-04: review journal state for the current snapshot's decision
  const [reviewState, setReviewState] = useState(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  // R8-02/R8-04: matched decision + next-to-review queue + save flow.
  const [reviewDec, setReviewDec] = useState(null);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [reviewReason, setReviewReason] = useState("");
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewNonce, setReviewNonce] = useState(0);
  // R8-04: replay jump requested from the next-to-review list.
  const [replayOpenRequest, setReplayOpenRequest] = useState(null);

  // R8-02: when followWall is on, persist the wall_id from the current
  // selection so compatible live refreshes keep the same wall. Cleared on
  // ticker change (no cross-symbol leakage) and when follow is turned off.
  // The wall inspector uses effectiveWallId when follow is active.
  const effectiveWallId = followWall && followWallId ? followWallId : null;
  const paneScaleReady = useCallback((pane, s) => {
    setCompareScales((prev) => {
      const cur = prev[pane];
      if (cur && cur.min === s.min && cur.max === s.max) return prev;
      return { ...prev, [pane]: s };
    });
  }, []);
  const handleScaleReady = useCallback((s) => {
    setLiveScale((prev) => (prev && prev.min === s.min && prev.max === s.max ? prev : s));
  }, []);
  // P09 guided replay: stored snapshot replaces the SAME grid/inspector/
  // evidence while active; live refresh is ignored; return to live is
  // deliberate. Cleared on ticker change (no cross-symbol leakage).
  const [replaySnap, setReplaySnap] = useState(null);
  useEffect(() => { setReplaySnap(null); }, [ticker]);
  const baseData = data && (!data.ticker || data.ticker === ticker) ? data : null;
  const displayData = replaySnap?.ticker && replaySnap.ticker !== ticker ? null : (replaySnap || baseData);
  const isReplay = Boolean(replaySnap);
  useEffect(() => { onReplayChange?.(isReplay); }, [isReplay, onReplayChange]);
  useEffect(() => () => { onReplayChange?.(false); }, [onReplayChange]);
  // R5-B: in replay every data view renders the RECORDED spot; live keeps
  // the caller-supplied spot prop exactly (never the chain-build spot).
  // Live spot must never masquerade as replay, nor replay as live.
  const displaySpot = isReplay ? (displayData?.spot ?? null) : spot;
  // Grid zoom, in-frame only (2026-09-04): the expanded overlay keeps its
  // designed full density instead of compounding scale on scale.
  const [gridZoom, setGridZoom] = useState(1);
  const zoomIn = useCallback(() => setGridZoom((z) => Math.min(1.5, +(z + 0.25).toFixed(2))), []);
  const zoomOut = useCallback(() => setGridZoom((z) => Math.max(0.75, +(z - 0.25).toFixed(2))), []);
  const zoomReset = useCallback(() => setGridZoom(1), []);
  // Fill-height rows (2026-09-04): the in-frame window sizes itself to the
  // measured heatmap area so strikes run as long as possible instead of a
  // fixed short list with dead space below. Falls back to 21 pre-measure.
  const heatAreaRef = useRef(null);
  const [fitRows, setFitRows] = useState(21);
  useEffect(() => {
    const el = heatAreaRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const measure = () => {
      const h = el.clientHeight || 0;
      if (h > 0) {
        const rows = Math.floor((h - 40) / 24);
        setFitRows(Math.max(10, Math.min(120, rows)));
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // Full-page grid overlay: the in-frame heatmap only shows what fits;
  // expand renders the same grid + sidebar full-screen with all rows.
  const [expanded, setExpanded] = useState(false);

  // Esc closes the expanded grid (local to this component).
  useEffect(() => {
    if (!expanded) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  // Expanded view preserves analytical scope (F18): same mode/expiries as the
  // in-frame grid by default; widening analysis is an explicit user action.
  // expData is cleared on ticker/mode/expiries change with query-keyed guards
  // so no stale/cross-symbol response is ever shown under a new heading.
  const [expData, setExpData] = useState(null);
  const [expLoading, setExpLoading] = useState(false);
  const [expWidened, setExpWidened] = useState(false);
  const expQueryKey = `${ticker}|${timeframe}|${expiries}|${dte ?? ""}|${expWidened ? "wide" : "same"}`;
  useEffect(() => {
    setExpData(null);
    setExpWidened(false);
  }, [ticker, timeframe, expiries, dte]);
  // R5-B resweep: closing the overlay drops expanded data so stale
  // expanded scope can never drive inline clicks after close. Reopening
  // refetches under the current scope (loading state, never old pixels).
  useEffect(() => {
    if (!expanded) setExpData(null);
  }, [expanded]);
  // Locked comparison scale never survives a scope change.
  useEffect(() => {
    setScaleLock(null);
    setCompareLock(null);
  }, [ticker, metric, viewMode, timeframe, expiries, dte, expWidened, replaySnap]);
  useEffect(() => {
    if (!expanded || isReplay) return undefined;
    let cancelled = false;
    const ctrl = new AbortController();
    const myKey = expQueryKey;
    setExpData(null);
    setExpLoading(true);
    const widen = expWidened ? "&expiries=8" : "";
    // Preserve full analytical scope (R4-15): mode + dte + scalp travel with
    // the expand fetch; widening expiries is the only explicit scope change.
    const modeParam = timeframe === "scalp" ? "scalp" : timeframe === "swing" ? "swing" : "day";
    const dteParam = dte != null ? `&dte=${encodeURIComponent(dte)}` : "";
    const scalpParam = timeframe === "scalp" ? "&scalp=true" : "";
    axios
      .get(`${BACKEND_API}/heatmap/${encodeURIComponent(ticker)}?mode=${modeParam}&expiries=${expWidened ? 8 : expiries}${dteParam}${scalpParam}${widen && expWidened ? "" : ""}`, {
        timeout: 45000,
        signal: ctrl.signal,
      })
      .then((r) => {
        if (!cancelled && myKey === expQueryKey && r?.data?.strikes?.length && (!r.data.ticker || r.data.ticker === ticker)) setExpData({...r.data,ticker});
      })
      .catch(() => { /* fallback to in-frame data below */ })
      .finally(() => { if (!cancelled && myKey === expQueryKey) setExpLoading(false); });
    return () => { cancelled = true; ctrl.abort(); };
  }, [expanded, ticker, timeframe, expiries, dte, expWidened, expQueryKey, isReplay]);
  const overlayData = isReplay ? displayData : (expData?.ticker === ticker ? expData : baseData);
  const visibleData = expanded ? overlayData : displayData;
  const activeView = compareMode ? activePane : viewMode;
  const activeMetric = ["gex", "skylit"].includes(activeView) ? metric : "raw";
  const activeSurface = useMemo(() => mapSurface(visibleData, activeView, activeMetric), [visibleData, activeView, activeMetric]);
  const selectedReading = useMemo(() => {
    if (!selectedCell || selectedCell.ticker !== ticker || selectedCell.view !== activeView || selectedCell.metric !== activeMetric) return null;
    const {strike,colKey} = selectedCell;
    if (!shownMapStrikes(visibleData,displaySpot,expanded?null:fitRows,activeView,activeMetric).includes(strike) || !activeSurface.expiries.includes(colKey)) return null;
    const value = activeSurface.matrix[colKey]?.[String(strike)];
    return typeof value === "number" && Number.isFinite(value) ? {...selectedCell,value} : null;
  }, [selectedCell,ticker,activeView,activeMetric,visibleData,displaySpot,expanded,fitRows,activeSurface]);
  useEffect(() => {
    if (selectedCell?.colKey && !selectedReading) {
      setSelectedCell(selectedCell.wall_id ? {...selectedCell,colKey:null,value:null} : null);
    }
  }, [selectedCell,selectedReading]);
  useEffect(() => {
    publishScreenContext({page:"heatseeker",ticker,dte:dte==null?"all":dte===0?"0dte":`days:${dte}`,
      metric:activeView,overlayMetric:activeMetric,displayMode:isReplay?"replay":"live",snapshotId:visibleData?.snapshotId || null,mode:timeframe,
      expiries,selectedStrike:selectedReading?.strike ?? null,selectedExpiry:selectedReading?.colKey ?? null,
      mapQuery:visibleData?.map_query || null,mapVersion:visibleData?.asof || null,
      mapStrikes:shownMapStrikes(visibleData,displaySpot,expanded?null:fitRows,activeView,activeMetric),
      mapExpiries:activeSurface.expiries,observedAt:visibleData?.event_time || visibleData?.observed_at || null});
  }, [ticker,dte,activeView,activeMetric,isReplay,timeframe,expiries,selectedReading,visibleData,displaySpot,expanded,fitRows,activeSurface]);
  useEffect(() => { setFollowWall(false); setFollowWallId(null); }, [ticker,timeframe,expiries,dte,expWidened]);
  const overlayNote = (() => {
    const n = overlayData?.strikes?.length || 0;
    const scope = `${timeframe} · ${expWidened ? 8 : expiries} expiries`;
    // Loading is explicit even with no rows yet: reopening after close must
    // show a loading state, never stale pixels and never a blank header.
    if (expLoading && !expData) return "loading scope…";
    if (!n) return "";
    if (expData) return `${scope} · ${n} strikes`;
    return `${scope} · ${n} strikes`;
  })();

  const handleCellClick = useCallback(
    (strike, colKey, value, pane = activeView) => {
      // P05 identity selection (R6-1: overlayData listed so replay-only
      // updates cannot retain a stale selection source): store wall_id +
      // strike at click time; values always re-resolved from the current
      // snapshot (never a stored number reused across refreshes).
      const src = visibleData;
      const snap = { asof: src?.asof || null, ticker };
      // R8-02 deeper edge: when follow is active, prefer the followed wall
      // over the struck wall so clicking near the followed zone keeps it
      // selected instead of switching to a different wall.
      const walls = src?.metrics?.walls || [];
      const s = Number(strike);
      const hit = walls.find((w) => s >= Number(w.low) && s <= Number(w.high)) || null;
      const wall_id = followWall && followWallId
        ? (hit?.wall_id === followWallId ? hit?.wall_id : followWallId)
        : (hit?.wall_id || null);
      const sel = { strike, colKey, value, ...snap, wall_id, view:pane, metric:["gex","skylit"].includes(pane)?metric:"raw" };
      // R7-F12: historical/study clicks NEVER reach the live Trade handler.
      // Both the call boundary (here) and the arming control (below) enforce
      // it; entering replay also disarms an armed live session.
      if (tradeMode && !isReplay && onCellClick) {
        onCellClick(strike, colKey, value, sel);
      } else {
        setSelectedCell(sel);
      }
    },
    [tradeMode,onCellClick,visibleData,ticker,isReplay,followWall,followWallId,activeView,metric]
  );
  // Clear ticker-dependent selection on symbol change (F18).
  useEffect(() => { setSelectedCell(null); setActivePane("gex"); }, [ticker]);
  // R7-F12: entering replay disarms live Trade mode; returning to live does
  // not re-arm it (deliberate user action required).
  useEffect(() => { if (isReplay) setTradeMode(false); }, [isReplay]);

  const handleStrikeClick = useCallback(
    (strike) => {
      if (!isReplay && onStrikeClick) onStrikeClick(strike);
    },
    [onStrikeClick,isReplay]
  );
  // R7-04: pane clicks share one selection source; the clicked pane owns
  // the readout. Defined after handleCellClick (same render scope).
  const handlePaneCellClick = useCallback((pane, strike, colKey, value) => {
    setActivePane(pane);
    handleCellClick(strike, colKey, value, pane);
  }, [handleCellClick]);

  // R8-02 (deeper edge): when followWall is on and a new live snapshot
  // arrives, re-resolve the followed wall_id against the new snapshot's
  // walls. If it's still present, keep it selected; if it vanished, clear
  // the follow so the next click picks a fresh wall instead of a ghost.
  useEffect(() => {
    if (!followWall || !followWallId || isReplay || !data) return;
    const stillPresent = data.metrics?.walls?.some(
      (w) => String(w.wall_id) === String(followWallId)
    );
    if (stillPresent === false) {
      setFollowWallId(null);
      setFollowWall(false);
    }
  }, [data?.metrics?.walls, followWall, followWallId, isReplay]);

  // R8-04: fetch the review state for the current snapshot's decision.
  // Only on live data (never during replay — outcomes/close owns that path).
  // Also builds the next-to-review queue: unreviewed decisions, newest
  // first, capped — evidence readiness via stored features, never returns.
  useEffect(() => {
    if (isReplay || !data || !data.snapshotId) return;
    setReviewState(null);          // clear previous snapshot's state
    setReviewDec(null);
    setReviewQueue([]);
    setReviewLoading(true);
    const snapId = data.snapshotId;
    let cancelled = false;
    axios
      .get(`${BACKEND_API}/solstice/${encodeURIComponent(ticker)}/decisions`)
      .then((r) => {
        if (cancelled) return;
        const list = r?.data?.decisions || [];
        const dec = list.find((d) => d.snapshot_id === snapId) || null;
        const queue = list
          .filter((d) => !d.review_state && d.snapshot_id !== snapId)
          .sort((a, b) => String(b.at_ts || "") < String(a.at_ts || "") ? -1 : 1)
          .slice(0, 5);
        if (!cancelled) {
          setReviewDec(dec);
          setReviewState(dec ? dec.review_state : null);
          setReviewQueue(queue);
        }
      })
      .catch(() => { /* review journal not yet populated — leave null */ })
      .finally(() => { if (!cancelled) setReviewLoading(false); });
    return () => { cancelled = true; };
  }, [data?.snapshotId, ticker, isReplay, reviewNonce]);

  // R8-02: Save review freezes a coherent snapshot context (wall/metric/
  // mode/snapshot) onto the decision's review — never a partial live screen.
  const saveReview = useCallback((state) => {
    if (isReplay || !reviewDec?.decision_id || reviewSaving) return;
    setReviewSaving(true);
    const note = `wall ${selectedCell?.wall_id || reviewDec?.features?.wall_id || "?"} ` +
      `metric ${metric} view ${viewMode} mode live`;
    axios
      .post(`${BACKEND_API}/solstice/${encodeURIComponent(ticker)}/decisions/${encodeURIComponent(reviewDec.decision_id)}/review`,
        { state, reason: reviewReason || null, note })
      .then(() => setReviewNonce((n) => n + 1))
      .catch(() => { /* save failed — pill keeps prior state, no false durable */ })
      .finally(() => setReviewSaving(false));
  }, [isReplay, reviewDec, reviewSaving, reviewReason, selectedCell, metric, viewMode, ticker]);

  return (
    <div className="skylit-full-dashboard">
      {/* 1. Top Ticker Bar */}
      <SkylitTickerBar
        activeTicker={ticker}
        onTickerChange={onTickerChange}
        tickers={tickers}
      />

      {/* 2. Control Bar */}
      <SkylitControlBar
        ticker={ticker}
        spot={displaySpot}
        change={isReplay ? null : change}
        changePct={isReplay ? null : changePct}
        viewMode={viewMode}
        onViewModeChange={onViewModeChange}
        timeframe={timeframe}
        onTimeframeChange={onTimeframeChange}
        expiries={expiries}
        onExpiriesChange={onExpiriesChange}
        metric={metric}
        onMetricChange={setMetric}
        isLive={!isReplay && isLive}
        onRefresh={isReplay ? undefined : onRefresh}
        onExpand={() => setExpanded(true)}
        onTickerChange={onTickerChange}
        tickers={tickers}
      />

      {/* 2.4 Solstice status strip — Environment · Location · Setup state · Data status (T23) */}
      <SolsticeStatusStrip
        data={displayData} spot={displaySpot} ticker={ticker} isLive={isReplay ? false : isLive}
        onSelectWall={(wall) => {
          if (!wall) return;
          setSelectedCell({
            strike: wall.mid ?? wall.low, colKey: null, value: null,
            asof: (displayData || data)?.asof || data?.asof || null,
            ticker, wall_id: wall.wall_id || null,
          });
        }}
      />

      {/* 2.5 Exposure strip — live backend exposure-rule badges, hidden when none.
          Live-only: never rendered inside historical replay. */}
      {!isReplay && <ExposureStrip ticker={ticker} />}

      {/* 2.6 Bottom replay strip — deterministic session replay + data status */}
      <ReplayStrip ticker={ticker} onReplay={setReplaySnap} openRequest={replayOpenRequest} />
      {isReplay && (
        <div className="skylit-replay-banner" data-testid="solstice-replay-banner" title="Replay mode — live refresh ignored">
          REPLAY {replaySnap?.asof || ""} — live updates paused · select Live in the replay strip to return
        </div>
      )}

      {/* 2.6 Alert-engine strip — live detector badges (GAMMA_FLIP excluded; stays in exposure path).
          Live-only: hidden in replay so live alerts cannot masquerade as history. */}
      {!isReplay && <AlertEngineStrip ticker={ticker} />}

      {/* 2.5 Trade Mode bar */}
      <div className="skylit-col-bar">
        <div className="skylit-col-spacer" />
        {selectedReading && !tradeMode && (
          <SelectedCellReadout selectedCell={selectedReading} displayData={visibleData} metric={metric} viewMode={compareMode ? activePane : viewMode} />
        )}
        <button
          className="skylit-trade-mode-btn"
          onClick={zoomOut}
          title="Smaller grid"
          data-testid="skylit-zoom-out"
        >
          A−
        </button>
        <button
          className="skylit-trade-mode-btn"
          onClick={zoomReset}
          title={`Reset zoom (now ${Math.round(gridZoom * 100)}%)`}
          data-testid="skylit-zoom-reset"
        >
          {Math.round(gridZoom * 100)}%
        </button>
        <button
          className="skylit-trade-mode-btn"
          onClick={zoomIn}
          title="Bigger grid"
          data-testid="skylit-zoom-in"
        >
          A+
        </button>
        <button
          className={`skylit-trade-mode-btn${scaleLock && !compareMode ? " active" : ""}${compareLock ? " active" : ""}`}
          onClick={() => {
            if (compareMode) {
              setCompareLock((cur) => (cur ? null : { ...compareScales }));
            } else {
              setScaleLock((cur) => (cur ? null : liveScale));
            }
          }}
          title={compareMode
            ? (compareLock ? "Unlock per-pane comparison scales" : "Lock per-pane GEX+VEX scales for replay comparison (clears on scope change)")
            : (scaleLock ? "Unlock comparison scale — back to relative" : "Lock the current color scale for replay comparison (clears on scope change)")}
          data-testid="skylit-scale-lock"
        >
          {compareMode ? (compareLock ? "Scales locked" : "Lock scales") : (scaleLock ? "Scale locked" : "Lock scale")}
        </button>
        <button
          className={`skylit-trade-mode-btn${compareMode ? " active" : ""}`}
          onClick={() => setCompareMode((m) => !m)}
          title={compareMode ? "Back to single grid (keeps symbol and wall)" : "Compare GEX + VEX side by side (one snapshot, no extra request)"}
          data-testid="skylit-compare-toggle"
        >
          GEX+VEX
        </button>
        {/* R8-02: follow-wall toggle — keep the same wall_id across compatible
            live refreshes. Toggled on/off; seeded from current selection. */}
        <button
          className={`skylit-trade-mode-btn${followWall ? " active" : ""}`}
          onClick={() => {
            const turningOn = !followWall;
            setFollowWall((f) => !f);
            if (turningOn && selectedCell?.wall_id) setFollowWallId(selectedCell.wall_id);
          }}
          title={followWall
            ? "Stop following this wall (next selection picks a new one)"
            : (selectedCell?.wall_id ? `Follow wall ${selectedCell.wall_id} across refreshes` : "Pick a wall first, then follow it")}
          data-testid="skylit-follow-wall-toggle"
          disabled={!selectedCell || isReplay}
        >
          {followWall ? (selectedCell?.wall_id ? `Following ${selectedCell.wall_id}` : "Follow") : (selectedCell?.wall_id ? "Follow this wall" : "Follow")}
        </button>
        <button
          className="skylit-trade-mode-btn"
          onClick={() => setExpanded(true)}
          title="Expand grid full-screen (Esc to close)"
          data-testid="skylit-expand-btn"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 3h6v6" /><path d="M9 21H3v-6" />
            <path d="M21 3l-7 7" /><path d="M3 21l7-7" />
          </svg>
          Expand
        </button>
        <button
          className={`skylit-trade-mode-btn${tradeMode ? " active" : ""}`}
          onClick={() => { if (!isReplay) setTradeMode(!tradeMode); }}
          disabled={isReplay}
          title={isReplay ? "Trade is disabled in replay (live-only action)" : "Trade Mode: click any cell to open Quick Trade"}
          data-testid="skylit-trade-btn"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          Trade
        </button>
      </div>

      {/* 3. Main Content Area */}
      <div className="skylit-main-area">
        {/* Heatmap Grid — fills available height (fitRows) with zoom */}
        <div
          className="skylit-heatmap-area"
          ref={heatAreaRef}
          style={{ zoom: gridZoom }}
          data-testid="skylit-heatmap-area"
        >
          {loading && (
            <div className="skylit-loading-overlay">
              <div className="skylit-loading-spinner" />
              <span>Loading market data…</span>
            </div>
          )}
          {!loading && data && (!data.strikes || data.strikes.length === 0) && (
            <div style={{
              padding: "24px", textAlign: "center", color: "var(--text-secondary, #94a3b8)",
              border: "1px dashed rgba(148,163,184,0.3)", borderRadius: 8, margin: "12px",
            }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                No strikes match the current filters
              </div>
              <div style={{ fontSize: 12 }}>
                {dte != null
                  ? `No listed expiries within ${dte} DTE right now (weekends/holidays). `
                  : ""}
                Try: DTE → All, or Expiries → 4+.
              </div>
            </div>
          )}
          {compareMode ? (
            <CompareWorkspace
              data={displayData}
              spot={displaySpot}
              ticker={ticker}
              metric={metric}
              gridZoom={gridZoom}
              density="compact"
              windowRows={fitRows}
              onPaneCellClick={handlePaneCellClick}
              onStrikeClick={handleStrikeClick}
              onPaneScale={paneScaleReady}
              compareLock={compareLock}
            />
          ) : (
          <SkylitHeatmapGrid
            data={displayData}
            spot={displaySpot}
            ticker={ticker}
            viewMode={viewMode}
            metric={metric}
            scale={scaleLock ? { ...scaleLock, locked: true } : null}
            onScaleReady={handleScaleReady}
            onCellClick={handleCellClick}
            onStrikeClick={handleStrikeClick}
            windowRows={fitRows}
          />
          )}
        </div>

        {/* Metrics Sidebar */}
        <div className="skylit-sidebar-area">
          <SkylitMetricsSidebar
            data={displayData}
            spot={displaySpot}
            viewMode={viewMode}
            metric={metric}
            regime={isReplay ? (visibleData?.regime || null) : regime}
          />
          {/* T07/T23: selected-wall inspector + two-sided scenarios (deterministic) */}
          <SelectedWallBlock
            data={displayData} spot={displaySpot}
            selectedCell={followWall && effectiveWallId
              ? { ...selectedCell, wall_id: effectiveWallId }
              : selectedCell}
            metric={metric} replay={isReplay}
          />
          {/* R8-04: review journal state for the current snapshot's decision */}
          <div className="skylit-review-pill" data-testid="skylit-review-pill">
            {reviewLoading && (
              <span className="skylit-review-loading" data-testid="skylit-review-loading">
                loading review…
              </span>
            )}
            {!reviewLoading && reviewState !== null && (
              <>
                <span className="skylit-review-label">Decision:</span>
                <span className={`skylit-review-state skylit-review-${reviewState}`}>
                  {reviewState}
                </span>
              </>
            )}
            {!reviewLoading && reviewState === null && !isReplay && displayData?.snapshotId && (
              <span className="skylit-review-pending" data-testid="skylit-review-pending">
                No review yet
              </span>
            )}
          </div>
          {/* R8-02/R8-04: Save review + Next to review. Live only; read-only
              controls never call brokerage routes (POST goes to the review
              journal, which persists research rows, not orders). */}
          {!isReplay && reviewDec && (
            <div className="skylit-review-save" data-testid="skylit-review-save">
              <span className="skylit-review-label">Save:</span>
              {["reviewed", "waiting", "skipped"].map((s) => (
                <button key={s} className="skylit-trade-mode-btn"
                  data-testid={`skylit-review-save-${s}`}
                  disabled={reviewSaving}
                  title={`Mark this decision ${s} (frozen snapshot context)`}
                  onClick={() => saveReview(s)}>
                  {s}
                </button>
              ))}
              <select data-testid="skylit-review-reason" value={reviewReason}
                title="Reason recorded with the review"
                onChange={(e) => setReviewReason(e.target.value)}>
                <option value="">reason…</option>
                {["CONFIRMED_SETUP", "NEEDS_MORE_EVIDENCE", "STALE_DATA", "WRONG_WALL", "TIME_EXPIRED"].map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
          )}
          {!isReplay && reviewQueue.length > 0 && (
            <div className="skylit-review-queue" data-testid="skylit-review-queue"
              title="Unreviewed decisions, newest first (max 5). Replay jump only — never live orders.">
              <span className="skylit-review-label">Next to review:</span>
              {reviewQueue.map((d) => (
                <button key={d.decision_id} className="skylit-trade-mode-btn"
                  data-testid={`skylit-review-open-${d.decision_id}`}
                  title={`Replay snapshot ${d.snapshot_id || "?"} (${d.scenario || "?"} ${d.side || ""})`}
                  onClick={() => d.snapshot_id && setReplayOpenRequest({ id: d.snapshot_id, nonce: Date.now() })}>
                  {d.scenario || d.side || d.decision_id} · {String(d.at_ts || "").slice(11, 16)}
                </button>
              ))}
            </div>
          )}
          </div>
      </div>

      {/* 3.5 Meridian & Velocity band REMOVED from Solstice (2026-09-03,
          Nav directive: "get rid of these boxes"). The panels still live
          in HeatseekerDashboard (Zenith) rows + serve direct API consumers;
          their backends were repaired in Phase 8 (numba gamma, IV reasons,
          wheel cache). This component renders grid + sidebar only. */}

      {/* 3.6 Expanded full-page grid overlay (2026-09-03). Same grid +
          sidebar, full viewport, all rows visible. Esc or ✕ closes. */}
      {expanded && (
        <div
          className="skylit-expanded-overlay"
          data-testid="skylit-grid-expanded"
          role="dialog"
          aria-label="Expanded heatmap grid"
        >
          <div className="skylit-expanded-header">
            <div className="skylit-expanded-title">
              <span className="skylit-expanded-ticker">{ticker}</span>
              <span className="skylit-expanded-label">Full grid</span>
              {overlayNote && <span className="skylit-expanded-coverage">{overlayNote}</span>}
              <button
                className="skylit-trade-mode-btn"
                onClick={() => setExpWidened((w) => !w)}
                title="Widen analysis to 8 expiries (explicit scope change)"
                data-testid="skylit-expand-widen"
              >
                {expWidened ? "Scope: wide (8)" : "Widen to 8"}
              </button>
              <span className="skylit-expanded-hint">Esc to close</span>
            </div>
            <button
              className="skylit-expanded-close"
              onClick={() => setExpanded(false)}
              data-testid="skylit-expand-close"
            >
              ✕ Close
            </button>
          </div>
          <div className="skylit-expanded-body">
            <div className="skylit-expanded-grid">
              {compareMode ? (
                <CompareWorkspace
                  data={overlayData}
                  spot={displaySpot}
                  ticker={ticker}
                  metric={metric}
                  gridZoom={1}
                  density="full"
                  windowRows={null}
                  onPaneCellClick={handlePaneCellClick}
                  onStrikeClick={handleStrikeClick}
                  onPaneScale={paneScaleReady}
                  compareLock={compareLock}
                />
              ) : (
              <SkylitHeatmapGrid
                data={overlayData}
                spot={displaySpot}
                ticker={ticker}
                viewMode={viewMode}
                metric={metric}
                scale={scaleLock ? { ...scaleLock, locked: true } : null}
                onCellClick={handleCellClick}
                onStrikeClick={handleStrikeClick}
                density="full"
              />
              )}
            </div>
            <div className="skylit-expanded-sidebar">
              <SkylitMetricsSidebar
                data={overlayData}
                spot={displaySpot}
                viewMode={viewMode}
                metric={metric}
                regime={isReplay ? (visibleData?.regime || null) : regime}
              />
              {/* R6-1 expanded inspector parity: same wall/scenarios as inline. */}
              <SelectedWallBlock data={overlayData} spot={displaySpot} selectedCell={selectedCell} metric={metric} replay={isReplay} />
            </div>
          </div>
        </div>
      )}

      {/* 4. Bottom Ticker Info Bar */}
      <div className="skylit-bottom-bar">
        <div className="skylit-bottom-ticker">
          <span className="skylit-bottom-ticker-name">{ticker}</span>
          <span className="skylit-bottom-spot">
            ${displaySpot != null ? Number(displaySpot).toFixed(2) : "—"}
          </span>
          {!isReplay && changePct != null && (
            <span
              className="skylit-bottom-change"
              style={{ color: changePct >= 0 ? "#34d399" : "#f87171" }}
            >
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
            </span>
          )}
        </div>
        <div className="skylit-bottom-tabs">
          <button
            className={`skylit-bottom-tab${viewMode === "gex" ? " active" : ""}`}
            onClick={() => onViewModeChange && onViewModeChange("gex")}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
            GEX
          </button>
          <button
            className={`skylit-bottom-tab${viewMode === "vex" ? " active" : ""}`}
            onClick={() => onViewModeChange && onViewModeChange("vex")}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            VEX
          </button>
        </div>
      </div>
    </div>
  );
}

export default memo(SkylitDashboard);
