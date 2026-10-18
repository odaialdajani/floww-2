/**
 * StrikeConeBadge.jsx — STEAL-LIST #10
 *
 * Renders the implied-move strike cone from
 * GET http://localhost:8000/api/strike_cone/{ticker}?target_probs=0.16,0.30,0.70,0.84&target_deltas=0.16,0.30
 *
 * Visualization (top → bottom):
 *   1. SVG cone bands — outer (1σ, full 84% range) + inner (½σ, 40% range),
 *      with the spot marked via a dashed amber vertical line.
 *   2. Two sub-tiles below: 16Δ wing strikes + 30Δ wing strikes.
 *   3. Footer: magnitude in strikes either side of spot for 1σ and ½σ wings.
 *
 * Visual treatment mirrors `HeatseekerDashboard.jsx`'s slate palette
 * (text-slate-200, bg-slate-900/40, sky/rose/emerald/amber accents).
 *
 * Defensive degrade: any backend failure (timeout / 500 / unreachable)
 * shows an amber offline card, not a crash. Empty `prob_cones` or
 * missing spot falls back to "—" labels rather than rendering NaN SVG
 * coordinates (which would otherwise silently corrupt the cone).
 *
 * Distinct from `StrikeConeTile` inside `ConfluenceVelocityRow.jsx` —
 * this badge is the LARGE standalone panel that draws the cone shape;
 * the tile is the 5-up compact summary. Both can coexist on the same
 * dashboard.
 */

import React, { memo, useEffect, useState } from "react";
import { BACKEND_BASE } from "../../config/api";
import { fetchStudyJSON } from "./studyFetch";
import StudyErrorCard from "./StudyErrorCard";

const SIDE_BASE =
  process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;

function fmt(n, d = 0) {
  return n == null || !Number.isFinite(Number(n))
    ? "—"
    : Number(n).toFixed(d);
}

/** Build a safe [minK, maxK] domain even when the endpoint returns a
 *  degenerate / single-sided / fully empty range. Each branch is
 *  individualised rather than collapsing one-sided-but-valid cases
 *  into a synthetic (0, 1) box — that would mask an upstream warning
 *  case as "rendered fine". */
function safeRange(minK, maxK) {
  const lo = Number(minK);
  const hi = Number(maxK);
  const loOk = Number.isFinite(lo);
  const hiOk = Number.isFinite(hi);

  // Both invalid → synthetic (0, 1) box.
  if (!loOk && !hiOk) return { minK: 0, maxK: 1, range: 1 };

  // Single-side valid: anchor ±5 around whichever endpoint came back.
  // Preserves the real boundary instead of throwing it away.
  if (!loOk) return { minK: hi - 5, maxK: hi, range: 5 };
  if (!hiOk) return { minK: lo, maxK: lo + 5, range: 5 };

  // Both valid: degenerate (==) or happy path.
  if (lo === hi) return { minK: lo - 0.5, maxK: lo + 0.5, range: 1 };
  return { minK: lo, maxK: hi, range: hi - lo };
}

