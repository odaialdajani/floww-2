import React, { memo, useEffect, useMemo, useRef, useState } from "react";

/**
 * SkylitHeatmapGrid — Zenith heatseeker matrix
 *
 * Matches the Zenith reference exactly: a 2D matrix of
 *   STRIKE rows (descending, sticky left rail) × EXPIRATION-DATE columns.
 * Each cell is the GEX / VEX / CHARM at that (strike, expiry), colored on a
 * viridis scale over the signed value across the whole matrix.
 *
 * - Strike rail: sticky; the row closest to spot gets a white chip + notch
 * - King cell (max |value| in the matrix): bordered + ★
 * - % badge per cell: change vs the previous data refresh (asof-guarded)
 * - Column headers: expiry dates (MM-DD, full date in the title tooltip)
 * - Bottom legend: min → max viridis gradient
 *
 * Data source: data.grid = { expiries[], strikes[], grid, vex_grid,
 * charm_grid } where grid[expiry][strikeKey] is the value. strikeKey is the
 * integer string when whole, else the float string (backend _k()).
 */

const GRID_BY_VIEW = { gex: "grid", vex: "vex_grid", charm: "charm_grid", skylit: "grid" };

// Viridis stops, most-negative → max
const VIRIDIS = [
  [0x44, 0x01, 0x54], [0x46, 0x32, 0x7e], [0x36, 0x5c, 0x8d], [0x27, 0x7f, 0x8e],
  [0x1f, 0xa1, 0x87], [0x4a, 0xc1, 0x6d], [0xa0, 0xda, 0x39], [0xfd, 0xe7, 0x25],
];

function viridis(t) {
  const x = Math.max(0, Math.min(1, t)) * (VIRIDIS.length - 1);
  const i = Math.min(Math.floor(x), VIRIDIS.length - 2);
  const f = x - i;
  const [r1, g1, b1] = VIRIDIS[i];
  const [r2, g2, b2] = VIRIDIS[i + 1];
  return `rgb(${Math.round(r1 + (r2 - r1) * f)}, ${Math.round(g1 + (g2 - g1) * f)}, ${Math.round(b1 + (b2 - b1) * f)})`;
}

function fmtK(v) {
  if (v === null || v === undefined || isNaN(v)) return "";
  const sign = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a < 50) return `${sign}$0.0K`;
  if (a >= 1e9) {
    return `${sign}$${(a / 1e6).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`;
  }
  return `${sign}$${(a / 1e3).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}K`;
}

function strikeKey(s) {
  return Number.isInteger(s) ? String(s) : String(s);
}
function fmtStrike(s) {
  return s >= 1000 ? s.toFixed(0) : s.toFixed(1);
}
function fmtExpiry(e) {
  // "2026-07-06" → "07-06"
  const m = /^\d{4}-(\d{2})-(\d{2})$/.exec(e);
  return m ? `${m[1]}-${m[2]}` : e;
}

