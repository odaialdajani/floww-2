import React, { useState, useEffect, useCallback } from "react";
import { fmt } from "../lib/helpers";
import { strategyRiskReward, effectiveOptionPrice, formatNotional, ticketToJournalEntries, JOURNAL_STORAGE_KEY, legQuote } from "./tradeMath";
import { API } from "../config/api";

/**
 * Quick Trade Panel — slide-up panel for rapid trade entry from Triad
 *
 * Triggered by clicking any strike row in TrinityView.
 * Pre-populates with strike, spot, GEX data.
 * Supports: Buy Call, Buy Put, Sell Call, Sell Put, Iron Condor, Straddle
 */

const STRATEGIES = [
  { id: "buy_call", label: "Buy Call", icon: "▲", color: "#34d399" },
  { id: "buy_put", label: "Buy Put", icon: "▼", color: "#f87171" },
  { id: "sell_call", label: "Sell Call", icon: "▽", color: "#c4b5fd" },
  { id: "sell_put", label: "Sell Put", icon: "△", color: "#c4b5fd" },
  { id: "iron_condor", label: "Iron Condor", icon: "◆", color: "#fbbf24" },
  { id: "straddle", label: "Straddle", icon: "◇", color: "#38bdf8" },
];

export default function QuickTradePanel({ selection, onClose, onSubmit }) {
  const [strategy, setStrategy] = useState("buy_call");
  const [quantity, setQuantity] = useState(1);
  const [limitPrice, setLimitPrice] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [wings, setWings] = useState({ put_long: "", put_short: "", call_short: "", call_long: "", credit: "" });
  const [backendSha, setBackendSha] = useState("");

  const [submitted, setSubmitted] = useState(false);

  // Reset when selection changes
  useEffect(() => {
    setStrategy("buy_call");
    setQuantity(1);
    setLimitPrice("");
    setShowConfirm(false);
    setSubmitted(false);
  }, [selection?.strike]);

  // Prefill condor wings around the clicked strike; fetch backend SHA once
  // for the freshness stamp.
  useEffect(() => {
    if (selection?.strike != null && strategy === "iron_condor" && !wings.call_short) {
      const k = Math.round(Number(selection.strike) || 0);
      setWings(w => ({ ...w, put_long: k - 10, put_short: k - 5, call_short: k, call_long: k + 5 }));
    }
  }, [selection?.strike, strategy]);
  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/version`).then(r => r.json()).then(d => {
      if (!cancelled && d?.sha) setBackendSha(d.sha);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const setWing = (key, val) => setWings(prev => ({ ...prev, [key]: val }));

  const handleSubmit = useCallback(() => {
    if (!selection) return;
    const W = strategy === "iron_condor" ? wings : undefined;
    const { price: effectivePrice, source: priceSource } = effectiveOptionPrice(selection, strategy, limitPrice, W);
    const trade = {
      ticker: selection.ticker,
      strike: selection.strike,
      spot: selection.spot,
      expiry: selection.expiry ?? null,
      strategy,
      quantity,
      limitPrice: limitPrice ? parseFloat(limitPrice) : null,
      effectivePrice: Number.isFinite(effectivePrice) ? effectivePrice : null,
      priceSource,
      wings: W,
      gex: selection.gex,
      iv: selection.iv,
      delta: selection.delta,
      oi: selection.oi,
      oi_symbol: selection.oi_symbol ?? null,
      call_bid: selection.call_bid, call_ask: selection.call_ask, call_last: selection.call_last,
      put_bid: selection.put_bid, put_ask: selection.put_ask, put_last: selection.put_last,
      timestamp: new Date().toISOString(),
    };
    // Journal first: every confirmed ticket lands in the store TradeJournal
    // + TradeAnalytics read. Previously non-OSI tickets were dropped by the
    // App-level submit handler and never appeared anywhere.
    try {
      const entries = ticketToJournalEntries(trade).map(e => ({
        ...e, id: e.id ?? Date.now() + Math.floor(Math.random() * 1000),
        created_at: new Date().toISOString(),
      }));
      const saved = JSON.parse(localStorage.getItem(JOURNAL_STORAGE_KEY) || "[]");
      localStorage.setItem(JOURNAL_STORAGE_KEY, JSON.stringify([...entries, ...saved]));
    } catch (e) { console.error("[QuickTrade] journal write failed:", e); }
    setSubmitted(true);
    if (onSubmit) onSubmit(trade);
    // Auto-close after showing success
    setTimeout(() => {
      if (onClose) onClose();
    }, 1500);
  }, [selection, strategy, quantity, limitPrice, wings, onSubmit, onClose]);

  if (!selection) return null;

  const { ticker, strike, spot, gex, iv, delta, oi, call_gex, put_gex, vex, charm } = selection;
  const isCall = strategy.includes("call") || strategy === "straddle" || strategy === "iron_condor";
  const isBuy = strategy.startsWith("buy");

  // Effective premium: limit > side-aware executable side (buys at ask,
  // sells at bid; straddle sums asks; condor needs credit) > IV estimate.
  const W = strategy === "iron_condor" ? wings : undefined;
  const quote = effectiveOptionPrice(selection, strategy, "", W);
  const estNum = quote.price;
  const estPrice = Number.isFinite(estNum) ? estNum.toFixed(2) : "—";
  const live = effectiveOptionPrice(selection, strategy, limitPrice, W);
  const effNum = live.price;
  const hasPrice = Number.isFinite(effNum);
  const srcLabel = { limit: "", ask: " (ask)", bid: " (bid)", "ask-sum": " (asks)", "ref-sum": " (ref)", mid: " (mid)", last: " (last)", iv: " (est)", credit: " (credit)", none: "" }[live.source] ?? "";
  // Risk follows the price the order will actually use (limit wins), so
  // typing a limit rescues risk/reward on quoteless strikes instead of "—".
  const { maxRisk, maxReward } = strategyRiskReward(strategy, effNum, quantity, strike, W);
  const notional = formatNotional(effNum, quantity);
  const callQ = legQuote(selection, "call");
  const putQ = legQuote(selection, "put");
  const bundleSha = (typeof process !== "undefined" && process.env?.REACT_APP_GIT_SHA) || "dev";
  const stale = backendSha && bundleSha !== "dev" && backendSha !== bundleSha;

  const fmtGex = (v) => {
    if (v == null) return "—";
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(1) + "K";
    return v.toFixed(0);
  };

  return (
    <div className="quick-trade-overlay" onClick={onClose}>
      <div className="quick-trade-panel" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="quick-trade-header">
          <div className="quick-trade-title">
            <span className="quick-trade-ticker">{ticker.replace("^", "")}</span>
            <span className="quick-trade-strike">@{fmt(strike, 0)}</span>
            <span className={`quick-trade-gex ${gex >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {gex >= 0 ? "+" : ""}{(gex / 1e3).toFixed(1)}K GEX
            </span>
          </div>
          <button className="quick-trade-close" onClick={onClose}>✕</button>
        </div>

        {/* Spot + context */}
        <div className="quick-trade-context">
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Spot</span>
            <span className="quick-trade-stat-value">${fmt(spot, 2)}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Distance</span>
            <span className={`quick-trade-stat-value ${strike >= spot ? "text-emerald-400" : "text-rose-400"}`}>
              {strike >= spot ? "+" : ""}{((strike - spot) / spot * 100).toFixed(2)}%
            </span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">IV</span>
            <span className="quick-trade-stat-value text-indigo-400">{iv ? `${(iv * 100).toFixed(1)}%` : "—"}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Delta</span>
            <span className="quick-trade-stat-value">{delta ? delta.toFixed(2) : "—"}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">OI</span>
            <span className="quick-trade-stat-value text-slate-400">{oi ? fmtGex(oi) : "—"}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">VEX</span>
            <span className={`quick-trade-stat-value ${vex >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {vex != null ? fmtGex(vex) : "—"}
            </span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Charm</span>
            <span className={`quick-trade-stat-value ${charm >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {charm != null ? fmtGex(charm) : "—"}
            </span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Call GEX</span>
            <span className="quick-trade-stat-value text-emerald-400">{call_gex != null ? fmtGex(call_gex) : "—"}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Put GEX</span>
            <span className="quick-trade-stat-value text-rose-400">{put_gex != null ? fmtGex(put_gex) : "—"}</span>
          </div>
        </div>

        {/* Strategy selector */}
        <div className="quick-trade-strategies">
          {STRATEGIES.map(s => (
            <button
              key={s.id}
              className={`quick-trade-strategy-btn${strategy === s.id ? " quick-trade-strategy-active" : ""}`}
              onClick={() => setStrategy(s.id)}
              style={{ "--strategy-color": s.color }}
            >
              <span className="quick-trade-strategy-icon">{s.icon}</span>
              <span className="quick-trade-strategy-label">{s.label}</span>
            </button>
          ))}
        </div>

        {/* Order details */}
        <div className="quick-trade-details">
          <div className="quick-trade-row">
            <label>Qty (contracts)</label>
            <input
              type="number"
              min={1}
              max={100}
              value={quantity}
              onChange={e => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
              className="quick-trade-input"
            />
          </div>
          <div className="quick-trade-row">
            <label>Limit Price</label>
            <input
              type="number"
              step="0.01"
              placeholder={Number.isFinite(estNum) ? estPrice : "Enter limit — no quote"}
              value={limitPrice}
              onChange={e => setLimitPrice(e.target.value)}
              className="quick-trade-input"
            />
          </div>
        </div>

        {/* Iron condor wing builder */}
        {strategy === "iron_condor" && (
          <div className="quick-trade-details">
            <div className="quick-trade-row">
              <label>Put long / short</label>
              <div style={{ display: "flex", gap: 6 }}>
                <input type="number" step="1" value={wings.put_long} onChange={e => setWing("put_long", e.target.value)} className="quick-trade-input" placeholder="long" />
                <input type="number" step="1" value={wings.put_short} onChange={e => setWing("put_short", e.target.value)} className="quick-trade-input" placeholder="short" />
              </div>
            </div>
            <div className="quick-trade-row">
              <label>Call short / long</label>
              <div style={{ display: "flex", gap: 6 }}>
                <input type="number" step="1" value={wings.call_short} onChange={e => setWing("call_short", e.target.value)} className="quick-trade-input" placeholder="short" />
                <input type="number" step="1" value={wings.call_long} onChange={e => setWing("call_long", e.target.value)} className="quick-trade-input" placeholder="long" />
              </div>
            </div>
            <div className="quick-trade-row">
              <label>Expected credit</label>
              <input type="number" step="0.01" value={wings.credit} onChange={e => setWing("credit", e.target.value)} className="quick-trade-input" placeholder="net credit" />
            </div>
          </div>
        )}

        {/* Risk summary */}
        <div className="quick-trade-risk">
          <div className="quick-trade-risk-row">
            <span>Est. Price</span>
            <span className="text-amber-400">
              {hasPrice ? `$${effNum.toFixed(2)}${srcLabel}` : (strategy === "iron_condor" ? "— enter credit" : "— enter limit")}
            </span>
          </div>
          {strategy === "straddle" && Number.isFinite(callQ.ask) && Number.isFinite(putQ.ask) && (
            <div className="quick-trade-risk-row">
              <span>Legs</span>
              <span className="text-slate-400">C ${callQ.ask.toFixed(2)} + P ${putQ.ask.toFixed(2)}</span>
            </div>
          )}
          <div className="quick-trade-risk-row">
            <span>Max Risk</span>
            <span className="text-rose-400">{maxRisk}</span>
          </div>
          <div className="quick-trade-risk-row">
            <span>Max Reward</span>
            <span className="text-emerald-400">{maxReward}</span>
          </div>
          <div className="quick-trade-risk-row">
            <span>Notional</span>
            <span className="text-slate-300">
              {notional}
            </span>
          </div>
        </div>

        {/* Submit */}
        {submitted ? (
          <div className="quick-trade-success">
            <div className="quick-trade-success-icon">✓</div>
            <div className="quick-trade-success-text">Trade Recorded</div>
            <div className="quick-trade-success-sub">
              {STRATEGIES.find(s => s.id === strategy)?.label} × {quantity} @ ${hasPrice ? effNum.toFixed(2) : "—"} · saved to journal
            </div>
          </div>
        ) : !showConfirm ? (
          <button
            className="quick-trade-submit"
            onClick={() => hasPrice && setShowConfirm(true)}
            disabled={!hasPrice}
            title={hasPrice ? "" : "No market quote or IV for this strike — enter a limit price"}
            style={{
              background: !hasPrice
                ? "#334155"
                : isBuy
                  ? "linear-gradient(135deg, #16a34a, #22c55e)"
                  : "linear-gradient(135deg, #dc2626, #ef4444)",
              opacity: hasPrice ? 1 : 0.55,
              cursor: hasPrice ? "pointer" : "not-allowed",
            }}
          >
            {hasPrice
              ? `Review ${STRATEGIES.find(s => s.id === strategy)?.label} × ${quantity}`
              : "Enter limit price to review"}
          </button>
        ) : (
          <div className="quick-trade-confirm">
            <p className="quick-trade-confirm-text">
              {isBuy ? "Buy" : "Sell"} {quantity} contract{quantity > 1 ? "s" : ""}{" "}
              {ticker.replace("^", "")} {fmt(strike, 0)} {strategy.includes("call") ? "Call" : strategy.includes("put") ? "Put" : ""}{" "}
              @ ${hasPrice ? effNum.toFixed(2) : "—"}?
            </p>
            <div className="quick-trade-confirm-btns">
              <button className="quick-trade-cancel" onClick={() => setShowConfirm(false)}>Cancel</button>
              <button className="quick-trade-confirm-btn" onClick={handleSubmit}>
                ✓ Confirm Order
              </button>
            </div>
          </div>
        )}
        {/* Freshness stamp: bundle SHA vs backend SHA */}
        <div className="quick-trade-risk-row" style={{ marginTop: 6 }}>
          <span className="text-slate-600">build {bundleSha}{backendSha ? ` · api ${backendSha}` : ""}</span>
          {stale
            ? <span className="text-rose-400">stale — rebuild frontend</span>
            : <span className="text-slate-600">fresh</span>}
        </div>
      </div>
    </div>
  );
}
