/**
 * DataSourceBadge.jsx
 *
 * Renders a small badge in the app header showing the current data
 * source and data delay.
 *
 * Props:
 *   - source (string):      e.g. "alpha_vantage", "databento", "schwab"
 *   - delaySeconds (number|null):  known data delay in seconds
 *   - badgeStatus (string):  "live" | "delayed" | "cached" | "offline"
 *   - onClick (function):    optional click handler to refresh
 *
 * Styling:
 *   - Green pulse dot   → live (real-time source)
 *   - Yellow dot        → delayed (AV 15-min delay)
 *   - Orange dot        → cached/stale (fallback data)
 *   - Red dot           → offline (no source)
 */

import React from "react";

const STATUS_CONFIG = {
  live: {
    label: "Live",
    dotClass: "bg-emerald-400",
    pulseClass: "animate-pulse",
    textClass: "text-emerald-400",
    title: "Real-time data source active",
  },
  delayed: {
    label: "15 min delay",
    dotClass: "bg-amber-400",
    pulseClass: "",
    textClass: "text-amber-400",
    title: "Data delayed ~15 minutes (Alpha Vantage free tier)",
  },
  cached: {
    label: "Cached",
    dotClass: "bg-orange-400",
    pulseClass: "",
    textClass: "text-orange-400",
    title: "Serving cached/stale data from fallback",
  },
  offline: {
    label: "Offline",
    dotClass: "bg-rose-500",
    pulseClass: "",
    textClass: "text-rose-400",
    title: "No data source reachable",
  },
};

const SOURCE_LABELS = {
  alpha_vantage: "AV",
  databento: "DB",
  schwab: "Schwab",
  auto: "Auto",
};

/**
 * @param {Object} props
 * @param {string|null} props.source
 * @param {number|null} props.delaySeconds
 * @param {"live"|"delayed"|"cached"|"offline"} props.badgeStatus
 * @param {function} [props.onClick]
 */
export function DataSourceBadge({
  source = null,
  delaySeconds = null,
  badgeStatus = "offline",
  onClick,
}) {
  const cfg = STATUS_CONFIG[badgeStatus] || STATUS_CONFIG.offline;
  const sourceLabel = SOURCE_LABELS[source] || source || "??";

  const delayLabel = _formatDelay(delaySeconds);

  return (
    <button
      className="data-source-badge"
      onClick={onClick}
      title={cfg.title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "10px",
        fontWeight: 600,
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        background: "var(--bg-2, #1a2332)",
        border: "1px solid var(--border-color, #2d3a4e)",
        cursor: onClick ? "pointer" : "default",
        transition: "opacity 0.2s",
        opacity: badgeStatus === "offline" ? 0.7 : 1,
        whiteSpace: "nowrap",
      }}
    >
      {/* Status dot */}
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full ${cfg.dotClass} ${cfg.pulseClass}`}
        style={{ flexShrink: 0 }}
      />

      {/* Source label */}
      <span className={cfg.textClass} style={{ fontFamily: "monospace" }}>
        {sourceLabel}
      </span>

      {/* Separator */}
      {delayLabel && (
        <>
          <span style={{ color: "var(--text-muted, #64748b)", margin: "0 1px" }}>·</span>
          <span style={{ color: "var(--text-muted, #64748b)", fontSize: "9px" }}>
            {delayLabel}
          </span>
        </>
      )}
    </button>
  );
}

function _formatDelay(seconds) {
  if (seconds == null) return "";

  if (seconds === 0) return "live";

  if (seconds < 60) {
    return `${seconds}s`;
  }

  const mins = Math.round(seconds / 60);
  if (mins < 60) {
    return `${mins}min`;
  }

  const hrs = (seconds / 3600).toFixed(1);
  return `${hrs}h`;
}

export default DataSourceBadge;
