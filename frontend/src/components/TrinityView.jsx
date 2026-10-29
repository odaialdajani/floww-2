import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API } from "../config/api";
import SkylitHeatmapGrid from "./heatseeker/SkylitHeatmapGrid";
import { mapSurface } from "./heatseeker/shownMapStrikes";
import { wallPositionOf } from "../lib/solsticeSelection";
import { useReviewJournal } from "./triad/useReviewJournal";
import { ALL_BASES, surfaceStatus, wallValues, wallRead } from "../lib/solsticeMetrics";
import StrikeExposureProfile from "./triad/StrikeExposureProfile";
import MarketObservationLine from './triad/MarketObservationLine';
import { marketMoney, exactMoney } from './triad/marketFormat';
import AskFlow from "./heatseeker/AskFlow";
import HeatmapLandmarks from "./heatseeker/HeatmapLandmarks";
import { usePublishScreenContext } from "../agent/useScreenContext";
import { replayToDisplay } from "../lib/solsticeReplay";
import ReplayStrip from "./heatseeker/ReplayStrip";
import MarketInspectorDock from "./triad/MarketInspectorDock";
import {OpenInterestPanel, CallPutLadder} from "./heatseeker/LoadedContractPanels";
import "./triad/MarketDesktop.css";

/**
 * TrinityView — Triad 0DTE review desk (O4 rebuild).
 *
 * Consumes the versioned heatmap snapshot projection directly
 * (GET /api/heatmap/{ticker}: snapshotId, formula_version, walls, grids,
 * scenarios, quality). The old Public-chain mapper (client-side gex split
 * by sign, 200-contract truncation, hardcoded fallback expiry, vex: 0,
 * empty floors/ceilings) is gone: every number on screen is a backend
 * packet field, and anything missing renders as unavailable.
 *
 * Layout: compact SPY/QQQ/SPX context strip, one focused symbol, one
 * raw/adjusted pair on the same rail, selected-wall scenario card,
 * contract-review drawer, second-level review journal.
 */
const TRIAD = ["^SPX", "SPY", "QQQ"];
const HANDOFF_KEY = "solstice.triadHandoff";

// Adjusted bases available in the snapshot contract (metrics.grids).
// Window Δvolume×delta has no per-strike surface in the packet, so it is
// offered disabled with the reason rather than invented client-side.
const ADJUSTED_BASES = ALL_BASES.filter(b => b.id !== "raw");

