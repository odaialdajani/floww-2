import React, { memo } from "react";

/**
 * WallInspector — selected-wall inspector (T07 §28.3): Now / Changed /
 * Confirm / Invalidates + data quality. Shows gross/net/call/put with units
 * and basis, per-expiry contributions, magnitude ratio, pair provenance and
 * OI-effective-date coverage. Deterministic template; optional AI prose
 * deepens it but never replaces numbers. Unknown/no-data are first-class.
 */
function Row({ k, v, tip }) {
  return (
    <div className="skylit-metric-row" title={tip || undefined}>
      <span className="skylit-metric-label">{k}</span>
      <span className="skylit-metric-value">{v ?? "—"}</span>
    </div>
  );
}

function fmtUsd(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

function WallInspector({ wall = null, interaction = null, metrics = null, grids = null, quality = null, scenario = null, goneReason = null, lastWallId = null }) {
  if (!wall) {
    if (goneReason === "WALL_GONE") {
      return (
        <div className="skylit-metrics-section" data-testid="wall-inspector-gone">
          <div className="skylit-section-title">Selected wall · gone</div>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>Wall {lastWallId || ""} is not in this snapshot — no nearby substitute selected. Last observation retained in history.</div>
        </div>
      );
    }
    return (
      <div className="skylit-metrics-section" data-testid="wall-inspector-empty">
        <div className="skylit-section-title">Selected wall</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>Select a cell to inspect its wall.</div>
      </div>
    );
  }
  const members = wall.members || [];
  // Per-expiry contributions for member strikes from the same snapshot grids.
  const perExpiry = [];
  if (grids) {
    const seen = new Set();
    for (const [name, g] of Object.entries(grids)) {
      if (!g || !g.grid) continue;
      for (const [exp, col] of Object.entries(g.grid)) {
        let sum = 0;
        let hit = false;
        for (const s of members) {
          const k = Number.isInteger(s) ? String(s) : String(s);
          if (col[k] != null) { sum += col[k]; hit = true; }
        }
        if (hit && !seen.has(`${name}|${exp}`)) {
          seen.add(`${name}|${exp}`);
          perExpiry.push({ grid: name, expiry: exp, value: sum });
        }
      }
    }
  }
  const ratio = metrics?.magnitude_ratio_delta_over_raw;
  const pairNote = metrics
    ? `Δ usable ${metrics.dadgex_usable ?? "—"}, missing ${metrics.dadgex_missing_delta ?? "—"}`
    : "—";
  // Wall-local window activity comes from the live assembly when a recorded
  // baseline exists; otherwise the row honestly reports unavailability.
  const winVal = metrics?.window_daddex_v1;
  const winReason = metrics?.window_daddex_reason;
  const winNote = winVal != null ? `${fmtUsd(winVal)} (window Δ-weighted)`
    : winReason === "VOLUME_REBASE" ? "unavailable — volume rebase, new baseline required"
    : "unavailable — no recorded baseline yet";
  return (
    <div className="skylit-metrics-section" data-testid="wall-inspector">
      <div className="skylit-section-title">Selected wall · {wall.wall_id || `${wall.low}–${wall.high}`}</div>
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 6 }}>Now / Changed / Confirm / Invalidates</div>
      <Row k="Now" v={`${wall.low}–${wall.high} · gross ${fmtUsd(wall.gross)} · net ${fmtUsd(wall.net)} (USD/1% move, ${wall.exposure_basis || "OI"})`} />
      <Row k="Call / Put" v={`${fmtUsd(wall.call)} / ${fmtUsd(wall.put)}`} tip="Call-plus vs put-minus components; high gross + near-zero net is two-sided concentration" />
      <Row k="Distance" v={wall.distance != null ? `${Number(wall.distance).toFixed(2)} (${(Number(wall.distance_pct) * 100).toFixed(2)}%)` : "—"} />
      {perExpiry.length > 0 && (
        <Row k="Per-expiry" v={perExpiry.slice(0, 6).map((p) => `${p.grid}:${p.expiry.slice(5)}=${fmtUsd(p.value)}`).join(" · ")} tip="Same-snapshot per-expiry contributions for member strikes" />
      )}
      <Row k="Δ/Raw (scope)" v={ratio != null ? Number(ratio).toFixed(3) : "—"} tip="Scope-wide delta gross / raw gross over the same snapshot set — not the selected wall. Wall-local ratio needs same-wall delta + raw grids." />
      <Row k="Window activity" v={winNote} tip="Wall-local window delta-weighted activity from the recorded baseline; turnover, never buyer-minus-seller flow" />
      <Row k="Δ provenance" v={pairNote} tip="Vendor/vendor, local/local eligible; mixed pairs blocked without policy" />
      <Row k="OI eff. date" v="unavailable in snapshot" tip="OI effective date coverage comes from the recorder, not this snapshot" />
      <Row k="Changed" v={interaction ? `${interaction.state}${interaction.event ? ` · ${interaction.event}` : ""} (first sighting — see replay compare)` : "see replay compare"} tip="Wall-level change needs 2+ recorded snapshots" />
      <Row k="Interaction" v={interaction ? interaction.state : "unobserved"} tip="Time-debounced state machine; session/feed gaps break continuity" />
      <Row k="Touches" v={interaction && interaction.taps != null ? String(interaction.taps) : "unknown — no history"} tip="Observed touches only; never a calibrated probability" />
      <Row k="Confirm" v={scenario?.confirmation || "reclaim and hold above zone"} />
      <Row k="Invalidates" v={scenario?.invalidation || "acceptance beyond zone"} />
      <Row k="Data" v={quality ? `${quality.state || "unknown"} · ${(quality.reasonCodes || []).join(", ") || "ok"}` : "unknown"} />
    </div>
  );
}

export default memo(WallInspector);
