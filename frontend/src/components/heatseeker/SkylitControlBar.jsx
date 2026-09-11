import React, { memo, useCallback, useEffect, useState } from "react";
import { TICKER_SETS } from "./SkylitTickerBar";

/**
 * SkylitControlBar — Second header bar with GEX/VEX tabs, LIVE badge,
 * price display, timeframe selector, and action buttons.
 *
 * Matches Zenith reference:
 *   Left: GEX/VEX toggles + info icon
 *   Center: Ticker name, price, change, timeframe dropdown
 *   Right: Refresh, playback, view, share
 */
function SkylitControlBar({
  ticker = "SPY",
  spot = null,
  change = null,
  changePct = null,
  viewMode = "gex",
  onViewModeChange,
  timeframe = "5m",
  onTimeframeChange,
  isLive = false,
  lastUpdate = null,
  onRefresh,
  expiries = 4,
  onExpiriesChange,
  // Optional: open the full-page grid overlay (wired by SkylitDashboard;
  // frozen App.js call sites omit it and the button degrades to a no-op).
  onExpand,
  // Optional ticker cycling for the prev/next arrows (2026-09-03).
  // Defaults to the tape list; unknown current ticker → no-op so open
  // universe symbols never get yanked back into the list.
  onTickerChange,
  tickers = null,
  // Auto-refresh cadence while Playback is armed.
  playbackIntervalMs = 15000,
}) {
  const [now, setNow] = useState(new Date());
  // Playback (2026-09-03): arms interval refresh via onRefresh.
  const [playing, setPlaying] = useState(false);
  // Share feedback (2026-09-03): transient "Copied" label.
  const [copied, setCopied] = useState(false);
  // Info popover (2026-09-03): the ⓘ button now explains the grid
  // instead of sitting decorative.
  const [showInfo, setShowInfo] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => { if (onRefresh) onRefresh(); }, playbackIntervalMs);
    return () => clearInterval(id);
  }, [playing, onRefresh, playbackIntervalMs]);

  const stepTicker = useCallback((dir) => {
    if (!onTickerChange) return;
    const list = tickers || TICKER_SETS.popular;
    const idx = list.indexOf(ticker);
    if (idx === -1) return; // open-universe symbol: stay put
    const next = list[(idx + dir + list.length) % list.length];
    if (next) onTickerChange(next);
  }, [onTickerChange, tickers, ticker]);

  const handleShare = useCallback(async () => {    const url = typeof window !== "undefined" ? window.location.href : "";
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (_) {
      setCopied(false);
    }
  }, []);

  const timeStr = now.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  const isPositive = change != null && change >= 0;
  const changeColor = isPositive ? "#34d399" : "#f87171";
  const changeSign = isPositive ? "+" : "";

  return (
    <div className="skylit-control-bar">
      {/* Left: GEX/VEX toggles */}
      <div className="skylit-control-left">
        <button
          className={`skylit-mode-btn${viewMode === "gex" ? " active" : ""}`}
          onClick={() => onViewModeChange && onViewModeChange("gex")}
          title="Gamma Exposure"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
          </svg>
          GEX
        </button>
        <button
          className={`skylit-mode-btn${viewMode === "vex" ? " active" : ""}`}
          onClick={() => onViewModeChange && onViewModeChange("vex")}
          title="Vanna Exposure"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          VEX
        </button>
        <button
          className="skylit-info-btn"
          title="How to read this grid"
          onClick={() => setShowInfo(!showInfo)}
          data-testid="skylit-info-btn"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4" /><path d="M12 8h.01" />
          </svg>
        </button>
        {showInfo && (
          <div
            className="skylit-info-popover"
            data-testid="skylit-info-popover"
            onClick={() => setShowInfo(false)}
          >
            <div><b>GEX</b> — gold/teal cells: dealer gamma walls (King ★ = max).</div>
            <div><b>VEX</b> — blue/purple cells: vanna exposure regime.</div>
            <div>Click a cell to inspect it · arm <b>Trade</b> to open Quick Trade.</div>
            <div>Data: Public.com live chain → cvserver → yfinance.</div>
          </div>
        )}
      </div>

      {/* Center: Ticker + Price + Timeframe */}
      <div className="skylit-control-center">
        <button
          className="skylit-nav-arrow"
          title="Previous ticker"
          onClick={() => stepTicker(-1)}
          data-testid="skylit-prev-ticker"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        <div className="skylit-ticker-display">
          <span className="skylit-ticker-name">{ticker}</span>
          {isLive && <span className="skylit-live-dot" />}
        </div>

        <div className="skylit-price-display">
          <span className="skylit-spot-price">${spot != null ? Number(spot).toFixed(2) : "—"}</span>
          {change != null && (
            <span className="skylit-price-change" style={{ color: changeColor }}>
              {changeSign}{change.toFixed(2)} ({changeSign}{(changePct || 0).toFixed(2)}%)
            </span>
          )}
        </div>

        <button
          className="skylit-nav-arrow"
          title="Next ticker"
          onClick={() => stepTicker(1)}
          data-testid="skylit-next-ticker"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>

        <div className="skylit-control-sep" />

        {/* Timeframe selector */}
        <div className="skylit-tf-dropdown">
          <select
            value={timeframe}
            onChange={(e) => onTimeframeChange && onTimeframeChange(e.target.value)}
            className="skylit-tf-select"
          >
            {/* Only timeframes with real behavioral differences: each maps to a
                distinct mode (scalp/day/swing) which changes strike band and
                expiry depth server-side. Removed 15m/4h/1d — they collapsed to
                "day" and made the control feel broken. */}
            <option value="1m">Scalp · 1m</option>
            <option value="5m">Day · 5m</option>
            <option value="1h">Swing · 1h</option>
          </select>
        </div>

        {/* Expiries selector */}
        <div className="skylit-tf-dropdown">
          <select
            value={expiries}
            onChange={(e) => onExpiriesChange && onExpiriesChange(Number(e.target.value))}
            className="skylit-tf-select"
          >
            <option value={2}>2 Exp</option>
            <option value={4}>4 Exp</option>
            <option value={6}>6 Exp</option>
            <option value={8}>8 Exp</option>
            <option value={12}>12 Exp</option>
          </select>
        </div>
      </div>

      {/* Right: Actions */}
      <div className="skylit-control-right">
        <span className="skylit-live-time">{timeStr}</span>
        <button className="skylit-action-btn" title="Refresh" onClick={onRefresh}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
        </button>
        <button
          className={`skylit-action-btn${playing ? " active" : ""}`}
          title={playing ? "Playback on — auto-refreshing" : "Playback"}
          onClick={() => setPlaying(!playing)}
          data-testid="skylit-playback-btn"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill={playing ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
            {playing ? (
              <><rect x="5" y="4" width="4" height="16" /><rect x="15" y="4" width="4" height="16" /></>
            ) : (
              <polygon points="5 3 19 12 5 21 5 3" />
            )}
          </svg>
        </button>
        <button
          className="skylit-action-btn"
          title="Expand grid full-screen"
          onClick={() => { if (onExpand) onExpand(); }}
          data-testid="skylit-expand-toolbar-btn"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
          </svg>
        </button>
        <button
          className="skylit-action-btn"
          title={copied ? "Copied!" : "Share"}
          onClick={handleShare}
          data-testid="skylit-share-btn"
        >
          {copied ? (
            <span style={{ fontSize: 10, fontWeight: 700 }}>✓</span>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}

export default memo(SkylitControlBar);
