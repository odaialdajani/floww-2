import React, { memo } from "react";

/**
 * SolsticeStatusStrip — one-line market state (T23): Environment · Location ·
 * Setup state · Data status. Deterministic from the snapshot; at most five
 * short lines in the inspector, one line here. WAIT is a successful output.
 */
function SolsticeStatusStrip({ data = null, spot = null, ticker = "", isLive = false }) {
  const walls = data?.metrics?.nearest_walls || data?.metrics?.walls || [];
  const q = data?.quality || {};
  const regime = data?.gamma_regime_v1?.sign || data?.nodes?.regime || "unknown";
  const basis = data?.exposure_basis || "OI";
  let location = "no wall in scope";
  if (walls.length && spot != null) {
    const w = walls[0];
    const side = spot < Number(w.low) ? "below lower" : spot > Number(w.high) ? "above upper" : "inside";
    location = `${side} wall ${w.low}–${w.high}`;
  }
  const setup = q.setupEligible === false
    ? `Wait — ${(q.reasonCodes || []).join(", ") || "blocked"}`
    : "Observe — awaiting price confirmation";
  const dataState = !isLive ? "Data degraded/unknown" : `Data ${q.state || "usable"} · ${basis}`;
  return (
    <div className="skylit-status-strip" data-testid="solstice-status-strip"
      title="Environment · Location · Setup state · Data status (deterministic)">
      <span data-testid="solstice-env">Env: {String(regime)} γ proxy</span>
      <span data-testid="solstice-loc">Loc: {location}</span>
      <span data-testid="solstice-setup">{setup}</span>
      <span data-testid="solstice-data">{dataState}</span>
    </div>
  );
}

export default memo(SolsticeStatusStrip);
