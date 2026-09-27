import React from "react";
import { fmt } from "../lib/helpers";

export default function BarHeatmap({ data, filters, compact = true, viewMode = "gex" }) {
  if (!data?.strikes) return null;
  const { spot, strikes, nodes } = data;
  const key = viewMode === "vex" ? "vex" : viewMode === "charm" ? "charm" : "gex";
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const matrixKey = key === "vex" ? "vex_grid" : "charm_grid";
  const hasSelectedGrid = key !== "gex" && Object.prototype.hasOwnProperty.call(data.grid || {}, matrixKey);
  const matrix = data.grid?.[matrixKey];
  const expiries = [...new Set([...(data.grid?.expiries || []), ...Object.keys(matrix || {})])];
  const selectedValue = row => {
    if (!hasSelectedGrid) return finite(row[key]) ? row[key] : null;
    if (!expiries.length) return null;
    const cells = expiries.map(expiry => matrix?.[expiry]?.[String(row.strike)]);
    if (!cells.every(finite)) return null;
    const total = cells.reduce((sum, value) => sum + value, 0);
    return finite(total) ? total : null;
  };
  const filtered = strikes.map(row => ({...row, selectedValue: selectedValue(row)})).filter((s) => {
    const val = s.selectedValue;
    if (filters?.magMin && (val === null || Math.abs(val) < filters.magMin)) return false;
    if (filters?.lifecycle && filters.lifecycle !== "all" && s.lifecycle !== filters.lifecycle) return false;
    if (filters?.side === "above" && s.strike <= spot) return false;
    if (filters?.side === "below" && s.strike >= spot) return false;
    return true;
  });
  if (!filtered.length) return <div className="text-slate-500 text-xs p-4">No strikes match filters.</div>;
  const sorted = [...filtered].sort((a, b) => b.strike - a.strike);
  const maxAbs = Math.max(...filtered.map(s => Math.abs(s.selectedValue ?? 0)), 1);
  const king = key === "gex" ? nodes?.king?.strike : null;
  const fSet = new Set((key === "gex" ? nodes?.floors || [] : []).map(f => f.strike));
  const cSet = new Set((key === "gex" ? nodes?.ceilings || [] : []).map(f => f.strike));
  const rowH = compact ? 14 : 18;
  const barColorPos = viewMode === "vex" ? "rgba(245, 158, 11, 0.7)" : viewMode === "charm" ? "rgba(34, 211, 238, 0.7)" : "rgba(45, 212, 191, 0.7)";
  const barColorNeg = viewMode === "vex" ? "rgba(219, 39, 119, 0.7)" : viewMode === "charm" ? "rgba(168, 85, 247, 0.7)" : "rgba(168, 85, 247, 0.7)";
  const kingColorPos = viewMode === "vex" ? "rgba(251, 191, 36, 0.9)" : viewMode === "charm" ? "rgba(34, 211, 238, 0.9)" : "rgba(190, 242, 100, 0.9)";
  const kingColorNeg = viewMode === "vex" ? "rgba(219, 39, 119, 0.85)" : viewMode === "charm" ? "rgba(168, 85, 247, 0.85)" : "rgba(232, 121, 249, 0.85)";

  return (
    <div className="relative" style={{ paddingTop: 4, paddingBottom: 4 }}>
      {sorted.map((s, i) => {
        const isKing = s.strike === king;
        const isF = fSet.has(s.strike);
        const isC = cSet.has(s.strike);
        const val = s.selectedValue;
        const pos = val > 0;
        const w = Math.max(2, (Math.abs(val) / maxAbs) * 48);
        const prev = sorted[i - 1];
        const showSpot = prev && prev.strike > spot && s.strike <= spot;
        return (
          <React.Fragment key={s.strike}>
            {showSpot && (
              <div className="flex items-center my-1 px-2">
                <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)" }} />
                <div className="px-1 text-[9px] tracking-widest text-teal-300">{fmt(spot, 1)}</div>
                <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)" }} />
              </div>
            )}
            <div className="bar-row flex items-center text-[10px] mono px-1" style={{ height: rowH }} aria-label={`${s.strike} ${key.toUpperCase()}: ${val === null ? "unavailable" : val}`} title={`${key.toUpperCase()}: ${val === null ? "Unavailable for the selected scope" : val}`}>
              <div className="flex-1 flex justify-end pr-1">
                {val !== null && val < 0 && <div style={{ width: `${w}%`, height: 10, borderRadius: 2, background: isKing ? kingColorNeg : barColorNeg }} />}
              </div>
              <div className={`w-14 text-center ${isKing ? "text-amber-300 font-bold" : isF ? "text-emerald-400" : isC ? "text-rose-400" : "text-slate-400"}`}>{fmt(s.strike, 0)}</div>
              <div className="flex-1 flex pl-1">
                {val === null ? <span className="text-slate-500">Unavailable</span> : val === 0 ? <span className="text-slate-500">0</span> : null}
                {val !== null && pos && <div style={{ width: `${w}%`, height: 10, borderRadius: 2, background: isKing ? kingColorPos : barColorPos }} />}
              </div>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}
