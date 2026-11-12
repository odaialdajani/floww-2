import React from "react";
import { fmt, fmtAbs, tagFor } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 1 — Node Lifecycle.
 * Top 10 nodes with strike / GEX / visit episodes / state.
 *
 * Taps are counted as VISIT EPISODES: spot resting on a strike across many
 * consecutive snapshots is one sustained visit, and only leaving the band
 * and returning starts another. Repeated identical timestamps are one
 * sample, so a replayed or re-sent row can never add a visit. No tap
 * percentage is shown — outcome probability is not calibrated here.
 */
function stateClass(state) {
  if (!state) return "tag";
  const key = String(state).toLowerCase();
  if (key.startsWith("fresh")) return tagFor("fresh");
  if (key.startsWith("test")) return tagFor("tested");
  if (key.startsWith("deliver")) return tagFor("delivered");
  if (key.startsWith("decay")) return tagFor("decaying");
  if (key.startsWith("unknown")) return tagFor("unknown");
  return "tag";
}

export default function NodeLifecyclePanel({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("node-lifecycle", { ticker });
  const nodes = (data?.nodes || []).slice(0, 25);
  // Build #1 — durable memory: the badge tells whether node/wall state
  // survived a restart (DuckDB) or is this process's memory only.
  const durable = data?.durable;
  const memNote = data?.memory_only === true || durable === false
    ? "memory-only"
    : durable === true ? "durable" : null;
  const samples = data?.history_samples;
  const duplicates = data?.duplicate_timestamps_dropped;
  const historyUnknown = data?.history_status === "unknown";

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-node-lifecycle">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">🔄</span>
          <span className="text-xs font-semibold text-slate-200">Node Lifecycle</span>
          {memNote && (
            <span
              className="text-[9px] px-1.5 py-0.5 rounded border border-slate-600/50 text-slate-400"
              title={durable === true
                ? "Lifecycle state restored from DuckDB — survives restarts"
                : "Lifecycle state is in-process memory only — lost on restart"}
            >
              {memNote === "durable" ? "durable · survives restart" : "memory-only"}
            </span>
          )}
        </div>
        <span className="text-[10px] text-slate-500">{nodes.length} of top-25</span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && historyUnknown && (
        <div className="text-slate-500 text-[10px] mb-1.5">
          History unknown · no visit claim{(data?.reason ? ` (${data.reason})` : "")}
        </div>
      )}
      {data && !historyUnknown && (samples != null || duplicates != null) && (
        <div className="text-slate-500 text-[10px] mb-1.5">
          {samples ?? 0} distinct samples
          {duplicates ? ` · ${duplicates} repeated timestamps ignored` : ""}
        </div>
      )}
      {data && nodes.length === 0 && <div className="text-slate-500 text-xs py-2 text-center">No lifecycle data</div>}
      {nodes.length > 0 && (
        <div className="overflow-y-auto" style={{ maxHeight: 280 }}>
          <table className="w-full text-xs">
            <thead className="text-slate-500 text-[9px] uppercase tracking-widest">
              <tr>
                <th className="text-left px-1.5 py-1 font-semibold">Strike</th>
                <th className="text-right px-1.5 py-1 font-semibold">Net γ</th>
                <th className="text-right px-1.5 py-1 font-semibold" title="Visit episodes: a sustained dwell counts once; exit and re-entry counts again.">Visits</th>
                <th className="text-left px-1.5 py-1 font-semibold">State</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((n, i) => {
                const visits = n.visit_episodes ?? n.taps;
                return (
                  <tr key={`${n.strike}-${i}`} className="border-t border-slate-800/40">
                    <td className="px-1.5 py-1.5 font-bold text-slate-200 mono">${fmt(n.strike, 0)}</td>
                    <td className={`px-1.5 py-1.5 text-right mono font-bold ${(n.net_gex ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {fmtAbs(n.net_gex)}
                    </td>
                    <td className="px-1.5 py-1.5 text-right text-slate-400 mono">{visits ?? "—"}</td>
                    <td className="px-1.5 py-1.5"><span className={stateClass(n.state)}>{n.state || "—"}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
