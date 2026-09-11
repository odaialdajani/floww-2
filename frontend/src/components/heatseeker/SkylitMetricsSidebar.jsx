import React, { memo } from "react";

/**
 * SkylitMetricsSidebar — Right-side metrics panel
 *
 * Matches Zenith reference:
 * - KING strike (highest GEX)
 * - |GEX| total absolute gamma
 * - TOP FLOOR (highest support)
 * - TOP CEILING (highest resistance)
 * - Net GEX
 * - Flip point
 * - Regime indicator
 */

function fmtStrike(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return Number(v) >= 1000 ? String(Math.round(v)) : Number(v).toFixed(1);
}

function fmtGex(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return v.toFixed(0);
}

function MetricRow({ label, value, color = "#c9d1d9", sub }) {
  return (
    <div className="skylit-metric-row">
      <span className="skylit-metric-label">{label}</span>
      <span className="skylit-metric-value" style={{ color }}>{value}</span>
      {sub && <span className="skylit-metric-sub">{sub}</span>}
    </div>
  );
}

function SkylitMetricsSidebar({
  data = null,
  spot = null,
  viewMode = "gex",
  regime = null,
}) {
  const nodes = data?.nodes || {};
  const kingNode = nodes.king;
  const floors = nodes.floors || [];
  const ceilings = nodes.ceilings || [];
  // net GEX lives on nodes.total_gex; |GEX| is summed client-side because the
  // heatmap payload never exports total_abs_gex; flip point from gamma_flip
  const netGex = data?.net_gex_total ?? nodes?.total_gex;
  const totalAbsGex =
    data?.total_abs_gex ??
    (data?.strikes?.length
      ? data.strikes.reduce((acc, s) => acc + Math.abs(s.gex || 0), 0)
      : null);
  const flipPoint = data?.flip_zones?.[0]?.price ?? data?.gamma_flip?.gamma_flip;
  const polarityLevel = nodes?.polarity_level;
  const gatekeeperCount = nodes?.gatekeepers?.length || 0;

  const regimeColor =
    regime === "positive" ? "#34d399" :
    regime === "negative" ? "#f87171" :
    "#fbbf24";

  const regimeLabel =
    regime === "positive" ? "Positive γ" :
    regime === "negative" ? "Negative γ" :
    regime === "neutral" ? "Neutral γ" : "Gamma reading unavailable";

  return (
    <div className="skylit-metrics-sidebar">
      {/* Regime indicator */}
      <div className="skylit-regime-badge" style={{ borderColor: regimeColor + "40" }}>
        <span className="skylit-regime-dot" style={{ background: regimeColor }} />
        <span className="skylit-regime-label" style={{ color: regimeColor }}>{regimeLabel}</span>
      </div>

      {/* Key metrics */}
      <div className="skylit-metrics-section">
        <div className="skylit-section-title">Key Levels</div>

        <MetricRow
          label="KING"
          value={kingNode ? `$${fmtStrike(kingNode.strike || kingNode)}` : "—"}
          color="#fbbf24"
          sub={kingNode?.gex ? fmtGex(kingNode.gex) : null}
        />

        <MetricRow
          label="|GEX|"
          value={totalAbsGex != null ? fmtGex(totalAbsGex) : "—"}
          color="#e2e8f0"
        />

        <MetricRow
          label="Net GEX"
          value={netGex != null ? (netGex >= 0 ? "+" : "") + fmtGex(netGex) : "—"}
          color={netGex >= 0 ? "#34d399" : "#f87171"}
        />

        <MetricRow
          label="TOP FLOOR"
          value={floors.length > 0 ? `$${fmtStrike(floors[0].strike)}` : "—"}
          color="#34d399"
        />

        <MetricRow
          label="TOP CEILING"
          value={ceilings.length > 0 ? `$${fmtStrike(ceilings[0].strike)}` : "—"}
          color="#f87171"
        />

        <MetricRow
          label="Flip Point"
          value={flipPoint != null ? `$${fmtStrike(flipPoint)}` : "—"}
          color="#a78bfa"
        />
      </div>

      {/* Structure */}
      <div className="skylit-metrics-section">
        <div className="skylit-section-title">Structure</div>

        <MetricRow
          label="Polarity"
          value={polarityLevel != null ? Number(polarityLevel).toFixed(1) : "—"}
          color="#38bdf8"
        />

        <MetricRow
          label="Gatekeepers"
          value={String(gatekeeperCount)}
          color="#c084fc"
        />

        <MetricRow
          label="Floors"
          value={String(floors.length)}
          color="#34d399"
        />

        <MetricRow
          label="Ceilings"
          value={String(ceilings.length)}
          color="#f87171"
        />
      </div>

      {/* Spot */}
      {spot != null && (
        <div className="skylit-spot-box">
          <div className="skylit-spot-label">SPOT</div>
          <div className="skylit-spot-value">${Number(spot).toFixed(2)}</div>
        </div>
      )}
    </div>
  );
}

export default memo(SkylitMetricsSidebar);
