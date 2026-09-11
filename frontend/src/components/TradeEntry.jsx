import React, { useState, useEffect } from "react";
import { BACKEND_URL, API } from "../config/api";
import { tradeIdeaToJournalEntries, JOURNAL_STORAGE_KEY } from "./tradeMath";

// API imported from config/api.js

const TRADE_TEMPLATES = {
  iron_condor: {
    name: "Iron Condor",
    description: "Sell premium between put wall and call wall. Best in positive gamma.",
    fields: [
      { key: "put_short", label: "Put Short Strike", type: "number", hint: "Put wall strike" },
      { key: "put_long", label: "Put Long Strike", type: "number", hint: "5-10 points below short" },
      { key: "call_short", label: "Call Short Strike", type: "number", hint: "Call wall strike" },
      { key: "call_long", label: "Call Long Strike", type: "number", hint: "5-10 points above short" },
      { key: "contracts", label: "Contracts", type: "number", hint: "From position sizing" },
      { key: "credit", label: "Expected Credit", type: "number", step: "0.01" },
    ],
  },
  long_straddle: {
    name: "Long Straddle",
    description: "Buy ATM call + put. Best in negative gamma when expecting breakout.",
    fields: [
      { key: "strike", label: "ATM Strike", type: "number", hint: "Nearest to spot" },
      { key: "contracts", label: "Contracts (each leg)", type: "number" },
      { key: "call_premium", label: "Call Premium", type: "number", step: "0.01" },
      { key: "put_premium", label: "Put Premium", type: "number", step: "0.01" },
    ],
  },
  call_spread: {
    name: "Bull Call Spread",
    description: "Buy lower call, sell higher call. Directional bullish with defined risk.",
    fields: [
      { key: "long_strike", label: "Long Call Strike", type: "number", hint: "ATM or slightly OTM" },
      { key: "short_strike", label: "Short Call Strike", type: "number", hint: "Call wall or above" },
      { key: "contracts", label: "Contracts", type: "number" },
      { key: "debit", label: "Max Debit", type: "number", step: "0.01" },
    ],
  },
  put_spread: {
    name: "Bear Put Spread",
    description: "Buy higher put, sell lower put. Directional bearish with defined risk.",
    fields: [
      { key: "long_strike", label: "Long Put Strike", type: "number", hint: "ATM or slightly OTM" },
      { key: "short_strike", label: "Short Put Strike", type: "number", hint: "Put wall or below" },
      { key: "contracts", label: "Contracts", type: "number" },
      { key: "debit", label: "Max Debit", type: "number", step: "0.01" },
    ],
  },
  single_leg: {
    name: "Single Leg (Call or Put)",
    description: "Buy or sell a single option. Higher risk, higher reward.",
    fields: [
      { key: "action", label: "Action", type: "select", options: ["Buy Call", "Buy Put", "Sell Call", "Sell Put"] },
      { key: "strike", label: "Strike", type: "number" },
      { key: "contracts", label: "Contracts", type: "number" },
      { key: "premium", label: "Premium", type: "number", step: "0.01" },
    ],
  },
};

