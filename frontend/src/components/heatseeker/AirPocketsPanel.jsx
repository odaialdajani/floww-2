import React from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 1 — Air Pockets panel.
 * Each pocket: { low, high, span_pct, max_abs_gex_in_run }
 * Renders each row with a range-bar visualization.
 *
 * The pocket is computed over GROSS exposure and only inside runs of
 * continuously observed strikes, so the panel discloses the loaded ladder it
 * was measured over (strikes observed, expected spacing, unobserved
 * strikes). An unknown coverage is not the same reading as "no pockets".
 */
export default function AirPocketsPanel({ ticker = "SPY", minGapPct = 0.02 }) {
  const { data, loading, error } = useHeatseeker("air-pockets", { ticker, min_gap_pct: minGapPct });
  const pockets = data?.air_pockets || [];
  const coverageOk = data?.coverage_status === "ok";
  const strikes = Number(data?.strikes_observed) || 0;
  const omitted = Number(data?.n_omitted_strikes) || 0;
  const unknownExposure = Number(data?.strikes_unknown_exposure) || 0;
  const step = data?.expected_step;

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
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-air-pockets">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm">🕳️</span>
          <span className="text-xs font-semibold text-slate-200">Air Pockets</span>
        </div>
        <span className="text-[10px] text-slate-500">{data && !coverageOk ? "Coverage incomplete" : `${pockets.length} found`}</span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && !coverageOk && (
        <div className="text-slate-500 text-xs py-2 text-center">
          Coverage unknown · {unknownExposure > 0
            ? `exposure unavailable at ${unknownExposure} observed strike${unknownExposure === 1 ? "" : "s"}`
            : strikes > 0 ? "strike spacing not established" : "strike ladder not loaded"}
        </div>
      )}
      {data && coverageOk && pockets.length === 0 && (
        <div className="text-slate-500 text-xs py-2 text-center">No air pockets detected</div>
      )}
      {data && (
        <div className="text-[10px] text-slate-500 mb-1.5" data-testid="hs-air-pockets-coverage">
          {strikes} strikes observed · expected spacing {step == null ? "unknown" : `$${fmt(step, 2)}`}
          {` · ${omitted} unobserved strike${omitted === 1 ? "" : "s"}`} · measured over gross exposure
        </div>
      )}
      {pockets.length > 0 && (
        <div className="space-y-2.5">
          {pockets.map((p, i) => {
            const left = ((p.low - env.lo) / span) * 100;
            const width = ((p.high - p.low) / span) * 100;
            return (
              <div key={i} className="text-xs">
                <div className="flex justify-between mono text-slate-200 mb-1">
                  <span className="font-bold">${fmt(p.low, 0)} – ${fmt(p.high, 0)}</span>
                  <span className="text-amber-300 font-bold">{((p.span_pct ?? 0) * 100).toFixed(2)}%</span>
                </div>
                <div className="relative h-2 bg-slate-800/60 rounded-full overflow-hidden">
                  <div className="absolute top-0 bottom-0 bg-gradient-to-r from-amber-500/60 to-amber-400/60 rounded-full"
                    style={{ left: `${Math.max(0, left)}%`, width: `${Math.max(2, Math.min(100, width))}%` }} />
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">max gross exposure in run: {fmtAbs(p.max_abs_gex_in_run)}</div>
              </div>
            );
          })}
          <div className="text-[10px] text-slate-500 italic pt-1 border-t border-slate-700/30">Pathways, not targets.</div>
        </div>
      )}
    </div>
  );
}
