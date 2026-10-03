import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API } from "../config/api";
import SkylitHeatmapGrid from "./heatseeker/SkylitHeatmapGrid";
import { mapSurface } from "./heatseeker/shownMapStrikes";
import { wallPositionOf } from "../lib/solsticeSelection";
import { useReviewJournal } from "./triad/useReviewJournal";
import { ALL_BASES, surfaceStatus, wallValues, wallRead } from "../lib/solsticeMetrics";
import StrikeExposureProfile from "./triad/StrikeExposureProfile";
import ExactContractReview from "./heatseeker/ExactContractReview";
import AskLodestar from "./heatseeker/AskLodestar";
import { usePublishScreenContext } from "../agent/useScreenContext";
import { replayToDisplay } from "../lib/solsticeReplay";
import ReplayStrip from "./heatseeker/ReplayStrip";
import { GroundedPublicReview } from "./public/PublicHandoffReview";

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
  const onContractSelection = useCallback(selection => {
    setContractSelection(selection);
    if (selection?.status === "resolved") setCell({strike: Number(selection.identity.strike), colKey: selection.identity.expiry});
  }, []);
  const [scope, setScope] = useState("0dte");
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
  // O5: same focus ownership as the Solstice inspector drawer.
  const drawerCloseRef = useRef(null);
  const drawerPrevFocusRef = useRef(null);
  useEffect(() => {
    if (!drawerOpen) return undefined;
    drawerPrevFocusRef.current = document.activeElement;
    drawerCloseRef.current?.focus();
    return () => {
      try { drawerPrevFocusRef.current?.focus?.(); } catch { /* noop */ }
    };
  }, [drawerOpen]);
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
    setWallId(id);
    setCell(null);
    setDrawerOpen(false);
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
  }, [walls, selectWall]);

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
        <span>Loading Triad…</span>
      </div></div>
    );
  }
  if ((error || !payload) && !loading) {
    return (
      <div className="trinity-layout">{replayControls}<div className="trinity-error" data-testid="triad-error">
        <span>⚠</span> {isSPX
          ? "SPX unavailable in this session (entitlement/coverage unknown). No substitution made — pick another symbol."
          : `Error: ${error || "no data"}`}
        <button onClick={() => { setReplayDisplay(null); setReplayId(null); setTicker("SPY"); }}>SPY</button>
      </div></div>
    );
  }

  return (
    <div className="trinity-layout" data-testid="trinity-view">
      {replayControls}
      {replayId && !replayDisplay && <button type="button" onClick={() => onReplayDisplay(null)}>Leave recorded observation · Live</button>}
      <ContextStrip board={board} ticker={ticker} symbolInput={symbolInput}
        onSymbolInput={setSymbolInput} onSubmit={submitSymbol} />
      <div className="triad-board-status" role="status">Solstice research ranks · {boardStatus} · unvalidated, not probability</div>
            {payload?.scope_selection?.status === "unavailable" && <div role="status" data-testid="triad-empty-scope">No listed expiry in the server's 30-day bound — no substitution made.</div>}
      {!isReplay && scope === "0dte" && !sameDayAdmitted && <p role="status" data-testid="triad-scope-admission">
        Same-day admission unavailable — the loaded observation is not verified 0DTE. Exact loaded dates remain visible; no same-session expiry or entitlement is invented.
      </p>}
      <div className="triad-desk-toolbar">
        <span>Raw = where · adjusted = weighting, not observed direction</span>
        <select aria-label="Triad expiry scope" value={isReplay ? declaredScope : scope} disabled={isReplay} onChange={e => setScope(e.target.value)}>
          <option value="loaded">All loaded · max 4 expiries</option><option value="0dte">0DTE · request same session</option><option value="week">Week · ≤7 calendar DTE</option>
          <option value="next">Next listed · one expiry, ≤30 calendar DTE</option>
          {isReplay && declaredScope === "recorded" && <option value="recorded">Recorded scope · exact dates below</option>}
        </select>
        <label>Adjusted context <select aria-label="Adjusted context" value={basis} onChange={e => { setBasis(e.target.value); setActivePane("adjusted"); }}>
          {ADJUSTED_BASES.map(b => <option key={b.id} value={b.id} data-testid={`triad-basis-${b.id}`}
            disabled={surfaceStatus(payload, b.id).status === "unavailable" && basis !== b.id} title={surfaceStatus(payload, b.id).reason || b.units}>{b.label}</option>)}
        </select></label>
        <AskLodestar subject={`${ticker} · raw wall ${wallId || "none"}`} overlayMetric={activeMetric} displayMode={isReplay ? "replay" : "live"} compact />
        <div className="triad-mobile-switch"><button onClick={() => setMobilePane("raw")}>Raw</button><button onClick={() => setMobilePane("adjusted")}>Adjusted</button></div>
      </div>
      {["session_delta_volume", "activity", "window"].includes(basis) && <details data-testid="triad-activity-coverage">
        <summary>Activity window and coverage</summary>
        <p>Volume window: {payload?.metrics?.grids?.[basis]?.interval?.start && payload?.metrics?.grids?.[basis]?.interval?.end
          ? `${payload.metrics.grids[basis].interval.start} → ${payload.metrics.grids[basis].interval.end}` : "unavailable — no declared bounds"}.
          {" "}Usable inputs: {surfaceStatus(payload, basis).usable ?? "unknown"} · {surfaceStatus(payload, basis).status}.
          {" "}{surfaceStatus(payload, basis).reason || "No volume or Greeks are inferred from OI."}</p>
      </details>}
      <StrikeExposureProfile data={payload} basis={basis} wall={selectedWall} onSelect={onGridCell} />
      <div className="triad-pair" data-testid="triad-raw-adjusted" data-mobile-pane={mobilePane}>
        <div className="triad-pane" data-testid="triad-pane-raw">
          <div className="triad-pane-header" title="Raw structural GEX — gex_net_v1/gex_gross_v1, USD per 1% spot move">
            Raw GEX · USD/1% move · {payload?.formula_version || "gex.v2"}
          </div>
          <SkylitHeatmapGrid data={payload} spot={spot} ticker={ticker}
            viewMode="gex" metric="raw" axes={pairAxes} scale={pairScale} onCellClick={(s, e) => onGridCell(s, e, "raw")} selected={cell ? { strike: cell.strike, expiry: cell.colKey } : null} wallBand={selectedWall} />
        </div>
        <div className="triad-pane" data-testid="triad-pane-adjusted">
          <div className="triad-pane-header" title={adjDef?.units || "No per-strike surface for this basis in the snapshot"}>
            Adjusted · {adjDef?.label || basis}{adjAvailable ? ` · ${adjDef.units}` : " · unavailable"}
          </div>
          {adjAvailable ? (
            <SkylitHeatmapGrid data={payload} spot={spot} ticker={ticker}
              viewMode="gex" metric={basis} axes={pairAxes} scale={pairScale} onCellClick={(s, e) => onGridCell(s, e, "adjusted")} selected={cell ? { strike: cell.strike, expiry: cell.colKey } : null} wallBand={selectedWall} />
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

      {spxMissing && (
        <div className="triad-capability" data-testid="triad-spx-capability">
          SPX unavailable in this session (entitlement/coverage unknown). No substitution made.
        </div>
      )}
      <WallBar walls={walls} wallId={selectedWall?.wall_id || null} onSelect={selectWall} />
      {selectedWall ? (
        <ScenarioCard wall={selectedWall} scenarios={scenarios} spot={spot}
          quality={quality} onContracts={openContracts} ticker={ticker} read={read} replay={isReplay} />
      ) : (
        <div className="triad-nowall" data-testid="triad-no-wall">
          No structural wall selected — pick a cell in either pane. An adjusted-only peak with no
          corresponding GEX wall will say so here rather than inheriting another wall's story.
        </div>
      )}
      {drawerOpen && (
        <ContractDrawer data={payload} cell={cell} replay={isReplay}
          wall={selectedWall} onClose={() => setDrawerOpen(false)} ticker={ticker}
          closeRef={drawerCloseRef} selectionScope={contractScope} onSelection={onContractSelection} />
      )}
      <ReviewSection journal={journal} ticker={ticker} snapshotId={payload?.snapshotId} />
      <div className="triad-source" data-testid="triad-source">
        {isReplay ? "REPLAY · " : "LIVE · "}{payload?.snapshotId ? `snapshot ${payload.snapshotId}` : "no snapshot"}
        {payload?.asof ? ` · ${payload.asof}` : ""}
        {payload?.data_source ? ` · ${payload.data_source}` : ""}
        {quality?.state ? ` · quality ${quality.state}` : ""}
      </div>
    </div>
  );
}

function ContextStrip({ board, ticker, symbolInput, onSymbolInput, onSubmit }) {
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
      <div className="triad-context-focus">
        <input value={symbolInput} onChange={(e) => onSymbolInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSubmit(); }}
          data-testid="triad-symbol-input" aria-label="Focused symbol" placeholder="SYM" />
        <button onClick={onSubmit} data-testid="triad-symbol-go" title="Load this symbol's snapshot (its own data only)">Go</button>
      </div>
      <div className="triad-context-note" data-testid="triad-coverage-note"
        title="Coverage description only — never a position size">
        {observed.length}/3 observed{dirs.length ? ` · ${dirs.join(" / ")}` : ""}
      </div>
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

function ScenarioCard({ wall, scenarios, spot, quality, onContracts, ticker, read, replay }) {
  const [first, second] = scenarios || [];
  // Position strip: spot marker against the wall zone on one shared scale.
  // Pure geometry (percent positions), no inferred levels.
  const pos = useMemo(() => {
    const low = Number(wall.low);
    const high = Number(wall.high);
    const sp = typeof spot === "number" && Number.isFinite(spot) ? spot : NaN;
    if (!Number.isFinite(low) || !Number.isFinite(high) || high <= low) return null;
    const lo = Number.isFinite(sp) ? Math.min(low, sp) : low;
    const hi = Number.isFinite(sp) ? Math.max(high, sp) : high;
    const pad = Math.max((hi - lo) * 0.5, Math.abs(hi) * 0.002, 0.01);
    const loP = lo - pad;
    const span = (hi - lo) + 2 * pad;
    const pct = (v) => Math.min(100, Math.max(0, ((v - loP) / span) * 100));
    return { z0: pct(low), z1: pct(high), sp: Number.isFinite(sp) ? pct(sp) : null };
  }, [wall, spot]);
  // State text derives from CURRENT spot vs zone (observable now), not the
  // packet's scenario label (which may describe an older observation).
  // wallPositionOf names the WALL's side of spot; the strip names the
  // PRICE's side of the wall, so the two are mirrored.
  const wposNow = wallPositionOf(wall, spot);
  const posState = wposNow === "inside" ? "price inside wall"
    : wposNow === "below" ? "price above wall"
    : wposNow === "above" ? "price below wall" : null;
  return (
    <div className="triad-scenario" data-testid="triad-scenario">
      <div className="triad-scenario-zone" data-testid="triad-scenario-zone">
        Wall {wall.wall_id} · zone {wall.low}–{wall.high}
        {spot != null && wall.mid != null ? ` · ${Math.abs(spot - wall.mid).toFixed(1)} from mid` : ""}
      </div>
      <div className="triad-readiness" data-testid="triad-readiness" role="status">
        <strong>{read?.readiness || "Observe"}</strong><span>{read?.watch || "No directional watch"}</span>
        <small>{read?.reasons?.join(" · ")} · Conditional review only; adjusted sign is not a price forecast.</small>
      </div>
      {pos && (
        <div className="triad-position" data-testid="triad-position"
          title="Spot position against the wall zone (shared scale)">
          <div className="triad-position-rail">
            <div className="triad-position-zone" data-testid="triad-position-zone"
              style={{ left: `${pos.z0}%`, width: `${pos.z1 - pos.z0}%` }} />
            {pos.sp != null && (
              <div className="triad-position-spot" data-testid="triad-position-spot"
                style={{ left: `${pos.sp}%` }} />
            )}
          </div>
          <div className="triad-position-labels">
            <span>Below</span><span>Spot</span><span>Above</span>
          </div>
          {posState && (
            <div className="triad-position-state" data-testid="triad-position-state">{posState}</div>
          )}
        </div>
      )}
      {first ? (
        <div className="triad-scenario-side" data-testid="triad-scenario-first">
          <span className="triad-scenario-name">{first.name}</span>
          <span className="triad-scenario-confirm" title="Confirmation condition">Confirm: {first.confirmation}</span>
          <span className="triad-scenario-invalidate" title="Invalidation condition">Invalidate: {first.invalidation}</span>
        </div>
      ) : null}
      {second ? (
        <div className="triad-scenario-side" data-testid="triad-scenario-second">
          <span className="triad-scenario-name">{second.name}</span>
          <span className="triad-scenario-confirm" title="Confirmation condition">Confirm: {second.confirmation}</span>
          <span className="triad-scenario-invalidate" title="Invalidation condition">Invalidate: {second.invalidation}</span>
        </div>
      ) : null}
      {!first && (
        <div className="triad-scenario-empty">No scenario attached to this wall in the snapshot.</div>
      )}
      <div className="triad-scenario-blocker" data-testid="triad-blocker"
        title="Primary interpretation blocker">
        Blocker: {quality?.reasonCodes?.[0] || quality?.state || "none stated"}
      </div>
      {replay ? <div className="triad-price-empty">Replay: fresh price history is not requested. Use recorded interaction evidence.</div> : <WallPricePath ticker={ticker} wall={wall} spot={spot} />}
      <button className="triad-contracts-btn" data-testid="triad-contracts-btn"
        title="Review contracts at this wall (identity, delta, spread, quote age)"
        onClick={onContracts}>
        Review contracts
      </button>
    </div>
  );
}

function WallPricePath({ ticker, wall, spot }) {
  const [frames, setFrames] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!ticker || !wall) return undefined;
    let cancelled = false;
    const ctrl = new AbortController();
    setFrames(null);
    setFailed(false);
    axios
      .get(`${API}/heatseeker/price-history/${encodeURIComponent(ticker)}`, {
        params: { days: 5 }, timeout: 30000, signal: ctrl.signal,
      })
      .then((r) => { if (!cancelled) setFrames(r?.data?.frames || []); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; ctrl.abort(); };
  }, [ticker, wall?.wall_id]);
  const closes = useMemo(
    () => (frames || []).map((f) => f.close).filter((c) => typeof c === "number" && Number.isFinite(c)),
    [frames]
  );
  if (frames === null && !failed) {
    return <div className="triad-price-loading">loading price path…</div>;
  }
  if (failed) {
    return <div className="triad-price-empty" data-testid="triad-price-empty">Price history unavailable for this symbol.</div>;
  }
  if (!closes.length) {
    return <div className="triad-price-empty" data-testid="triad-price-empty">No price candles for this period.</div>;
  }
  const W = 300, H = 120, PAD = 6;
  const lo = Math.min(...closes, Number(wall.low));
  const hi = Math.max(...closes, Number(wall.high));
  const span = hi - lo || 1;
  const X = (i) => PAD + (closes.length < 2 ? W / 2 : (i / (closes.length - 1)) * (W - 2 * PAD));
  const Y = (v) => H - PAD - ((Number(v) - lo) / span) * (H - 2 * PAD);
  const pts = closes.map((c, i) => `${X(i).toFixed(1)},${Y(c).toFixed(1)}`).join(" ");
  const zy1 = Y(Math.min(Number(wall.high), hi));
  const zy2 = Y(Math.max(Number(wall.low), lo));
  const spotY = spot != null && Number.isFinite(Number(spot)) ? Y(Number(spot)) : null;
  return (
    <div className="triad-price" data-testid="triad-price-path">
      <svg data-testid="triad-price-path-svg" viewBox={`0 0 ${W} ${H}`} width="100%" height="120"
        role="img" aria-label={`Recent closes with wall zone ${wall.low} to ${wall.high}`}>
        <rect data-testid="triad-price-zone" x={PAD} y={Math.min(zy1, zy2)}
          width={W - 2 * PAD} height={Math.abs(zy2 - zy1)}
          fill="rgba(251,191,36,0.12)" />
        <polyline points={pts} fill="none" stroke="#7dd3fc" strokeWidth="1.5" />
        {spotY != null && spotY >= 0 && spotY <= H && (
          <line x1={PAD} x2={W - PAD} y1={spotY} y2={spotY} stroke="#f472b6" strokeWidth="1" strokeDasharray="4 3" />
        )}
      </svg>
      <div className="triad-price-caption" data-testid="triad-price-caption">
        {closes.length} closes · zone shaded · VWAP unavailable (no verified source)
      </div>
    </div>
  );
}

function ContractDrawer({ data, cell, replay, wall, onClose, ticker, closeRef, selectionScope, onSelection }) {
  useEffect(() => {
    const close = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);
  return <div className="triad-drawer" data-testid="triad-contract-drawer" role="dialog" aria-label="Contract review">
    <div className="triad-drawer-header">
      <span>Contracts · {ticker} {wall ? `${wall.low}–${wall.high}` : ""}</span>
      <button ref={closeRef} onClick={onClose} data-testid="triad-drawer-close" aria-label="Close contract review">✕</button>
    </div>
    <ExactContractReview key={`${ticker}|${wall?.wall_id || ""}|${data?.snapshotId || ""}`} ticker={ticker} data={data} wall={wall} cell={cell} replay={replay} selectionScope={selectionScope} onSelection={onSelection} />
    <AskLodestar subject={`${ticker} · exact contract review`} compact />
    <GroundedPublicReview />
  </div>;
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
