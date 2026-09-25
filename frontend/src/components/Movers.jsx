import React, { useEffect, useState } from "react";
import axios from "axios";
import { pctClass } from "../lib/helpers";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

/**
 * Movers — Top Movers panel (R7-01). Reads the movers.v2 contract:
 * canonical change_pct (+legacy pct/change aliases), explicit status,
 * session dates and coverage. Bounded loading, empty, stale, error+retry.
 * Rows are keyboard-selectable; one onPick per activation.
 */
function Movers({ onPick }) {
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState(null);
  const [state, setState] = useState("loading"); // loading|ready|empty|error
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let mounted = true;
    setState("loading");
    const f = async () => {
      try {
        const res = await axios.get(`${API}/movers?limit=12`);
        if (!mounted) return;
        const body = res.data || {};
        const list = Array.isArray(body.results) ? body.results : [];
        setRows(list);
        setMeta(body);
        if (body.status === "unavailable" && list.length === 0) setState("error");
        else if (list.length === 0) setState("empty");
        else setState("ready");
      } catch (e) {
        if (mounted) {
          setRows([]);
          setMeta(null);
          setState("error");
        }
      }
    };
    f();
    const id = setInterval(f, 60000);
    return () => { mounted = false; clearInterval(id); };
  }, [reload]);

  const changeOf = (r) => (typeof r.change_pct === "number" ? r.change_pct : r.change);
  const stale = meta && (meta.status === "stale" || meta.status === "partial");
  const footer = meta && (meta.session_date || meta.coverage)
    ? `${meta.session_date || "?"} vs ${meta.prior_session_date || "?"} · ` +
      `${meta.coverage ? `${meta.coverage.valid}/${meta.coverage.requested} valid` : ""}` +
      (meta.status === "stale" ? " · stale" : meta.status === "partial" ? " · partial" : "")
    : null;

  return (
    <div className="panel p-3" data-testid="movers-panel">
      <div className="label mb-2">Top Movers (prev session %)</div>
      <div className="flex flex-col gap-1 text-[12px]">
        {state === "loading" && <div className="text-slate-500" aria-busy="true">…</div>}
        {state === "empty" && <div className="text-slate-500">No eligible rows</div>}
        {state === "error" && (
          <div className="text-slate-500">
            Movers unavailable{" "}
            <button className="underline" data-testid="movers-retry" onClick={() => setReload((n) => n + 1)}>
              Retry
            </button>
          </div>
        )}
        {rows.map((r) => {
          const ch = changeOf(r);
          return (
            <button
              key={r.ticker}
              className="flex justify-between bar-row cursor-pointer text-left"
              data-testid={`movers-row-${r.ticker}`}
              onClick={() => onPick && onPick(r.ticker)}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && onPick) {
                  e.preventDefault();
                  onPick(r.ticker);
                }
              }}
            >
              <span className="mono text-amber-300 font-medium">{r.ticker}</span>
              <span className={`${pctClass(ch)} font-medium`}>
                {typeof ch === "number" ? `${ch > 0 ? "+" : ""}${ch.toFixed(2)}%` : "n/a"}
              </span>
            </button>
          );
        })}
      </div>
      {footer && <div className="text-[10px] text-slate-500 mt-1" data-testid="movers-meta">{footer}</div>}
      {stale && <div className="text-[10px] text-amber-400" data-testid="movers-stale">last-good values</div>}
    </div>
  );
}

export default Movers;
