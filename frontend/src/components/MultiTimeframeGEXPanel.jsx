import React, { useEffect, useState } from "react";
import axios from "axios";
import { fmt, fmtAbs } from "../lib/helpers";
import { BACKEND_URL, API } from "../config/api";

// API imported from config/api.js

const TF_ORDER = ["0DTE", "1DTE", "weekly", "monthly", "all"];
const TF_LABELS = { "0DTE": "0DTE", "1DTE": "1DTE", "weekly": "Weekly", "monthly": "Monthly", "all": "All" };

export default function MultiTimeframeGEXPanel({ ticker }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    if (!ticker) return;
    axios.get(`${API}/gex-timeframes/${ticker}`).then(r => setData(r.data)).catch((e) => {
      console.error("MultiTimeframeGEXPanel fetch failed:", e);
    });
  }, [ticker]);

  if (!data?.timeframes) return null;

  return (
    <div className="panel-2 p-2">
      <button className="flex items-center justify-between w-full text-left" onClick={() => setOpen(!open)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}>
        <div className="label mb-0">Multi-Timeframe GEX</div>
        <span className="text-slate-500 text-[10px]">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5">
          {TF_ORDER.map(tf => {
            const v = data.timeframes[tf];
            if (!v) return null;
            const hasData = v.contract_count > 0 || v.gex_total !== 0;
            const netClass = v.gex_total > 0 ? "text-teal-400" : v.gex_total < 0 ? "text-purple-400" : "text-slate-500";
            return (
              <div key={tf} className="bg-slate-800/50 rounded px-2 py-1.5">
                <div className="flex justify-between items-baseline mb-1">
                  <span className="text-[10px] font-bold text-slate-300">{TF_LABELS[tf]}</span>
                  <span className={`text-[10px] mono font-bold ${netClass}`}>
                    {hasData ? fmtAbs(v.gex_total) : "—"}
                  </span>
                </div>
                {hasData ? (
                  <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[9px]">
                    <div className="flex justify-between"><span className="text-slate-500">Calls</span><span className="text-teal-400 mono">{fmtAbs(v.call_gex)}</span></div>
                    <div className="flex justify-between"><span className="text-slate-500">Puts</span><span className="text-purple-400 mono">{fmtAbs(v.put_gex)}</span></div>
                    {/* services/gex_history.py:341 returns `net_gex`. This row
                        read `net_gamma`, which no endpoint emits, so the Net Γ
                        cell was permanently blank. The ?? alias keeps it correct
                        if either name ever comes back. */}
                    <div className="flex justify-between"><span className="text-slate-500">Net Γ</span><span className="mono">{fmtAbs(v.net_gex ?? v.net_gamma)}</span></div>
                    <div className="flex justify-between"><span className="text-slate-500">Contracts</span><span className="text-slate-400 mono">{v.contract_count || "—"}</span></div>
                  </div>
                ) : (
                  <div className="text-[9px] text-slate-600">No contracts</div>
                )}
                {hasData && v.top_floors?.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {v.top_floors.slice(0, 3).map((f, i) => (
                      <span key={i} className="text-[8px] px-1 py-px rounded bg-teal-500/10 text-teal-400">
                        ↑{f.strike.toFixed(0)} {fmtAbs(f.gex)}
                      </span>
                    ))}
                  </div>
                )}
                {hasData && v.top_ceilings?.length > 0 && (
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {v.top_ceilings.slice(0, 3).map((c, i) => (
                      <span key={i} className="text-[8px] px-1 py-px rounded bg-purple-500/10 text-purple-400">
                        ↓{c.strike.toFixed(0)} {fmtAbs(c.gex)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
