import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";
import SkylitTickerBar from "./SkylitTickerBar";
import SkylitControlBar from "./SkylitControlBar";
import SkylitHeatmapGrid from "./SkylitHeatmapGrid";
import SkylitMetricsSidebar from "./SkylitMetricsSidebar";

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
  isLive = false,
  regime = null,
  loading = false,
}) {
  const [tradeMode, setTradeMode] = useState(false);
  const [selectedCell, setSelectedCell] = useState(null);
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

  // Expanded view fetches its OWN wider band (2026-09-04): the in-frame
  // grid is deliberately windowed to 21 rows around spot, so expanding the
  // same payload could never show more strikes. swing mode widens the
  // server band (±25%) with more expiries; failure falls back to the
  // in-frame data so the overlay never blanks.
  const [expData, setExpData] = useState(null);
  const [expLoading, setExpLoading] = useState(false);
  useEffect(() => {
    if (!expanded) return undefined;
    let cancelled = false;
    const ctrl = new AbortController();
    setExpLoading(true);
    axios
      .get(`${BACKEND_API}/heatmap/${encodeURIComponent(ticker)}?mode=swing&expiries=8`, {
        timeout: 45000,
        signal: ctrl.signal,
      })
      .then((r) => { if (!cancelled && r?.data?.strikes?.length) setExpData(r.data); })
      .catch(() => { /* fallback to in-frame data below */ })
      .finally(() => { if (!cancelled) setExpLoading(false); });
    return () => { cancelled = true; ctrl.abort(); };
  }, [expanded, ticker]);
  const overlayData = expData || data;
  const overlayNote = (() => {
    const n = overlayData?.strikes?.length || 0;
    if (!n) return "";
    if (expData) return `±25% band · ${n} strikes · 8 expiries`;
    return expLoading ? "widening band…" : `${n} strikes`;
  })();

  const handleCellClick = useCallback(
    (strike, colKey, value) => {
      if (tradeMode && onCellClick) {
        onCellClick(strike, colKey, value);
      } else {
        setSelectedCell({ strike, colKey, value });
      }
    },
    [tradeMode, onCellClick]
  );

  const handleStrikeClick = useCallback(
    (strike) => {
      if (onStrikeClick) onStrikeClick(strike);
    },
    [onStrikeClick]
  );

  return (
    <div className="skylit-full-dashboard">
      {/* 1. Top Ticker Bar */}
      <SkylitTickerBar
        activeTicker={ticker}
        onTickerChange={onTickerChange}
        allCount={703}
      />

      {/* 2. Control Bar */}
      <SkylitControlBar
        ticker={ticker}
        spot={spot}
        change={change}
        changePct={changePct}
        viewMode={viewMode}
        onViewModeChange={onViewModeChange}
        timeframe={timeframe}
        onTimeframeChange={onTimeframeChange}
        expiries={expiries}
        onExpiriesChange={onExpiriesChange}
        isLive={isLive}
        onRefresh={onRefresh}
        onExpand={() => setExpanded(true)}
        onTickerChange={onTickerChange}
      />

      {/* 2.5 Trade Mode bar */}
      <div className="skylit-col-bar">
        <div className="skylit-col-spacer" />
        {selectedCell && !tradeMode && (
          <span
            className="skylit-selected-cell-readout"
            data-testid="skylit-selected-cell"
            title="Clicked cell (arm Trade to open Quick Trade)"
          >
            {selectedCell.strike} · {selectedCell.colKey} · {typeof selectedCell.value === "number" ? selectedCell.value.toFixed(1) : selectedCell.value}
          </span>
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
          onClick={() => setTradeMode(!tradeMode)}
          title="Trade Mode: click any cell to open Quick Trade"
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
          <SkylitHeatmapGrid
            data={data}
            spot={spot}
            ticker={ticker}
            viewMode={viewMode}
            onCellClick={handleCellClick}
            onStrikeClick={handleStrikeClick}
            windowRows={fitRows}
          />
        </div>

        {/* Metrics Sidebar */}
        <div className="skylit-sidebar-area">
          <SkylitMetricsSidebar
            data={data}
            spot={spot}
            viewMode={viewMode}
            regime={regime}
          />
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
              <SkylitHeatmapGrid
                data={overlayData}
                spot={spot}
                ticker={ticker}
                viewMode={viewMode}
                onCellClick={handleCellClick}
                onStrikeClick={handleStrikeClick}
                density="full"
              />
            </div>
            <div className="skylit-expanded-sidebar">
              <SkylitMetricsSidebar
                data={overlayData}
                spot={spot}
                viewMode={viewMode}
                regime={regime}
              />
            </div>
          </div>
        </div>
      )}

      {/* 4. Bottom Ticker Info Bar */}
      <div className="skylit-bottom-bar">
        <div className="skylit-bottom-ticker">
          <span className="skylit-bottom-ticker-name">{ticker}</span>
          <span className="skylit-bottom-spot">
            ${spot != null ? Number(spot).toFixed(2) : "—"}
          </span>
          {changePct != null && (
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