function StrikeConeBadge({ ticker = "SPY", expiries = 1 }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setErr(null);
    const qs = new URLSearchParams({
      target_probs: "0.16,0.30,0.70,0.84",
      target_deltas: "0.16,0.30",
      expiries: String(expiries),
    });
    fetchStudyJSON(
      `${SIDE_BASE}/api/strike_cone/${encodeURIComponent(ticker)}?${qs.toString()}`
    )
      .then((j) => {
        if (!cancelled) setData(j);
      })
      .catch((e) => {
        if (!cancelled) setErr(e);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, expiries]);

  if (err) {
    return (
      <StudyErrorCard
        title="Strike Cone"
        base={SIDE_BASE}
        error={err}
        testId="hs-strike-cone"
        className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3"
      />
    );
  }

  if (!data) {
    return (
      <div
        className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3 animate-pulse"
        data-testid="hs-strike-cone"
      >
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">
          Strike Cone · {ticker}
        </div>
        <div className="text-[10px] text-slate-400">solving…</div>
      </div>
    );
  }

  const prob_cones = Array.isArray(data.prob_cones) ? data.prob_cones : [];
  const delta_cones = Array.isArray(data.delta_cones) ? data.delta_cones : [];
  const outer16 = prob_cones[0]; // P=0.16 — supplies ±1σ wing strikes
  const inner30 = prob_cones[1]; // P=0.30 — supplies ±½σ wing strikes
  const delta16 = delta_cones[0]; // 16Δ — typical iron-condor far wing
  const delta30 = delta_cones[1]; // 30Δ — typical iron-condor short strike

  // Build a safe [minK, maxK] domain from the outer 1σ wing strikes,
  // then map every strike to a 0..100 SVG X coordinate.
  const { minK, maxK, range } = safeRange(
    outer16?.strike_below,
    outer16?.strike_above
  );
  const toX = (K) => {
    if (K == null || !Number.isFinite(Number(K))) return null;
    return Math.min(100, Math.max(0, ((Number(K) - minK) / range) * 100));
  };
  const xSpot = toX(data.spot);
  const xInnerLo = inner30?.strike_below != null ? toX(inner30.strike_below) : null;
  const xInnerHi = inner30?.strike_above != null ? toX(inner30.strike_above) : null;
  const innerWidth = xInnerLo != null && xInnerHi != null ? xInnerHi - xInnerLo : null;

  const move1s = data.spot != null && outer16?.strike_above != null
    ? outer16.strike_above - data.spot
    : null;
  const moveHalf = data.spot != null && inner30?.strike_above != null
    ? inner30.strike_above - data.spot
    : null;

  return (
    <div
      className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3"
      data-testid="hs-strike-cone"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
          <span className="text-[10px] uppercase tracking-widest font-bold text-slate-200">
            Strike Cone · {ticker}
          </span>
        </div>
        <span className="text-[9px] uppercase tracking-widest font-mono text-slate-400">
          {data.n_strikes ?? 0} strikes · {data.method || "linear_interp_bisect"}
        </span>
      </div>

      {/* SVG implied-move cone */}
      <div className="relative w-full">
        <svg
          viewBox="0 0 100 40"
          preserveAspectRatio="none"
          className="w-full h-[90px] overflow-visible"
        >
          {/* Outer 1σ band (84% range) — light sky fill */}
          <rect
            x="0"
            y="6"
            width="100"
            height="16"
            fill="rgba(56,189,248,0.10)"
            stroke="rgba(56,189,248,0.45)"
            strokeWidth="0.4"
          />
          {/* Inner ½σ band (40% range) — nested tighter fill */}
          {innerWidth != null && innerWidth > 0 && (
            <rect
              x={xInnerLo}
              y="6"
              width={innerWidth}
              height="16"
              fill="rgba(125,211,252,0.22)"
              stroke="rgba(186,230,253,0.7)"
              strokeWidth="0.5"
            />
          )}
          {/* Spot marker — dashed amber vertical */}
          {xSpot != null && (
            <line
              x1={xSpot}
              y1="2"
              x2={xSpot}
              y2="26"
              stroke="#fbbf24"
              strokeWidth="0.5"
              strokeDasharray="1.5,1.5"
            />
          )}
          {/* 1σ wing labels (at bottom of svg) */}
          <text
            x="0"
            y="34"
            fontSize="3.2"
            fill="#94a3b8"
            fontFamily="ui-monospace,monospace"
          >
            ${fmt(outer16?.strike_below, 0)}
          </text>
          <text
            x="100"
            y="34"
            fontSize="3.2"
            fill="#94a3b8"
            fontFamily="ui-monospace,monospace"
            textAnchor="end"
          >
            ${fmt(outer16?.strike_above, 0)}
          </text>
          {/* Spot label sits centred above the line, clamped inside the box */}
          {xSpot != null && (
            <text
              x={Math.max(15, Math.min(85, xSpot))}
              y="29"
              fontSize="3.0"
              fill="#fbbf24"
              fontFamily="ui-monospace,monospace"
              textAnchor="middle"
            >
              spot ${fmt(data.spot, 2)}
            </text>
          )}
        </svg>
      </div>

      {/* 16Δ / 30Δ wing sub-tiles */}
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] font-mono">
        <div className="bg-slate-900/40 rounded-md px-2 py-1">
          <div className="text-[8px] uppercase tracking-widest text-slate-500">
            16Δ wing
          </div>
          <div className="text-slate-300">
            <span className="text-rose-300">↓ ${fmt(delta16?.strike_below, 0)}</span>
            <span className="text-slate-500 mx-1">·</span>
            <span className="text-emerald-300">↑ ${fmt(delta16?.strike_above, 0)}</span>
          </div>
        </div>
        <div className="bg-slate-900/40 rounded-md px-2 py-1">
          <div className="text-[8px] uppercase tracking-widest text-slate-500">
            30Δ wing
          </div>
          <div className="text-slate-300">
            <span className="text-rose-300">↓ ${fmt(delta30?.strike_below, 0)}</span>
            <span className="text-slate-500 mx-1">·</span>
            <span className="text-emerald-300">↑ ${fmt(delta30?.strike_above, 0)}</span>
          </div>
        </div>
      </div>

      <div className="mt-2 text-[8px] text-slate-600 uppercase tracking-widest">
        ½σ wing {fmt(moveHalf, 1)}pt · 1σ wing {fmt(move1s, 1)}pt · interp on prob_above / prob_below / Δ
      </div>
    </div>
  );
}

export default memo(StrikeConeBadge);
