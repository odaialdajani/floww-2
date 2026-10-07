import React, { useMemo } from "react";

/**
 * TriadExposure — signed per-strike exposure SVG from annotated chain rows.
 *
 * Each chain row carries ONE canonical signed gex (services/triad_projection
 * annotate_contract_exposure) plus gex_basis ("OI" measured vs "OI_UNKNOWN").
 * Bars: measured rows cyan (positive) / violet (negative); unknown rows
 * render as gray outlined slots, never zero-filled (unknown is not neutral).
 * Gold dashed line marks spot; the selected strike highlights. Pure
 * presentational transform of admitted rows — no new metric is invented.
 */
export default function TriadExposure({ rows, spot, selectedStrike, onSelect }) {
  const model = useMemo(() => {
    const byStrike = new Map();
    for (const row of rows || []) {
      if (!row || typeof row !== "object") continue;
      const strike = Number(row.strike);
      if (!Number.isFinite(strike)) continue;
      const entry = byStrike.get(strike) || { strike, gex: 0, known: false };
      if (typeof row.gex === "number" && Number.isFinite(row.gex)) {
        entry.gex += row.gex;
        entry.known = true;
      }
      byStrike.set(strike, entry);
    }
    let strikes = [...byStrike.keys()].sort((a, b) => a - b);
    if (typeof spot === "number" && Number.isFinite(spot) && strikes.length > 21) {
      let anchor = 0;
      for (let i = 0; i < strikes.length; i++) {
        if (Math.abs(strikes[i] - spot) <= Math.abs(strikes[anchor] - spot)) anchor = i;
      }
      const lo = Math.max(0, Math.min(strikes.length - 21, anchor - 10));
      strikes = strikes.slice(lo, lo + 21);
    } else {
      strikes = strikes.slice(0, 21);
    }
    const max = Math.max(1, ...strikes.map(s => Math.abs(byStrike.get(s).gex)));
    return { byStrike, strikes, max };
  }, [rows, spot]);

  const w = 750, h = 190, y = 99, step = 31, x0 = 65;
  const scale = 66 / model.max;
  return <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Signed exposure by strike. Measured cyan or violet, unknown gray.">
    <line x1="37" y1={y} x2="727" y2={y} stroke="#476374" />
    <line x1="37" y1="28" x2="727" y2="28" stroke="#1d3342" />
    <line x1="37" y1="164" x2="727" y2="164" stroke="#1d3342" />
    <text x="5" y="31" fill="#8ea6b5" fontSize="9">+{Math.round(model.max)}M</text>
    <text x="19" y="103" fill="#8ea6b5" fontSize="9">0</text>
    <text x="5" y="167" fill="#8ea6b5" fontSize="9">−{Math.round(model.max)}M</text>
    {model.strikes.map((strike, i) => {
      const entry = model.byStrike.get(strike);
      const x = x0 + i * step, rh = Math.abs(entry.gex) * scale;
      const selected = strike === selectedStrike;
      return <g key={strike} data-action="cell" data-strike={strike} style={{ cursor: "pointer" }}
        onClick={() => onSelect && onSelect(strike)}>
        {entry.known
          ? <rect x={x - 11} y={entry.gex > 0 ? y - rh : y} width="23" height={rh}
              fill={entry.gex > 0 ? "#33d4df" : "#9368ed"} opacity=".85" />
          : <rect x={x - 11} y={y - 8} width="23" height="16" fill="none"
              stroke="#86919b" strokeDasharray="3 2" opacity=".7"><title>Unknown exposure</title></rect>}
        {selected && <rect x={x - 13} y="24" width="27" height="143" fill="#f2d44b08" stroke="#c2aa41" strokeWidth="1" />}
        {(i % 3 === 0 || selected) && <text x={x} y="182" textAnchor="middle"
          fill={selected ? "#f2d44b" : "#8ea6b5"} fontSize="10">{strike}</text>}
      </g>;
    })}
    {typeof spot === "number" && Number.isFinite(spot) && model.strikes.length > 0 && (() => {
      const first = model.strikes[0], last = model.strikes[model.strikes.length - 1];
      const span = Math.max(1, last - first);
      const spotx = x0 + ((spot - first) / span) * (model.strikes.length - 1) * step;
      return <g><line x1={spotx} y1="20" x2={spotx} y2="165" stroke="#f2d44b" strokeDasharray="3 3" />
        <text x={spotx} y="15" fill="#f2d44b" textAnchor="middle" fontSize="10">Spot {spot}</text></g>;
    })()}
  </svg>;
}
