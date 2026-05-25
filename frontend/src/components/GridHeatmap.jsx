import React from "react";
import { fmt, fmtAbs, pctClass, tagFor, cellColor, expFmt, fmtCell } from "../lib/helpers";

export default function GridHeatmap({ data, filters, onCellClick, viewMode = "gex" }) {
  const spotRowRef = React.useRef(null);
  React.useEffect(() => {
    if (spotRowRef.current) spotRowRef.current.scrollIntoView({ block: "center", behavior: "auto" });
  }, [data?.ticker, data?.mode]);

  if (!data?.grid) return <div className="text-slate-500 text-xs p-4">No grid data</div>;
  const { spot, grid, vex_grid, charm_grid, nodes } = data;
  const expiries = grid.expiries || [];
  let strikes = (grid.strikes || []).slice().sort((a, b) => b - a);
  if (filters?.side === "above") strikes = strikes.filter(s => s > spot);
  if (filters?.side === "below") strikes = strikes.filter(s => s < spot);

  const cellOf = (e, s) => {
    const g = (viewMode === "charm" ? charm_grid : viewMode === "vex" ? vex_grid : grid.grid) || {};
    const ge = g[e];
    if (!ge) return 0;
    return ge[String(Number.isInteger(s) ? s : s)] ?? ge[String(s)] ?? ge[String(s.toFixed(1))] ?? ge[String(parseInt(s))] ?? 0;
  };

  strikes = strikes.filter(s => expiries.some(e => Math.abs(cellOf(e, s)) > 0));

  if (filters?.lifecycle && filters.lifecycle !== "all") {
    const lifecycleStrikes = new Set((data.strikes || []).filter(s => s.lifecycle === filters.lifecycle).map(s => s.strike));
    strikes = strikes.filter(s => lifecycleStrikes.has(s));
  }

  let maxAbs = 1;
  for (const e of expiries) for (const s of strikes) { const v = cellOf(e, s); if (Math.abs(v) > maxAbs) maxAbs = Math.abs(v); }

  const kingStrike = nodes?.king?.strike;
  const floorSet = new Set((nodes?.floors || []).map(f => f.strike));
  const ceilSet = new Set((nodes?.ceilings || []).map(f => f.strike));
  const gkSet = new Set((nodes?.gatekeepers || []).map(f => f.strike));
  const inAir = (s) => (nodes?.air_pockets || []).some(a => s >= a.low && s <= a.high);
  const spotIdx = strikes.findIndex(s => s <= spot);

  return (
    <div className="overflow-auto" data-testid="grid-heatmap" style={{ maxHeight: "60vh" }}>
      <table className="border-collapse mono text-[10px]">
        <thead className="sticky top-0 z-10" style={{ background: "var(--panel)" }}>
          <tr>
            <th className="px-2 py-1 text-left text-slate-500 sticky left-0 z-20" style={{ background: "var(--panel)" }}>Strike</th>
            {expiries.map((e) => <th key={e} className="px-2 py-1 text-slate-400 font-normal" style={{ minWidth: 64 }}>{expFmt(e)}</th>)}
            <th className="px-2 py-1 text-slate-500 text-left">Tags</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((s, i) => {
            const isKing = s === kingStrike;
            const isFloor = floorSet.has(s);
            const isCeil = ceilSet.has(s);
            const isGate = gkSet.has(s);
            const airy = inAir(s);
            return (
              <React.Fragment key={s}>
                {i === spotIdx && (
                  <tr ref={spotRowRef}>
                    <td colSpan={expiries.length + 2} style={{ padding: 0 }}>
                      <div className="relative" style={{ height: 18 }}>
                        <div className="absolute inset-x-0 top-1/2" style={{ height: 1, background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)", boxShadow: "0 0 6px rgba(94,234,212,0.55)" }} />
                        <div className="absolute left-2 top-0 text-[10px] font-bold tracking-widest text-teal-300 px-1" style={{ background: "var(--panel)", textShadow: "0 0 6px rgba(94,234,212,0.6)" }}>◆ SPOT {fmt(spot, 2)}</div>
                      </div>
                    </td>
                  </tr>
                )}
                <tr className={`bar-row ${airy ? "opacity-65" : ""}`} data-testid={`grid-row-${s}`}>
                  <td className={`px-2 py-1 font-bold sticky left-0 z-10 ${isKing ? "text-amber-300" : isFloor ? "text-emerald-400" : isCeil ? "text-rose-400" : isGate ? "text-sky-400" : "text-slate-400"}`} style={{ background: "var(--panel)" }}>
                    {fmt(s, s >= 1000 ? 0 : 1)}
                  </td>
                  {expiries.map((e) => {
                    const v = cellOf(e, s);
                    const isKingCell = isKing && Math.abs(v) > 0.6 * maxAbs;
                    const col = cellColor(v, maxAbs, isKingCell, viewMode);
                    return (
                      <td key={e} className="px-1 py-1 text-center cursor-pointer hover:outline hover:outline-1 hover:outline-teal-400" style={{ background: col.bg, color: col.text, minWidth: 60 }} onClick={() => onCellClick && onCellClick(s, e, v)} title={`strike ${s} · exp ${e} · ${viewMode === "charm" ? "charm" : viewMode === "vex" ? "vex" : "gex"} ${fmtCell(v)}`}>
                        {fmtCell(v)}
                      </td>
                    );
                  })}
                  <td className="px-2 py-1">
                    <div className="flex gap-1 items-center">
                      {isKing && <span className="tag king">KING</span>}
                      {isFloor && <span className="tag floor">FLR</span>}
                      {isCeil && <span className="tag ceiling">CEIL</span>}
                      {isGate && <span className="tag gate">GATE</span>}
                      {airy && <span className="tag air">AIR</span>}
                    </div>
                  </td>
                </tr>
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
