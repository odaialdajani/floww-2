import React, { useMemo } from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 1 — GET /api/heatseeker/flip-zones
 * Renders flip zones sorted by |price - spot| ascending.
 */
export default function FlipZonesPanel({ ticker = "SPY", spot = null, windowPct = 0.05 }) {
  const { data, loading, error } = useHeatseeker("flip-zones", {
    ticker,
    window_pct: windowPct,
  });

  const rows = useMemo(() => {
    const zones = data?.flip_zones || [];
    if (spot == null) return zones;
    return [...zones].sort(
      (a, b) => Math.abs(a.price - spot) - Math.abs(b.price - spot)
    );
  }, [data, spot]);

  return (
    <div className="panel p-3" data-testid="hs-flip-zones">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Flip Zones</div>
        <span className="text-[9px] text-slate-500">
          {data?.window_low != null && data?.window_high != null
            ? `${fmt(data.window_low, 0)} – ${fmt(data.window_high, 0)}`
            : "—"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-[11px]">Loading…</div>}
      {error && (
        <div className="text-rose-400 text-[10px]">Error: {error}</div>
      )}
      {data && rows.length === 0 && (
        <div className="text-slate-500 text-[11px]">No flip zones in window.</div>
      )}
      {rows.length > 0 && (
        <div className="space-y-1">
          {rows.map((z, i) => {
            const dir = `${z.from_sign > 0 ? "+" : "−"} → ${z.to_sign > 0 ? "+" : "−"}`;
            const isBullish = z.to_sign > 0;
            return (
              <div
                key={`${z.price}-${i}`}
                className="flex items-center justify-between text-[11px] border-t border-slate-800/60 pt-1 first:border-t-0 first:pt-0"
              >
                <span className="mono font-bold text-slate-200">
                  {fmt(z.price, 1)}
                </span>
                <span
                  className={`mono text-[10px] ${
                    isBullish ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {dir}
                </span>
                <span className="mono text-slate-400 text-[10px]">
                  γ {fmtAbs(z.strength)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