export function TradeEntry({ ticker, spot }) {
  const [checklist, setChecklist] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState("iron_condor");
  const [formData, setFormData] = useState({});
  const [savedTrades, setSavedTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch checklist when ticker changes (not on every spot poll to avoid resetting user input)
  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${API}/daily-checklist/${ticker}?expiries=4`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => {
        if (cancelled) return;
        setChecklist(d);
        const gf = d?.key_levels || {};
        setFormData(prev => ({
          ...prev,
          put_short: gf?.put_wall ?? "",
          put_long: gf?.put_wall != null ? gf.put_wall - 5 : "",
          call_short: gf?.call_wall ?? "",
          call_long: gf?.call_wall != null ? gf.call_wall + 5 : "",
          strike: Math.round(spot || 0),
          long_strike: Math.round(spot || 0),
          short_strike: gf?.call_wall ?? "",
          contracts: prev?.contracts || 1,
        }));
      })
      .catch((e) => {
        if (cancelled) return;
        setChecklist(null);
        setError(e?.message || "Failed to load checklist");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [ticker]);

  const template = TRADE_TEMPLATES[selectedTemplate];
  const regime = checklist?.regime?.gex_regime || "unknown";

  // Recommend template based on regime
  const recommendedTemplate = regime === "positive_gamma" ? "iron_condor" :
    regime === "negative_gamma" ? "long_straddle" : "single_leg";

  const handleSave = () => {
    const trade = {
      id: Date.now(),
      template: selectedTemplate,
      templateName: template?.name || selectedTemplate,
      ticker,
      spot,
      data: { ...formData },
      regime,
      timestamp: new Date().toISOString(),
    };
    // Issue #17 O-1: persist to the shared journal store in TradeJournal
    // shape so the idea survives unmount/remount + page reload and renders
    // in TradeJournal + TradeAnalytics. Prepend (newest first, matching the
    // in-session list); never overwrite rows from other panels. On corrupt
    // store or quota failure keep the idea in-session and flag the error
    // instead of silently dropping existing records.
    try {
      const entries = tradeIdeaToJournalEntries(trade).map(e => ({
        ...e,
        id: e.id ?? Date.now() + Math.floor(Math.random() * 1000),
        created_at: new Date().toISOString(),
      }));
      const saved = JSON.parse(localStorage.getItem(JOURNAL_STORAGE_KEY) || "[]");
      localStorage.setItem(JOURNAL_STORAGE_KEY, JSON.stringify([...entries, ...saved]));
    } catch (e) {
      console.error("[TradeEntry] journal write failed:", e);
      setError("Saved in session only — journal store unavailable");
    }
    setSavedTrades(prev => [trade, ...prev].slice(0, 10));
  };

  // Issue #17 O-1: rebuild the in-session list from our own journal rows
  // after unmount/remount (other panels' rows are left for the journal).
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(JOURNAL_STORAGE_KEY) || "[]");
      const ours = saved
        .filter(e => e?.source === "trade-entry")
        .slice(0, 10)
        .map(e => ({
          id: e.id ?? Date.now(),
          template: e.template || "single_leg",
          templateName: e.templateName || e.setup || e.template || "Single Leg",
          ticker: e.ticker,
          spot: e.spot ?? null,
          data: {},
          regime: e.gex_regime || "unknown",
          timestamp: e.created_at || new Date().toISOString(),
        }));
      if (ours.length > 0) setSavedTrades(ours);
    } catch (e) { console.error("[TradeEntry] journal hydrate failed:", e); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="panel p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="label mb-0">Trade Entry</div>
        <div className="flex items-center gap-1.5">
          {loading && <span className="inline-block w-2 h-2 rounded-full bg-amber-500 animate-pulse" />}
          {error && <span className="text-[8px] text-rose-400" title={error}>⚠</span>}
          <div className="text-[9px] text-slate-500">
            {regime === "positive_gamma" ? "🟢" : regime === "negative_gamma" ? "🔴" : "⚪"} {regime?.replace?.("_", " ") ?? "unknown"}
          </div>
        </div>
      </div>

      {/* Template Selector */}
      <div>
        <div className="label mb-1">Template</div>
        <select
          value={selectedTemplate}
          onChange={e => setSelectedTemplate(e.target.value)}
          className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
        >
          {Object.entries(TRADE_TEMPLATES).map(([key, tmpl]) => (
            <option key={key} value={key}>
              {tmpl.name}{key === recommendedTemplate ? " ⭐" : ""}
            </option>
          ))}
        </select>
        <div className="text-[9px] text-slate-500 mt-0.5">{template?.description}</div>
        {recommendedTemplate !== selectedTemplate && (
          <div className="text-[9px] text-amber-400 mt-0.5">
            ⭐ Recommended for {regime?.replace?.("_", " ") ?? "unknown"} regime: {TRADE_TEMPLATES[recommendedTemplate]?.name}
          </div>
        )}
      </div>

      {/* Form Fields */}
      <div className="space-y-1.5">
        {template?.fields?.map(field => (
          <div key={field.key}>
            <div className="label mb-0.5">{field.label}</div>
            {field.type === "select" ? (
              <select
                value={formData[field.key] || ""}
                onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
                className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              >
                {field.options?.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            ) : (
              <div className="flex items-center gap-1">
                <input
                  type={field.type}
                  step={field.step || "1"}
                  value={formData[field.key] ?? ""}
                  onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
                  placeholder={field.hint || ""}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
                />
              </div>
            )}
            {field.hint && <div className="text-[8px] text-slate-600">{field.hint}</div>}
          </div>
        ))}
      </div>

      {/* Risk Preview */}
      {formData.contracts > 0 && (() => {
        const c = parseInt(formData.contracts) || 0;
        let maxProfit = null, maxRisk = null, breakeven = null;

        if (selectedTemplate === "iron_condor") {
          const credit = parseFloat(formData.credit) || 0;
          const ps = parseFloat(formData.put_short) || 0;
          const pl = parseFloat(formData.put_long) || 0;
          const cs = parseFloat(formData.call_short) || 0;
          const cl = parseFloat(formData.call_long) || 0;
          const wingPut = ps - pl;
          const wingCall = cl - cs;
          const maxWing = Math.max(wingPut, wingCall);
          maxProfit = credit * c * 100;
          maxRisk = (maxWing - credit) * c * 100;
          breakeven = `${ps - credit} / ${cs + credit}`;
        } else if (selectedTemplate === "long_straddle") {
          const callP = parseFloat(formData.call_premium) || 0;
          const putP = parseFloat(formData.put_premium) || 0;
          const total = callP + putP;
          maxProfit = "Unlimited";
          maxRisk = total * c * 100;
          const strike = parseFloat(formData.strike) || 0;
          breakeven = `${((strike - total))?.toFixed(1) ?? "—"} / ${((strike + total))?.toFixed(1) ?? "—"}`;
        } else if (selectedTemplate === "call_spread") {
          const debit = parseFloat(formData.debit) || 0;
          const ls = parseFloat(formData.long_strike) || 0;
          const ss = parseFloat(formData.short_strike) || 0;
          const width = Math.max(0, ss - ls);   // inverted strikes = invalid spread, not negative profit
          maxProfit = (width - debit) * c * 100;
          maxRisk = debit * c * 100;
          breakeven = `${((ls + debit))?.toFixed(1) ?? "—"}`;
        } else if (selectedTemplate === "put_spread") {
          const debit = parseFloat(formData.debit) || 0;
          const ls = parseFloat(formData.long_strike) || 0;
          const ss = parseFloat(formData.short_strike) || 0;
          const width = Math.max(0, ls - ss);   // inverted strikes = invalid spread, not negative profit
          maxProfit = (width - debit) * c * 100;
          maxRisk = debit * c * 100;
          breakeven = `${((ls - debit))?.toFixed(1) ?? "—"}`;
        } else if (selectedTemplate === "single_leg") {
          const premium = parseFloat(formData.premium) || 0;
          const action = formData.action || "";
          if (action.startsWith("Buy")) {
            maxProfit = "Unlimited";
            maxRisk = premium * c * 100;
          } else {
            maxProfit = premium * c * 100;
            maxRisk = "Unlimited";
          }
        }

        return (
          <div className="bg-slate-800/50 rounded p-2 border border-slate-700/50 text-[10px]">
            <div className="label mb-1">Risk Preview</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              <div className="flex justify-between">
                <span className="text-slate-500">Contracts</span>
                <span className="mono text-slate-200">{c}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Max Profit</span>
                <span className={`mono ${typeof maxProfit === "number" && maxProfit < 0 ? "text-rose-400" : "text-emerald-400"}`}>
                  {typeof maxProfit === "number" ? `${maxProfit >= 0 ? "+" : "−"}$${Math.abs(maxProfit).toFixed(0)}` : maxProfit || "—"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Max Risk</span>
                <span className="mono text-rose-400">
                  {typeof maxRisk === "number" ? `$${(maxRisk)?.toFixed(0) ?? "—"}` : maxRisk || "—"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Breakeven</span>
                <span className="mono text-amber-400">{breakeven ?? "—"}</span>
              </div>
            </div>
            {typeof maxProfit === "number" && typeof maxRisk === "number" && maxRisk > 0 && (
              <div className="mt-1 pt-1 border-t border-slate-700/50 flex justify-between">
                <span className="text-slate-500">Risk/Reward</span>
                <span className={`mono ${(maxProfit / maxRisk) >= 2 ? "text-emerald-400" : (maxProfit / maxRisk) >= 1 ? "text-amber-400" : "text-rose-400"}`}>
                  1:{((maxProfit / maxRisk))?.toFixed(2) ?? "—"}
                </span>
              </div>
            )}
          </div>
        );
      })()}

      {/* Save Button */}
      <button onClick={handleSave} className="btn w-full text-[11px]">
        + Save Trade Idea
      </button>

      {/* Saved Trades */}
      {savedTrades.length > 0 && (
        <div>
          <div className="label mb-1">Saved Trades ({savedTrades.length})</div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {savedTrades.map(trade => (
              <div key={trade.id} className="bg-slate-800/30 rounded px-2 py-1 text-[9px] flex justify-between items-center">
                <div>
                  <span className="font-bold text-slate-300">{trade.templateName}</span>
                  <span className="text-slate-500 ml-1">@ {trade.spot != null ? Math.round(trade.spot) : "—"}</span>
                </div>
                <div className="text-slate-600">
                  {trade.timestamp ? new Date(trade.timestamp).toLocaleTimeString() : "—"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
