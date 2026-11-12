import React from "react";
import { fmt } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Beach Ball pattern indicator — shows when spot is stretched past king node.
 * Compact card with脉冲 animation when active.
 *
 * The reading is the measured DISTANCE from the king node, in points and in
 * percent. The legacy probability-like "confidence" label is retired: a
 * distance ratio is not a calibrated outcome probability, and no time
 * series exists here to support one. Overshoot, unwind and squeeze stay
 * unverified hypotheses, so the card shows distance and nothing more.
 */
export default function BeachBallIndicator({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("beach-ball", { ticker });
  const active = !!data?.active;
  const pts = data?.spot_distance_points;
  const pct = data?.spot_distance_pct;
  const dirSign = data?.direction === "above" ? 1 : data?.direction === "below" ? -1 : 0;

  return (
    <div className={`rounded-xl border p-3 transition-all ${active ? "border-amber-400/40 bg-amber-500/5" : "border-slate-700/30 bg-slate-800/20"}`}
      data-testid="hs-beach-ball">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm">🏖️</span>
          <span className="text-xs font-semibold text-slate-200">Beach Ball</span>
        </div>
        <span className={`text-[10px] uppercase tracking-widest font-bold ${active ? "text-amber-300" : "text-slate-500"}`}>
          {active ? <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />ACTIVE</span> : "○ idle"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className="space-y-1.5 text-xs">
          <div className="flex justify-between items-center">
            <span className="text-slate-400">King Node</span>
            <span className="mono font-bold text-amber-300">{data.king_node ? `$${fmt(data.king_node, 0)}` : "—"}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Distance</span>
            <span className={`mono font-bold ${dirSign > 0 ? "text-emerald-400" : dirSign < 0 ? "text-rose-400" : "text-slate-300"}`}>
              {pts != null && pct != null
                ? `${pts >= 0 ? "+" : "−"}$${fmt(Math.abs(pts), 2)} pts · ${(pct * 100).toFixed(2)}%`
                : "—"}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Direction</span>
            <span className="mono text-slate-300 capitalize">{data.direction || "—"}</span>
          </div>
        </div>
      )}
    </div>
  );
}
