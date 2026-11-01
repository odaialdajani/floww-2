// @ts-nocheck
import React, { useState, useEffect } from "react";
import { fmtAbs } from "../lib/helpers";
import { API } from "../config/api";

// API imported from config/api.js

export function DashboardSummary({ ticker, spot }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    let pending = false, controller = null;
    setSummary(null);
    const fetchSummary = async () => {
      if (pending) return;
      pending = true;
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 45000);
      setLoading(true);
      try {
        const r = await fetch(`${API}/heatmap/${ticker}?expiries=4&mode=day`, {signal:controller.signal});
        if (!r.ok) throw new Error("Summary unavailable");
        if (!cancelled) {
          const data = await r.json();
          if (cancelled) return;
          const rawRegime = data.nodes?.regime;
          const rawNetGex = data.nodes?.total_gex;
          setSummary({
            ticker: data.ticker,
            spot: data.spot,
            regime: typeof rawRegime === "string" && rawRegime.trim() ? rawRegime.trim().toUpperCase() : "UNKNOWN",
            gamma_flip: data.gamma_flip?.gamma_flip || data.nodes?.gamma_flip,
            net_gex: Number.isFinite(rawNetGex) ? rawNetGex : null,
            call_wall: data.gamma_flip?.call_wall,
            put_wall: data.gamma_flip?.put_wall,
            max_pain: data.nodes?.max_pain,
            alert_count: data.nodes?.alerts?.length || 0,
            high_priority: 0,
            timestamp: data.asof,
          });
        }
      } catch (e) {
        if (!cancelled) setSummary(null);
      } finally {
        clearTimeout(timeout);
        pending = false;
        if (!cancelled) setLoading(false);
      }
    };
    fetchSummary();
    const id = setInterval(fetchSummary, 30000);
    return () => { cancelled = true; controller?.abort(); clearInterval(id); };
  }, [ticker]);

  if (loading && !summary) {
    return (
      <div className="panel-2 p-2">
        <div className="label mb-1">Dashboard</div>
        <div className="text-[10px] text-slate-500 flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-slate-600 animate-pulse" />
          Loading dashboard…
        </div>
      </div>
    );
  }

  if (!summary) return (
    <div className="panel-2 p-2">
      <div className="label mb-1">Dashboard</div>
      <div className="text-[10px] text-slate-500">No dashboard data available</div>
    </div>
  );

  const safeTimestamp = summary?.timestamp != null ? new Date(summary.timestamp).toLocaleTimeString() : "—";
  const regime = String(summary?.regime || "UNKNOWN").toUpperCase();
  const isPositive = regime === "POSITIVE";
  const isNegative = regime === "NEGATIVE";
  const regimeColor = isPositive ? "text-emerald-400" : isNegative ? "text-rose-400" : "text-slate-400";
  const regimeBg = isPositive ? "bg-emerald-500/10 border-emerald-500/20" : isNegative ? "bg-rose-500/10 border-rose-500/20" : "bg-slate-800/50 border-slate-700/50";
  const regimeIcon = isPositive ? "🟢" : isNegative ? "🔴" : "⚪";
  const regimeLabel = isPositive ? "POSITIVE GAMMA" : isNegative ? "NEGATIVE GAMMA" : regime === "UNKNOWN" ? "UNKNOWN" : `${regime} GAMMA`;
  const netGex = summary?.net_gex;
  const hasNetGex = Number.isFinite(netGex);
  const netGexColor = hasNetGex ? (netGex >= 0 ? "text-emerald-400" : "text-rose-400") : "text-slate-400";
  const alertCount = summary?.alert_count || 0;
  const highPriority = summary?.high_priority || 0;

  return (
    <div className="panel-2 p-2">
      <div className="label mb-1">Dashboard</div>

      <div className={`rounded px-2 py-1.5 border mb-1.5 ${regimeBg}`}>
        <div className="flex justify-between items-center">
          <div className="text-[10px] font-bold">
            {regimeIcon} <span className={regimeColor}>{regimeLabel}</span>
          </div>
          <div className="text-[9px] text-slate-400">
            Spot: {fmtAbs(spot || summary?.spot)}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1 mb-1.5">
        <div className="bg-slate-800/50 rounded px-2 py-1">
          <div className="text-[8px] text-slate-500">Gamma Flip</div>
          <div className="text-[10px] font-bold text-amber-400">{fmtAbs(summary?.gamma_flip)}</div>
        </div>
        <div className="bg-slate-800/50 rounded px-2 py-1">
          <div className="text-[8px] text-slate-500">Net GEX</div>
          <div className={`text-[10px] font-bold ${netGexColor}`} title={hasNetGex ? undefined : "Net GEX unavailable"}>
            {hasNetGex ? `${netGex >= 0 ? "+" : ""}${fmtAbs(netGex)}` : "—"}
          </div>
        </div>
        <div className="bg-slate-800/50 rounded px-2 py-1">
          <div className="text-[8px] text-slate-500">Call Wall</div>
          <div className="text-[10px] font-bold text-sky-400">{fmtAbs(summary?.call_wall)}</div>
        </div>
        <div className="bg-slate-800/50 rounded px-2 py-1">
          <div className="text-[8px] text-slate-500">Put Wall</div>
          <div className="text-[10px] font-bold text-orange-400">{fmtAbs(summary?.put_wall)}</div>
        </div>
      </div>

      {alertCount > 0 && (
        <div className={`rounded px-2 py-1 border ${highPriority > 0 ? "bg-rose-500/10 border-rose-500/20" : "bg-amber-500/10 border-amber-500/20"}`}>
          <div className="flex justify-between items-center">
            <div className="text-[9px] font-bold">
              {highPriority > 0 ? "🔴" : "🟡"} {alertCount} Active Alert{alertCount > 1 ? "s" : ""}
            </div>
            {highPriority > 0 && (
              <div className="text-[8px] text-rose-400">{highPriority} HIGH</div>
            )}
          </div>
        </div>
      )}

      <div className="text-[8px] text-slate-600 mt-1 text-right">
        {safeTimestamp}
      </div>
    </div>
  );
}
