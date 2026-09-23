import React, { memo } from "react";

/**
 * WallInspector — selected-wall inspector (T07): Now / Changed / Confirm /
 * Invalidates + data quality. Deterministic template; optional AI prose deepens
 * it but never replaces numbers. Unknown/no-data are first-class states.
 */
function Row({ k, v }) {
  return (
    <div className="skylit-metric-row">
      <span className="skylit-metric-label">{k}</span>
      <span className="skylit-metric-value">{v ?? "—"}</span>
    </div>
  );
}

function WallInspector({ wall = null, interaction = null, quality = null, scenario = null }) {
  if (!wall) {
    return (
      <div className="skylit-metrics-section" data-testid="wall-inspector-empty">
        <div className="skylit-section-title">Selected wall</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>Select a cell to inspect its wall.</div>
      </div>
    );
  }
  return (
    <div className="skylit-metrics-section" data-testid="wall-inspector">
      <div className="skylit-section-title">Selected wall · {wall.wall_id || `${wall.low}–${wall.high}`}</div>
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 6 }}>Now / Changed / Confirm / Invalidates</div>
      <Row k="Now" v={`${wall.low}–${wall.high} · gross ${wall.gross?.toFixed?.(1) ?? wall.gross} · net ${wall.net?.toFixed?.(1) ?? wall.net}`} />
      <Row k="Distance" v={`${Number(wall.distance).toFixed(2)} (${(Number(wall.distance_pct) * 100).toFixed(2)}%)`} />
      <Row k="Changed" v={interaction?.change || "window change unavailable"} />
      <Row k="Interaction" v={interaction?.state || "unobserved"} />
      <Row k="Confirm" v={scenario?.confirmation || "reclaim and hold above zone"} />
      <Row k="Invalidates" v={scenario?.invalidation || "acceptance beyond zone"} />
      <Row k="Data" v={quality ? `${quality.state || "unknown"} · ${(quality.reasonCodes || []).join(", ") || "ok"}` : "unknown"} />
    </div>
  );
}

export default memo(WallInspector);