function SkylitHeatmapGrid({
  data,
  spot = null,
  ticker = "",
  viewMode = "gex",
  onCellClick,
  onStrikeClick,
  // Compact (default): tight rows for the in-frame view. "full": roomy
  // rows + larger type for the expanded overlay.
  density = "compact",
  // Window the rendered rows to N strikes centered on spot (2026-09-03:
  // the in-frame grid fits on screen instead of squeezing 100+ rows).
  // null = render every strike (expanded overlay).
  windowRows = null,
}) {
  const gridKey = GRID_BY_VIEW[viewMode] || "grid";

  const g = data?.grid || null;
  const expiries = useMemo(() => (g?.expiries ? [...g.expiries] : []), [g]);
  const matrix = useMemo(() => (g?.[gridKey] || {}), [g, gridKey]);

  // Strikes descending. Prefer grid.strikes; fall back to data.strikes.
  const strikes = useMemo(() => {
    const src = g?.strikes?.length ? g.strikes : (data?.strikes || []).map((s) => s.strike);
    return [...new Set(src)].filter((s) => s != null).sort((a, b) => b - a);
  }, [g, data]);

  const cellVal = (expiry, strike) => {
    const col = matrix[expiry];
    if (!col) return null;
    const v = col[strikeKey(strike)];
    return v === undefined ? null : v;
  };

  // Signed min/max across the whole matrix for the viridis scale
  const [minV, maxV] = useMemo(() => {
    let lo = 0, hi = 0;
    for (const e of expiries) {
      const col = matrix[e] || {};
      for (const k in col) {
        const v = col[k];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    return [lo, hi];
  }, [expiries, matrix]);

  // King cell: max |value| across the matrix
  const king = useMemo(() => {
    let best = null, bestAbs = 0;
    for (const e of expiries) {
      const col = matrix[e] || {};
      for (const k in col) {
        const a = Math.abs(col[k]);
        if (a > bestAbs) { bestAbs = a; best = { expiry: e, strikeKey: k }; }
      }
    }
    return best;
  }, [expiries, matrix]);

  // Spot row (closest strike to spot)
  const spotStrike = useMemo(() => {
    if (spot == null || !strikes.length) return null;
    let best = strikes[0], bestDist = Math.abs(strikes[0] - spot);
    for (let i = 1; i < strikes.length; i++) {
      const d = Math.abs(strikes[i] - spot);
      if (d < bestDist) { bestDist = d; best = strikes[i]; }
    }
    return best;
  }, [strikes, spot]);

  // % change vs previous refresh, per (expiry, strike). Computed in the effect
  // (once per new asof) and HELD in state — computing it in a useMemo raced the
  // snapshot update, so badges flashed for one render then recomputed to empty.
  const prevRef = useRef({ key: null, asof: null, matrix: null });
  const snapKey = `${ticker}|${gridKey}`;
  const [badges, setBadges] = useState({});

  useEffect(() => {
    if (!data?.asof) return;
    const prev = prevRef.current;
    if (prev.key === snapKey && prev.asof === data.asof) return;   // same payload — keep badges
    // Compute % change vs the previous snapshot of THIS ticker/view only.
    const out = {};
    if (prev.key === snapKey && prev.matrix) {
      for (const e of expiries) {
        const col = matrix[e] || {};
        const pcol = prev.matrix[e] || {};
        for (const k in col) {
          const p = pcol[k];
          if (p != null && p !== 0) {
            const pct = Math.round(((col[k] - p) / Math.abs(p)) * 100);
            if (pct !== 0) out[`${e}|${k}`] = Math.max(-999, Math.min(999, pct));
          }
        }
      }
    }
    setBadges(out);
    // Snapshot the current matrix for the next refresh's comparison.
    const snap = {};
    for (const e of expiries) snap[e] = { ...(matrix[e] || {}) };
    prevRef.current = { key: snapKey, asof: data.asof, matrix: snap };
  }, [expiries, matrix, snapKey, data]);

  if (!expiries.length || !strikes.length) {
    return (
      <div className="skylit-heatmap-empty">
        <span>No heatmap data available</span>
      </div>
    );
  }

  const range = maxV - minV;

  // Windowing (2026-09-03): slice the RENDERED rows only — King, spot,
  // and the viridis scale above always use the full matrix.
  let shownStrikes = strikes;
  if (windowRows != null && strikes.length > windowRows) {
    let center = strikes.indexOf(spotStrike);
    if (center === -1) center = Math.floor(strikes.length / 2);
    const half = Math.floor(windowRows / 2);
    let start = Math.max(0, Math.min(center - half, strikes.length - windowRows));
    shownStrikes = strikes.slice(start, start + windowRows);
  }

  return (
    <div className="skylit-heatmap-wrapper">
      <div className="skylit-heatmap-container">
        <table className={`trin-grid-table${density === "full" ? " density-full" : ""}`}>
          <thead>
            <tr>
              <th className="trin-th-strike">Strike</th>
              {expiries.map((e) => (
                <th key={e} className="trin-th-exp" title={e}>{fmtExpiry(e)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shownStrikes.map((strike) => {
              const isSpot = strike === spotStrike;
              const sk = strikeKey(strike);
              return (
                <tr key={strike} className="trin-row">
                  <td
                    className="trin-strike-cell"
                    onClick={() => onStrikeClick && onStrikeClick(strike)}
                  >
                    {isSpot ? (
                      <span className="trin-spot-chip">{fmtStrike(strike)}</span>
                    ) : (
                      <span className="trin-strike">{fmtStrike(strike)}</span>
                    )}
                  </td>
                  {expiries.map((e) => {
                    const v = cellVal(e, strike);
                    const has = v != null;
                    const t = has && range > 0 ? (v - minV) / range : 0.5;
                    const bright = has && t > 0.55;
                    const isKing = king && king.expiry === e && king.strikeKey === sk;
                    const pct = badges[`${e}|${sk}`];
                    return (
                      <td
                        key={e}
                        className={`trin-cell${isKing ? " trin-king" : ""}`}
                        style={{
                          background: has ? viridis(t) : "rgba(13,17,23,0.85)",
                          color: has ? (bright ? "#000" : "#fff") : "#3a4566",
                        }}
                        onClick={() => onCellClick && onCellClick(strike, e, v)}
                        title={`${strike} · ${e} · ${fmtK(v) || "$0"}`}
                      >
                        {pct != null && (
                          <span className={`trin-pct ${pct > 0 ? "up" : "down"}`}>
                            {pct > 0 ? "+" : ""}{pct}%
                          </span>
                        )}
                        <span className={isKing ? "trin-val-bold" : undefined}>
                          {fmtK(v)}
                          {isKing && <span className="trin-star">★</span>}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="trin-legend">
        <span className="trin-legend-label">{fmtK(minV) || "$0"}</span>
        <div className="trin-legend-bar" />
        <span className="trin-legend-label">{fmtK(maxV) || "$0"}</span>
        {shownStrikes.length < strikes.length && (
          <span className="trin-legend-window" data-testid="skylit-grid-window-note">
            Showing {shownStrikes.length} of {strikes.length} strikes · Expand for full grid
          </span>
        )}
      </div>
    </div>
  );
}

export default memo(SkylitHeatmapGrid);
