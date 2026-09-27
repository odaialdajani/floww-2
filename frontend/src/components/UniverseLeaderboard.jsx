import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../config/api";

/**
 * UniverseLeaderboard - fused conviction leaderboard (builds #2+#3).
 * One ranked list: conviction + tier + direction + trade_type +
 * invalidation + evidence. Scan button sweeps next slice; age shown
 * honestly (stale = prior rows, not fresh ideas).
 */
function UniverseLeaderboard({ onPick, limit = 12 }) {
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState(null);
  const [state, setState] = useState("loading");
  const [scanning, setScanning] = useState(false);

  const load = async (refresh) => {
    try {
      if (refresh) setScanning(true);
      else setState("loading");
      const url = refresh
        ? `${API}/flowseeker/universe/scan?limit=${limit}&refresh=true`
        : `${API}/flowseeker/universe/leaderboard?limit=${limit}`;
      const res = await axios.get(url);
      const body = res.data || {};
      const list = Array.isArray(body.leaderboard) ? body.leaderboard : [];
      setRows(list);
      setMeta(body);
      setState(list.length ? "ready" : "empty");
    } catch (e) {
      setState("error");
    } finally {
      setScanning(false);
    }
  };

  useEffect(() => { load(false); const id = setInterval(() => load(false), 300000); return () => clearInterval(id); }, [limit]);

  const tierClass = (t) => t === "HIGH" ? "text-emerald-400" : t === "MED" ? "text-amber-400" : "text-slate-400";
  const age = meta && meta.leaderboard_age_s != null ? `${Math.round(meta.leaderboard_age_s)}s ago` : "never scanned";

  return (
    <div className="panel p-3" data-testid="universe-leaderboard">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Conviction Leaderboard</div>
        <button className="btn text-[11px]" disabled={scanning} onClick={() => load(true)} title="Sweep the next universe slice against the shared budget">
          {scanning ? "Scanning…" : "Scan"}
        </button>
      </div>
      <div className="text-[10px] text-slate-500 mb-2">ranked ideas · {age}</div>
      <div className="flex flex-col gap-1 text-[12px]">
        {state === "loading" && <div className="text-slate-500">…</div>}
        {state === "empty" && <div className="text-slate-500">No ideas yet — press Scan</div>}
        {state === "error" && <div className="text-slate-500">Leaderboard unavailable <button className="btn ml-1" onClick={() => load(false)}>Retry</button></div>}
        {rows.map((r) => (
          <button key={r.ticker} className="flex items-center justify-between gap-2 text-left hover:bg-slate-800/40 rounded px-1 py-0.5"
            onClick={() => onPick && onPick(r.ticker)} title={`${r.ticker}: ${r.invalidation || ""}`}>
            <span className="font-bold text-slate-200">#{r.rank || "—"} {r.ticker}</span>
            <span className={tierClass(r.tier)}>{r.tier} {r.conviction != null ? Math.round(r.conviction) : "—"}</span>
            <span className="text-slate-500 text-[11px]">{r.direction} · {r.trade_type}</span>
          </button>
        ))}
      </div>
      {meta && meta.batch && meta.batch.skipped && meta.batch.skipped.length > 0 && (
        <div className="text-[10px] text-slate-500 mt-1">{meta.batch.skipped.length} skipped on budget — prior rows kept</div>
      )}
    </div>
  );
}

export default UniverseLeaderboard;
