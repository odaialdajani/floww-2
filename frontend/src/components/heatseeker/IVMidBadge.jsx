/**
 * IVMidBadge.jsx — STEAL-TOP-3 RANK #5
 *
 * Cross-checks yfinance's stale last-price IV against the clean
 * Newton-bisection solve on the bid/ask mid. Lists each ATM-ish strike
 * with yfinance_iv vs solved_iv and the round-trip residual.
 *
 * Endpoint: GET http://127.0.0.1:8001/api/iv_mid/{ticker}
 */

import React, { memo, useEffect, useState } from "react";
import { BACKEND_BASE } from "../../config/api";
import { fetchStudyJSON } from "./studyFetch";
import StudyErrorCard from "./StudyErrorCard";

const SIDE_BASE = process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;
const SOLVED_IV_NULL = 0.0;

function fmtPct(n) {
  return n == null ? "—" : `${(Number(n) * 100).toFixed(2)}%`;
}
function fmt(n, d = 4) {
  return n == null ? "—" : Number(n).toFixed(d);
}

function IVMidBadge({ ticker = "SPY", width = 6 }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setErr(null);
    const qs = new URLSearchParams({ width: String(width) });
    fetchStudyJSON(`${SIDE_BASE}/api/iv_mid/${encodeURIComponent(ticker)}?${qs.toString()}`)
      .then((j) => { if (!cancelled) setData(j); })
      .catch((e) => { if (!cancelled) setErr(e); });
    return () => { cancelled = true; };
  }, [ticker, width]);

  if (err) {
    return (
      <StudyErrorCard
        title="IV-Mid"
        base={SIDE_BASE}
        error={err}
        testId="hs-iv-mid"
        className="panel p-3 rounded-xl border border-amber-500/20 bg-amber-500/5"
      />
    );
  }

  if (!data) {
    return (
      <div className="panel p-3 rounded-xl border border-slate-700/30 bg-slate-900/40 animate-pulse">
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">IV-Mid · {ticker}</div>
        <div className="text-[10px] text-slate-400">solving…</div>
      </div>
    );
  }

  const rows = data.rows || [];
  const avgDelta = rows.length
    ? rows.reduce((a, r) => a + (Math.abs(r.iv_delta ?? 0)), 0) / rows.length
    : 0;
  const avgRt = rows.length
    ? rows.reduce((a, r) => a + Math.abs(r.round_trip_diff ?? 0), 0) / rows.length
    : 0;

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3" data-testid="hs-iv-mid">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
          <span className="text-[10px] uppercase tracking-widest font-bold text-slate-200">
            IV-Mid · {ticker}
          </span>
        </div>
        <span className="text-[9px] uppercase tracking-widest font-mono text-slate-400">
          avg Δ {fmt(avgDelta * 100, 2)} pts  ·  mean |rt| {fmt(avgRt * 100, 3)}¢
        </span>
      </div>

      <div className="overflow-auto max-h-48">
        <table className="w-full text-[10px] font-mono">
          <thead className="text-[8px] uppercase tracking-widest text-slate-500 border-b border-slate-700/30">
            <tr>
              <th className="text-left py-1 px-1">Type</th>
              <th className="text-right py-1 px-1">Strike</th>
              <th className="text-right py-1 px-1">Mid</th>
              <th className="text-right py-1 px-1">Y! IV</th>
              <th className="text-right py-1 px-1">Solved</th>
              <th className="text-right py-1 px-1">Δ</th>
              <th className="text-right py-1 px-1">|rt|</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.strike}-${r.kind}-${i}`} className="border-b border-slate-800/40">
                <td className="py-1 px-1 uppercase text-[9px] tracking-widest text-slate-400">{r.kind}</td>
                <td className="py-1 px-1 text-right text-slate-200">${fmt(r.strike, 0)}</td>
                <td className="py-1 px-1 text-right text-slate-300">{fmt(r.mid, 2)}</td>
                <td className="py-1 px-1 text-right text-slate-500">{fmtPct(r.yfinance_iv)}</td>
                <td className="py-1 px-1 text-right text-purple-300 font-bold">
                  {r.solved_iv === SOLVED_IV_NULL
                    ? <span className="text-amber-300">INVALID</span>
                    : fmtPct(r.solved_iv)}
                </td>
                <td className={`py-1 px-1 text-right ${(r.iv_delta ?? 0) > 0.005 ? "text-emerald-300" : (r.iv_delta ?? 0) < -0.005 ? "text-rose-300" : "text-slate-500"}`}>
                  {r.solved_iv === SOLVED_IV_NULL || r.iv_delta == null
                    ? "—"
                    : `${r.iv_delta > 0 ? "+" : ""}${(r.iv_delta * 100).toFixed(1)}pt`}
                </td>
                <td className="py-1 px-1 text-right text-slate-500">
                  {r.round_trip_diff == null ? "—" : `${fmt(r.round_trip_diff * 100, 2)}¢`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-[8px] text-slate-600 uppercase tracking-widest">
        expiry {data.expiry || "—"} · T={fmt(data.T_years, 3)}y · endpoint rt diff stable
      </div>
    </div>
  );
}

export default memo(IVMidBadge);
