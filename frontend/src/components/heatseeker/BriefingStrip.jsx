/**
 * BriefingStrip — Solstice top strip showing the paper-accurate briefing
 * metrics that were previously invisible in the UI (net GEX, regime, gamma
 * imbalance, flip level, intraday regime prediction).
 *
 * Data: /api/briefing/{ticker} — now populated after the gamma-backfill fix
 * (cvserver rows arrive without gamma; route backfills via bs_gamma from IV).
 */
import React, { useState, useEffect } from "react";
import { BACKEND_URL } from "../../config/api";

function fmtB(v) {
  if (v == null || isNaN(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "+";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(0)}M`;
  return `${sign}$${a.toFixed(0)}`;
}
function fmtPct(v) {
  if (v == null || isNaN(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function Metric({ label, value, tone = "neutral", title }) {
  const tones = {
    positive: { color: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.25)" },
    negative: { color: "#fb7185", bg: "rgba(251,113,133,0.08)", border: "rgba(251,113,133,0.25)" },
    neutral: { color: "#94a3b8", bg: "rgba(30,41,59,0.5)", border: "rgba(51,65,85,0.6)" },
    amber: { color: "#fbbf24", bg: "rgba(251,191,36,0.08)", border: "rgba(251,191,36,0.25)" },
  };
  const t = tones[tone] || tones.neutral;
  return (
    <div className="px-2.5 py-1.5 rounded-lg border" style={{ background: t.bg, borderColor: t.border }} title={title}>
      <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">{label}</div>
      <div className="text-[13px] font-bold font-mono mt-0.5" style={{ color: t.color }}>{value}</div>
    </div>
  );
}

export default function BriefingStrip({ ticker = "SPY", spot = null }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  // Agent-brief export (P0): a research DRAFT for Public's native Agents
  // UI — the user pastes it there and signs off there. FLOWW never places
  // orders and never connects anything; the brief says so explicitly.
  const [exportState, setExportState] = useState(null); // null | 'copied' | 'manual'
  const [exportText, setExportText] = useState("");
  const exportBrief = () => {
    const brief = { brief: "floww-agent-brief.v1", ticker,
      asof: data?.asof || null, spot,
      executes_nothing: true,
      note: "Research draft for Public Agents (user paste + sign-off). Not an order.",
      metrics: data?.metrics || null, regime: data?.regime || null };
    const text = JSON.stringify(brief, null, 2);
    const clip = navigator?.clipboard?.writeText;
    if (typeof clip === "function") {
      clip.call(navigator.clipboard, text).then(
        () => { setExportState("copied"); setExportText(""); },
        () => { setExportState("manual"); setExportText(text); });
    } else {
      setExportState("manual"); setExportText(text);
    }
  };

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    fetch(`${BACKEND_URL}/api/briefing/${encodeURIComponent(ticker)}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => {
        if (e.name === "AbortError") return;
        setError(e.message);
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [ticker]);

  if (loading && !data) {
    return (
      <div className="rounded-xl border p-3 mb-2" style={{ background: "rgba(15,23,42,0.5)", borderColor: "rgba(51,65,85,0.5)" }}>
        <div className="h-10 animate-pulse bg-slate-800/40 rounded" />
      </div>
    );
  }
  if (error && !data) return null; // silent — strip is supplementary

  const m = data?.metrics || {};
  const netGex = m.net_gex ?? 0;
  const gi = m.gamma_imbalance || {};
  const giPct = gi.gamma_imbalance_pct;
  const regime = data.regime || "—";
  const intraday = m.intraday_regime || {};
  const flip = m.flip_level;
  const flipDist = spot && flip ? ((flip - spot) / spot) * 100 : null;

  const regimeTone =
    /BULL/i.test(regime) ? "positive" : /BEAR/i.test(regime) ? "negative" : "neutral";

  return (
    <div data-testid="hs-briefing-strip"
      className="rounded-xl border p-3 mb-2"
      style={{ background: "rgba(15,23,42,0.5)", borderColor: "rgba(51,65,85,0.5)" }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">
          Paper Metrics · Ni-Pearson / Barbon-Buraschi
        </div>
        <span className="px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider"
          style={{
            background: regimeTone === "positive" ? "rgba(52,211,153,0.12)" : regimeTone === "negative" ? "rgba(251,113,133,0.12)" : "rgba(30,41,59,0.6)",
            color: regimeTone === "positive" ? "#34d399" : regimeTone === "negative" ? "#fb7185" : "#94a3b8",
          }}>
          {regime}
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Metric label="Net GEX" value={fmtB(netGex)}
          tone={netGex > 0 ? "positive" : netGex < 0 ? "negative" : "neutral"}
          title="Total dealer gamma exposure — positive suppresses vol, negative amplifies" />
        <Metric label="γ Imbalance" value={fmtPct(giPct)}
          tone={giPct == null ? "neutral" : giPct < -0.4 ? "negative" : giPct > 0.4 ? "amber" : "neutral"}
          title={`${gi.interpretation || ""}${gi.gamma_imbalance_dollars_per_share != null ? ` · $${gi.gamma_imbalance_dollars_per_share}/share` : ""}`} />
        <Metric label="Flip Level" value={flip ? `$${flip.toFixed(0)}` : "—"}
          tone="amber"
          title={flipDist != null ? `Zero-gamma flip ${flipDist.toFixed(1)}% ${flip > (spot || 0) ? "above" : "below"} spot` : "Zero-gamma level"} />
        <Metric label="Intraday" value={(intraday.predicted_regime || "—").replace(/_/g, " ")}
          tone={intraday.expected_autocorr_sign === "negative" ? "negative" : "neutral"}
          title={`Expected autocorrelation: ${intraday.expected_autocorr_sign ?? "—"}`} />
        <Metric label="IV Skew" value={m.iv_skew != null && m.iv_skew !== 0 ? fmtPct(m.iv_skew) : "balanced"}
          tone="neutral" title="25-delta put vs call IV" />
      </div>
      <div className="flex items-center gap-2 mt-2">
        <button type="button" data-testid="export-brief" onClick={exportBrief}
          className="px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider"
          style={{ background: "rgba(30,41,59,0.6)", color: "#94a3b8" }}
          title="Copy a research draft for Public's native Agents UI (paste + sign off there)">
          Export agent brief
        </button>
        {exportState === "copied" && (
          <span data-testid="export-brief-status" role="status" className="text-[10px] text-slate-400">
            Brief copied — paste into Public Agents and sign off there. FLOWW executes nothing.
          </span>)}
        {exportState === "manual" && (
          <span data-testid="export-brief-status" role="status" className="text-[10px] text-slate-400">
            Copy unavailable — select the draft text manually:
          </span>)}
      </div>
      {exportState === "manual" && (
        <textarea data-testid="export-brief-text" readOnly rows={6}
          value={exportText} aria-label="Agent brief draft"
          className="w-full mt-1 font-mono text-[10px]" />)}
    </div>
  );
}
