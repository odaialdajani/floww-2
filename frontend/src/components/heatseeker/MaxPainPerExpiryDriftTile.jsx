/**
 * MaxPainPerExpiryDriftTile.jsx
 *
 * HeatseekerDashboard Row 3 + Zenith steal-list band tile — multi-line SVG
 * chart showing the per-expiry max_pain_strike evolution across the last N
 * days. Fetches GET /api/max_pain_drift/{ticker}/per_expiry_history?days=30
 * (a sibling endpoint of the aggregate /api/max_pain_drift/{ticker} that
 * exposes one trajectory per listed expiry for the rendering polyline).
 *
 * Steal intent: peer pattern with `StrikeConeBadge.jsx` and
 * `OpportunityBadge.jsx` — same data-fetch lifecycle (useState + useEffect +
 * defensive degrade on missing rows), same slate palette, same
 * ``data-testid`` convention so jest pinning picks it up.
 *
 * Mount:
 *   - HeatseekerDashboard.jsx sub-section C, AFTER the existing
 *     ``MaxPainBadge`` (the OVERALL scalar readout). The rich tile and the
 *     at-a-glance tile complement each other.
 *   - (Removed from SkylitDashboard.jsx 2026-09-03 with the rest of the
 *     Solstice bottom band; served via Zenith + direct API use.)
 *
 * Color palette per the steal-list .md convention (8 hues, all -400):
 *   sky / emerald / amber / rose / purple / teal / violet / fuchsia.
 * The palette rotates for >8 listed expiries (rare — most chains cap at
 * 4-8 listed expiries in the scrollable window anyway).
 *
 * Edge cases (defensive degrade):
 *   - Empty ``expiries`` array → empty-state slate advising to run cron
 *     accumulate=true first.
 *   - Single data point per expiry → draw as a terminal dot only
 *     (polyline ``M`` breaks on <2 points).
 *   - Today spot missing → skip the spot reference line; polylines still
 *     render against strike.
 *   - <30 days of data → X-axis flexes to actual span (no rigid 30-day
 *     block).
 */

import React, { memo, useEffect, useState, useMemo, useCallback } from "react";
import { BACKEND_BASE } from "../../config/api";

// ─────────────────────────────────────────────────────────────────────
// Endpoint configuration
// ─────────────────────────────────────────────────────────────────────

const SIDE_BASE =
  process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;
const DEFAULT_DAYS = 30;

// ─────────────────────────────────────────────────────────────────────
// Color palette — 8 hues (Tailwind -400 variants) rotated on expiry
// index. Picked from the established steal-list palette to align with
// StrikeConeBadge / OpportunityBadge / IVMidBadge.
// ─────────────────────────────────────────────────────────────────────

const PALETTE = [
  // slate-on-slate tint for readability on the dark dashboard:
  //   stroke="#38bdf8"  marker-end="..."
  "stroke-sky-400",         // sky-400 (#38bdf8)
  "stroke-emerald-400",     // emerald-400 (#34d399)
  "stroke-amber-400",       // amber-400 (#fbbf24)
  "stroke-rose-400",        // rose-400 (#fb7185)
  "stroke-purple-400",      // purple-400 (#a78bfa)
  "stroke-teal-400",        // teal-400 (#2dd4bf)
  "stroke-violet-400",      // violet-400 (#8b5cf6)
  "stroke-fuchsia-400",     // fuchsia-400 (#e879f9)
];

const PALETTE_FILLED_FILLS = [
  "fill-sky-400",
  "fill-emerald-400",
  "fill-amber-400",
  "fill-rose-400",
  "fill-purple-400",
  "fill-teal-400",
  "fill-violet-400",
  "fill-fuchsia-400",
];

const PALETTE_FOOTER_TEXT = [
  "text-sky-300",
  "text-emerald-300",
  "text-amber-300",
  "text-rose-300",
  "text-purple-300",
  "text-teal-300",
  "text-violet-300",
  "text-fuchsia-300",
];

// ─────────────────────────────────────────────────────────────────────
// Utility helpers (pure-Python-style, no numpy dependency)
// ─────────────────────────────────────────────────────────────────────

function toXStr(dateObj, minMs, maxMs) {
  // Convert a date to an X-coordinate (string) on the chart's [0, 100] axis.
  if (!dateObj || maxMs === minMs) return 50; // mid-axis when no range
  const ms = new Date(dateObj).getTime();
  return ((ms - minMs) / (maxMs - minMs)) * 100;
}

function toYStr(strike, minStrike, maxStrike) {
  // Convert a strike to a Y-coordinate on the chart's [0, 40] axis with
  // 0 at TOP. Inverts so high strikes render near bottom.
  if (strike == null || maxStrike === minStrike) return 20;
  return ((maxStrike - strike) / (maxStrike - minStrike)) * 40;
}