function readHandoff() {
  try {
    const raw = sessionStorage.getItem(HANDOFF_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(HANDOFF_KEY);
    const h = JSON.parse(raw);
    return h && typeof h === "object" ? h : null;
  } catch {
    return null;
  }
}

function wallForStrike(walls, strike) {
  const s = Number(strike);
  if (!Number.isFinite(s)) return null;
  return (walls || []).find((w) => s >= Number(w.low) && s <= Number(w.high)) || null;
}

function scenariosForWall(scenarios, wall, spot) {
  const list = (scenarios || []).filter((sc) => !wall || sc.wall_id === wall.wall_id);
  if (list.length || !wall) return list;
  // Compat fallback (same derivation as the Solstice drawer): position-based
  // two-sided watch. Never another wall's scenarios.
  const wpos = wallPositionOf(wall, spot);
  const side = wpos === "inside" ? "below" : wpos;
  return [
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

function TrinityView({ onFocusTicker, ticker: sharedTicker = null }) {
  const sharedStockChoice = Boolean(sharedTicker) && typeof onFocusTicker === "function";
  const [handoff] = useState(readHandoff);
  const [ticker, setTicker] = useState(handoff?.ticker || sharedTicker || "SPY");
  const [symbolInput, setSymbolInput] = useState(handoff?.ticker || sharedTicker || "SPY");
  const [loadedPayload, setPayload] = useState(null);
  const [replayDisplay, setReplayDisplay] = useState(null);
  const [liveReload, setLiveReload] = useState(0);
  const candidate = replayDisplay?.ticker === ticker ? replayDisplay : loadedPayload;
  const payload = candidate?.ticker && candidate.ticker !== ticker ? null : candidate;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wallId, setWallId] = useState(handoff?.wall_id || null);
  const [basis, setBasis] = useState("session_delta_volume");
  const [activePane, setActivePane] = useState("raw");
  const [mobilePane, setMobilePane] = useState("raw");
  const [cell, setCell] = useState(null);
  const [contractSelection, setContractSelection] = useState(null);
  const [reviewSelectionRevision, setReviewSelectionRevision] = useState(0);
  const onContractSelection = useCallback(selection => {
    setContractSelection(selection);
    if (selection?.status === "resolved") setCell({strike: Number(selection.identity.strike), colKey: selection.identity.expiry});
  }, []);
  // Owner UX decision 2026-10-24 (live request): a FRESH Market entry uses
  // the existing explicitly-labeled "All loaded" scope so the desk is useful
  // on weekends too. 0DTE stays an explicitly selectable request with its
  // strict same-day refusal (UI-M02 semantics preserved: the refusal never
  // auto-substitutes a broader scope — the distinct next action stays a
  // user-initiated click). Nothing persists: this is session state only.
  const [scope, setScope] = useState("loaded");
  const [replayId, setReplayId] = useState(handoff?.replayAsOf ? handoff.snapshotId || null : null);
  const isReplay = Boolean(replayId || replayDisplay);
  const [board, setBoard] = useState([]);
  const [boardStatus, setBoardStatus] = useState("loading");
  const lastSharedTicker = useRef(sharedTicker);
  const handoffReported = useRef(false);
  useLayoutEffect(() => {
    if (!handoffReported.current) {
      handoffReported.current = true;
      if (handoff?.ticker && handoff.ticker !== sharedTicker) onFocusTicker?.(handoff.ticker);
    }
    if (sharedTicker && sharedTicker !== lastSharedTicker.current && sharedTicker !== ticker) {
      setTicker(sharedTicker); setSymbolInput(sharedTicker); setWallId(null); setCell(null);
      setContractSelection(null); setReplayId(null); setReplayDisplay(null); setDrawerOpen(false);
    }
    lastSharedTicker.current = sharedTicker;
  }, [sharedTicker, ticker, handoff, onFocusTicker]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  // Desktop composition (market-desktop-20261025): the selected-object
  // inspector is a persistent right dock at wide desktop widths and a proper
  // overlay at <=1280px (owner 13:40 + the composed-build measurement: at
  // 1280 docked, each map starves to ~305px while 4 expiry columns need
  // ~454px — so 1280 joins the overlay band; measured at 56f218ed).
  // `inspectorOpen` collapses the dock column / closes
  // the overlay; the explicit review action (`Review contracts`) forces it
  // open via drawerOpen. matchMedia is feature-detected: environments without
  // it (jsdom) stay in dock mode so behavior tests are unaffected.
  const initialNarrow = typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(max-width: 1280px)").matches : false;
  const [narrow, setNarrow] = useState(initialNarrow);
  const narrowRef = useRef(initialNarrow);
  useEffect(() => {
    narrowRef.current = narrow;
  }, [narrow]);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia("(max-width: 1280px)");
    const onChange = e => { setNarrow(e.matches); narrowRef.current = e.matches; };
    if (query.addEventListener) query.addEventListener("change", onChange);
    else if (query.addListener) query.addListener(onChange);
    return () => {
      if (query.removeEventListener) query.removeEventListener("change", onChange);
      else if (query.removeListener) query.removeListener(onChange);
    };
  }, []);
  // Owner 13:40 desktop composition: the dock starts CLOSED — the empty
  // 352px inspector no longer eats ~30% of the desk while nothing is
  // selected. A REAL selection (cell click, strike click, wall pick) or the
  // header toggle opens it; close/reopen/tabs are all retained.
  const [inspectorOpen, setInspectorOpen] = useState(false);
  // Owner 20:51 declutter: the secondary chrome (walls/landmarks/replay/
  // profile/review) renders as ONE deliberate workspace tab at a time —
  // quiet by default so the comparison leads. Nothing is deleted; every
  // block keeps its testids and honest strings.
  const [workspaceTab, setWorkspaceTab] = useState(null);
  // Owner 20:51: reversible Focus working-canvas — the maps fill the
  // viewport, obvious Exit/Esc, selection/scope state untouched (a layout
  // class only; never a CSS zoom, never a scale change).
  const [focusMode, setFocusMode] = useState(false);
  useEffect(() => {
    if (!focusMode) return undefined;
    const onKey = (ev) => { if (ev.key === "Escape") setFocusMode(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusMode]);
  // O5: same focus ownership as the Solstice inspector drawer.
  const drawerCloseRef = useRef(null);
  const drawerPrevFocusRef = useRef(null);
  useEffect(() => {
    if (!drawerOpen) return undefined;
    drawerPrevFocusRef.current = document.activeElement;
    drawerCloseRef.current?.focus({ preventScroll: true });
    return () => {
      // preventScroll: the measured owner preflight caught the plain restore
      // jumping the PAGE (ancestor scroller) 439px to reveal the Contracts
      // button — focus restoration must never move the desk underneath the
      // user. The sticky drawer close needs no scroll either.
      try { drawerPrevFocusRef.current?.focus?.({ preventScroll: true }); } catch { /* noop */ }
    };
  }, [drawerOpen]);
  const rawMapRef = useRef(null);
  // Reading position recorded by the show-loaded action (see the fetch
  // effect for the one-shot restore).
  const restoreScrollRef = useRef(null);
  const adjustedMapRef = useRef(null);
  // M1 (2026-10-24): a basis change re-centers only the adjusted grid (its
  // metric basis is part of the grid's centering key), which leaves the two
  // maps at different strike offsets (measured 80px at 1470x950). The same
  // divergence appears on every payload reload when the two panes' legends
  // wrap differently (at 1024x768 the adjusted legend wraps one line deeper,
  // its container is 25px shorter, and the grids' independent load-time
  // centering lands same-strike rows 13px apart). Raw keeps the user's
  // scroll, so on every basis or payload change the adjusted scroller is
  // re-anchored to raw: matching strike rows stay within 1px. This effect
  // runs after the grids' own layout-effect centering, so it is final.
  useEffect(() => {
    const raw = rawMapRef.current;
    const adjusted = adjustedMapRef.current;
    if (raw && adjusted && adjusted.scrollTop !== raw.scrollTop) adjusted.scrollTop = raw.scrollTop;
  }, [basis, payload]);
  // M1 (2026-10-24): programmatic re-centers (Center on price, Show selected
  // level, the grids' own mount/scope centering) write scrollTop with no user
  // gesture, and renderers that defer scroll events to rendering
  // opportunities which never arrive never fire the onScroll sync (measured
  // in an embedded headless pass: raw 978 vs adjusted 991 — same-strike rows
  // 13px apart at 1024x768). The grid marks every programmatic center on
  // the container via data-centered-scroll, so watching that marker keeps
  // the pair anchored to raw in those environments too; in normal browsers
  // this is redundant with the event path. Raw is the anchor by design —
  // an adjusted-side re-center falls back to raw's position.
  useEffect(() => {
    const raw = rawMapRef.current;
    const adjusted = adjustedMapRef.current;
    if (!raw || !adjusted || typeof MutationObserver === "undefined") return undefined;
    const anchor = () => {
      if (adjusted.scrollTop !== raw.scrollTop) adjusted.scrollTop = raw.scrollTop;
    };
    const observer = new MutationObserver(anchor);
    observer.observe(raw, { attributes: true, attributeFilter: ["data-centered-scroll"] });
    observer.observe(adjusted, { attributes: true, attributeFilter: ["data-centered-scroll"] });
    return () => observer.disconnect();
  }, [payload]);
  const syncMaps = event => {
    const source = event.currentTarget;
    const target = source === rawMapRef.current ? adjustedMapRef.current : rawMapRef.current;
    if (!target) return;
    if (target.scrollTop !== source.scrollTop) target.scrollTop = source.scrollTop;
    if (target.scrollLeft !== source.scrollLeft) target.scrollLeft = source.scrollLeft;
  };
  const genRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Focused-symbol snapshot projection (the contract — no client math).
  useEffect(() => {
    const myGen = ++genRef.current;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    setPayload(null);
    setWallId(ticker === handoff?.ticker ? handoff.wall_id || null : null);
    setCell(null);
    setDrawerOpen(false);
    const dteQuery = scope === "0dte" ? "&dte=0" : scope === "week" ? "&dte=7" : scope === "next" ? "&expiry_scope=next" : "";
    const url = replayId ? `${API}/solstice/replay/${encodeURIComponent(replayId)}` : `${API}/heatmap/${encodeURIComponent(ticker)}?mode=day&expiries=4${dteQuery}`;
    axios
      .get(url, {
        timeout: 45000, signal: ctrl.signal,
      })
      .then((r) => {
        if (!mountedRef.current || genRef.current !== myGen) return;
        const next = replayId ? replayToDisplay(r.data, ticker) : r.data;
        if (!next || (next.ticker && next.ticker !== ticker) || (replayId && next.snapshotId !== replayId)) { setError("Snapshot identity mismatch — no substitution made"); setLoading(false); return; }
        setPayload(next);
        setLoading(false);
        // Owner live request 2026-10-24 (ancestor scroll jumps): loading all
        // expiries from the 0DTE refusal unmounts the refusal blocks and the
        // document collapses mid-transition, so the browser clamps the page
        // from the user's reading position to the top (measured 355 -> 0).
        // The show-loaded click records the reading position; restore it
        // once, after the loaded content lays out (rAF fires post-commit).
        if (restoreScrollRef.current != null) {
          const y = restoreScrollRef.current;
          restoreScrollRef.current = null;
          // Double rAF: the first frame lays out the loaded commit; restoring
          // in the second lands after any post-commit re-anchoring settles.
          requestAnimationFrame(() => { requestAnimationFrame(() => { window.scrollTo(0, y); }); });
        }
      })
      .catch((e) => {
        if (!mountedRef.current || genRef.current !== myGen) return;
        if (e?.name === "CanceledError" || e?.code === "ERR_CANCELED") return;
        setError(e?.response?.data?.detail || e.message || "fetch failed");
        setLoading(false);
      });
    return () => { ctrl.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, scope, replayId, liveReload]);

  // Context strip: free leaderboard read (no scan, no budget spend).
  useEffect(() => {
    let cancelled = false;
    axios
      .get(`${API}/solstice/scan/leaderboard?limit=12`, { timeout: 15000 })
      .then((r) => { if (!cancelled) { setBoard(r?.data?.leaderboard || []); setBoardStatus(r?.data?.status || "unknown"); } })
      .catch(() => { if (!cancelled) setBoardStatus("source-error"); });
    return () => { cancelled = true; };
  }, []);

  const walls = useMemo(() => payload?.metrics?.walls || [], [payload]);
  const spot = payload?.spot ?? null;
  const selectedWall = useMemo(
    () => (walls || []).find((w) => w.wall_id === wallId) || null,
    [walls, wallId]
  );
  const rawSurface = useMemo(() => mapSurface(payload, "gex", "raw"), [payload]);
  const adjSurface = useMemo(() => mapSurface(payload, "gex", basis), [payload, basis]);
  const pairAxes = useMemo(() => ({strikes: rawSurface.strikes, expiries: rawSurface.expiries}), [rawSurface]);
  const pairScale = useMemo(() => {
    let min = 0, max = 0;
    for (const surface of [rawSurface, adjSurface]) for (const expiry of rawSurface.expiries) {
      for (const strike of rawSurface.strikes) {
        const value = surface.matrix?.[expiry]?.[String(strike)];
        if (typeof value === "number" && Number.isFinite(value)) { min = Math.min(min, value); max = Math.max(max, value); }
      }
    }
    return max > min ? {min, max, locked: true} : null;
  }, [rawSurface, adjSurface]);
  const adjDef = ADJUSTED_BASES.find((b) => b.id === basis);
  // Loaded expiry dates (2026-10-18): derived from the ACTUAL displayed raw
  // axis (payload.grid.expiries via mapSurface) — never the request scope,
  // session date or adjusted surface, which can list different or fewer
  // dates. Replay keeps the stored snapshot dates; there is no live
  // fallback. Display validation only (YYYY-MM-DD, UTC parse + roundtrip so
  // Feb 30 rejects): a valid subset is filtered out of an invalid value and
  // then declared incomplete — never claimed complete.
  const loadedExpiries = useMemo(() => {
    const list = Array.isArray(rawSurface?.expiries) ? rawSurface.expiries : [];
    const valid = [];
    let invalid = 0;
    for (const value of list) {
      if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
        && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
        && new Date(value + "T00:00:00Z").toISOString().slice(0, 10) === value) {
        valid.push(value);
      } else {
        invalid += 1;
      }
    }
    valid.sort();
    return { valid, invalid, total: list.length };
  }, [rawSurface]);
  const adjAvailable = adjSurface.available && surfaceStatus(payload, basis).status !== "unavailable";
  const scenarios = useMemo(
    () => scenariosForWall(payload?.scenarios, selectedWall, spot),
    [payload, selectedWall, spot]
  );
  const quality = payload?.quality || null;
  const values = wallValues(payload, selectedWall);
  const interaction = (payload?.interactions || []).find(i => i.wall_id === wallId) || null;
  const value = values?.[basis];
  const read = wallRead({ wall: selectedWall, spot, adjNet: value?.net ?? null,
    adjAvailable: adjAvailable && value?.net != null && !(value?.missing > 0) && !(value?.invalid > 0),
    rawGross: selectedWall?.gross ?? null, interaction, quality });
  const sessionDate = payload?.map_query?.sessionDate;
  const sameDayAdmitted = payload?.map_query?.dte === 0 && sessionDate && rawSurface.expiries.length > 0
    && rawSurface.expiries.every(expiry => expiry === sessionDate) && !["stale", "unavailable"].includes(quality?.state);
  const declaredScope = payload?.map_query?.expiryScope === "next" ? "next"
    : sameDayAdmitted ? "0dte" : payload?.map_query?.dte === 7 ? "week"
    : payload?.map_query && payload.map_query.dte == null ? "loaded" : "recorded";
  const activeMetric = activePane === "raw" ? "raw" : basis;
  const activeSurface = activePane === "raw" ? rawSurface : adjSurface;
  const contractScope = `${basis}|${activePane}|${declaredScope}`;
  const currentContract = contractSelection?.ticker === ticker && contractSelection.snapshotId === payload?.snapshotId
    && contractSelection.wallId === (selectedWall?.wall_id || null) && contractSelection.replay === isReplay
    && contractSelection.selectionScope === contractScope ? contractSelection : null;
  usePublishScreenContext({ contextVersion: 2, page: "trinity", selectedContract: currentContract?.identity || null,
    contractResolution: currentContract?.status || null, ticker, dte: declaredScope === "0dte" ? "0dte" : declaredScope === "week" ? "week" : "all",
    metric: "gex", overlayMetric: activeMetric, displayMode: isReplay ? "replay" : "live", snapshotId: payload?.snapshotId || null,
    mapQuery: payload?.map_query || null, mapVersion: payload?.asof || null, mapStrikes: activeSurface.strikes,
    mapExpiries: activeSurface.expiries, mode: "day", expiries: 4, provider: payload?.data_source || null,
    formula: payload?.formula_version || payload?.metrics?.formula_version || null, activePane, selectedWall: selectedWall?.wall_id || null,
    selectedStrike: cell?.strike ?? null, selectedExpiry: cell?.colKey || null,
    observedAt: payload?.event_time || payload?.observed_at || null });

  const submitSymbol = useCallback(() => {
    const t = (symbolInput || "").trim().toUpperCase();
    if (!t || t === ticker) return;
    setTicker(t);
    setWallId(null);
    setCell(null);
    setReplayId(null);
    setReplayDisplay(null);
    setDrawerOpen(false);
    if (onFocusTicker) onFocusTicker(t);
  }, [symbolInput, ticker, onFocusTicker]);

  const selectWall = useCallback((id) => {
    setReviewSelectionRevision(value => value + 1);
    setWallId(id);
    setCell(null);
    setDrawerOpen(false);
    // A wall pick is a REAL selection: surface the inspector on every
    // desktop (owner 13:40) — narrow mode overlays it, wide mode docks it.
    setInspectorOpen(true);
  }, []);

  const onGridCell = useCallback((strike, colKey = null, pane = "raw") => {
    const w = wallForStrike(walls, strike);
    if (w) {
      selectWall(w.wall_id);
    } else {
      selectWall(null);
    }
    setCell({ strike, colKey });
    setActivePane(pane);
    setInspectorOpen(true); // a REAL selection opens the inspector (owner 13:40)
  }, [walls, selectWall]);

  // Owner 20:51: ONE synchronized Center for the PAIR. The per-map button
  // semantics (scroll the container so the spot is centered; never a scale
  // change) applied to BOTH maps at once. Selection and scroll anchors are
  // untouched; if a map has no rendered spot row it stays where it is.
  const centerPair = useCallback(() => {
    for (const ref of [rawMapRef, adjustedMapRef]) {
      const el = ref && ref.current;
      if (!el || typeof el.scrollTo !== "function") continue;
      const spot = el.querySelector(".trin-spot-rail") || el.querySelector('[data-testid="skylit-spot-chip"]');
      if (!spot) continue;
      const box = el.getBoundingClientRect();
      const sr = spot.getBoundingClientRect();
      el.scrollTo({ top: el.scrollTop + (sr.top - box.top) - box.height / 2 + sr.height / 2 });
    }
  }, []);
  // Root 21:3x: the per-map "Show selected level" row is hidden in Market
  // mode (it duplicated Center AND selected-level on both maps); ONE pair
  // action scrolls BOTH maps to the selected strike instead. Scroll-only —
  // the selection itself never changes.
  const centerSelected = useCallback(() => {
    for (const ref of [rawMapRef, adjustedMapRef]) {
      const el = ref && ref.current;
      if (!el || typeof el.scrollTo !== "function") continue;
      const sel = el.querySelector("td.trin-selected") || el.querySelector("tr.trin-row-selected");
      if (!sel) continue;
      const box = el.getBoundingClientRect();
      const sr = sel.getBoundingClientRect();
      el.scrollTo({ top: el.scrollTop + (sr.top - box.top) - box.height / 2 + sr.height / 2 });
    }
  }, []);
  const openContracts = useCallback(() => setDrawerOpen(true), []);

  const journal = useReviewJournal(ticker, isReplay ? null : payload?.snapshotId,
    `triad wall ${selectedWall?.wall_id || "?"} basis ${basis} mode live`);

  const onReplayDisplay = useCallback(display => {
    setReplayDisplay(display);
    setCell(null);
    setWallId(null);
    setDrawerOpen(false);
    if (!display) { setReplayId(null); setLiveReload(n => n + 1); }
  }, []);
  const replayControls = <ReplayStrip ticker={ticker} onReplay={onReplayDisplay} />;
  const isSPX = ticker === "^SPX" || ticker === "SPX";
  const spxMissing = isSPX && !loading && (!payload || !payload.strikes?.length);

  if (loading && !payload) {
    return (
      <div className="trinity-layout">{replayControls}<div className="trinity-loading">
        <div className="trinity-loading-spinner" />
        <span>Loading Market view…</span>
      </div></div>
    );
  }
  if ((error || !payload) && !loading) {
    return (
      <div className="trinity-layout">{replayControls}<div className="trinity-error" data-testid="triad-error">
        <span>⚠</span> {isSPX
          ? "SPX unavailable in this session (entitlement/coverage unknown). No substitution made — pick another symbol."
          : `Error: ${error || "no data"}`}
        {sharedStockChoice
          ? <button type="button" onClick={() => { setReplayDisplay(null); setReplayId(null); setLiveReload(value => value + 1); }}>Retry this stock</button>
          : <button onClick={() => { setReplayDisplay(null); setReplayId(null); setTicker("SPY"); }}>SPY</button>}
      </div></div>
    );
  }

  return (
    <div className={`trinity-layout trinity-desktop ${inspectorOpen || drawerOpen ? "tdk-dock-open" : "tdk-dock-closed"}${focusMode ? " tdk-focus-mode" : ""}`} data-testid="triad-view">
      {/* Desktop composition (market-desktop-20261025): ONE calm grouped
          command header — focus, scope, basis, assistant, context — then the
          raw/adjusted comparison immediately, and the selected-object
          inspector docked beside it. Every control, testid, honest refusal
          string and data path is preserved; only the composition moves. */}
      <header className="tdk-head tdk-command-bar" data-testid="triad-command-bar">
        <div className="tdk-head-row">
          {!sharedStockChoice ? (
            <div className="tdk-head-group">
              <span className="tdk-head-label">Market</span>
              <input value={symbolInput} onChange={(e) => setSymbolInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") submitSymbol(); }}
                data-testid="triad-symbol-input" aria-label="Focused symbol" placeholder="SYM" />
              <button type="button" onClick={submitSymbol} data-testid="triad-symbol-go"
                title="Load this symbol's snapshot (its own data only)">Go</button>
            </div>
          ) : (
            <div className="tdk-head-group">
              <span className="tdk-head-label">Market ·</span>
              <span className="tdk-chip" data-testid="triad-head-focus">Focused: {ticker}</span>
            </div>
          )}
          <div className="tdk-head-group">
            <select aria-label="Market view expiry scope" value={isReplay ? declaredScope : scope} disabled={isReplay} onChange={e => setScope(e.target.value)}>
              <option value="loaded">All loaded · max 4 expiries</option><option value="0dte">0DTE · request same session</option><option value="week">Week · ≤7 calendar DTE</option>
              <option value="next">Next listed · one expiry, ≤30 calendar DTE</option>
              {isReplay && declaredScope === "recorded" && <option value="recorded">Recorded scope · exact dates below</option>}
            </select>
            <label>Adjusted context <select aria-label="Adjusted context" value={basis} onChange={e => { setBasis(e.target.value); setActivePane("adjusted"); }}>
              {ADJUSTED_BASES.map(b => <option key={b.id} value={b.id} data-testid={`triad-basis-${b.id}`}
                disabled={surfaceStatus(payload, b.id).status === "unavailable" && basis !== b.id} title={surfaceStatus(payload, b.id).reason || b.units}>{b.label}</option>)}
            </select></label>
          </div>
          <div className="tdk-head-group">
            <AskFlow subject={`${ticker} · raw wall ${wallId || "none"}`} overlayMetric={activeMetric} displayMode={isReplay ? "replay" : "live"} compact />
          </div>
          <div className="tdk-head-group">
            <details className="triad-context-disclosure" data-testid="triad-context-disclosure">
              <summary role="button" aria-label="Market context">Market context</summary>
              <div className="triad-context-body">
                <p className="triad-context-method">Raw = where · adjusted = weighting, not observed direction.</p>
                <ContextStrip board={board} ticker={ticker} symbolInput={symbolInput}
                  onSymbolInput={setSymbolInput} onSubmit={submitSymbol} showStockControl={false}
                  boardStatus={boardStatus} />
                {["session_delta_volume", "activity", "window"].includes(basis) && <details data-testid="triad-activity-coverage">
                  <summary>Activity window and coverage</summary>
                  <p>Volume window: {payload?.metrics?.grids?.[basis]?.interval?.start && payload?.metrics?.grids?.[basis]?.interval?.end
                    ? `${payload.metrics.grids[basis].interval.start} → ${payload.metrics.grids[basis].interval.end}` : "unavailable — no declared bounds"}.
                    {" "}Usable inputs: {surfaceStatus(payload, basis).usable ?? "unknown"} · {surfaceStatus(payload, basis).status}.
                    {" "}{surfaceStatus(payload, basis).reason || "No volume or Greeks are inferred from OI."}</p>
                </details>}
              </div>
            </details>
          </div>
          <div className="tdk-head-group">
            <button type="button" className="tdk-head-toggle" data-testid="triad-pair-center"
              onClick={centerPair} title="Center both maps on the current price (synchronized)">
              Center
            </button>
            {cell && (
              <button type="button" className="tdk-head-toggle" data-testid="triad-pair-selected"
                onClick={centerSelected} title="Scroll both maps to the selected strike (the per-map selected-level action, synchronized)">
                Selected
              </button>
            )}
            <button type="button" className="tdk-head-toggle" data-testid="triad-focus-toggle"
              aria-pressed={focusMode} onClick={() => setFocusMode(value => !value)}
              title="Focus the comparison — maps fill the screen; Esc or Exit returns exactly here (no zoom)">
              {focusMode ? "Exit focus" : "Focus"}
            </button>
            <button type="button" className="tdk-head-toggle" data-testid="triad-inspector-toggle"
              aria-pressed={inspectorOpen} onClick={() => setInspectorOpen(value => !value)}
              title="Show or hide the selected-object inspector">
              {inspectorOpen ? "Hide inspector" : "Inspector"}
            </button>
            {replayId && !replayDisplay && <button type="button" onClick={() => onReplayDisplay(null)}>Leave recorded observation · Live</button>}
          </div>
          {!inspectorOpen && !cell && !selectedWall && (
            <span className="triad-selection-cue" data-testid="triad-selection-cue" role="status">
              Select a strike or wall to open its inspector
            </span>
          )}
          <div className="triad-mobile-switch"><button onClick={() => setMobilePane("raw")}>Raw</button><button onClick={() => setMobilePane("adjusted")}>Adjusted</button></div>
        </div>
        <div className="tdk-head-sub">
          {/* Actual loaded expiry dates (2026-10-18): the displayed raw axis,
              validated display-only. Missing or unreadable dates stay honest;
              an excluded invalid value is declared, never claimed complete. */}
          <span className="triad-loaded-dates" data-testid="triad-loaded-dates"
            title="Actual loaded expiry dates from the displayed raw axis — never the request scope">
            Loaded expiries: {loadedExpiries.total === 0
              ? "unavailable — no expiry dates in this snapshot"
              : loadedExpiries.valid.length
                ? loadedExpiries.valid.join(", ")
                : "none valid — expiry dates unreadable in this snapshot"}
            {loadedExpiries.invalid > 0 && ` · ${loadedExpiries.invalid} invalid expiry value${loadedExpiries.invalid === 1 ? "" : "s"} excluded — not complete`}
          </span>
          <MarketObservationLine replay={isReplay} data={payload} quality={quality} />
        </div>
      </header>
      {payload?.scope_selection?.status === "unavailable" && <div role="status" data-testid="triad-empty-scope" className="triad-band-note">No listed expiry in the server's 30-day bound — no substitution made.</div>}
      {/* P0-1 (UX review): when the default 0DTE request is honestly refused
          AND no walls are classified, the desk renders its designed empty
          state — a centered honest callout with the "Show all loaded
          expiries" action visually primary, the exact loaded dates and the
          LIVE/REPLAY identity. Panes below keep their headers, so the desk
          keeps visible structure while empty. When walls DO exist, the same
          admission renders as the compact in-band chip instead. */}
      {!isReplay && scope === "0dte" && !sameDayAdmitted && (walls || []).length > 0 && <div className="triad-band-note triad-scope-notice">
        <p role="status" data-testid="triad-scope-admission">
          Same-day admission unavailable — the loaded observation is not verified 0DTE. 0DTE was your explicit request, not a saved choice — nothing is saved between visits, and the desk does not substitute a broader scope by itself. Exact loaded dates remain visible; no same-session expiry or entitlement is invented.
        </p>
        <button type="button" data-testid="triad-show-loaded" onClick={() => { restoreScrollRef.current = window.scrollY; setScope("loaded"); }}>Show all loaded expiries</button>
      </div>}
      {!isReplay && scope === "0dte" && !sameDayAdmitted && !(walls || []).length && (
        <div className="triad-empty-desk" data-testid="triad-empty-desk">
          <p role="status" data-testid="triad-scope-admission">
            <strong>0DTE not admitted — the loaded observation is not verified 0DTE.</strong>
            0DTE was your explicit request, not a saved choice; no same-session expiry was invented — switch to all loaded expiries:
          </p>
          <span className="triad-empty-desk-identity">
            {isReplay ? "REPLAY" : "LIVE"} · loaded expiries: {loadedExpiries.total === 0
              ? "unavailable — no expiry dates in this snapshot"
              : loadedExpiries.valid.length
                ? loadedExpiries.valid.join(", ")
                : "none valid — expiry dates unreadable in this snapshot"}
            {loadedExpiries.invalid > 0 && ` · ${loadedExpiries.invalid} invalid excluded — not complete`}
          </span>
          <button type="button" data-testid="triad-show-loaded" className="triad-empty-desk-action" onClick={() => { restoreScrollRef.current = window.scrollY; setScope("loaded"); }}>Show all loaded expiries</button>
        </div>
      )}
      <div className="tdk-body">
      <main className="tdk-main">
      {focusMode && (
        <button type="button" className="triad-focus-exit" data-testid="triad-focus-exit"
          onClick={() => setFocusMode(false)} title="Leave focus and return exactly here (Esc)">
          Exit focus · Esc
        </button>
      )}
      <div className="triad-pair" data-testid="triad-raw-adjusted" data-mobile-pane={mobilePane}>
        <div className="triad-pane" data-testid="triad-pane-raw">
          <div className="triad-pane-header" title="Raw structural GEX — gex_net_v1/gex_gross_v1, USD per 1% spot move">
            <span className="triad-pane-title">Raw GEX · USD/1% move · {payload?.formula_version || "gex.v2"}</span>
            <PaneUnits testid="triad-pane-units-raw" text="Raw structural GEX — gex_net_v1/gex_gross_v1, USD per 1% spot move" />
          </div>
          <SkylitHeatmapGrid data={payload} spot={spot} ticker={ticker}
            viewMode="gex" metric="raw" showLandmarks={false} scrollRef={rawMapRef} displayMode="market" formatValue={marketMoney} formatTitle={exactMoney} onScroll={syncMaps} axes={pairAxes} scale={pairScale} onCellClick={(s, e) => onGridCell(s, e, "raw")} selected={cell ? { strike: cell.strike, expiry: cell.colKey } : null} wallBand={selectedWall} />
        </div>
        <div className="triad-pane" data-testid="triad-pane-adjusted">
          <div className="triad-pane-header" title={adjDef?.units || "No per-strike surface for this basis in the snapshot"}>
            <span className="triad-pane-title">Adjusted · {adjDef?.label || basis}{adjAvailable ? " · USD/1% move" : " · unavailable"}</span>
            <PaneUnits testid="triad-pane-units-adjusted" text={adjDef?.units || "No per-strike surface for this basis in the snapshot"} />
          </div>
          {adjAvailable ? (
            <SkylitHeatmapGrid data={payload} spot={spot} ticker={ticker}
              viewMode="gex" metric={basis} showLandmarks={false} scrollRef={adjustedMapRef} displayMode="market" formatValue={marketMoney} formatTitle={exactMoney} onScroll={syncMaps} axes={pairAxes} scale={pairScale} onCellClick={(s, e) => onGridCell(s, e, "adjusted")} selected={cell ? { strike: cell.strike, expiry: cell.colKey } : null} wallBand={selectedWall} />
          ) : (
            <div className="triad-unavailable" data-testid="triad-adjusted-unavailable"
              title={basis === "window" ? "window_dadgex has no per-strike surface in the snapshot contract" : "adjusted surface missing from this snapshot"}>
              {basis === "window"
                ? "Window Δvol has no per-strike surface in this snapshot — not invented here."
                : "Adjusted surface unavailable in this snapshot — showing nothing rather than borrowing Raw."}
            </div>
          )}
        </div>
      </div>

      {/* Owner 20:51 declutter: the secondary workspace renders as ONE
          deliberate tab at a time — quiet by default so the comparison
          leads. Every block below is the EXISTING component with its
          testids and honest strings unchanged; only its placement moves.
          Root 21:3x: in Focus the whole section does not RENDER — an open
          tab body never crowds the focused canvas — and because the tab
          VALUE is untouched, Exit restores the prior view exactly. */}
      {/* Review 10:xx: the supporting workspace stays MOUNTED in Focus —
          only hidden via CSS — so native state (the Profile disclosure's
          open attribute, replay inputs, review drafts) survives the
          roundtrip exactly; the tab ID alone never had to reconstruct it. */}
      <div className="triad-workspace">
      <div className="triad-workspace-tabs" data-testid="triad-workspace-tabs" role="tablist" aria-label="Market workspace">
        {[["walls", "Walls"], ["landmarks", "Landmarks"], ["replay", "Replay"], ["profile", "Profile"], ["interest", "Open interest"], ["ladder", "Call / put ladder"], ["review", "Review"]].map(([id, label]) => (
          <button key={id} type="button" role="tab" data-testid={`triad-tab-${id}`}
            id={`triad-ws-${id}-tab`} aria-controls={`triad-ws-${id}-panel`}
            aria-selected={workspaceTab === id}
            onClick={() => setWorkspaceTab((cur) => (cur === id ? null : id))}>{label}</button>
        ))}
      </div>
      {workspaceTab === "walls" && (
        <div role="tabpanel" id="triad-ws-walls-panel" aria-labelledby="triad-ws-walls-tab">
          <WallBar walls={walls} wallId={selectedWall?.wall_id || null} onSelect={selectWall} />
        </div>
      )}
      {workspaceTab === "interest" && <div role="tabpanel" id="triad-ws-interest-panel" aria-labelledby="triad-ws-interest-tab"><OpenInterestPanel data={payload}/></div>}
      {workspaceTab === "ladder" && <div role="tabpanel" id="triad-ws-ladder-panel" aria-labelledby="triad-ws-ladder-tab"><CallPutLadder data={payload}/></div>}
      {workspaceTab === "landmarks" && (
        <div role="tabpanel" id="triad-ws-landmarks-panel" aria-labelledby="triad-ws-landmarks-tab">
          <HeatmapLandmarks data={payload} />
        </div>
      )}
      {/* UI-M03 (M1 2026-10-24): stored-session replay is supporting context,
          so the strip follows the maps. Every control is preserved. */}
      {workspaceTab === "replay" && (
        <div role="tabpanel" id="triad-ws-replay-panel" aria-labelledby="triad-ws-replay-tab">
          {replayControls}
        </div>
      )}
      {workspaceTab === "profile" && (
        <div role="tabpanel" id="triad-ws-profile-panel" aria-labelledby="triad-ws-profile-tab">
        <details className="triad-profile-disclosure" data-testid="triad-profile-disclosure">
          <summary>Signed exposure profile · raw and adjusted</summary>
        <StrikeExposureProfile data={payload} basis={basis} wall={selectedWall} onSelect={onGridCell} />
        </details>
        </div>
      )}

      {spxMissing && (
        <div className="triad-capability" data-testid="triad-spx-capability">
          SPX unavailable in this session (entitlement/coverage unknown). No substitution made.
        </div>
      )}
      {workspaceTab === "review" && (
        <div role="tabpanel" id="triad-ws-review-panel" aria-labelledby="triad-ws-review-tab">
          <ReviewSection journal={journal} ticker={ticker} snapshotId={payload?.snapshotId} />
        </div>
      )}
      </div>
      </main>
      <MarketInspectorDock
        ticker={ticker}
        data={payload}
        cell={cell}
        wall={selectedWall}
        scenario={scenarios[0] || null}
        scenarios={scenarios}
        spot={spot}
        quality={quality}
        read={read}
        adjNet={value?.net ?? null}
        adjLabel={adjDef?.label || basis}
        metric={activeMetric}
        replay={isReplay}
        drawerOpen={drawerOpen}
        onClose={() => { setDrawerOpen(false); setInspectorOpen(false); }}
        closeRef={drawerCloseRef}
        selectionScope={contractScope}
        onSelection={onContractSelection}
        selectionRevision={reviewSelectionRevision}
        onContracts={openContracts}
      />
      </div>
      <div className="tdk-backdrop" onClick={() => { setDrawerOpen(false); setInspectorOpen(false); }} />
    </div>
  );
}

// One pane-header line for both maps (M1): the short title keeps the header a
// fixed-height single line so the adjusted title can never wrap deeper than
// raw and offset its strike rows. The FULL units/metric/basis/note string is
// preserved verbatim in this named details; its body overlays the grid
// (absolutely positioned), so opening it never shifts row geometry.
function PaneUnits({ testid, text }) {
  return <details className="triad-pane-units" data-testid={testid}>
    <summary title="Exact units, metric id, basis and producer note for this pane">Units & provenance</summary>
    <div className="triad-pane-units-body"><p>{text}</p></div>
  </details>;
}

function ContextStrip({ board, ticker, symbolInput, onSymbolInput, onSubmit, showStockControl = true, boardStatus }) {
  const byTicker = useMemo(() => {
    const m = {};
    for (const r of board || []) m[String(r.ticker || "").toUpperCase()] = r;
    return m;
  }, [board]);
  const observed = TRIAD.filter((t) => byTicker[t.replace("^", "")] || byTicker[t]);
  const dirs = observed.map((t) => (byTicker[t.replace("^", "")] || byTicker[t])?.direction).filter(Boolean);
  return (
    <div className="triad-context" data-testid="triad-context">
      {TRIAD.map((t) => {
        const r = byTicker[t.replace("^", "")] || byTicker[t];
        return (
          <div key={t} className="triad-context-cell" data-testid={`triad-context-${t.replace("^", "")}`}>
            <span className="triad-context-ticker">{t}</span>
            {r ? (
              <>
                <span className="triad-context-conv">{r.conviction ?? "—"}</span>
                <span className="triad-context-tier">{r.tier || ""}</span>
                <span className="triad-context-dir">{r.direction || ""}</span>
              </>
            ) : (
              <span className="triad-context-missing" title="Not in the latest leaderboard sweep — unobserved, not zero">unscanned</span>
            )}
          </div>
        );
      })}
      {showStockControl && <div className="triad-context-focus">
        <input value={symbolInput} onChange={(e) => onSymbolInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSubmit(); }}
          data-testid="triad-symbol-input" aria-label="Focused symbol" placeholder="SYM" />
        <button onClick={onSubmit} data-testid="triad-symbol-go" title="Load this symbol's snapshot (its own data only)">Go</button>
      </div>}
      <div className="triad-context-note" data-testid="triad-coverage-note"
        title="Coverage description only — never a position size">
        {observed.length}/3 observed{dirs.length ? ` · ${dirs.join(" / ")}` : ""}
      </div>
      <span className="triad-board-status" role="status" title="Research ranks are unvalidated and are not probabilities">
        Ranks: {boardStatus} · unvalidated
      </span>
      {ticker && !TRIAD.includes(ticker) && (
        <div className="triad-context-focusname" data-testid="triad-focus-name">Focused: {ticker}</div>
      )}
    </div>
  );
}

function WallBar({ walls, wallId, onSelect }) {
  if (!walls || !walls.length) {
    return (
      <div className="triad-walls" data-testid="triad-walls-empty">
        No structural walls in this snapshot.
      </div>
    );
  }
  return (
    <div className="triad-walls" data-testid="triad-walls">
      {(walls || []).map((w) => (
        <button key={w.wall_id}
          className={`triad-wall-chip${w.wall_id === wallId ? " active" : ""}`}
          data-testid={`triad-wall-${w.wall_id}`}
          title={`zone ${w.low}–${w.high} · gross ${w.gross} · net ${w.net}`}
          onClick={() => onSelect(w.wall_id === wallId ? null : w.wall_id)}>
          {w.low}–{w.high}
        </button>
      ))}
    </div>
  );
}

function ReviewSection({ journal, ticker, snapshotId }) {
  const { reviewState, reviewDec, reviewQueue, reviewReason, setReviewReason,
    reviewSaving, reviewLoading, saveReview } = journal;
  return (
    <div className="triad-review" data-testid="triad-review">
      <span className="triad-review-label">Review</span>
      {reviewLoading && <span data-testid="triad-review-loading">loading review…</span>}
      {!reviewLoading && reviewState !== null && (
        <span data-testid="triad-review-state">Decision: {reviewState}</span>
      )}
      {!reviewLoading && reviewState === null && snapshotId && (
        <span data-testid="triad-review-pending">No review yet</span>
      )}
      {!reviewLoading && reviewDec && (
        <div data-testid="triad-review-save">
          {["reviewed", "waiting", "skipped"].map((s) => (
            <button key={s} data-testid={`triad-review-save-${s}`} disabled={reviewSaving}
              title={`Mark this decision ${s} (frozen snapshot context)`}
              onClick={() => saveReview(s)}>{s}</button>
          ))}
          <select data-testid="triad-review-reason" value={reviewReason}
            onChange={(e) => setReviewReason(e.target.value)} title="Reason recorded with the review">
            <option value="">reason…</option>
            {["CONFIRMED_SETUP", "NEEDS_MORE_EVIDENCE", "STALE_DATA", "WRONG_WALL", "TIME_EXPIRED"].map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
      )}
      {reviewQueue.length > 0 && (
        <div data-testid="triad-review-queue" title="Unreviewed decisions, newest first (max 5)">
          <span>Next to review:</span>
          {reviewQueue.map((d) => (
            <span key={d.decision_id} className="triad-review-chip" data-testid={`triad-review-open-${d.decision_id}`}>
              {d.scenario || d.side || d.decision_id}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default TrinityView;
