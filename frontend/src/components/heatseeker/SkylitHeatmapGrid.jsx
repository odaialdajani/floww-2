import React, { memo, useEffect, useMemo, useRef, useState } from "react";
import { shownMapStrikes } from "./shownMapStrikes";
import "./SolsticeWorkspace.css";

/**
 * SkylitHeatmapGrid — Solstice strike × expiry matrix.
 *
 * STRIKE rows (descending, sticky rail) × EXPIRY columns. Each cell is ONE
 * signed compact value of the active surface, colored on the viridis field
 * (purple negatives → indigo → cyan/green → yellow positives) over a
 * zero-anchored range. Colors describe exposure, never a forecast.
 *
 * R11 additions (no new calculation — every number is a backend cell):
 *  - precise spot line placed BETWEEN the bracketing strike rows (gold);
 *    the nearest-strike chip stays, so spot and selection never look alike
 *  - selected cell + selected strike outline; selected wall band on the rail
 *  - partial-cell marker from `cell_missing_delta` (contracts excluded for
 *    unknown delta), invalid-cell marker from `cell_invalid_delta`
 *    (contracts excluded for unusable delta readings) and a "δ unknown" /
 *    "δ invalid" state for cells with no usable input
 *  - optional aligned signed profile column (Raw under, adjusted over) that
 *    sums one surface over one declared expiry scope (see solsticeMetrics)
 *  - rows are memoised: a spot tick or selection change re-renders only the
 *    rows whose inputs changed, not the whole matrix
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

export function cellPalette(t) {
  const background = viridis(t);
  const rgb = background.match(/\d+/g).map(Number).map(value => {
    const s = value / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  const luminance = rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  const white = 1.05 / (luminance + 0.05), black = (luminance + 0.05) / 0.05;
  return {background, foreground: black > white ? "#000" : "#fff", contrast: Math.max(black, white)};
}

// en-US grouping without Intl per cell (same output as toLocaleString with
// one fraction digit; ~20× cheaper across a few thousand cells).
function group1(n) {
  const s = n.toFixed(1);
  const dot = s.indexOf(".");
  const int = dot === -1 ? s : s.slice(0, dot);
  const frac = dot === -1 ? "" : s.slice(dot);
  return int.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + frac;
}

export function fmtK(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  const sign = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a < 50) return `${sign}$0.0K`;
  if (a >= 1e9) return `${sign}$${group1(a / 1e6)}M`;
  return `${sign}$${group1(a / 1e3)}K`;
}

function strikeKey(s) {
  return String(s);
}
function fmtStrike(s) {
  return Number.isInteger(s) ? s.toFixed(s >= 1000 ? 0 : 1) : String(s);
}
function fmtExpiry(e) {
  // "2026-07-06" → "07-06"
  const m = /^\d{4}-(\d{2})-(\d{2})$/.exec(e);
  return m ? `${m[1]}-${m[2]}` : e;
}

const EMPTY = Object.freeze({});

function moveFocus(ev) {
  const keyMap = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
  const d = keyMap[ev.key];
  if (!d) return false;
  const td = ev.currentTarget;
  const r = Number(td.dataset.r);
  const c = Number(td.dataset.c);
  const body = td.closest("tbody");
  if (!body || !Number.isFinite(r) || !Number.isFinite(c)) return false;
  for (let step = 1; step < 200; step++) {
    const next = body.querySelector(`td[data-r="${r + d[0] * step}"][data-c="${c + d[1] * step}"]`);
    if (!next) break;
    if (next.tabIndex === 0) {
      ev.preventDefault();
      next.focus();
      return true;
    }
  }
  return false;
}

/** Signed profile bar pair: raw underneath (muted), adjusted over (bright). */
export function ProfileBars({ raw, adj, rawMax, adjMax, adjLabel, partial, invalid }) {
  const bar = (v, max, cls) => {
    if (v == null || !(max > 0)) return null;
    const w = Math.min(50, (Math.abs(v) / max) * 50);
    const style = v >= 0 ? { left: "50%", width: `${w}%` } : { left: `${50 - w}%`, width: `${w}%` };
    return <span className={`trin-prof-bar ${cls} ${v >= 0 ? "pos" : "neg"}`} style={style} />;
  };
  const title = [
    raw == null ? "Raw: no cell in scope (gap, not zero)" : `Raw ${fmtK(raw)}`,
    adjLabel ? (adj == null ? `${adjLabel}: unavailable (gap)` : `${adjLabel} ${fmtK(adj)}`) : null,
    partial ? `${partial} contract(s) excluded for unknown δ` : null,
    invalid ? `${invalid} contract(s) excluded for invalid δ (unusable reading)` : null,
  ].filter(Boolean).join(" · ");
  return (
    <span className="trin-prof" title={title}>
      <span className="trin-prof-zero" />
      {bar(raw, rawMax, "raw")}
      {adjLabel ? bar(adj, adjMax, "adj") : null}
      {partial ? <span className="trin-prof-partial" aria-hidden="true" /> : null}
      {invalid ? <span className="trin-prof-invalid" aria-hidden="true" /> : null}
    </span>
  );
}

