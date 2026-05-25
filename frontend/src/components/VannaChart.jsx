/**
 * VannaChart.jsx
 *
 * Displays vanna exposure by strike price.
 * Vanna = d(Delta)/d(Vol) — how delta changes with implied volatility.
 *
 * Bars: positive vanna (call-heavy) in teal, negative (put-heavy) in red.
 * Overlay: spot price line.
 *
 * Uses Plotly for rendering with WebGL fallback to SVG on low-end devices.
 */

import React, { useMemo, useCallback, memo } from "react";
import Plot from "react-plotly.js";
import { useMarketData } from "../hooks/useMarketData";
import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
import { ErrorState } from "./RetryButton";

const VannaChart = memo(function VannaChart({ ticker = "SPY", spot = null }) {
  const { data, loading, error, showBadge, refresh } = useMarketData(
    `analytics/vanna-exposure/${ticker}`,
    { refreshMs: 60000, query: { expiries: 4 } }
  );

  const useWebGL = useMemo(() => isWebGLAvailable(), []);

  // Prepare chart data
  const chartData = useMemo(() => {
    if (!data || !data.strikes || !data.vanna) return null;

    const strikes = data.strikes;
    const vannaValues = data.vanna;

    // Decimate if too many points
    let plotStrikes = strikes;
    let plotVanna = vannaValues;
    if (strikes.length > 200) {
      const decimated = autoDecimate(
        strikes.map((s, i) => ({ x: s, y: vannaValues[i] })),
        200
      );
      plotStrikes = decimated.map((d) => d.x);
      plotVanna = decimated.map((d) => d.y);
    }

    const colors = plotVanna.map((v) => (v >= 0 ? "#5eead4" : "#f87171"));

    return [
      {
        x: plotStrikes,
        y: plotVanna,
        type: "bar",
        marker: { color: colors, opacity: 0.8 },
        name: "Vanna Exposure",
        hovertemplate:
          "Strike: $%{x}<br>Vanna: %{y:,.0f}<extra></extra>",
      },
      // Spot price line
      spot
        ? {
            x: [spot, spot],
            y: [Math.min(...plotVanna) * 1.1, Math.max(...plotVanna) * 1.1],
            type: "scatter",
            mode: "lines",
            line: { color: "#fbbf24", width: 2, dash: "dash" },
            name: "Spot",
            hovertemplate: "Spot: $%{x}<extra></extra>",
          }
        : null,
    ].filter(Boolean);
  }, [data, spot]);

  const layout = useMemo(
    () => ({
      title: {
        text: `Vanna Exposure — ${ticker}`,
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
        title: "Vanna",
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
    return <ErrorState error={error} onRetry={refresh} title="Vanna data unavailable" />;
  }

  if (loading && !data) {
    return (
      <div className="panel p-4 flex items-center justify-center" style={{ minHeight: 250 }}>
        <div className="text-[11px] text-slate-500 animate-pulse">Loading vanna exposure…</div>
      </div>
    );
  }

  if (!chartData) {
    return (
      <div className="panel p-4 flex items-center justify-center" style={{ minHeight: 250 }}>
        <div className="text-[11px] text-slate-500">No vanna data available</div>
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
        Vanna = d(Delta)/d(Vol) · Positive = call-heavy · Negative = put-heavy
      </div>
    </div>
  );
});

export default VannaChart;
