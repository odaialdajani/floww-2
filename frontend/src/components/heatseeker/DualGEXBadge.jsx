/**
 * DualGEXBadge.jsx — STEAL-TOP-3 RANK #1
 *
 * Renders the activity-ratio badge + dual-GEX series from
 * GET {BACKEND_BASE}/api/dual_gex/{ticker} (mounted steal_three route on
 * :8000 by default; REACT_APP_STEAL_THREE_BASE only to point at the :8001
 * dev sidecar explicitly).
 *
 * Visual tier matches the HeatseekerDashboard subtle panel aesthetic
 * (Tailwind + dark slate, mono numerics, tiny labels).
 */

import React, { memo, useEffect, useState } from "react";
import { BACKEND_BASE } from "../../config/api";

const SIDE_BASE = process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;

const BADGE_TONE = {
  live:   { fg: "text-rose-300",   bg: "rgba(244,63,94,0.10)",   border: "rgba(244,63,94,0.30)",   label: "LIVE:   flow ≥ structure" },
  active: { fg: "text-amber-300",  bg: "rgba(251,191,36,0.10)",  border: "rgba(251,191,36,0.30)",  label: "ACTIVE: flow ≈ structure" },
  quiet:  { fg: "text-emerald-300", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.25)", label: "QUIET:  structure dominates" },
};

const numFmt = (n, suffix = "") =>
  n == null ? "—" : `${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;

function DualGEXBadge({ ticker = "SPY" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setErr(null);
    fetch(`${SIDE_BASE}/api/dual_gex/${encodeURIComponent(ticker)}`)
      .then((r) => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((j) => { if (!cancelled) setData(j); })
      .catch((e) => { if (!cancelled) setErr(e.message || String(e)); });
    return () => { cancelled = true; };
  }, [ticker]);

  if (err) {
    return (
      <div className="panel p-3 rounded-xl border border-amber-500/20 bg-amber-500/5">
        <div className="text-[10px] uppercase tracking-widest text-amber-300 font-bold mb-1">Dual-GEX · offline</div>
        <div className="text-[10px] text-amber-200/80">backend @ {SIDE_BASE} unreachable → {err}</div>
        <div className="text-[9px] text-amber-200/60 mt-1">start :8000, or sidecar: <code>cd backend && python -m services.steal_three_server</code></div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="panel p-3 rounded-xl border border-slate-700/30 bg-slate-900/40 animate-pulse">
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">Dual-GEX · {ticker}</div>
        <div className="text-[10px] text-slate-400">fetching…</div>
      </div>
    );
  }

  const tone = BADGE_TONE[data.activity_badge] || BADGE_TONE.quiet;
  const ratio = data.activity_ratio ?? 0;

  return (
    <div
      className="rounded-xl border p-3"
      style={{ background: tone.bg, borderColor: tone.border }}
      data-testid="hs-dual-gex"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${tone.fg.replace("text-", "bg-")} animate-pulse`} />
          <span className={`text-[10px] uppercase tracking-widest font-bold ${tone.fg}`}>
            Dual-GEX · {ticker}
          </span>
        </div>
        <span className={`text-[9px] font-mono ${tone.fg}`}>{(data.activity_badge || "quiet").toUpperCase()}</span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="bg-slate-900/40 rounded-md px-2 py-1.5">
          <div className="text-[8px] uppercase tracking-widest text-slate-500">Activity Ratio</div>
          <div className={`text-base font-bold mono ${tone.fg}`}>{ratio.toFixed(2)}×</div>
        </div>
        <div className="bg-slate-900/40 rounded-md px-2 py-1.5">
          <div className="text-[8px] uppercase tracking-widest text-slate-500">GEX (OI)</div>
          <div className="text-sm font-bold mono text-slate-200">{numFmt((data.positive_gex_oi ?? 0) / 1e6)}M</div>
        </div>
        <div className="bg-slate-900/40 rounded-md px-2 py-1.5">
          <div className="text-[8px] uppercase tracking-widest text-slate-500">GEX (Vol)</div>
          <div className="text-sm font-bold mono text-slate-200">{numFmt((data.positive_gex_volume ?? 0) / 1e6)}M</div>
        </div>
      </div>

      <div className="mt-2 text-[9px] text-slate-500">{tone.label}</div>
      {data.note && (
        <div className="mt-1 text-[8px] text-slate-600 italic">{data.note}</div>
      )}
    </div>
  );
}

export default memo(DualGEXBadge);
