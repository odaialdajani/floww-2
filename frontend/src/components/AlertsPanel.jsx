import React, { useEffect, useState } from "react";
import axios from "axios";
import { fmtAbs } from "../lib/helpers";
import { BACKEND_URL, API } from "../config/api";

// API imported from config/api.js

const ALERT_TYPES = [
  { v: "gex_cross", l: "GEX Cross", desc: "Total GEX crosses threshold" },
  { v: "gex_spike", l: "GEX Spike", desc: "Single strike GEX spike" },
  { v: "oi_spike", l: "OI Spike", desc: "Open interest spike" },
  { v: "iv_spike", l: "IV Spike", desc: "Implied vol spike" },
  { v: "gamma_flip", l: "Gamma Flip", desc: "Regime change positive ↔ negative gamma" },
  { v: "gamma_squeeze", l: "Gamma Squeeze", desc: "Negative gamma + spot near flip + volume spike" },
  { v: "wall_breach", l: "Wall Breach", desc: "Spot crosses call/put wall" },
  { v: "charm_pinning", l: "Charm Pinning", desc: "Charm-driven pinning (0DTE)" },
  { v: "vanna_regime", l: "Vanna Regime Change", desc: "Sign flip in net VEX" },
  { v: "pc_oi_ratio", l: "Unusual P/C OI Ratio", desc: "Put OI / call OI ratio > 2x" },
  { v: "max_pain_magnet", l: "Max Pain Magnet", desc: "Spot within 1% of max pain" },
  { v: "momentum_extreme", l: "Momentum Extreme", desc: "Strong bullish/bearish momentum" },
  { v: "gex_magnitude_shift", l: "GEX Magnitude Shift", desc: "Total GEX changed > 40%" },
  { v: "pin_risk", l: "Pin Risk", desc: "Spot near max gamma strike" },
  { v: "ml_prediction", l: "ML Prediction", desc: "ML model predicts direction change" },
];

const PRIORITY_STYLES = {
  HIGH: "bg-rose-500/20 text-rose-400 border-rose-500/30",
  MEDIUM: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  LOW: "bg-sky-500/20 text-sky-400 border-sky-500/30",
};

const PRIORITY_ICONS = {
  HIGH: "🔴",
  MEDIUM: "🟡",
  LOW: "🔵",
};

