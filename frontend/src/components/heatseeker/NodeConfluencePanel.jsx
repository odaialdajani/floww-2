import React from "react";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * NodeConfluencePanel — roadmap #4 (confluence as a first-class overlay)
 * and #5 (flow-at-node).
 *
 * `services/agent/confluence.py::score` existed with zero production
 * callers; this panel is its first mounted consumer. It shows the fused
 * score per major level alongside the flow prints sitting at that level,
 * so a trader can confirm a wall without tab-switching.
 *
 * Honesty is the point of this component. A dimension with no real
 * per-strike input is rendered as "—" with a tooltip, never as a zero
 * that reads as "neutral on purpose". `structure` is labelled unsigned
 * context because gamma magnitude is not a direction. A strike with thin
 * tape shows "no tape" rather than a lean.
 */

const TONE = {
  bullish: "text-emerald-400",
  bearish: "text-rose-400",
  neutral: "text-slate-400",
};

const DIM_LABELS = {
  flow: "flow",
  structure: "structure",
  microstructure: "tape",
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
      <span className="text-slate-500" title="Gamma magnitude is unsigned context — it is not a direction and does not tilt the score.">
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
                ? "Flow prints matched to levels from the alert feed"
                : data.flow_status === "no_prints"
                ? "No flow prints near these levels in the window — absence of flow, not a bearish read"
                : data.flow_status === "disabled"
                ? "Flow read disabled for this request"
                : "Flow feed unavailable"
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
                      {c.total?.toFixed?.(1) ?? "—"} {c.direction || "neutral"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2 text-slate-500">
                    <span title="Signed dealer dollar-gamma at this strike (calls +, puts −).">
                      GEX {Math.abs(r.gex || 0).toExponential(2)}
                    </span>
                    <span
                      className={r.microstructure_status === "ok" ? (r.microstructure_skew > 0 ? "text-emerald-400/70" : "text-rose-400/70") : "text-slate-600"}
                      title={
                        r.microstructure_status === "ok"
                          ? "Call/put volume skew at this strike — a tape observation, not a dealer-positioning claim"
                          : "Thin or missing tape: skew reported unknown, not zero"
                      }
                    >
                      {r.microstructure_status === "ok"
                        ? `skew ${r.microstructure_skew > 0 ? "+" : ""}${r.microstructure_skew?.toFixed?.(2)}`
                        : "no tape"}
                    </span>
                    <span
                      className={flow.count > 0 ? "text-slate-300" : "text-slate-600"}
                      title={
                        flow.count > 0
                          ? `${flow.count} flow print(s) within ${flow.window} of this strike (${flow.call_side} call-side, ${flow.put_side} put-side)`
                          : `No flow prints within ${flow.window} of this strike`
                      }
                    >
                      {flow.count > 0 ? `${flow.count} print${flow.count === 1 ? "" : "s"}` : "no prints"}
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
            A small or neutral score here is honest, not broken: most confluence dimensions have no
            per-strike input, so only tape and flow can move it. Dashed dims are unknown, not zero.
          </p>
        </>
      )}
    </div>
  );
}
