import React, { useId, useMemo, useState } from "react";
import { signedCellPalette } from "../../lib/signedGridPalette";

/** Render the backend-admitted per-strike series from the same chain snapshot.
 * Values, measured/unknown counts and partial flags come from the producer.
 * This component only selects a visible window and draws pixels. Unknown
 * remains an outlined slot, partial exposure remains explicitly outlined,
 * and spot/selection retain the existing gold rail. No client aggregation.
 */
export function formatExposureTick(v) {
  const n = v;
  if (typeof n !== 'number' || !Number.isFinite(n)) return "unavailable";
  const sign = n < 0 ? "−" : "+";
  const abs = Math.abs(n);
  if (abs >= 1000000) {
    const m = abs / 1000000;
    const text = m >= 100 ? String(Math.round(m)) : String(Math.round(m * 10) / 10);
    return `${sign}${text}M`;
  }
  return `${sign}${Math.round(abs)}`;
}

export default function TriadExposure({ series, spot, selectedStrike, onSelect }) {
  const hatchId = `triad-negative-${useId().replace(/:/g, '')}`;
  const [windowStart, setWindowStart] = useState(null);
  const full = useMemo(() => {
    const byStrike = new Map();
    for (const row of series?.strikes || []) {
      if (!row || typeof row !== "object") continue;
      const strike = Number(row.strike);
      if (!Number.isFinite(strike)) continue;
      // Backend values and coverage are authoritative; this renderer only
      // chooses visible strikes and maps values to pixels.
      const entry = { strike, gex: row.gex, nKnown: row.n_measured,
        nTotal: row.n_total, partial: row.partial };
      byStrike.set(strike, entry);
    }
    return { byStrike, strikes: [...byStrike.keys()].sort((a, b) => a - b) };
  }, [series]);
  const spotKnown = typeof spot === 'number' && Number.isFinite(spot);
  let anchor = 0;
  if (spotKnown) for (let i = 0; i < full.strikes.length; i++) {
    if (Math.abs(full.strikes[i] - spot) <= Math.abs(full.strikes[anchor] - spot)) anchor = i;
  }
  const lastStart = Math.max(0, full.strikes.length - 21);
  const centered = spotKnown ? Math.max(0, Math.min(lastStart, anchor - 10)) : 0;
  const start = Math.min(lastStart, windowStart ?? centered);
  const strikes = full.strikes.slice(start, start + 21);
  const model = { byStrike: full.byStrike, strikes,
    max: Math.max(1, ...strikes.map(s => {
      const value = full.byStrike.get(s).gex;
      return typeof value === 'number' && Number.isFinite(value) ? Math.abs(value) : 0;
    })) };

  const w = 750, h = 190, y = 99, step = 31, x0 = 65;
  const scale = 66 / model.max;
  const first = strikes[0], last = strikes[strikes.length - 1];
  const outside = spotKnown && strikes.length > 0 && (spot < first || spot > last);
  // Slots are equally spaced, so interpolate within the enclosing pair of
  // listed strikes, not across the global strike range (which may have gaps).
  let spotx = x0;
  if (spotKnown && !outside) {
    const upper = strikes.findIndex(s => s >= spot);
    if (upper > 0) spotx += (upper - 1 + (spot - strikes[upper - 1]) / (strikes[upper] - strikes[upper - 1])) * step;
  }
  return <div>
    <div className="wall-desk-window">
      <span>{strikes.length ? `Showing strikes ${start + 1}–${start + strikes.length} of ${full.strikes.length} · ${first}–${last}` : 'No admitted strike rows'}</span>
      {full.strikes.length > 21 && <>
        <button type="button" disabled={start === 0} onClick={() => setWindowStart(Math.max(0, start - 21))}>Lower strikes</button>
        <button type="button" disabled={start >= lastStart} onClick={() => setWindowStart(Math.min(lastStart, start + 21))}>Higher strikes</button>
        <button type="button" disabled={!spotKnown} onClick={() => setWindowStart(null)}>Center on spot</button>
      </>}
    </div>
    {outside && <p role="status">Spot {spot.toFixed(2)} is {spot < first ? 'below' : 'above'} this window. No off-window marker is extrapolated.</p>}
    {selectedStrike != null && !strikes.includes(selectedStrike) && <p role="status">Selected strike {selectedStrike} is outside this window.</p>}
    <svg className="triad-exposure" viewBox={`0 0 ${w} ${h}`} role="group" aria-label="Signed exposure by strike. Gold positive, purple negative with hatching, partial outlined, unknown gray.">
    <defs><pattern id={hatchId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="2" height="6" fill="rgba(0,0,0,0.28)" />
    </pattern></defs>
    <line x1="37" y1={y} x2="727" y2={y} stroke="#454545" />
    <line x1="37" y1="28" x2="727" y2="28" stroke="#282828" />
    <line x1="37" y1="164" x2="727" y2="164" stroke="#282828" />
    <text x="5" y="31" fill="#8ea6b5" fontSize="9">{formatExposureTick(model.max)}</text>
    <text x="19" y="103" fill="#8ea6b5" fontSize="9">0</text>
    <text x="5" y="167" fill="#8ea6b5" fontSize="9">{formatExposureTick(-model.max)}</text>
    {model.strikes.map((strike, i) => {
      const entry = model.byStrike.get(strike);
      const known = entry.nKnown > 0;
      const partial = entry.partial === true;
      const x = x0 + i * step, rh = Math.abs(entry.gex) * scale;
      const selected = strike === selectedStrike;
      const palette = signedCellPalette(entry.gex, model.max);
      const barY = entry.gex > 0 ? y - rh : y;
      const barHeight = Math.max(rh, entry.gex === 0 ? 2 : 0);
      return <g key={strike} data-action="cell" data-strike={strike}
        data-known={entry.nKnown} data-total={entry.nTotal}
        data-exposure={entry.gex == null ? 'unknown' : entry.gex}
        data-partial={partial ? "true" : "false"}
        role="button" tabIndex={0} aria-pressed={selected}
        aria-label={`Strike ${strike}, ${known ? `${entry.gex} exposure, ${partial ? 'partial, ' : ''}${entry.nKnown}/${entry.nTotal} measured` : 'unknown exposure'}`}
        style={{ cursor: "pointer" }}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            if (onSelect) onSelect(strike);
          }
        }}
        onClick={() => onSelect && onSelect(strike)}>
        {known
          ? <g>
              <rect x={x - 11} y={barY} width="23" height={barHeight}
              fill={palette.background}
              stroke={partial ? "#c9a84c" : entry.gex === 0 ? "#86919b" : "none"} strokeDasharray={partial ? "3 2" : undefined} strokeWidth={partial || entry.gex === 0 ? 1 : 0}>
                {partial && <title>Partial exposure {entry.nKnown}/{entry.nTotal} measured</title>}
              </rect>
              {palette.backgroundImage !== 'none' && <rect x={x - 11} y={barY} width="23" height={barHeight} fill={`url(#${hatchId})`} pointerEvents="none" />}
            </g>
          : <rect x={x - 11} y={y - 8} width="23" height="16" fill="none"
              stroke="#86919b" strokeDasharray="3 2" opacity=".7"><title>Unknown exposure</title></rect>}
        {selected && <rect x={x - 13} y="24" width="27" height="143" fill="#c9a84c08" stroke="#c9a84c" strokeWidth="1" pointerEvents="none" />}
        {(i % 3 === 0 || selected) && <text x={x} y="182" textAnchor="middle"
          fill={selected ? "#f2d44b" : "#8ea6b5"} fontSize="10">{strike}</text>}
      </g>;
    })}
    {spotKnown && !outside && strikes.length > 0 && <g data-spot-marker="true"><line x1={spotx} y1="20" x2={spotx} y2="165" stroke="#f2d44b" strokeDasharray="3 3" />
      <text x={spotx} y="15" fill="#f2d44b" textAnchor="middle" fontSize="10">Spot {spot.toFixed(2)}</text></g>}
  </svg></div>;
}
