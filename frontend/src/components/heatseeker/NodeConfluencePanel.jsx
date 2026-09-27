import React from "react";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * NodeConfluencePanel — roadmap #4 (confluence as a first-class overlay)
 * and #5 (flow-at-node).
 *
 * `services/agent/confluence.py::score` existed with zero production
 * callers; this panel is its first mounted consumer. It shows the fused
 * score per major level alongside the saved alerts sitting at that level,
 * so a trader can confirm a wall without tab-switching.
 *
 * Honesty is the point of this component. A dimension with no real
 * per-strike input is rendered as "—" with a tooltip, never as a zero
 * that reads as "neutral on purpose". `structure` is labelled unsigned
 * context because gamma magnitude is not a direction. A strike with thin
 * tape shows "volume unknown" rather than a lean.
 */

const TONE = {
  bullish: "text-emerald-400",
  bearish: "text-rose-400",
  neutral: "text-slate-400",
};

const DIM_LABELS = {
  flow: "alert bias",
  structure: "structure",
  microstructure: "activity",
  ml: "ml",
  vol: "vol",
  time_delta: "time",
};

function DimStatus({ name, dim }) {
  if (!dim) return <span className="text-slate-600">—</span>;
  const status = dim.inputs_status;
  const label = DIM_LABELS[name] || name;

  if (status === "context_only") {
    return (
      <span className="text-slate-500" title="Option activity and gamma size are context; neither establishes price direction.">
        {label} ·ctx
      </span>
    );
  }
  if (status === "missing") {
    return (
      <span className="text-slate-600" title={`${label}: no real per-strike input available, so it contributes nothing. Shown as unknown, not as zero.`}>
        {label} ·—
      </span>
    );
  }
  return (
    <span className="text-slate-300" title={`${label}: ${dim.value?.toFixed?.(2) ?? "?"} (weight ${dim.weight})`}>
      {label} {dim.value?.toFixed?.(2) ?? "?"}
    </span>
  );
}

export default function NodeConfluencePanel({ ticker = "SPY", limit = 8 }) {
  const { data, loading, error } = useHeatseeker("node-confluence", {
    ticker,
    limit,
    expiries: 2,
    include_flow: true,
    refreshMs: 30000,
  });

  const rows = data?.rows || [];
  const degraded = data?.status === "degraded";

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-node-confluence">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">🎯</span>
        <span className="text-xs font-semibold text-slate-200">Level Confluence</span>
        {data?.flow_status && (
          <span
            className="text-[9px] px-1.5 py-0.5 rounded border border-slate-600/50 text-slate-400"
            title={
              data.flow_status === "ok"
                ? "Saved alerts matched to contract strikes"
                : data.flow_status === "no_prints"
                ? "No saved alerts near these levels; this is not a bearish reading"
                : data.flow_status === "disabled"
                ? "Flow read disabled for this request"
                : "Saved alert feed unavailable"
            }
          >
            flow:{data.flow_status}
          </span>
        )}
      </div>

      {loading && <div className="text-[11px] text-slate-500">reading levels…</div>}

      {error && (
        <div className="text-[11px] text-rose-400">
          confluence unavailable <span className="text-slate-500">({error})</span>
        </div>
      )}

      {degraded && (
        <div className="text-[11px] text-amber-400/80" title={data?.error}>
          levels unavailable — {data?.error}
        </div>
      )}

      {!loading && !error && !degraded && rows.length === 0 && (
        <div className="text-[11px] text-slate-500">no levels with open interest in scope</div>
      )}

      {rows.length > 0 && (
        <>
          <div className="flex flex-col gap-1.5 text-[11px]">
            {rows.map((r) => {
              const c = r.confluence || {};
              const flow = r.flow || {};
              return (
                <div
                  key={r.strike}
                  className="rounded border border-slate-700/40 px-2 py-1 hover:bg-slate-800/40"
                  data-testid={`hs-confluence-row-${r.strike}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-slate-100">{r.strike}</span>
                    <span className={`font-semibold ${TONE[c.direction] || TONE.neutral}`} title="Fused confluence score. Only dimensions with real per-strike input contribute.">
                      {c.total > 0 ? "+" : ""}
                      {c.total?.toFixed?.(1) ?? "—"} {c.direction === "insufficient_evidence" ? "not enough evidence" : c.direction || "unknown"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2 text-slate-500">
                    <span title="Assumed dollar-gamma at this strike: calls positive, puts negative; actual dealer holdings are unknown.">
                      GEX {typeof r.gex === "number" && Number.isFinite(r.gex) ? r.gex.toExponential(2) : "—"}
                    </span>
                    <span
                      className="text-slate-500"
                      title={
                        ["ok", "context_only"].includes(r.microstructure_status)
                          ? "Call/put volume balance at this strike; buy/sell direction is unknown"
                          : "Thin or missing volume: balance is unknown, not zero"
                      }
                    >
                      {["ok", "context_only"].includes(r.microstructure_status)
                        ? `call/put ${r.microstructure_skew > 0 ? "+" : ""}${r.microstructure_skew?.toFixed?.(2)}`
                        : "volume unknown"}
                    </span>
                    <span
                      className={flow.count > 0 ? "text-slate-300" : "text-slate-600"}
                      title={
                        flow.count > 0
                          ? `${flow.count} saved alert(s) within ${flow.window} of this strike (${flow.call_side} call-side, ${flow.put_side} put-side)`
                          : `No saved alerts within ${flow.window} of this strike`
                      }
                    >
                      {flow.count > 0 ? `${flow.count} alert${flow.count === 1 ? "" : "s"}` : "no alerts"}
                    </span>
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[9px] text-slate-500">
                    {Object.entries(c.dimensions || {}).map(([name, dim]) => (
                      <DimStatus key={name} name={name} dim={dim} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="mt-1.5 text-[9px] leading-tight text-slate-600">
            Only fresh declared alert bias contributes. Call/put activity does not prove direction.
            Missing readings stay unknown; this is not a trading probability.
          </p>
        </>
      )}
    </div>
  );
}
