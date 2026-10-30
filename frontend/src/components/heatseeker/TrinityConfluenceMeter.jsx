import React from "react";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Triad Meridian — SPY/QQQ/SPX alignment score (0-100).
 */
function scoreColor(s) {
  if (s >= 70) return { stroke: "#34d399", text: "text-emerald-400", label: "Strong Alignment" };
  if (s >= 40) return { stroke: "#fbbf24", text: "text-amber-400", label: "Moderate" };
  return { stroke: "#f87171", text: "text-rose-400", label: "Weak / Divergent" };
}

export default function TrinityConfluenceMeter() {
  const { data, loading, error } = useHeatseeker("trinity-confluence", {});
  const score = Math.max(0, Math.min(100, Number(data?.score) || 0));
  const c = scoreColor(score);
  const dash = (score / 100) * 125;
  const aligned = Array.isArray(data?.aligned_dimensions) ? data.aligned_dimensions : [];
  const divergences = Array.isArray(data?.divergences) ? data.divergences : [];

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-trinity-confluence">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">🔱</span>
          <span className="text-xs font-semibold text-slate-200">Meridian alignment</span>
        </div>
        <span className="text-[10px] text-slate-500">SPY · QQQ · SPX</span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className="flex items-center gap-4">
          <div className="flex-shrink-0">
            <svg viewBox="0 0 100 60" width="120" height="72">
              <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke="#1f2a3a" strokeWidth="8" />
              <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke={c.stroke} strokeWidth="8" strokeDasharray={`${dash} 200`} strokeLinecap="round" />
            </svg>
          </div>
          <div className="flex-1">
            <div className={`text-3xl font-bold mono ${c.text}`}>{score.toFixed(0)}</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">{data.verdict || c.label}</div>
          </div>
        </div>
      )}
      {(aligned.length > 0 || divergences.length > 0) && (
        <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-slate-700/30">
          <div>
            <div className="text-emerald-400 font-semibold text-[10px] mb-1">✓ Aligned</div>
            {aligned.length === 0 ? (
              <div className="text-slate-600 text-[10px]">—</div>
            ) : (
              <ul className="space-y-0.5">
                {aligned.map((d, i) => <li key={i} className="text-emerald-300 text-[10px] mono">{d}</li>)}
              </ul>
            )}
          </div>
          <div>
            <div className="text-rose-400 font-semibold text-[10px] mb-1">✗ Divergent</div>
            {divergences.length === 0 ? (
              <div className="text-slate-600 text-[10px]">—</div>
            ) : (
              <ul className="space-y-0.5">
                {divergences.map((d, i) => <li key={i} className="text-rose-300 text-[10px] mono">{d}</li>)}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
