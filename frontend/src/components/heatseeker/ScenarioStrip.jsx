import React, { memo } from "react";

/**
 * ScenarioStrip — compact two-sided conditional strip (T07): bounce/reject vs
 * acceptance/continuation with trigger + invalidation. Watch language until
 * price confirms; never a trade instruction.
 */
function ScenarioStrip({ scenarios = [] }) {
  if (!scenarios.length) return null;
  return (
    <div className="skylit-metrics-section" data-testid="scenario-strip">
      <div className="skylit-section-title">Scenarios</div>
      {scenarios.slice(0, 2).map((s, i) => (
        <div key={i} style={{ fontSize: 12, marginBottom: 6 }}>
          <div style={{ fontWeight: 600 }}>{s.name || s.type}</div>
          <div style={{ color: "#94a3b8" }}>Confirm: {s.confirmation || s.trigger || "price confirmation"}</div>
          <div style={{ color: "#f87171" }}>Invalid: {s.invalidation || "acceptance beyond zone"}</div>
        </div>
      ))}
    </div>
  );
}

export default memo(ScenarioStrip);