const GridRow = memo(function GridRow({
  strike, r, cells, minV, range, kingExp, rowBadges, isSpot, spot, conc, concPct,
  selExp, selStrike, inWall, rowMiss, rowInv, prof, onCell, onStrike,
}) {
  const sk = strikeKey(strike);
  const spotOffset = isSpot && spot != null ? Number(spot) - strike : null;
  const spotTitle = isSpot && spot != null
    ? `Spot ${Number(spot).toFixed(2)} · nearest listed ${fmtStrike(strike)} (${spotOffset >= 0 ? "+" : ""}${spotOffset.toFixed(2)})`
    : null;
  return (
    <tr className={`trin-row${selStrike ? " trin-row-selected" : ""}`}>
      <td
        className={`trin-strike-cell${inWall ? " trin-wall-member" : ""}${selStrike ? " trin-strike-selected" : ""}`}
        onClick={onStrike ? () => onStrike(strike) : undefined}
        title={conc > 0 ? `Gross concentration ${fmtK(conc)} (${concPct}% of max)${inWall ? " · selected wall member" : ""}` : "No aggregated exposure for this strike"}
      >
        {isSpot ? (
          <span className="trin-spot-chip" title={spotTitle || undefined} data-testid="skylit-spot-chip">{fmtStrike(strike)}</span>
        ) : (
          <span className="trin-strike">{fmtStrike(strike)}</span>
        )}
        {conc > 0 && (
          <span className="trin-conc-bar" data-testid="skylit-conc-bar" style={{ width: `${Math.max(concPct, 4)}%` }} />
        )}
      </td>
      {cells.map(({ e, v }, c) => {
        const has = v != null && !Number.isNaN(v);
        const isZero = has && v === 0;
        const t = has && range > 0 ? (v - minV) / range : 0.5;
        const palette = has && !isZero ? cellPalette(t) : null;
        const isKing = kingExp === e;
        const pct = rowBadges[e];
        const miss = rowMiss ? (rowMiss[e] || 0) : 0;
        const inv = rowInv ? (rowInv[e] || 0) : 0;
        const partial = has ? miss : 0;
        const absent = has ? 0 : miss;
        const absentInv = has ? 0 : inv;
        const sel = selExp === e && selStrike;
        const txt = fmtK(v);
        const label = has
          ? `${strike} by ${e}, value ${txt || "$0"}${isKing ? ", largest cell" : ""}${partial ? `, partial: ${partial} excluded for unknown delta` : ""}${inv ? `, ${inv} excluded for invalid delta` : ""}${sel ? ", selected" : ""}`
          : `${strike} by ${e}, ${absent ? "delta unknown" : absentInv ? "delta invalid (unusable reading)" : "no data"}`;
        return (
          <td
            key={e}
            data-r={r}
            data-c={c}
            className={`trin-cell${isKing ? " trin-king" : ""}${!has ? " trin-missing" : ""}${isZero ? " trin-zero" : ""}${partial ? " trin-partial" : ""}${inv ? " trin-invalid" : ""}${sel ? " trin-selected" : ""}`}
            style={{
              background: has ? (palette?.background || "rgba(13,17,23,0.95)") : "rgba(13,17,23,0.85)",
              color: has ? (palette?.foreground || "#fff") : "#9baab9",
            }}
            onClick={has && onCell ? () => onCell(strike, e, v) : undefined}
            onKeyDown={(ev) => {
              if (moveFocus(ev)) return;
              if (!has) return;
              if (ev.key === "Enter" || ev.key === " ") {
                ev.preventDefault();
                if (onCell) onCell(strike, e, v);
              }
            }}
            tabIndex={has ? 0 : -1}
            role="gridcell"
            aria-selected={sel ? true : undefined}
            aria-label={label}
            title={has
              ? `${strike} · ${e} · ${txt || "$0"}${partial ? ` · partial (${partial} δ-unknown excluded)` : ""}${inv ? ` · ${inv} δ-invalid excluded (unusable reading)` : ""} (largest cell ★ = max |cell|)`
              : `${strike} · ${e} · ${absent ? `${absent} contract(s), delta unknown — not zero` : absentInv ? `${absentInv} contract(s), delta invalid — not zero` : "no data (not zero)"}`}
          >
            {pct != null && (
              <span className={`trin-pct ${pct > 0 ? "up" : "down"}`}>{pct > 0 ? "+" : ""}{pct}%</span>
            )}
            {absent ? <span className="trin-absent" aria-hidden="true">δ?</span> : null}
            {(!absent && absentInv) ? <span className="trin-absent" aria-hidden="true">δ!</span> : null}
            <span className={isKing ? "trin-val-bold" : undefined}>
              {has ? txt : !absent && !absentInv ? "—" : ""}
              {isKing && <span className="trin-star">★</span>}
            </span>
          </td>
        );
      })}
      {prof && (
        <td className="trin-profile-cell" data-testid="skylit-profile-cell" data-strike={sk}>
          <ProfileBars {...prof} />
        </td>
      )}
    </tr>
  );
});

