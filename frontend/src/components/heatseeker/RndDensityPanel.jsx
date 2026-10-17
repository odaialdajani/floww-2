/**
 * RndDensityPanel.jsx — STEAL-LIST #4 (frontend mount)
 *
 * Renders the Breeden-Litzenberger risk-neutral PDF + CDF from
 * GET http://localhost:8000/api/rnd/{ticker}?expiry_index=N
 *
 * Visualization (top → bottom, single tile):
 *   1. PDF shape (top half SVG, sky stroke) — mode line in slate
 *      + amber dashed vertical spot marker for reference.
 *   2. CDF shape (bottom half SVG, emerald stroke) — slate dashed
 *      median line at 0.5 + amber dashed vertical spot marker.
 *   3. 4 tail-prob chips below (p<95%, p<98%, p>102%, p>105%).
 *
 * Visual treatment mirrors HeatseekerDashboard.jsx's slate palette
 * (slate-200 text, bg-slate-900/40, sky/emerald/rose/amber accents,
 *  mono font on numerical readouts).
 *
 * Defensive degrade: any backend failure (timeout / 500 / unreachable)
 * shows the same amber offline card pattern StrikeConeBadge uses —
 * consistent with the dashboard's other steal-list tiles.
 *
 * Distinct from the OS-served Solstice and Zenith rows — this tile
 * is Row 4b, full-width beneath the 3-col Row 4 grid (StrikeCone +
 * Opportunity + NewsBadge) per the user's spec "alongside the
 * just-shipped StrikeCone + Opportunity" interpreted as a dedicated
 * row positioned after them rather than crammed into the existing
 * 3-col grid.
 */

import React, { memo, useEffect, useState } from "react";
import { BACKEND_BASE } from "../../config/api";
import { fetchStudyJSON } from "./studyFetch";
import StudyErrorCard from "./StudyErrorCard";

const SIDE_BASE =
  process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;

function fmt(n, d = 2) {
  return n == null || !Number.isFinite(Number(n))
    ? "—"
    : Number(n).toFixed(d);
}

