/**
 * CharmChart.jsx
 *
 * Displays charm (delta decay) exposure by strike price.
 * Charm = d(Delta)/d(Time) — how delta decays as time passes.
 *
 * Shows the charm integral curve: cumulative charm exposure across strikes.
 * Positive charm = delta increases with time (long gamma).
 * Negative charm = delta decreases with time (short gamma).
 *
 * Uses Plotly for rendering with WebGL fallback to SVG on low-end devices.
 */

import React, { useMemo, memo } from "react";
import Plot from "react-plotly.js";
import { useMarketData } from "../hooks/useMarketData";
import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
import { ErrorState } from "./RetryButton";

const CharmChart = memo(function CharmChart({ ticker = "SPY", spot = null }) {
  const { data, loading, error, showBadge, refresh } = useMarketData(
    `analytics/charm-integral/${ticker}`,
    { refreshMs: 60000, query: { expiries: 4 } }
  );

  const useWebGL = useMemo(() => isWebGLAvailable(), []);

  // Prepare chart data
  const chartData = useMemo(() => {
    if (!data) return null;

    // Handle different response shapes
    let strikes, charmValues;
    if (data.strikes && data.charm) {
      strikes = data.strikes;
      charmValues = data.charm;
    } else if (data.charm_integral) {
      const ci = data.charm_integral;
      strikes = ci.strikes || ci.x || [];
      charmValues = ci.values || ci.y || [];
    } else {
      return null;
    }

    if (!strikes || !charmValues || strikes.length === 0) return null;

    // Decimate if too many points
    let plotStrikes = strikes;
    let plotCharm = charmValues;
    if (strikes.length > 200) {
      const decimated = autoDecimate(
        strikes.map((s, i) => ({ x: s, y: charmValues[i] })),
        200
      );
      plotStrikes = decimated.map((d) => d.x);
      plotCharm = decimated.map((d) => d.y);
    }

    const colors = plotCharm.map((v) => (v >= 0 ? "#a78bfa" : "#fb923c"));

    const traces = [
      {
        x: plotStrikes,
        y: plotCharm,
        type: "bar",
        marker: { color: colors, opacity: 0.8 },
        name: "Charm Exposure",
        hovertemplate:
          "Strike: $%{x}<br>Charm: %{y:,.0f}<extra></extra>",
      },
    ];

    // Spot price line
    if (spot) {
      traces.push({
        x: [spot, spot],
        y: [Math.min(...plotCharm) * 1.1, Math.max(...plotCharm) * 1.1],
        type: "scatter",
        mode: "lines",
        line: { color: "#fbbf24", width: 2, dash: "dash" },
        name: "Spot",
        hovertemplate: "Spot: $%{x}<extra></extra>",
      });
    }

    // Zero line
    traces.push({
      x: [Math.min(...plotStrikes), Math.max(...plotStrikes)],
      y: [0, 0],
      type: "scatter",
      mode: "lines",
      line: { color: "rgba(100,116,139,0.4)", width: 1 },
      name: "Zero",
      showlegend: false,
      hoverinfo: "skip",
    });

    return traces;
  }, [data, spot]);

  const layout = useMemo(
    () => ({
      title: {
        text: `Charm (Delta Decay) — ${ticker}`,
        font: { size: 13, color: "#94a3b8" },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#64748b", size: 10 },
      margin: { t: 35, b: 40, l: 55, r: 15 },
      xaxis: {
        title: "Strike",
        tickformat: "$,.0f",
        gridcolor: "rgba(100,116,139,0.15)",
        zerolinecolor: "rgba(100,116,139,0.3)",
      },
      yaxis: {
        title: "Charm",
        tickformat: ",.0f",
        gridcolor: "rgba(100,116,139,0.15)",
        zerolinecolor: "rgba(100,116,139,0.3)",
      },
      showlegend: true,
      legend: { x: 0, y: 1.1, orientation: "h", font: { size: 9 } },
      hovermode: "x unified",
      bargap: 0.05,
    }),
    [ticker]
  );

  const config = useMemo(
    () => ({
      responsive: true,
      displayModeBar: false,
      plotGlPixelRatio: useWebGL ? 2 : 1,
    }),
    [useWebGL]
  );

  if (error && !data) {
    return <ErrorState error={error} onRetry={refresh} title="Charm data unavailable" />;
  }

  if (loading && !data) {
    return (
      <div className="panel p-4 flex items-center justify-center" style={{ minHeight: 250 }}>
        <div className="text-[11px] text-slate-500 animate-pulse">Loading charm exposure…</div>
      </div>
    );
  }

  if (!chartData) {
    return (
      <div className="panel p-4 flex items-center justify-center" style={{ minHeight: 250 }}>
        <div className="text-[11px] text-slate-500">No charm data available</div>
      </div>
    );
  }

  return (
    <div className="panel p-3 relative">
      {showBadge && (
        <div className="absolute top-2 right-2 z-10">
          <span className="text-[8px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded"
            style={{ background: "rgba(251,191,36,0.15)", color: "#fbbf24" }}>
            Stale
          </span>
        </div>
      )}
      <Plot
        data={chartData}
        layout={layout}
        config={config}
        style={{ width: "100%", height: 280 }}
        useResizeHandler
      />
      <div className="text-[9px] text-slate-600 text-center mt-1">
        Charm = d(Delta)/d(Time) · Positive = long gamma · Negative = short gamma
      </div>
    </div>
  );
});

export default CharmChart;
