/**
 * MaxPainBadge.jsx — STEAL-LIST #9 (base max-pain per-expiry panel)
 *
 * Renders the per-expiry max-pain strikes + overall pin strike from
 * GET http://localhost:8000/api/max_pain/{ticker}.
 *
 * Distinct from MaxPainDriftTile in ConfluenceVelocityRow.jsx which
 * consumes /api/max_pain_drift/ — this badge shows the static
 * per-expiry pin strikes + overall pin magnet, NOT the daily drift.
 *
 * Visual tier matches the HeatseekerDashboard subtle panel aesthetic
 * (Tailwind + dark slate, mono numerics, tiny labels).
 */

import React, { memo, useEffect, useState } from "react";
import { BACKEND_BASE } from "../../config/api";
import { fetchStudyJSON } from "./studyFetch";
import StudyErrorCard from "./StudyErrorCard";

const SIDE_BASE = process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;

function fmt(n, d = 0) {
  return n == null ? "—" : Number(n).toFixed(d);
}

function MaxPainBadge({ ticker = "SPY", expiries = 8 }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setErr(null);
    const qs = new URLSearchParams({ expiries: String(expiries) });
    fetchStudyJSON(
      `${SIDE_BASE}/api/max_pain/${encodeURIComponent(ticker)}?${qs.toString()}`
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
        title="Max-Pain"
        base={SIDE_BASE}
        error={err}
        testId="hs-max-pain"
        className="panel p-3 rounded-xl border border-amber-500/20 bg-amber-500/5"
        hint={<>start :8000, or sidecar: <code>cd backend && python -m services.steal_three_server</code></>}
      />
    );
  }

  if (!data) {
    return (
      <div
        className="panel p-3 rounded-xl border border-slate-700/30 bg-slate-900/40 animate-pulse"
        data-testid="hs-max-pain"
      >
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">
          Max-Pain · {ticker}
        </div>
        <div className="text-[10px] text-slate-400">computing…</div>
      </div>
    );
  }

  const overallStrike = data?.overall?.strike;
  const spot = data?.spot;
  const distPct =
    overallStrike != null && spot != null
      ? ((overallStrike - spot) / spot) * 100
      : null;
  const distColor =
    distPct == null
      ? "text-slate-400"
      : Math.abs(distPct) < 1.0
      ? "text-emerald-400"   // close to spot — pin likely
      : distPct > 0
      ? "text-amber-400"     // above spot — pull-up magnet
      : "text-rose-400";     // below spot — pull-down magnet

  const rows = Array.isArray(data?.rows) ? data.rows.slice(0, 3) : [];

  return (
    <div
      className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3"
      data-testid="hs-max-pain"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] uppercase tracking-widest font-bold text-slate-200">
            Max-Pain · {ticker}
          </span>
        </div>
        <span className="text-[9px] uppercase tracking-widest font-mono text-slate-400">
          PIN MAGNET
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="bg-slate-900/40 rounded-md px-2 py-1.5">
          <div className="text-[8px] uppercase tracking-widest text-slate-500">Overall Strike</div>
          <div className="text-base font-bold mono text-emerald-400">
            {overallStrike != null ? `$${fmt(overallStrike, 0)}` : "—"}
          </div>
        </div>
        <div className="bg-slate-900/40 rounded-md px-2 py-1.5">
          <div className="text-[8px] uppercase tracking-widest text-slate-500">Spot</div>
          <div className="text-base font-bold mono text-slate-200">
            {spot != null ? `$${fmt(spot, 2)}` : "—"}
          </div>
        </div>
        <div className="bg-slate-900/40 rounded-md px-2 py-1.5">
          <div className="text-[8px] uppercase tracking-widest text-slate-500">Distance</div>
          <div className={`text-base font-bold mono ${distColor}`}>
            {distPct != null ? `${distPct > 0 ? "+" : ""}${distPct.toFixed(2)}%` : "—"}
          </div>
        </div>
      </div>

      {rows.length > 0 && (
        <div className="mt-2">
          <div className="text-[8px] uppercase tracking-widest text-slate-500 mb-1">
            Per-expiry pin strikes (top {rows.length})
          </div>
          <ul className="space-y-0.5">
            {rows.map((r, i) => (
              <li
                key={`${r.expiry}-${i}`}
                className="flex justify-between text-[10px] mono"
              >
                <span className="text-slate-400">{r.expiry || "—"}</span>
                <span className="text-emerald-300">
                  {r.max_pain_strike != null ? `$${fmt(r.max_pain_strike, 0)}` : "—"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-2 text-[8px] text-slate-600 uppercase tracking-widest">
        {data.expiries_scanned != null
          ? `${data.expiries_scanned} expiries scanned`
          : "—"}
      </div>
    </div>
  );
}

export default memo(MaxPainBadge);