function SkylitHeatmapGrid({
  data,
  spot = null,
  ticker = "",
  viewMode = "gex",
  // Metric overlay — raw | delta | session_delta_volume | activity | window.
  // Same snapshot, same wall identity; walls stay raw-locked.
  metric = "raw",
  onCellClick,
  onStrikeClick,
  // compact (in-frame) | full (expanded) | calendar (wide, quiet cells)
  density = "compact",
  // Window the rendered rows to N strikes centered on spot (or anchor).
  // null = render every strike (expanded overlay).
  windowRows = null,
  // Follow-spot pause: center the window on this strike instead of spot.
  anchorStrike = null,
  // F15: stable zero-anchor scale. `{min,max,locked:true}` = fixed range.
  scale = null,
  axes = null,
  onScaleReady,
  // R11 selection: {strike, expiry} — outline only, no value is stored here.
  selected = null,
  // R11 selected wall band on the strike rail: {low, high}
  wallBand = null,
  // R11 aligned profile: {raw, adj, adjLabel, scopeLabel, shared}
  profile = null,
  onScroll,
  scrollRef,
}) {
  const gridKey = GRID_BY_VIEW[viewMode] || "grid";

  const useOverlay = metric !== "raw" && (viewMode === "gex" || viewMode === "skylit");
  const overlay = useOverlay ? (data?.metrics?.grids || {})[metric] : null;
  // R6-1: a missing metric surface is UNAVAILABLE — never raw fallback.
  const overlayMissing = useOverlay && !(overlay && overlay.grid);
  const g = (!useOverlay || (overlay && overlay.grid)) ? ((overlay && overlay.grid ? overlay : data?.grid) || null) : null;
  const overlayReason = overlayMissing ? (overlay?.reason || "metric unavailable in this snapshot") : null;
  const namedSurface = !useOverlay && (viewMode === "vex" || viewMode === "charm") ? gridKey : null;
  const namedCells = namedSurface ? ((data?.grid || {})[namedSurface] || {}) : null;
  const surfaceMissing = !!namedSurface && !Object.keys(namedCells || {}).length;
  const surfaceMeta = viewMode === "vex" ? (data?.grid?.vex_meta || null) : null;
  const surfaceReason = surfaceMissing
    ? (surfaceMeta?.reason || surfaceMeta?.status || "surface unavailable in this snapshot")
    : null;
  const metricBasis = useOverlay && overlay && overlay.grid
    ? (metric === "delta" ? "OI_DELTA_WEIGHTED" : (overlay.exposure_basis || "VOLUME"))
    : (data?.exposure_basis || "OI");
  const expiries = useMemo(
    () => axes?.expiries ? [...axes.expiries] : (g?.expiries?.length ? [...g.expiries] : [...((data?.grid || {}).expiries || [])]),
    [g, data, axes]
  );
  const matrix = useMemo(() => (g?.[gridKey] || {}), [g, gridKey]);
  // Sparse per-cell coverage from the backend (only overlay sections carry it).
  // Missing (unknown δ) and invalid (unusable δ reading) stay distinct.
  const cellMissing = useMemo(() => (useOverlay && overlay?.cell_missing_delta) || EMPTY, [useOverlay, overlay]);
  const cellInvalid = useMemo(() => (useOverlay && overlay?.cell_invalid_delta) || EMPTY, [useOverlay, overlay]);

  const strikes = useMemo(() => {
    const src = axes?.strikes || (g?.strikes?.length
      ? g.strikes
      : (((data?.grid || {}).strikes || []).length
        ? data.grid.strikes
        : (data?.strikes || []).map((s) => s.strike)));
    return [...new Set(src)].filter((s) => s != null).sort((a, b) => b - a);
  }, [g, data, axes]);

  const [minV, maxV, scaleMode] = useMemo(() => {
    if (scale && Number.isFinite(scale.min) && Number.isFinite(scale.max) && scale.max > scale.min) {
      return [Math.min(scale.min, 0), Math.max(scale.max, 0), scale.locked ? "locked" : "fixed"];
    }
    let lo = 0, hi = 0;
    for (const e of expiries) {
      const col = matrix[e] || {};
      for (const k in col) {
        const v = col[k];
        if (v == null || Number.isNaN(v)) continue; // missing ≠ zero
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    return [lo, hi, "relative"];
  }, [expiries, matrix, scale]);

  const scaleLocked = !!(scale && scale.locked);
  useEffect(() => {
    if (!onScaleReady || scaleLocked) return;
    onScaleReady({ min: minV, max: maxV });
  }, [minV, maxV, onScaleReady, scaleLocked]);

  // King cell: max |value| across the matrix (largest CELL — the sidebar
  // owns strongest aggregate wall + nearest wall separately).
  const king = useMemo(() => {
    let best = null, bestAbs = 0;
    for (const e of expiries) {
      const col = matrix[e] || {};
      for (const k in col) {
        const v = col[k];
        if (v == null) continue;
        const a = Math.abs(v);
        // Deterministic tie: first expiry, then higher strike key order.
        if (a > bestAbs) { bestAbs = a; best = { expiry: e, strikeKey: k, scope: "cell" }; }
      }
    }
    return best;
  }, [expiries, matrix]);

  const spotStrike = useMemo(() => {
    if (spot == null || !strikes.length) return null;
    let best = strikes[0], bestDist = Math.abs(strikes[0] - spot);
    for (let i = 1; i < strikes.length; i++) {
      const d = Math.abs(strikes[i] - spot);
      if (d < bestDist) { bestDist = d; best = strikes[i]; }
    }
    return best;
  }, [strikes, spot]);

  // % change vs previous refresh, held in state; scope-keyed (F16).
  const prevRef = useRef({ key: null, asof: null, matrix: null });
  const scopeSig = `${(data?.expiries_used || []).join(",")}|${metricBasis}|${data?.mode || ""}|${data?.data_source || ""}`;
  const snapKey = `${ticker}|${gridKey}|${metric}|${scopeSig}`;
  const [badges, setBadges] = useState(EMPTY);

  useEffect(() => {
    if (!data?.asof) return;
    const prev = prevRef.current;
    if (prev.key === snapKey && prev.asof === data.asof) return;
    const out = {};
    if (prev.key === snapKey && prev.matrix) {
      for (const e of expiries) {
        const col = matrix[e] || {};
        const pcol = prev.matrix[e] || {};
        for (const k in col) {
          const p = pcol[k];
          if (p != null && p !== 0) {
            const pct = Math.round(((col[k] - p) / Math.abs(p)) * 100);
            if (pct !== 0) {
              (out[k] || (out[k] = {}))[e] = Math.max(-999, Math.min(999, pct));
            }
          }
        }
      }
    }
    setBadges(out);
    const snap = {};
    for (const e of expiries) snap[e] = { ...(matrix[e] || {}) };
    prevRef.current = { key: snapKey, asof: data.asof, matrix: snap };
  }, [expiries, matrix, snapKey, data]);

  const strikeGross = useMemo(() => {
    const rows = data?.strikes || [];
    const m = {};
    for (const r of rows) {
      const s = r?.strike;
      if (s == null) continue;
      m[s] = Math.abs(r.call_gex || 0) + Math.abs(r.put_gex || 0) || Math.abs(r.gex || 0);
    }
    return m;
  }, [data]);
  const maxStrikeGross = useMemo(() => Math.max(0, ...Object.values(strikeGross)), [strikeGross]);

  // Per-expiry header meta: calendar days left + |net cell| share (not gross).
  const expMeta = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let matrixAbsNet = 0;
    const cols = {};
    for (const e of expiries) {
      const col = matrix[e] || {};
      let absNet = 0;
      let n = 0;
      for (const k in col) {
        const v = col[k];
        if (v == null || Number.isNaN(v)) continue;
        absNet += Math.abs(v);
        n += 1;
      }
      cols[e] = { gross: absNet, absNet, n };
      matrixAbsNet += absNet;
    }
    const meta = {};
    for (const e of expiries) {
      const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(e);
      let daysLeft = null;
      if (m) {
        const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
        daysLeft = Math.round((d - today) / 86400000);
      }
      const share = matrixAbsNet > 0 ? cols[e].absNet / matrixAbsNet : null;
      meta[e] = { ...cols[e], daysLeft, share };
    }
    return { meta, matrixGross: matrixAbsNet, matrixAbsNet };
  }, [expiries, matrix]);
  const zeroDte = useMemo(
    () => expiries.filter((e) => expMeta.meta[e]?.daysLeft === 0),
    [expiries, expMeta]
  );

  // Row cell arrays for EVERY strike, stable while the matrix is unchanged,
  // so shifting the window or moving spot does not rebuild cells.
  const rowCells = useMemo(() => {
    const out = new Map();
    for (const s of strikes) {
      const k = strikeKey(s);
      out.set(s, expiries.map((e) => {
        const col = matrix[e];
        const v = col ? col[k] : undefined;
        return { e, v: v === undefined ? null : v };
      }));
    }
    return out;
  }, [strikes, expiries, matrix]);

  // Partial / absent (δ unknown) and invalid (δ unusable) cell maps keyed by strike key.
  const partialByRow = useMemo(() => {
    const partial = {};
    for (const e of Object.keys(cellMissing)) {
      const col = cellMissing[e] || {};
      for (const k of Object.keys(col)) {
        if (col[k] > 0) (partial[k] || (partial[k] = {}))[e] = col[k];
      }
    }
    return partial;
  }, [cellMissing]);
  const invalidByRow = useMemo(() => {
    const inv = {};
    for (const e of Object.keys(cellInvalid)) {
      const col = cellInvalid[e] || {};
      for (const k of Object.keys(col)) {
        if (col[k] > 0) (inv[k] || (inv[k] = {}))[e] = col[k];
      }
    }
    return inv;
  }, [cellInvalid]);

  const profRows = useMemo(() => {
    if (!profile || !profile.raw) return null;
    const out = {};
    const rawMax = profile.shared && profile.adj ? Math.max(profile.raw.maxAbs || 0, profile.adj.maxAbs || 0) : (profile.raw.maxAbs || 0);
    const adjMax = profile.shared ? rawMax : (profile.adj?.maxAbs || 0);
    for (const s of strikes) {
      const k = strikeKey(s);
      const raw = profile.raw.values[k];
      const adj = profile.adj ? profile.adj.values[k] : undefined;
      out[k] = {
        raw: raw === undefined ? null : raw,
        adj: adj === undefined ? null : adj,
        rawMax, adjMax,
        adjLabel: profile.adj ? profile.adjLabel : null,
        partial: profile.adj?.partial?.[k] || 0,
        invalid: profile.adj?.invalid?.[k] || 0,
      };
    }
    return out;
  }, [profile, strikes]);

  const shownRaw = shownMapStrikes(data, spot, windowRows, viewMode, metric, anchorStrike);
  const shownKey = shownRaw.join(",");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const shownStrikes = useMemo(() => shownRaw, [shownKey]);

  // Spot line position: between the two shown strikes that bracket spot.
  const spotLine = useMemo(() => {
    if (spot == null || !shownStrikes.length) return null;
    const sp = Number(spot);
    if (!Number.isFinite(sp)) return null;
    if (sp > shownStrikes[0]) return { at: -1, where: "above" };
    if (sp < shownStrikes[shownStrikes.length - 1]) return { at: shownStrikes.length, where: "below" };
    for (let i = 0; i < shownStrikes.length - 1; i++) {
      if (shownStrikes[i] >= sp && sp >= shownStrikes[i + 1]) {
        if (sp === shownStrikes[i]) return { at: i, where: "on" };
        if (sp === shownStrikes[i + 1]) return { at: i + 1, where: "on" };
        return { at: i, where: "between" };
      }
    }
    return { at: 0, where: "on" };
  }, [spot, shownStrikes]);

  // Hook order is fixed above; empty/unavailable states return after hooks.
  if ((!expiries.length || !strikes.length) && !overlayMissing) {
    return (
      <div className="skylit-heatmap-empty">
        <span>No heatmap data available</span>
      </div>
    );
  }

  if (overlayMissing) {
    return (
      <div className="skylit-heatmap-empty" data-testid="skylit-metric-unavailable">
        <span>Metric unavailable ({metric}) — {overlayReason}</span>
      </div>
    );
  }

  if (surfaceMissing) {
    return (
      <div className="skylit-heatmap-empty" data-testid="skylit-surface-unavailable">
        <span>{viewMode.toUpperCase()} unavailable — {surfaceReason}</span>
      </div>
    );
  }

  const range = maxV - minV;
  const selStrikeNum = selected && selected.strike != null ? Number(selected.strike) : null;
  const selExp = selected?.expiry || null;
  const wLo = wallBand && Number.isFinite(Number(wallBand.low)) ? Number(wallBand.low) : null;
  const wHi = wallBand && Number.isFinite(Number(wallBand.high)) ? Number(wallBand.high) : null;
  const nCols = expiries.length + 1 + (profRows ? 1 : 0);
  const spotRow = (key, where) => (
    <tr key={key} className={`trin-spot-rail trin-spot-${where}`} aria-hidden="true" data-testid="skylit-spot-line">
      <td colSpan={nCols}>
        <span className="trin-spot-rail-label">
          {where === "above" ? "▲ " : where === "below" ? "▼ " : ""}Spot {Number(spot).toFixed(2)}
          {where === "above" ? " · above view" : where === "below" ? " · below view" : ""}
        </span>
      </td>
    </tr>
  );

  const body = [];
  if (spotLine?.where === "above") body.push(spotRow("spot-above", "above"));
  shownStrikes.forEach((strike, r) => {
    const sk = strikeKey(strike);
    const conc = strikeGross[strike] || 0;
    const isSelStrike = selStrikeNum != null && strike === selStrikeNum;
    body.push(
      <GridRow
        key={strike}
        strike={strike}
        r={r}
        cells={rowCells.get(strike) || []}
        minV={minV}
        range={range}
        kingExp={king && king.strikeKey === sk ? king.expiry : null}
        rowBadges={badges[sk] || EMPTY}
        isSpot={strike === spotStrike}
        spot={strike === spotStrike ? spot : null}
        conc={conc}
        concPct={maxStrikeGross > 0 ? Math.round((conc / maxStrikeGross) * 100) : 0}
        selExp={isSelStrike ? selExp : null}
        selStrike={isSelStrike}
        inWall={wLo != null && wHi != null && strike >= wLo && strike <= wHi}
        rowMiss={partialByRow[sk] || null}
        rowInv={invalidByRow[sk] || null}
        prof={profRows ? profRows[sk] : null}
        onCell={onCellClick}
        onStrike={onStrikeClick}
      />
    );
    if (spotLine && spotLine.where === "between" && spotLine.at === r) body.push(spotRow("spot-between", "between"));
  });
  if (spotLine?.where === "below") body.push(spotRow("spot-below", "below"));

  const densityClass = density === "full" ? " density-full" : density === "calendar" ? " density-calendar" : "";
  return (
    <div className="skylit-heatmap-wrapper">
      <div className="skylit-heatmap-container" onScroll={onScroll} ref={scrollRef}>
        <table className={`trin-grid-table${densityClass}`} role="grid" aria-label={`${ticker} ${viewMode.toUpperCase()} ${metric} strike by expiry`}>
          <thead>
            <tr>
              <th className="trin-th-strike" title="Strike rail — bar shows gross-gamma concentration (|call|+|put|, no cancellation)">Strike</th>
              {expiries.map((e) => {
                const meta = expMeta.meta[e] || {};
                const dl = meta.daysLeft;
                const dlTxt = dl == null ? "date unknown" : dl === 0 ? "0DTE (expires today)" : dl > 0 ? `${dl}d left` : "expired";
                const shareTxt = meta.share != null ? ` · ${(meta.share * 100).toFixed(1)}% of sum |signed cells| (not raw gross)` : "";
                const isSelCol = selExp === e;
                return (
                  <th key={e} className={`trin-th-exp${isSelCol ? " trin-th-selected" : ""}`}
                    title={`${e} · ${dlTxt} · ${meta.n ?? 0} strikes covered${shareTxt}`}>
                    {fmtExpiry(e)}
                    {density === "calendar" && dl != null && <span className="trin-th-dte">{dl === 0 ? "0D" : `${dl}d`}</span>}
                  </th>
                );
              })}
              {profRows && (
                <th className="trin-th-profile" data-testid="skylit-profile-header"
                  title={`Signed strike profile · ${profile.scopeLabel || "declared scope"} · Raw underneath${profile.adj ? `, ${profile.adjLabel} over` : ""}${profile.adj && !profile.shared ? " (own scale)" : ""}. Gaps are missing data, not zero.`}>
                  <span className="trin-th-profile-title">Profile</span>
                  <span className="trin-th-profile-scope">{profile.scopeLabel}</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>{body}</tbody>
        </table>
      </div>
      <div className="trin-legend">
        <span className="trin-legend-label">{fmtK(minV) || "$0"}</span>
        <div className="trin-legend-bar" />
        <span className="trin-legend-label">{fmtK(maxV) || "$0"}</span>
        <span className="trin-legend-scale" title="Zero-anchored signed scale">
          {scaleMode === "locked" ? "locked scale · 0 anchored" : scaleMode === "fixed" ? "fixed scale · 0 anchored" : "relative scale · 0 anchored"}
        </span>
        <span className="trin-legend-basis" data-testid="skylit-grid-basis" title="Exposure basis for this overlay">
          {metricBasis}
        </span>
        {shownStrikes.length < strikes.length && (
          <span className="trin-legend-window" data-testid="skylit-grid-window-note">
            Showing {shownStrikes.length} of {strikes.length} strikes{anchorStrike != null ? " · follow paused" : ""} · Expand for full grid
          </span>
        )}
        {zeroDte.length > 0 && (
          <span
            className="trin-legend-0dte"
            data-testid="skylit-grid-0dte"
            title="Share of sum |signed cells| in today-expiring columns (not raw gross; structural context, not a signal)"
          >
            0DTE {zeroDte.map((e) => fmtExpiry(e)).join(", ")}:{" "}
            {zeroDte.map((e) => {
              const share = expMeta.meta[e]?.share;
              return `${fmtExpiry(e)} ${share != null ? (share * 100).toFixed(1) + "%" : "—"}`;
            }).join(" · ")}
          </span>
        )}
      </div>
    </div>
  );
}

export default memo(SkylitHeatmapGrid);