function RndDensityPanel({ ticker = "SPY", expiries = 1 }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setErr(null);
    // Use the canonical query-style contract — the path-style
    // /api/rnd/{ticker}/{expiry} alias is also shipped but the
    // default expiry_index param is sufficient for the dashboard
    // heatmap (no need to enumerate every listed expiry in the UI).
    const qs = new URLSearchParams({ expiry_index: String(expiries) });
    fetchStudyJSON(
      `${SIDE_BASE}/api/rnd/${encodeURIComponent(ticker)}?${qs.toString()}`
    )
      .then((j) => {
        if (!cancelled) setData(j);
      })
      .catch((e) => {
        if (!cancelled) setErr(e);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, expiries]);

  if (err) {
    return (
      <StudyErrorCard
        title="Rnd Density"
        base={SIDE_BASE}
        error={err}
        testId="hs-rnd-density"
        className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 py-8 text-center"
      />
    );
  }

  if (!data) {
    return (
      <div
        className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-4 py-8 animate-pulse text-center"
        data-testid="hs-rnd-density"
      >
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">
          Rnd Density · {ticker}
        </div>
        <div className="text-[10px] text-slate-400">
          solving Breeden-Litzenberger…
        </div>
      </div>
    );
  }

  const {
    x_grid,
    pdf,
    cdf,
    spot,
    mode,
    tail_probs,
    n_strikes_used,
    method,
    expiry,
  } = data;

  const validData =
    Array.isArray(x_grid) &&
    x_grid.length > 0 &&
    Array.isArray(pdf) &&
    pdf.length > 0;

  let svgBlock = null;
  if (validData) {
    const minX = Math.min(...x_grid);
    const maxX = Math.max(...x_grid);
    const rangeX = maxX - minX || 1;
    const maxPdf = Math.max(...pdf) || 1;

    const toX = (val) => ((val - minX) / rangeX) * 100;
    const toPdfY = (val) => 100 - (val / maxPdf) * 90;
    const toCdfY = (val) => 100 - val * 90;

    const pdfPoints = x_grid
      .map((x, i) => `${toX(x)},${toPdfY(pdf[i])}`)
      .join(" ");
    const cdfPoints = x_grid
      .map((x, i) => `${toX(x)},${toCdfY(cdf[i])}`)
      .join(" ");

    const spotX =
      spot != null && spot >= minX && spot <= maxX ? toX(spot) : null;
    const modeX =
      mode != null && mode >= minX && mode <= maxX ? toX(mode) : null;
    const median = 0.5;

    svgBlock = (
      <div className="flex flex-col gap-2">
        {/* PDF chart (top half) */}
        <div className="relative w-full h-[100px] border-b border-slate-700/30">
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            className="w-full h-full"
            data-testid="hs-rnd-svg-pdf"
          >
            <polyline
              fill="none"
              stroke="#38bdf8"
              strokeWidth="1.5"
              points={pdfPoints}
              vectorEffect="non-scaling-stroke"
            />
            {modeX != null && (
              <line
                x1={modeX}
                y1="0"
                x2={modeX}
                y2="100"
                stroke="#94a3b8"
                strokeWidth="0.5"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {spotX != null && (
              <line
                x1={spotX}
                y1="0"
                x2={spotX}
                y2="100"
                stroke="#fbbf24"
                strokeWidth="1"
                strokeDasharray="2,2"
                vectorEffect="non-scaling-stroke"
              />
            )}
          </svg>
          <div className="absolute top-1 left-2 text-[9px] text-slate-500 font-mono tracking-widest uppercase">
            PDF · mode ${fmt(mode)}
          </div>
        </div>

        {/* CDF chart (bottom half) */}
        <div className="relative w-full h-[80px]">
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            className="w-full h-full"
            data-testid="hs-rnd-svg-cdf"
          >
            <polyline
              fill="none"
              stroke="#10b981"
              strokeWidth="1.5"
              points={cdfPoints}
              vectorEffect="non-scaling-stroke"
            />
            <line
              x1="0"
              y1={toCdfY(median)}
              x2="100"
              y2={toCdfY(median)}
              stroke="#64748b"
              strokeWidth="0.5"
              strokeDasharray="1,2"
              vectorEffect="non-scaling-stroke"
            />
            {spotX != null && (
              <line
                x1={spotX}
                y1="0"
                x2={spotX}
                y2="100"
                stroke="#fbbf24"
                strokeWidth="1"
                strokeDasharray="2,2"
                vectorEffect="non-scaling-stroke"
              />
            )}
          </svg>
          <div className="absolute top-1 left-2 text-[9px] text-slate-500 font-mono tracking-widest uppercase">
            CDF · median
          </div>
        </div>

        {/* Tail_prob chips */}
        <div className="flex flex-wrap items-center justify-center gap-2 mt-2 pt-2 border-t border-slate-800">
          <div className="px-2 py-1 rounded bg-slate-800/50 text-[10px] font-mono text-slate-300">
            <span className="text-rose-400 mr-1">↓ p&lt;95%:</span>
            {fmt(tail_probs?.p_below_95pct_spot)}
          </div>
          <div className="px-2 py-1 rounded bg-slate-800/50 text-[10px] font-mono text-slate-300">
            <span className="text-rose-400 mr-1">↓ p&lt;98%:</span>
            {fmt(tail_probs?.p_below_98pct_spot)}
          </div>
          <div className="px-2 py-1 rounded bg-slate-800/50 text-[10px] font-mono text-slate-300">
            <span className="text-emerald-400 mr-1">↑ p&gt;102%:</span>
            {fmt(tail_probs?.p_above_102pct_spot)}
          </div>
          <div className="px-2 py-1 rounded bg-slate-800/50 text-[10px] font-mono text-slate-300">
            <span className="text-emerald-400 mr-1">↑ p&gt;105%:</span>
            {fmt(tail_probs?.p_above_105pct_spot)}
          </div>
        </div>
      </div>
    );
  } else {
    svgBlock = (
      <div className="text-xs text-slate-500 py-10 text-center">
        Insufficient Option Chain Data
      </div>
    );
  }

  return (
    <div
      className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-4"
      data-testid="hs-rnd-density"
    >
      <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
          <span className="text-[10px] uppercase tracking-widest font-bold text-slate-200">
            Rnd Density · {ticker} · {expiry || "N/A"}
          </span>
        </div>
        <span className="text-[9px] uppercase tracking-widest font-mono text-slate-400">
          n_strikes={n_strikes_used} · {method || "cubic_spline_2nd_derivative"}
        </span>
      </div>
      {svgBlock}
    </div>
  );
}

export default memo(RndDensityPanel);
