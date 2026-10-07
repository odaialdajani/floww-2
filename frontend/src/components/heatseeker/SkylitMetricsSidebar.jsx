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

const cellMap = value => value && typeof value === "object" && !Array.isArray(value);
function overlayTotals(section, rawGrid) {
  const cells = section?.grid;
  if (!cellMap(cells) || !Object.keys(cells).length || section?.status === "unavailable") return { status: "unavailable" };
  if (section?.usable != null && (typeof section.usable !== "number" || !Number.isFinite(section.usable) || section.usable <= 0)) return { status: "unavailable" };
  let complete = true, usable = 0, net = 0, absolute = 0;
  const observedStrikes = new Set();
  for (const column of Object.values(cells)) {
    if (!cellMap(column) || !Object.keys(column).length) { complete = false; continue; }
    for (const [strike, value] of Object.entries(column)) {
      observedStrikes.add(Number(strike));
      if (typeof value !== "number" || !Number.isFinite(value)) { complete = false; continue; }
      usable++; net += value; absolute += Math.abs(value);
    }
  }
  const expiries = section?.expiries ?? rawGrid?.expiries;
  if (expiries != null && (!Array.isArray(expiries) || !expiries.length || expiries.some(expiry => !cellMap(cells[expiry]) || !Object.keys(cells[expiry]).length))) complete = false;
  // Overlay producers intentionally use sparse cells. Declared strikes must
  // be present somewhere; an absent strike/expiry combination is not filled
  // with zero or inferred to contain a contract.
  const strikes = section?.strikes ?? rawGrid?.strikes;
  if (strikes != null && (!Array.isArray(strikes) || !strikes.length || strikes.some(strike => !observedStrikes.has(Number(strike))))) complete = false;
  for (const key of ["cell_missing_delta", "cell_invalid_delta"]) {
    const excluded = section?.[key];
    if (excluded != null && (!cellMap(excluded) || Object.values(excluded).some(column => !cellMap(column)
      || Object.values(column).some(count => typeof count !== "number" || !Number.isFinite(count) || count !== 0)))) complete = false;
  }
  if (["partial", "incomplete", "error", "invalid"].includes(section?.status)
    || ["missing_delta", "missing_volume", "missing_oi", "invalid", "invalid_delta", "invalid_mult", "invalid_type", "quarantined", "mixed_pair", "no_baseline"].some(key => typeof section?.[key] === "number" && section[key] > 0)
    || section?.coverage?.complete === false || section?.coverage?.status === "partial") complete = false;
  if (!usable || !Number.isFinite(net) || !Number.isFinite(absolute)) return { status: "unavailable" };
  return complete ? { status: "complete", net, absolute } : { status: "partial" };
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
  // R6-1: the active metric governs sidebar summaries. Raw uses the
  // structural strike rows; delta/activity sum the same snapshot's overlay
  // cells. Structural strongest-wall anchor never moves with the metric.
  metric = "raw",
}) {
  const nodes = data?.nodes && typeof data.nodes === "object" && !Array.isArray(data.nodes) ? data.nodes : {};
  const kingNode = nodes.king;
  const floors = Array.isArray(nodes.floors) ? nodes.floors : null;
  const ceilings = Array.isArray(nodes.ceilings) ? nodes.ceilings : null;
  // The fallback is the same recorded payload, never today's live selection.
  const observedRegime = regime ?? data?.regime ?? data?.gex_regime ?? nodes.regime;
  // F17: three distinct concepts — largest CELL (grid king), strongest
  // aggregate WALL (sidebar king), nearest relevant WALL. Sidebar respects the
  // active metric for its summary; grid king stays cell-scoped.
  const metricLabel = viewMode === "vex" ? "VEX" : viewMode === "charm" ? "Charm" : "GEX";
  const useOverlay = metric !== "raw" && (viewMode === "gex" || viewMode === "skylit");
  // R8: without an overlay the summaries below are raw structural anchors
  // (strongest wall, king cell, nodes) — never the active view's metric.
  // Say so explicitly in VEX/Charm views so the header never implies VEX
  // values; the GEX view keeps its established label.
  const summaryLabel = useOverlay
    ? metricLabel
    : (viewMode === "vex" || viewMode === "charm" ? "GEX structural" : "GEX");
  const overlaySection = useOverlay ? (data?.metrics?.grids || {})[metric] : null;
  const overlay = useOverlay ? overlayTotals(overlaySection, data?.grid) : null;
  const metricActive = !useOverlay || overlay.status === "complete";
  const exposureBasis = useOverlay
    ? (overlaySection?.exposure_basis
      || (metric === "delta" ? "OI_DELTA_WEIGHTED" : "VOLUME"))
    : (data?.exposure_basis || "OI");
  // net GEX lives on nodes.total_gex; |GEX| is summed client-side because the
  // heatmap payload never exports total_abs_gex; flip point from gamma_flip.
  // R6-1: a missing metric surface renders unavailable (—), never raw totals
  // under an active delta/activity control.
  const sumRows = () => (Array.isArray(data?.strikes) && data.strikes.length
    && data.strikes.every(row => typeof row?.gex === "number" && Number.isFinite(row.gex))
    ? data.strikes.reduce((acc, s) => acc + Math.abs(s.gex), 0)
    : null);
  const netGex = !metricActive
    ? null
    : (useOverlay
      ? overlay.net
      : (data?.net_gex_total ?? nodes?.total_gex));
  const totalAbsGex = !metricActive
    ? null
    : (useOverlay
      ? overlay.absolute
      : (data?.total_abs_gex ?? sumRows()));
  const flipPoint = data?.flip_zones?.[0]?.price ?? data?.gamma_flip?.gamma_flip;
  const polarityLevel = nodes?.polarity_level;
  const gatekeeperCount = Array.isArray(nodes.gatekeepers) ? nodes.gatekeepers.length : null;

  const regimeColor =
    observedRegime === "positive" ? "#34d399" :
    observedRegime === "negative" ? "#f87171" :
    "#fbbf24";

  const regimeLabel =
    observedRegime === "positive" ? "Positive γ" :
    observedRegime === "negative" ? "Negative γ" :
    observedRegime === "neutral" ? "Neutral γ" : "Gamma reading unavailable";

  return (
    <div className="skylit-metrics-sidebar">
      {/* Regime indicator */}
      <div className="skylit-regime-badge" style={{ borderColor: regimeColor + "40" }}>
        <span className="skylit-regime-dot" style={{ background: regimeColor }} />
        <span className="skylit-regime-label" style={{ color: regimeColor }}>{regimeLabel}</span>
      </div>

      {/* Key metrics */}
      <div className="skylit-metrics-section">
        <div className="skylit-section-title">
          Key Levels · {summaryLabel}{useOverlay ? ` · ${metric}` : ""} · {exposureBasis}
        </div>
        {!metricActive && (
          <div className="skylit-metric-row" data-testid={overlay?.status === "partial" ? "skylit-sidebar-partial" : "skylit-sidebar-unavailable"} role="status">
            <span className="skylit-metric-label">{overlay?.status === "partial" ? "Metric incomplete" : "Metric unavailable"}</span>
            <span className="skylit-metric-value">—</span>
          </div>
        )}

        <MetricRow
          label="STRONGEST WALL"
          value={kingNode ? `$${fmtStrike(kingNode.strike || kingNode)}` : "—"}
          color="#fbbf24"
          sub={kingNode?.gex ? `${fmtGex(kingNode.gex)} agg.` : "aggregate"}
        />

        <MetricRow
          label="|GEX|"
          value={totalAbsGex != null ? fmtGex(totalAbsGex) : "—"}
          color="#e2e8f0"
        />

        <MetricRow
          label="Net GEX"
          value={netGex != null ? (netGex >= 0 ? "+" : "") + fmtGex(netGex) : "—"}
          color={netGex == null ? "#c9d1d9" : (netGex >= 0 ? "#34d399" : "#f87171")}
        />

        <MetricRow
          label="TOP FLOOR"
          value={floors?.length > 0 ? `$${fmtStrike(floors[0].strike)}` : "—"}
          color="#34d399"
        />

        <MetricRow
          label="TOP CEILING"
          value={ceilings?.length > 0 ? `$${fmtStrike(ceilings[0].strike)}` : "—"}
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
        {data?.replay && data?.structure_status !== "complete" && <p role="status">Some price levels are unavailable for this saved view.</p>}

        <MetricRow
          label="Polarity"
          value={polarityLevel != null ? Number(polarityLevel).toFixed(1) : "—"}
          color="#38bdf8"
        />

        <MetricRow
          label="Gatekeepers"
          value={gatekeeperCount == null ? "Unknown" : String(gatekeeperCount)}
          color="#c084fc"
        />

        <MetricRow
          label="Floors"
          value={floors == null ? "Unknown" : String(floors.length)}
          color="#34d399"
        />

        <MetricRow
          label="Ceilings"
          value={ceilings == null ? "Unknown" : String(ceilings.length)}
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
