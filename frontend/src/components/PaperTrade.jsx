import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { fmt, fmtAbs, pctClass } from "../lib/helpers";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function PaperTrade({ ticker, spot }) {
  const [portfolio, setPortfolio] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [form, setForm] = useState({
    symbol: ticker || "SPY",
    option_type: "call",
    strike: "",
    expiry: "",
    quantity: 1,
    is_long: true,
    entry_price: "",
  });
  const [costEstimate, setCostEstimate] = useState(null);

  const fetchPortfolio = useCallback(async () => {
    try {
      const [portRes, histRes] = await Promise.all([
        axios.get(`${API}/paper-trading/portfolio`),
        axios.get(`${API}/paper-trading/history?limit=20`),
      ]);
      setPortfolio(portRes.data);
      setHistory(histRes.data || []);
    } catch (e) {
      // Noop - portfolio may not exist yet
    }
  }, []);

  useEffect(() => {
    fetchPortfolio();
    const id = setInterval(fetchPortfolio, 15000);
    return () => clearInterval(id);
  }, [fetchPortfolio]);

  useEffect(() => {
    setForm(prev => ({ ...prev, symbol: ticker || "SPY" }));
  }, [ticker]);

  const estimateCost = useCallback(async () => {
    if (!form.strike || !form.expiry || !spot) return;
    try {
      const res = await axios.post(`${API}/paper-trading/estimate-cost`, {
        symbol: form.symbol,
        option_type: form.option_type,
        strike: parseFloat(form.strike),
        expiry: form.expiry,
        quantity: parseInt(form.quantity),
        is_long: form.is_long,
        spot: spot,
      });
      setCostEstimate(res.data);
    } catch (e) {
      setCostEstimate(null);
    }
  }, [form, spot]);

  useEffect(() => {
    const id = setTimeout(estimateCost, 500);
    return () => clearTimeout(id);
  }, [form.strike, form.expiry, form.quantity, form.option_type, estimateCost]);

  const submitOrder = async () => {
    if (!form.strike || !form.expiry || !form.quantity) return;
    setLoading(true);
    setErr(null);
    try {
      await axios.post(`${API}/paper-trading/execute`, {
        symbol: form.symbol,
        option_type: form.option_type,
        strike: parseFloat(form.strike),
        expiry: form.expiry,
        quantity: parseInt(form.quantity),
        is_long: form.is_long,
        spot: spot,
      });
      setForm(prev => ({ ...prev, strike: "", expiry: "", quantity: 1, entry_price: "" }));
      setCostEstimate(null);
      fetchPortfolio();
    } catch (e) {
      setErr(e.response?.data?.detail || e.message || "Order failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 max-w-7xl mx-auto">
        {/* Portfolio Summary */}
        <div className="lg:col-span-1">
          <div className="panel p-4">
            <div className="label mb-3">Portfolio Summary</div>
            {portfolio ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <div className="text-slate-500 text-[10px]">Cash</div>
                    <div className="mono text-lg text-emerald-400">${fmt(portfolio.cash, 0)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-[10px]">Total Value</div>
                    <div className="mono text-lg">${fmt(portfolio.total_value, 0)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-[10px]">P&L</div>
                    <div className={`mono text-lg ${portfolio.total_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {portfolio.total_pnl >= 0 ? "+" : ""}${fmt(portfolio.total_pnl, 0)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-[10px]">P&L %</div>
                    <div className={`mono text-lg ${portfolio.total_pnl_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {portfolio.total_pnl_pct >= 0 ? "+" : ""}{portfolio.total_pnl_pct.toFixed(2)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-[10px]">Open Positions</div>
                    <div className="mono">{portfolio.open_positions}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-[10px]">Total Trades</div>
                    <div className="mono">{portfolio.total_trades}</div>
                  </div>
                </div>

                {portfolio.positions?.length > 0 && (
                  <>
                    <div className="dotted-divider" />
                    <div className="label text-[10px]">Open Positions</div>
                    <div className="space-y-2">
                      {portfolio.positions.map((p, i) => (
                        <div key={i} className="bg-slate-800/40 rounded p-2 text-[11px]">
                          <div className="flex justify-between">
                            <span className={`font-bold ${p.is_long ? "text-emerald-400" : "text-rose-400"}`}>
                              {p.is_long ? "LONG" : "SHORT"} {p.quantity}x
                            </span>
                            <span className="text-slate-400">{p.symbol}</span>
                          </div>
                          <div className="flex justify-between mt-1">
                            <span className="text-slate-500">{p.option_type} {p.strike}</span>
                            <span className="text-slate-500">Exp: {p.expiry}</span>
                          </div>
                          <div className="flex justify-between mt-1">
                            <span className="text-slate-500">Entry: ${fmt(p.entry_price, 2)}</span>
                            <span className={`${p.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                              {p.pnl >= 0 ? "+" : ""}${fmt(p.pnl || 0, 0)}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="text-slate-500 text-xs">Loading portfolio...</div>
            )}
          </div>
        </div>

        {/* Order Entry */}
        <div className="lg:col-span-1">
          <div className="panel p-4">
            <div className="label mb-3">Place Trade</div>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-slate-500 text-[10px] block mb-1">Symbol</label>
                  <input
                    value={form.symbol}
                    onChange={e => setForm(prev => ({ ...prev, symbol: e.target.value }))}
                    className="btn w-full"
                    style={{ padding: "4px 8px", fontSize: "12px" }}
                  />
                </div>
                <div>
                  <label className="text-slate-500 text-[10px] block mb-1">Type</label>
                  <select
                    value={form.option_type}
                    onChange={e => setForm(prev => ({ ...prev, option_type: e.target.value }))}
                    className="btn w-full"
                    style={{ padding: "4px 8px", fontSize: "12px" }}
                  >
                    <option value="call">CALL</option>
                    <option value="put">PUT</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-slate-500 text-[10px] block mb-1">Strike</label>
                  <input
                    type="number"
                    value={form.strike}
                    onChange={e => setForm(prev => ({ ...prev, strike: e.target.value }))}
                    placeholder={spot ? `${spot.toFixed(0)}` : "Strike"}
                    className="btn w-full"
                    style={{ padding: "4px 8px", fontSize: "12px" }}
                  />
                </div>
                <div>
                  <label className="text-slate-500 text-[10px] block mb-1">Expiry (YYYY-MM-DD)</label>
                  <input
                    value={form.expiry}
                    onChange={e => setForm(prev => ({ ...prev, expiry: e.target.value }))}
                    placeholder="2026-06-20"
                    className="btn w-full"
                    style={{ padding: "4px 8px", fontSize: "12px" }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-slate-500 text-[10px] block mb-1">Quantity</label>
                  <input
                    type="number"
                    value={form.quantity}
                    onChange={e => setForm(prev => ({ ...prev, quantity: e.target.value }))}
                    min="1"
                    className="btn w-full"
                    style={{ padding: "4px 8px", fontSize: "12px" }}
                  />
                </div>
                <div>
                  <label className="text-slate-500 text-[10px] block mb-1">Direction</label>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setForm(prev => ({ ...prev, is_long: true }))}
                      className={`btn flex-1 ${form.is_long ? "active" : ""}`}
                      style={{ padding: "4px 8px", fontSize: "11px" }}
                    >
                      LONG
                    </button>
                    <button
                      onClick={() => setForm(prev => ({ ...prev, is_long: false }))}
                      className={`btn flex-1 ${!form.is_long ? "active" : ""}`}
                      style={{ padding: "4px 8px", fontSize: "11px" }}
                    >
                      SHORT
                    </button>
                  </div>
                </div>
              </div>

              <div>
                <label className="text-slate-500 text-[10px] block mb-1">Entry Price (auto if empty)</label>
                <input
                  type="number"
                  value={form.entry_price}
                  onChange={e => setForm(prev => ({ ...prev, entry_price: e.target.value }))}
                  placeholder="Leave empty for market"
                  className="btn w-full"
                  style={{ padding: "4px 8px", fontSize: "12px" }}
                />
              </div>

              {costEstimate && (
                <div className="bg-slate-800/60 rounded p-2 text-[11px] space-y-1">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Est. Cost</span>
                    <span className="mono text-slate-300">${fmt(costEstimate.estimated_cost || costEstimate.total_cost, 0)}</span>
                  </div>
                  {costEstimate.slippage && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Slippage</span>
                      <span className="mono text-amber-400">${fmt(costEstimate.slippage, 2)}</span>
                    </div>
                  )}
                  {costEstimate.kyle_impact && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Kyle Impact</span>
                      <span className="mono text-slate-400">{costEstimate.kyle_impact}bps</span>
                    </div>
                  )}
                </div>
              )}

              {err && (
                <div className="text-rose-400 text-[11px] bg-rose-500/10 rounded px-2 py-1.5 border border-rose-500/20">
                  {err}
                </div>
              )}

              <button
                onClick={submitOrder}
                disabled={loading || !form.strike || !form.expiry || !form.quantity}
                className="btn active w-full py-2 font-bold"
                style={{ opacity: loading || !form.strike || !form.expiry ? 0.5 : 1 }}
              >
                {loading ? "Submitting..." : `${form.is_long ? "BUY" : "SELL"} ${form.quantity}x ${form.symbol} ${form.option_type.toUpperCase()} @ ${form.strike || "?"}`}
              </button>
            </div>
          </div>
        </div>

        {/* Trade History */}
        <div className="lg:col-span-1">
          <div className="panel p-4">
            <div className="label mb-3">Trade History</div>
            {history.length > 0 ? (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {history.map((t, i) => (
                  <div key={i} className="bg-slate-800/40 rounded p-2 text-[11px]">
                    <div className="flex justify-between items-start">
                      <div>
                        <span className={`font-bold ${t.is_long ? "text-emerald-400" : "text-rose-400"}`}>
                          {t.is_long ? "LONG" : "SHORT"} {t.quantity}x
                        </span>
                        <span className="text-slate-400 ml-1">{t.symbol} {t.option_type} {t.strike}</span>
                      </div>
                      {t.pnl != null && (
                        <span className={`mono font-bold ${t.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                          {t.pnl >= 0 ? "+" : ""}${fmt(t.pnl, 0)}
                        </span>
                      )}
                    </div>
                    <div className="flex justify-between mt-1">
                      <span className="text-slate-500">Entry: ${fmt(t.entry_price, 2)}</span>
                      <span className="text-slate-500">Exp: {t.expiry}</span>
                    </div>
                    <div className="text-slate-600 text-[9px] mt-1">
                      {t.timestamp || t.ts || t.created_at || ""}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-slate-500 text-xs">No trades yet. Place your first order above!</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
