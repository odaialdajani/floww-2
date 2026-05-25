import React, { useEffect, useRef } from "react";
import { fmt, pctClass, tagFor } from "../lib/helpers";

export default function BarHeatmap({ data, filters, compact = true, viewMode = "gex" }) {
  if (!data?.strikes) return null;
  const { spot, strikes, nodes } = data;
  const spotRef = useRef(null);
  const key = viewMode === "vex" ? "vex" : viewMode === "charm" ? "charm" : "gex";
  const filtered = strikes.filter((s) => {
    const val = s[key] || s.gex || 0;
    if (filters?.magMin && Math.abs(val) < filters.magMin) return false;
    if (filters?.lifecycle && filters.lifecycle !== "all" && s.lifecycle !== filters.lifecycle) return false;
    if (filters?.side === "above" && s.strike <= spot) return false;
    if (filters?.side === "below" && s.strike >= spot) return false;
    return true;
  });
  if (!filtered.length) return <div className="text-slate-500 text-xs p-4">No strikes match filters.</div>;
  const sorted = [...filtered].sort((a, b) => b.strike - a.strike);
  const maxAbs = Math.max(...filtered.map(s => Math.abs(s[key] || s.gex || 0)), 1);
  const king = nodes?.king?.strike;
  const fSet = new Set((nodes?.floors || []).map(f => f.strike));
  const cSet = new Set((nodes?.ceilings || []).map(f => f.strike));
  const rowH = compact ? 16 : 20;
  const barColorPos = viewMode === "vex" ? "rgba(245, 158, 11, 0.7)" : viewMode === "charm" ? "rgba(34, 211, 238, 0.7)" : "rgba(45, 212, 191, 0.7)";
  const barColorNeg = viewMode === "vex" ? "rgba(219, 39, 119, 0.7)" : viewMode === "charm" ? "rgba(168, 85, 247, 0.7)" : "rgba(168, 85, 247, 0.7)";
  const kingColorPos = viewMode === "vex" ? "rgba(251, 191, 36, 0.9)" : viewMode === "charm" ? "rgba(34, 211, 238, 0.9)" : "rgba(190, 242, 100, 0.9)";
  const kingColorNeg = viewMode === "vex" ? "rgba(219, 39, 119, 0.85)" : viewMode === "charm" ? "rgba(168, 85, 247, 0.85)" : "rgba(232, 121, 249, 0.85)";

  // auto-scroll to spot line on mount only
  useEffect(() => {
    if (spotRef.current) {
      spotRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="relative" style={{ paddingTop: 4, paddingBottom: 4 }}>
      {sorted.map((s, i) => {
        const isKing = s.strike === king;
        const isF = fSet.has(s.strike);
        const isC = cSet.has(s.strike);
        const val = s[key] || s.gex || 0;
        const pos = val > 0;
        const w = Math.max(2, (Math.abs(val) / maxAbs) * 48);
        const prev = sorted[i - 1];
        const showSpot = prev && prev.strike > spot && s.strike <= spot;
        return (
          <React.Fragment key={s.strike}>
            {showSpot && (
              <div ref={spotRef} className="flex items-center my-1 px-0" style={{ height: compact ? 22 : 26 }}>
                <div className="flex-1" style={{ height: 2, background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.95) 20%, rgba(94,234,212,1) 50%, rgba(94,234,212,0.95) 80%, transparent)", boxShadow: "0 0 8px rgba(94,234,212,0.7), 0 0 20px rgba(94,234,212,0.3)" }} />
                <div className="px-2 text-[10px] font-bold tracking-widest text-teal-300 whitespace-nowrap" style={{ textShadow: "0 0 10px rgba(94,234,212,0.7), 0 0 20px rgba(94,234,212,0.4)" }}>◆ SPOT {fmt(spot, 1)}</div>
                <div className="flex-1" style={{ height: 2, background: "linear-gradient(90deg, rgba(94,234,212,1) 20%, rgba(94,234,212,1) 50%, rgba(94,234,212,0.95) 80%, transparent)", boxShadow: "0 0 8px rgba(94,234,212,0.7), 0 0 20px rgba(94,234,212,0.3)" }} />
              </div>
            )}
            <div className="bar-row flex items-center text-[10px] mono px-1" style={{ height: rowH }}>
              <div className="flex-1 flex justify-end pr-1">
                {!pos && <div style={{ width: `${w}%`, height: 10, borderRadius: 2, background: isKing ? kingColorNeg : barColorNeg }} />}
              </div>
              <div className={`w-14 text-center ${isKing ? "text-amber-300 font-bold" : isF ? "text-emerald-400" : isC ? "text-rose-400" : "text-slate-400"}`}>{fmt(s.strike, 0)}</div>
              <div className="flex-1 flex pl-1">
                {pos && <div style={{ width: `${w}%`, height: 10, borderRadius: 2, background: isKing ? kingColorPos : barColorPos }} />}
              </div>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}
