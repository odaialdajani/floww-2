/**
 * WheelIncomeScreenerPanel.jsx — STEAL-TOP-3 RANK #3
 *
 * Renders the CSP / covered-call ranked table from
 * GET http://127.0.0.1:8001/api/screener/income.
 * Tabs between puts and calls; sortable by ARR; respects filters.
 */

import React, { memo, useEffect, useMemo, useState } from "react";
import { BACKEND_BASE } from "../../config/api";

const SIDE_BASE = process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;
const DEFAULT_FILTERS = { min_iv: 0.0, min_volume: 10, min_dte: 7, max_dte: 45, top: 25 };

function fmt(n, digits = 2) {
  return n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function PillFilter({ label, value, onChange, hint, type = "number" }) {
  return (
    <label className="flex flex-col gap-0.5 text-[9px] uppercase tracking-widest text-slate-400">
      <span>{label}</span>
      <input
        type={type}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        className="bg-slate-900/60 border border-slate-700/40 rounded-md text-[10px] font-mono text-slate-200 px-2 py-1 focus:border-sky-500/60 focus:outline-none"
        placeholder={hint || ""}
        style={{ width: "5.5rem" }}
      />
    </label>
  );
}

function WheelIncomeScreenerPanel({ ticker = "SPY" }) {
  const [tab, setTab] = useState("put"); // "put" | "call"
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setErr(null);
    setData(null);
    const qs = new URLSearchParams({
      symbol: ticker,
      side: "both",
      min_iv: String(filters.min_iv ?? 0),
      min_volume: String(filters.min_volume ?? 0),
      min_dte: String(filters.min_dte ?? 7),
      max_dte: String(filters.max_dte ?? 45),
      top: String(filters.top ?? 25),
    });
    fetch(`${SIDE_BASE}/api/screener/income?${qs.toString()}`)
      .then((r) => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((j) => { if (!cancelled) setData(j); })
      .catch((e) => { if (!cancelled) setErr(e.message || String(e)); });
    return () => { cancelled = true; };
  }, [ticker, filters.min_iv, filters.min_volume, filters.min_dte, filters.max_dte, filters.top]);

  const rows = useMemo(() => {
    if (!data) return [];
    return tab === "call" ? (data.calls || []) : (data.puts || []);
  }, [data, tab]);

  if (err) {
    return (
      <div className="panel p-3 rounded-xl border border-amber-500/20 bg-amber-500/5">
        <div className="text-[10px] uppercase tracking-widest text-amber-300 font-bold mb-1">Wheel · offline</div>
        <div className="text-[10px] text-amber-200/80">backend @ {SIDE_BASE} unreachable → {err}</div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3" data-testid="hs-wheel-income">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
          <span className="text-[10px] uppercase tracking-widest font-bold text-slate-200">
            Wheel · {ticker} · Premium Income
          </span>
        </div>
        <div className="flex bg-slate-900/60 rounded-md border border-slate-700/30 p-0.5">
          {["put", "call"].map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-[9px] px-2 py-1 rounded-sm uppercase tracking-widest font-bold transition-colors ${
                tab === t ? "bg-sky-500/20 text-sky-300" : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {t === "put" ? "CSP" : "CC"}
            </button>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-3">
        <PillFilter label="Min IV"     value={filters.min_iv}     onChange={(v) => setFilters({ ...filters, min_iv: v })} />
        <PillFilter label="Min Vol"    value={filters.min_volume} onChange={(v) => setFilters({ ...filters, min_volume: v })} />
        <PillFilter label="Min DTE"    value={filters.min_dte}    onChange={(v) => setFilters({ ...filters, min_dte: v })} />
        <PillFilter label="Max DTE"    value={filters.max_dte}    onChange={(v) => setFilters({ ...filters, max_dte: v })} />
        <PillFilter label="Top N"      value={filters.top}        onChange={(v) => setFilters({ ...filters, top: v })} />
      </div>

      {/* Table */}
      <div className="overflow-auto max-h-72">
        <table className="w-full text-[10px] font-mono">
          <thead className="text-[8px] uppercase tracking-widest text-slate-500 border-b border-slate-700/30">
            <tr>
              <th className="text-left py-1 px-1">Strike</th>
              <th className="text-left py-1 px-1">DTE</th>
              <th className="text-right py-1 px-1">Mid</th>
              <th className="text-right py-1 px-1">IV</th>
              <th className="text-right py-1 px-1">Vol</th>
              {tab === "put"
                ? <th className="text-right py-1 px-1">BE ↓%</th>
                : <th className="text-right py-1 px-1">OTM%</th>}
              <th className="text-right py-1 px-1">ARR %</th>
            </tr>
          </thead>
          <tbody>
            {!data && (
              <tr><td colSpan="7" className="py-3 text-center text-slate-500">fetching…</td></tr>
            )}
            {data && rows.length === 0 && (
              <tr><td colSpan="7" className="py-3 text-center text-slate-500">no candidates match filters</td></tr>
            )}
            {rows.map((r, i) => (
              <tr key={`${r.strike}-${r.expiry}-${i}`} className="border-b border-slate-800/40 hover:bg-slate-800/20">
                <td className="py-1 px-1 text-slate-100">${fmt(r.strike, 0)}</td>
                <td className="py-1 px-1 text-slate-300">{r.dte ?? "—"}d</td>
                <td className="py-1 px-1 text-right text-slate-300">{fmt(r.mid, 2)}</td>
                <td className="py-1 px-1 text-right text-slate-400">{Number.isFinite(r.iv) ? `${(r.iv * 100).toFixed(1)}%` : "—"}</td>
                <td className="py-1 px-1 text-right text-slate-400">{r.volume ?? 0}</td>
                <td className="py-1 px-1 text-right text-emerald-300">
                  {tab === "put" ? `${fmt(r.breakeven_drop_pct, 2)}%` : `${fmt(r.otm_pct, 2)}%`}
                </td>
                <td className="py-1 px-1 text-right font-bold text-amber-300">
                  {fmt(r.annualized_return_pct, 2)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && (
        <div className="mt-2 text-[8px] text-slate-600 uppercase tracking-widest">
          spot ${fmt(data.spot, 2)} · {rows.length} rows
        </div>
      )}
    </div>
  );
}

export default memo(WheelIncomeScreenerPanel);