function safeRange(minV, maxV) {
  if (minV == null || maxV == null || !Number.isFinite(minV) || !Number.isFinite(maxV)) {
    return { min: 0, max: 1 };
  }
  if (minV >= maxV) {
    const pad = Math.max(1, Math.abs(minV) * 0.005);
    return { min: minV - pad, max: maxV + pad };
  }
  return { min: minV, max: maxV };
}

// ─────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────

function MaxPainPerExpiryDriftTile({ ticker = "SPY", days = DEFAULT_DAYS }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const url =
      `${SIDE_BASE}/api/max_pain_drift/${encodeURIComponent(ticker)}` +
      `/per_expiry_history?days=${encodeURIComponent(Math.max(1, Math.min(days, 365)))}`;
    try {
      const r = await fetch(url);
      if (!r.ok) {
        setError(`HTTP ${r.status}`);
        setPayload(null);
        return;
      }
      const json = await r.json();
      setPayload(json);
      if (Array.isArray(json?.warnings) && json.warnings.length) {
        // Surface server-side warnings in dev (silent in prod — render
        // empty-state only if expiries is empty).
        if (!json?.expiries?.length) {
          // eslint-disable-next-line no-console
          console.warn(
            `MaxPainPerExpiryDriftTile(${ticker}): ${json.warnings.join("; ")}`
          );
        }
      }
    } catch (exc) {
      setError(exc?.message || String(exc));
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, [ticker, days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ── Derived scales (memoised so panning/rerender stays cheap) ─────
  const {
    expiries, xDomain, yDomain, todaySpot, hasData, nPoints,
  } = useMemo(() => {
    const expiries = Array.isArray(payload?.expiries) ? payload.expiries : [];
    // Filter: only entries with at least 1 history point survive.
    const filtered = expiries.filter((g) =>
      Array.isArray(g?.history) && g.history.length > 0
    );

    if (filtered.length === 0) {
      return {
        expiries: [],
        xDomain: { min: 0, max: 1 },
        yDomain: { min: 0, max: 1 },
        todaySpot: null,
        hasData: false,
        nPoints: 0,
      };
    }

    // Flatten all (date, strike, spot) tuples across per-expiry history,
    // plus the most-recent spot (right-edge marker).
    let minMs = Infinity;
    let maxMs = -Infinity;
    let minStrike = Infinity;
    let maxStrike = -Infinity;
    let totalPts = 0;
    let lastSpot = null;
    for (const g of filtered) {
      for (const pt of g.history) {
        const d = pt?.date ? new Date(pt.date).getTime() : NaN;
        const k = typeof pt?.strike === "number" ? pt.strike : NaN;
        if (Number.isFinite(d)) {
          if (d < minMs) minMs = d;
          if (d > maxMs) maxMs = d;
        }
        if (Number.isFinite(k)) {
          if (k < minStrike) minStrike = k;
          if (k > maxStrike) maxStrike = k;
        }
        // Use the most-recent spot (last point of any expiry) as today
        // proxy for the reference horizontal line.
        if (Number.isFinite(pt?.spot)) {
          lastSpot = pt.spot;
        }
        totalPts += 1;
      }
    }
    // Pad strike bounds by 1 strike on each side so the lines don't hit
    // the SVG edge.
    if (Number.isFinite(minStrike) && Number.isFinite(maxStrike)) {
      minStrike -= 1;
      maxStrike += 1;
    }
    return {
      expiries: filtered,
      xDomain: safeRange(Number.isFinite(minMs) ? minMs : 0,
                        Number.isFinite(maxMs) ? maxMs : 1),
      yDomain: safeRange(minStrike, maxStrike),
      todaySpot: lastSpot,
      hasData: totalPts > 0,
      nPoints: totalPts,
    };
  }, [payload]);

  // ── Hover state (line index + cursor-X) for the tooltip overlay ──
  const [hover, setHover] = useState({ idx: null, x: null, y: null });

  const onSvgMove = useCallback((evt) => {
    // Use the SVG coordinate space (viewBox-relative) so the cursor
    // position works regardless of the rendered card width.
    const tgt = evt.currentTarget;
    const rect = tgt.getBoundingClientRect();
    if (!rect || !rect.width) return;
    const xViewBox = ((evt.clientX - rect.left) / rect.width) * 100;
    const yViewBox = ((evt.clientY - rect.top) / rect.height) * 40;
    setHover({ idx: null, x: xViewBox, y: yViewBox });
  }, []);
  const onSvgLeave = useCallback(() => {
    setHover({ idx: null, x: null, y: null });
  }, []);

  // ── Empty/error/loading render states (panel shape consistent
  //    with peer badges: rounded slate, slate-700/30 border) ─────────
  return (
    <div
      className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3"
      data-testid="hs-max-pain-per-expiry-drift"
    >
      {/* Pulse-style header (peer convention) */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
          <h4 className="text-[11px] font-bold text-slate-200 uppercase tracking-wider">
            Max-Pain Drift · Per-Expiry
          </h4>
          <span className="text-[9px] text-slate-500 uppercase tracking-widest">
            {days}d window
          </span>
        </div>
        <div className="text-[10px] text-slate-400">
          {ticker}
        </div>
      </div>

      {/* Render branches */}
      {loading && (
        <div className="text-[10px] text-slate-500 italic py-3">
          Loading per-expiry history…
        </div>
      )}
      {!loading && error && (
        <div className="text-[10px] text-rose-400 italic py-3">
          fetch failed: {error}
        </div>
      )}
      {!loading && !error && !hasData && (
        <div className="text-[10px] text-slate-500 italic py-3">
          No per-expiry max_pain history yet — run cron{" "}
          <code className="text-slate-300">
            POST /api/max_pain_drift/{ticker}/accumulate?accumulate=true
          </code>{" "}
          first to populate the table.
        </div>
      )}

      {!loading && !error && hasData && (
        <>
          {/* SVG chart */}
          <svg
            viewBox="0 0 100 40"
            preserveAspectRatio="none"
            className="w-full h-[140px] overflow-visible block"
            onMouseMove={onSvgMove}
            onMouseLeave={onSvgLeave}
            aria-label="Max-pain strike evolution per listed expiry"
          >
            {/* Faint today-spot reference horizontal dashed line */}
            {todaySpot != null && (
              <line
                x1="0"
                y1={toYStr(todaySpot, yDomain.min, yDomain.max)}
                x2="100"
                y2={toYStr(todaySpot, yDomain.min, yDomain.max)}
                stroke="rgba(148, 163, 184, 0.35)"
                strokeWidth="0.25"
                strokeDasharray="1,1"
                vectorEffect="non-scaling-stroke"
              />
            )}

            {/* One polyline per expiry, with a terminal dot for the
                most-recent point. Lines with a single data point render
                as a small dot only (polyline M breaks otherwise). */}
            {expiries.map((g, idx) => {
              const colorText = PALETTE[idx % PALETTE.length];
              const colorFill = PALETTE_FILLED_FILLS[idx % PALETTE_FILLED_FILLS.length];
              const pts = g.history;
              if (pts.length === 0) return null;
              const linePath = pts
                .map((pt, i) => {
                  const x = toXStr(pt.date, xDomain.min, xDomain.max);
                  const y = toYStr(pt.strike, yDomain.min, yDomain.max);
                  return (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`);
                })
                .join(" ");
              const lastPt = pts[pts.length - 1];
              const lastX = toXStr(lastPt.date, xDomain.min, xDomain.max);
              const lastY = toYStr(lastPt.strike, yDomain.min, yDomain.max);
              return (
                <g key={g.expiry} className={colorText}>
                  {pts.length >= 2 && (
                    <path
                      d={linePath}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.1"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      vectorEffect="non-scaling-stroke"
                    />
                  )}
                  {/* Terminal dot (always drawn — works for the single-point
                      case too). */}
                  <circle
                    cx={lastX}
                    cy={lastY}
                    r="0.9"
                    className={colorFill}
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}

            {/* Right-edge "today" vertical marker */}
            <line
              x1="100"
              y1="0"
              x2="100"
              y2="40"
              stroke="rgba(251, 191, 36, 0.5)"
              strokeWidth="0.18"
              strokeDasharray="1,1"
              vectorEffect="non-scaling-stroke"
            />
          </svg>

          {/* Legend footer: first 8 expiries with their color + drift */}
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[9px] uppercase tracking-widest font-bold">
            {expiries.slice(0, 8).map((g, idx) => {
              const colorText = PALETTE_FOOTER_TEXT[idx % PALETTE_FOOTER_TEXT.length];
              const driftArrow = (g.drift_strike_Nd ?? 0) >= 0 ? "↑" : "↓";
              const driftAbs = Math.abs(g.drift_strike_Nd ?? 0).toFixed(2);
              return (
                <span
                  key={g.expiry}
                  className={`${colorText} inline-flex items-center gap-1`}
                >
                  <span className="opacity-70">{g.expiry}</span>
                  <span className="font-mono normal-case opacity-80">
                    {driftArrow}{driftAbs}pt · {g.n_points}d
                  </span>
                </span>
              );
            })}
            {expiries.length > 8 && (
              <span className="text-slate-500">
                +{expiries.length - 8} more
              </span>
            )}
          </div>

          {/* Hover tooltip overlay (positioned within the SVG bounds —
              only when cursor is inside the chart). */}
          {hover.x != null && hover.y != null && (
            <div
              className="absolute pointer-events-none text-[9px] text-slate-300 bg-slate-800/80 px-1.5 py-0.5 rounded border border-slate-700/50"
              style={{
                left: `${hover.x}%`,
                top: `${(hover.y / 40) * 100}%`,
                transform: "translate(-50%, -120%)",
              }}
            >
              x:{hover.x.toFixed(1)} y:{hover.y.toFixed(1)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default memo(MaxPainPerExpiryDriftTile);