export default function AlertsPanel({ ticker }) {
  const [rules, setRules] = useState([]);
  const [triggered, setTriggered] = useState([]);
  const [open, setOpen] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newRule, setNewRule] = useState({
    alert_type: "gex_cross", threshold: 0, direction: "below", label: "",
  });
  const [checkResult, setCheckResult] = useState(null);
  const [mlPrediction, setMlPrediction] = useState(null);
  // A failed ML read is NOT the same as no signal. Track it explicitly so the
  // panel can say why, instead of rendering nothing and looking neutral.
  const [mlError, setMlError] = useState(null);

  const fetchRules = async () => {
    try {
      const res = await axios.get(`${API}/alerts${ticker ? `?ticker=${ticker}` : ""}`);
      setRules(res.data.rules || []);
    } catch (e) { /* noop */ }
  };

  const checkAlerts = async () => {
    if (!ticker) return;
    try {
      const res = await axios.get(`${API}/alerts/check/${ticker}`);
      setTriggered(res.data.triggered || []);
      setCheckResult(res.data);
    } catch (e) { /* noop */ }
  };

  const createRule = async () => {
    if (!ticker) return;
    try {
      await axios.post(`${API}/alerts`, {
        ...newRule, ticker,
        threshold: Number(newRule.threshold),
      });
      setShowCreate(false);
      setNewRule({ alert_type: "gex_cross", threshold: 0, direction: "below", label: "" });
      fetchRules();
    } catch (e) { /* noop */ }
  };

  const deleteRule = async (id) => {
    try {
      await axios.delete(`${API}/alerts/${id}`);
      fetchRules();
    } catch (e) { /* noop */ }
  };

  // Fetch rules and check alerts on mount/ticker change (single effect to avoid double-fetch)
  useEffect(() => {
    if (!ticker) return;
    fetchRules();
    checkAlerts();
    const id = setInterval(checkAlerts, 30000);
    return () => clearInterval(id);
  }, [ticker]);

  // Fetch ML prediction
  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    const fetchMl = async () => {
      try {
        const r = await axios.get(`${API}/ml/predict/${ticker}`);
        if (!cancelled) { setMlPrediction(r.data); setMlError(null); }
      } catch (e) {
        if (cancelled) return;
        // Surface WHY. A 404 means no model was trained for this ticker; a
        // 503 names the artifact that could not be loaded (a corrupt or
        // un-promoted model). Both used to render exactly like a neutral
        // HOLD, which is the dangerous ambiguity: absence of a signal must
        // never look like a signal.
        const status = e?.response?.status;
        const d = e?.response?.data;
        const reason =
          status === 404
            ? "no model trained for this ticker"
            : status === 503
              ? `model unavailable${d?.artifact ? ` (${d.artifact})` : ""}`
              : `prediction unavailable${status ? ` (HTTP ${status})` : ""}`;
        setMlError(reason);
        setMlPrediction(null);
      }
    };
    fetchMl();
    const id = setInterval(fetchMl, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, [ticker]);

  return (
    <div className="panel-2 p-2">
      <button className="flex items-center justify-between w-full text-left" onClick={() => setOpen(!open)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}>
        <div className="label mb-0">
          Alerts
          {triggered.length > 0 && (
            <span className="ml-1 text-[8px] px-1 py-px rounded bg-rose-500/20 text-rose-400 flash-pulse">
              {triggered.length} LIVE
            </span>
          )}
        </div>
        <span className="text-slate-500 text-[10px]">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5">
          {/* Triggered alerts */}
          {triggered.length > 0 && (
            <div className="space-y-1">
              <div className="text-[9px] font-bold text-rose-400 mb-1">⚡ TRIGGERED ALERTS</div>
              {triggered.map((t, i) => {
                const priority = t.priority || "MEDIUM";
                const style = PRIORITY_STYLES[priority] || PRIORITY_STYLES.MEDIUM;
                const icon = PRIORITY_ICONS[priority] || PRIORITY_ICONS.MEDIUM;
                return (
                  <div key={i} className={`rounded px-2 py-1 border ${style}`}>
                    <div className="text-[9px] font-bold flex justify-between">
                      <span>{icon} {t.label || t.type}</span>
                      <span className="text-[8px] opacity-70">{priority}</span>
                    </div>
                    {t.message && <div className="text-[8px] opacity-80 mt-0.5">{t.message}</div>}
                    {!t.message && (
                      <div className="text-[8px] mono">
                        {fmtAbs(t.value)} {t.direction} {fmtAbs(t.threshold)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* ML unavailable — distinct from a neutral prediction */}
          {mlError && (
            <div
              data-testid="ml-unavailable"
              className="rounded px-2 py-1.5 border border-slate-600/40 bg-slate-700/10"
              title="The model did not answer. This is not a neutral reading."
            >
              <div className="text-[9px] font-bold text-slate-400">ML UNAVAILABLE</div>
              <div className="text-[8px] opacity-70 mt-0.5">{mlError}</div>
            </div>
          )}

          {/* ML Prediction */}
          {mlPrediction && mlPrediction.prediction && (
            <div data-testid="ml-prediction">
            <div className={`rounded px-2 py-1.5 border ${
              mlPrediction.prediction === "UP" || mlPrediction.prediction === "BULLISH"
                ? "bg-emerald-500/5 border-emerald-500/20"
                : mlPrediction.prediction === "DOWN" || mlPrediction.prediction === "BEARISH"
                ? "bg-rose-500/5 border-rose-500/20"
                : "bg-slate-800/50 border-slate-700/50"
            }`}>
              <div className="flex items-center justify-between">
                <div className="text-[9px] font-bold text-slate-400">🤖 ML PREDICTION</div>
                <span className={`text-[10px] font-bold mono ${
                  mlPrediction.prediction === "UP" || mlPrediction.prediction === "BULLISH"
                    ? "text-emerald-400"
                    : "text-rose-400"
                }`}>
                  {mlPrediction.prediction}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[8px] text-slate-500">Confidence:</span>
                <div className="flex-1 h-1 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${mlPrediction.confidence > 0.6 ? "bg-emerald-500" : mlPrediction.confidence > 0.5 ? "bg-amber-500" : "bg-slate-500"}`}
                    style={{ width: `${(mlPrediction.confidence || 0) * 100}%` }}
                  />
                </div>
                <span className="text-[8px] mono text-slate-400">{(mlPrediction.confidence || 0).toFixed(2)}</span>
              </div>
              {mlPrediction.spot && (
                <div className="text-[8px] text-slate-600 mt-0.5">
                  Spot: ${Number(mlPrediction.spot).toFixed(2)}
                </div>
              )}
            </div>
            </div>
          )}

          {/* Active rules */}
          {rules.length > 0 && (
            <div className="space-y-1">
              {rules.map(r => (
                <div key={r.id} className="bg-slate-800/50 rounded px-2 py-1 flex justify-between items-center">
                  <div className="text-[9px]">
                    <div className="text-slate-300">{r.label || r.alert_type}</div>
                    <div className="text-slate-500">
                      {r.ticker} · {r.direction} {fmtAbs(r.threshold)}
                      {r.trigger_count > 0 && <span className="ml-1 text-amber-400">({r.trigger_count}x)</span>}
                    </div>
                  </div>
                  <button onClick={() => deleteRule(r.id)} className="text-slate-600 hover:text-rose-400 text-[10px]" aria-label={`Delete alert rule ${r.id}`}>✕</button>
                </div>
              ))}
            </div>
          )}

          {/* Create new */}
          {!showCreate ? (
            <button onClick={() => setShowCreate(true)} className="btn text-[9px] w-full">+ New Alert</button>
          ) : (
            <div className="bg-slate-800/50 rounded px-2 py-1.5 space-y-1">
              <select value={newRule.alert_type} onChange={e => setNewRule({...newRule, alert_type: e.target.value})}
                className="btn text-[9px] w-full px-1 py-0.5">
                {ALERT_TYPES.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}
              </select>
              <input type="text" value={newRule.label} onChange={e => setNewRule({...newRule, label: e.target.value})}
                placeholder="Label (optional)" className="btn text-[9px] w-full px-1 py-0.5" />
              <div className="flex gap-1">
                <select value={newRule.direction} onChange={e => setNewRule({...newRule, direction: e.target.value})}
                  className="btn text-[9px] flex-1 px-1 py-0.5">
                  <option value="above">Above</option>
                  <option value="below">Below</option>
                </select>
                <input type="number" value={newRule.threshold} onChange={e => setNewRule({...newRule, threshold: e.target.value})}
                  placeholder="Threshold" className="btn text-[9px] flex-1 px-1 py-0.5" />
              </div>
              <div className="flex gap-1">
                <button onClick={createRule} className="btn text-[9px] flex-1 active">Create</button>
                <button onClick={() => setShowCreate(false)} className="btn text-[9px] flex-1">Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
