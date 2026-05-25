import React from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 1 — GET /api/heatseeker/air-pockets
 * Each pocket: { low, high, span_pct, max_abs_gex_in_run }
 *
 * Renders each row with a range-bar visualisation positioning the pocket
 * within the global low→high envelope.
 */
export default function AirPocketsPanel({ ticker = "SPY", minGapPct = 0.02 }) {
  const { data, loading, error } = useHeatseeker("air-pockets", {
    ticker,
    min_gap_pct: minGapPct,
  });
  const pockets = data?.air_pockets || [];

  // Compute the envelope for the visual bar
  const env = pockets.reduce(
    (acc, p) => {
      if (p.low < acc.lo) acc.lo = p.low;
      if (p.high > acc.hi) acc.hi = p.high;
      return acc;
    },
    { lo: Infinity, hi: -Infinity }
  );
  const span = env.hi - env.lo || 1;

  return (
    <div className="panel p-3" data-testid="hs-air-pockets">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Air Pockets</div>
        <span className="text-[9px] text-slate-500">{pockets.length}</span>
      </div>
      {loading && !data && (
        <div className="text-slate-500 text-[11px]">Loading…</div>
      )}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && pockets.length === 0 && (
        <div className="text-slate-500 text-[11px]">No air pockets detected.</div>
      )}
      {pockets.length > 0 && (
        <div className="space-y-2">
          {pockets.map((p, i) => {
            const left = ((p.low - env.lo) / span) * 100;
            const width = ((p.high - p.low) / span) * 100;
            return (
              <div key={i} className="text-[11px]">
                <div className="flex justify-between mono text-slate-300">
                  <span>
                    {fmt(p.low, 0)} – {fmt(p.high, 0)}
                  </span>
                  <span className="text-amber-300">
                    {(p.span_pct ?? 0).toFixed(2)}%
                  </span>
                </div>
                <div className="relative h-1.5 bg-slate-800/60 rounded mt-1 overflow-hidden">
                  <div
                    className="absolute top-0 bottom-0 bg-amber-400/60 rounded"
                    style={{
                      left: `${Math.max(0, left)}%`,
                      width: `${Math.max(2, Math.min(100, width))}%`,
                    }}
                  />
                </div>
                <div className="text-[9px] text-slate-500 mt-0.5">
                  max |γ| in run {fmtAbs(p.max_abs_gex_in_run)}
                </div>
              </div>
            );
          })}
          <div className="text-[9px] text-slate-600 italic">
            Pathways, not targets.
          </div>
        </div>
      )}
    </div>
  );
}
