import React, { useState, useCallback } from "react";
import axios from "axios";
import { fmt, fmtAbs, pctClass } from "../lib/helpers";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ============ Position Sizing Widget ============
function PositionSizing({ spot }) {
  const [accountSize, setAccountSize] = useState("100000");
  const [riskPct, setRiskPct] = useState("0.02");
  const [gexLevel, setGexLevel] = useState("0");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const calcSize = async () => {
    if (!spot) return;
    setLoading(true);
    try {
      const res = await axios.post(`${API}/position-size`, null, {
        params: {
          account_size: parseFloat(accountSize),
          risk_per_trade_pct: parseFloat(riskPct),
          spot,
          gex_level: parseFloat(gexLevel) || 0,
        },
      });
      setResult(res.data);
    } catch (e) {
      console.error("Position sizing failed:", e);
    }
    setLoading(false);
  };

  const inputCls = "w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none";

  return (
    <div className="panel p-3">
      <div className="label mb-2">Position Sizing</div>
      <div className="grid grid-cols-3 gap-1.5 mb-2">
        <div>
          <div className="label mb-0.5">Account $</div>
          <input type="number" className={inputCls} value={accountSize} onChange={(e) => setAccountSize(e.target.value)} />
        </div>
        <div>
          <div className="label mb-0.5">Risk %</div>
          <input type="number" step="0.005" className={inputCls} value={riskPct} onChange={(e) => setRiskPct(e.target.value)} />
        </div>
        <div>
          <div className="label mb-0.5">GEX Level</div>
          <input type="number" className={inputCls} value={gexLevel} onChange={(e) => setGexLevel(e.target.value)} placeholder="0" />
        </div>
      </div>
      <button onClick={calcSize} className="btn w-full text-[10px]" disabled={loading || !spot}>
        {loading ? "…" : "Calculate Size"}
      </button>
      {result && (
        <div className="mt-2 space-y-0.5 text-[10px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Contracts</span>
            <span className="mono font-bold text-slate-300">{result.recommended_contracts}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Position Value</span>
            <span className="mono text-slate-300">${fmt(result.position_value, 0)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">% of Account</span>
            <span className="mono text-slate-300">{result.position_pct_of_account}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Risk Amount</span>
            <span className="mono text-amber-400">${fmt(result.risk_per_trade, 0)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">GEX Factor</span>
            <span className="mono text-slate-400">{result.gex_factor}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ============ Position Entry Form ============
function PositionForm({ onAdd }) {
  const [form, setForm] = useState({
    symbol: "SPY", option_type: "call", strike: "", expiry: "",
    quantity: "1", entry_price: "", entry_iv: "", underlying_price: "",
  });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = (e) => {
    e.preventDefault();
    const qty = parseInt(form.quantity) * (form.option_type === "put" ? -1 : 1);
    onAdd({
      ...form,
      strike: parseFloat(form.strike),
      quantity: qty,
      entry_price: parseFloat(form.entry_price),
      entry_iv: parseFloat(form.entry_iv),
      underlying_price: parseFloat(form.underlying_price),
    });
    setForm({ symbol: form.symbol, option_type: "call", strike: "", expiry: "", quantity: "1", entry_price: "", entry_iv: "", underlying_price: "" });
  };

  const inputCls = "w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none";

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="grid grid-cols-2 gap-1.5">
        <div>
          <div className="label mb-0.5">Symbol</div>
          <input className={inputCls} value={form.symbol} onChange={(e) => set("symbol", e.target.value.toUpperCase())} />
        </div>
        <div>
          <div className="label mb-0.5">Type</div>
          <select className={inputCls} value={form.option_type} onChange={(e) => set("option_type", e.target.value)}>
            <option value="call">Call</option>
            <option value="put">Put</option>
          </select>
        </div>
        <div>
          <div className="label mb-0.5">Strike</div>
          <input type="number" step="0.5" className={inputCls} value={form.strike} onChange={(e) => set("strike", e.target.value)} required />
        </div>
        <div>
          <div className="label mb-0.5">Expiry</div>
          <input type="date" className={inputCls} value={form.expiry} onChange={(e) => set("expiry", e.target.value)} required />
        </div>
        <div>
          <div className="label mb-0.5">Qty (contracts)</div>
          <input type="number" className={inputCls} value={form.quantity} onChange={(e) => set("quantity", e.target.value)} required />
        </div>
        <div>
          <div className="label mb-0.5">Entry $</div>
          <input type="number" step="0.01" className={inputCls} value={form.entry_price} onChange={(e) => set("entry_price", e.target.value)} required />
        </div>
        <div>
          <div className="label mb-0.5">Entry IV</div>
          <input type="number" step="0.001" placeholder="0.15" className={inputCls} value={form.entry_iv} onChange={(e) => set("entry_iv", e.target.value)} required />
        </div>
        <div>
          <div className="label mb-0.5">Spot @ Entry</div>
          <input type="number" step="0.01" className={inputCls} value={form.underlying_price} onChange={(e) => set("underlying_price", e.target.value)} required />
        </div>
      </div>
      <button type="submit" className="btn w-full text-[11px]">+ Add Position</button>
    </form>
  );
}

// ============ CSV Export Helper ============
function sanitizeCSVField(value) {
  const s = value == null ? "" : String(value);
  // Prevent CSV/Excel injection: prefix dangerous characters with single quote
  if (s && /^[=+\-@]/.test(s)) {
    return "'" + s;
  }
  return s;
}

function downloadCSV(filename, headers, rows) {
  const csv = [headers.join(","), ...rows.map(r => headers.map(h => {
    const s = sanitizeCSVField(r[h]);
    return s.includes(",") || s.includes('"') || s.includes("\n") ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
// ============ Greeks Summary Bar ============
function GreeksBar({ greeks }) {
  const items = [
    { k: "delta", label: "Δ" },
    { k: "gamma", label: "Γ" },
    { k: "vega", label: "V" },
    { k: "theta", label: "Θ" },
    { k: "vanna", label: "Va" },
    { k: "charm", label: "Ch" },
    { k: "vomma", label: "Vo" },
    { k: "zomma", label: "Zo" },
  ];
  return (
    <div className="grid grid-cols-4 gap-x-3 gap-y-0.5 text-[10px]">
      {items.map(({ k, label }) => {
        const v = greeks[k];
        if (v === undefined || v === null) return null;
        const color = v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-slate-400";
        return (
          <div key={k} className="flex justify-between">
            <span className="text-slate-500">{label}</span>
            <span className={`mono font-bold ${color}`}>{typeof v === "number" ? v.toFixed(2) : v}</span>
          </div>
        );
      })}
    </div>
  );
}

// ============ Scenario Table ============
function ScenarioTable({ scenarios }) {
  if (!scenarios?.length) return null;
  const spotScenarios = scenarios.filter((s) => s.type === "spot");
  const volScenarios = scenarios.filter((s) => s.type === "vol");

  return (
    <div className="space-y-2">
      {spotScenarios.length > 0 && (
        <div>
          <div className="label mb-1">Spot Scenarios</div>
          <table className="w-full text-[10px] mono">
            <thead>
              <tr className="text-slate-500">
                <th className="text-left px-1">Shock</th>
                <th className="text-right px-1">Spot</th>
                <th className="text-right px-1">P&L</th>
                <th className="text-right px-1">Delta</th>
              </tr>
            </thead>
            <tbody>
              {spotScenarios.map((s, i) => (
                <tr key={i} className="border-t border-slate-800/40">
                  <td className="px-1 py-0.5">{s.shock_pct > 0 ? "+" : ""}{s.shock_pct.toFixed(0)}%</td>
                  <td className="text-right px-1 py-0.5 text-slate-300">{fmt(s.spot, 1)}</td>
                  <td className={`text-right px-1 py-0.5 ${s.pnl > 0 ? "text-emerald-400" : s.pnl < 0 ? "text-rose-400" : "text-slate-400"}`}>{fmt(s.pnl, 0)}</td>
                  <td className="text-right px-1 py-0.5 text-slate-400">{s.delta?.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {volScenarios.length > 0 && (
        <div>
          <div className="label mb-1">Vol Scenarios</div>
          <table className="w-full text-[10px] mono">
            <thead>
              <tr className="text-slate-500">
                <th className="text-left px-1">Shock</th>
                <th className="text-right px-1">IV</th>
                <th className="text-right px-1">P&L</th>
                <th className="text-right px-1">Vega</th>
              </tr>
            </thead>
            <tbody>
              {volScenarios.map((s, i) => (
                <tr key={i} className="border-t border-slate-800/40">
                  <td className="px-1 py-0.5">{s.shock_pct > 0 ? "+" : ""}{s.shock_pct.toFixed(0)}%</td>
                  <td className="text-right px-1 py-0.5 text-slate-300">{(s.iv * 100).toFixed(1)}%</td>
                  <td className={`text-right px-1 py-0.5 ${s.pnl > 0 ? "text-emerald-400" : s.pnl < 0 ? "text-rose-400" : "text-slate-400"}`}>{fmt(s.pnl, 0)}</td>
                  <td className="text-right px-1 py-0.5 text-slate-400">{s.vega?.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============ Hedge Result ============
function HedgeResult({ result }) {
  if (!result) return null;
  if (result.error) return <div className="text-rose-400 text-[10px]">{typeof result.error === 'string' ? result.error : JSON.stringify(result.error)}</div>;
  return (
    <div className="space-y-1.5 text-[10px]">
      <div className="label">Gamma/Vega Neutral Hedge</div>
      {result.hedge_positions?.map((hp, i) => (
        <div key={i} className="flex justify-between items-center">
          <span className="text-slate-400">{hp.direction} {Math.abs(hp.contracts)}x {hp.option.type} {hp.option.strike} {hp.option.expiry}</span>
        </div>
      ))}
      <div className="flex justify-between">
        <span className="text-slate-500">Stock Hedge</span>
        <span className={`mono font-bold ${result.stock_hedge > 0 ? "text-emerald-400" : "text-rose-400"}`}>
          {result.stock_hedge > 0 ? "BUY" : "SELL"} {Math.abs(result.stock_hedge)} shares
        </span>
      </div>
      <div className="dotted-divider" />
      <div className="label">Resulting Greeks</div>
      <div className="grid grid-cols-3 gap-1">
        {Object.entries(result.resulting_greeks || {}).map(([k, v]) => (
          <div key={k} className="text-center">
            <div className="text-slate-500 uppercase">{k}</div>
            <div className={`mono font-bold ${v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-slate-300"}`}>{typeof v === "number" ? v.toFixed(1) : v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============ Main Portfolio Panel ============
export default function PortfolioPanel({ ticker, spot }) {
  const [portfolioName] = useState("main");
  const [positions, setPositions] = useState([]);
  const [portfolioData, setPortfolioData] = useState(null);
  const [scenarios, setScenarios] = useState(null);
  const [hedgeResult, setHedgeResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("positions");
  const [spotInput, setSpotInput] = useState("");
  const [ivInput, setIvInput] = useState("0.15");

  const currentSpot = parseFloat(spotInput) || spot || 0;
  const currentIv = parseFloat(ivInput) || 0.15;

  const refreshPortfolio = useCallback(async () => {
    if (!currentSpot) return;
    try {
      const res = await axios.get(`${API}/portfolio/${portfolioName}`, {
        params: { spot: currentSpot, iv: currentIv },
      });
      setPortfolioData(res.data);
    } catch (e) {
      // Portfolio might not exist yet
    }
  }, [portfolioName, currentSpot, currentIv]);

  const addPosition = async (posData) => {
    setLoading(true);
    try {
      await axios.post(`${API}/portfolio/${portfolioName}/position`, posData);
      setPositions((p) => [...p, posData]);
      await refreshPortfolio();
    } catch (e) {
      console.error("Failed to add position:", e);
    }
    setLoading(false);
  };

  const removePosition = async (index) => {
    setLoading(true);
    try {
      await axios.delete(`${API}/portfolio/${portfolioName}/position/${index}`);
      setPositions((p) => p.filter((_, i) => i !== index));
      await refreshPortfolio();
    } catch (e) {
      console.error("Failed to remove position:", e);
    }
    setLoading(false);
  };

  const runScenarios = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/portfolio/${portfolioName}/scenario`, {
        params: { spot: currentSpot, iv: currentIv },
      });
      setScenarios(res.data.scenarios);
      setActiveTab("scenarios");
    } catch (e) {
      console.error("Scenario failed:", e);
      // Show a friendlier error for common issues
      if (e.response?.status === 503) {
        setScenarios({ _error: "Auth not configured. Add positions manually to enable analysis." });
      } else {
        setScenarios({ _error: `API error: ${e.response?.data?.detail || e.message}` });
      }
    }
    setLoading(false);
  };

  const calcHedge = async () => {
    setLoading(true);
    try {
      // Build hedge options from current positions' strikes + nearby
      const strikes = [...new Set(positions.map((p) => p.strike))];
      const expiries = [...new Set(positions.map((p) => p.expiry))];
      const hedgeOptions = [];
      if (strikes.length > 0 && expiries.length > 0) {
        for (const s of strikes.slice(0, 2)) {
          for (const exp of expiries.slice(0, 1)) {
            hedgeOptions.push({ strike: s, expiry: exp, type: "call", iv: currentIv });
            hedgeOptions.push({ strike: s, expiry: exp, type: "put", iv: currentIv });
          }
        }
      }
      const res = await axios.post(`${API}/portfolio/${portfolioName}/hedge`, {
        spot: currentSpot || 530,
        iv: currentIv || 0.15,
        hedge_options: hedgeOptions.length > 0 ? hedgeOptions.slice(0, 4) : [
          { strike: 525, expiry: "2026-06-20", type: "call", iv: currentIv || 0.15 },
          { strike: 525, expiry: "2026-06-20", type: "put", iv: currentIv || 0.15 },
          { strike: 535, expiry: "2026-06-20", type: "call", iv: currentIv || 0.15 },
          { strike: 535, expiry: "2026-06-20", type: "put", iv: currentIv || 0.15 },
        ],
      });
      setHedgeResult(res.data);
      setActiveTab("hedge");
    } catch (e) {
      console.error("Hedge calc failed:", e);
      setHedgeResult({ error: `Calculation failed: ${e.response?.data?.detail || e.message}` });
    }
    setLoading(false);
  };

  const pnl = portfolioData?.pnl;
  const greeks = portfolioData?.greeks;

  return (
    <div className="p-4 flex-1 overflow-auto">
      <div className="max-w-5xl mx-auto space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-bold tracking-wider">PORTFOLIO</div>
            <div className="text-[10px] text-slate-500">Position tracking · Greek aggregation · Scenario analysis · Hedge calculator</div>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-[10px] text-slate-500">Spot:</div>
            <input
              type="number" step="0.01" value={spotInput}
              onChange={(e) => setSpotInput(e.target.value)}
              placeholder={spot ? String(spot) : "0"}
              className="w-20 bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
            />
            <div className="text-[10px] text-slate-500">IV:</div>
            <input
              type="number" step="0.001" value={ivInput}
              onChange={(e) => setIvInput(e.target.value)}
              className="w-16 bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
            />
            <button onClick={refreshPortfolio} className="btn text-[10px]" disabled={loading}>Refresh</button>
          </div>
        </div>

        {/* P&L Summary */}
        {pnl && (
          <div className="panel p-3">
            <div className="grid grid-cols-4 gap-3 text-center">
              <div>
                <div className="label">Total P&L</div>
                <div className={`text-xl mono font-bold ${pnl.total_pnl > 0 ? "text-emerald-400" : pnl.total_pnl < 0 ? "text-rose-400" : "text-slate-300"}`}>
                  {pnl.total_pnl > 0 ? "+" : ""}{fmt(pnl.total_pnl, 0)}
                </div>
              </div>
              <div>
                <div className="label">P&L %</div>
                <div className={`text-xl mono font-bold ${pctClass(pnl.pct_pnl)}`}>
                  {pnl.pct_pnl > 0 ? "+" : ""}{pnl.pct_pnl}%
                </div>
              </div>
              <div>
                <div className="label">Entry Value</div>
                <div className="text-lg mono text-slate-300">{fmt(pnl.total_entry_value, 0)}</div>
              </div>
              <div>
                <div className="label">Current Value</div>
                <div className="text-lg mono text-slate-300">{fmt(pnl.total_current_value, 0)}</div>
              </div>
            </div>
          </div>
        )}

        {/* Aggregated Greeks */}
        {greeks && (
          <div className="panel p-3">
            <div className="label mb-2">Aggregated Greeks</div>
            <GreeksBar greeks={greeks} />
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1">
          {["positions", "scenarios", "hedge"].map((t) => (
            <button key={t} onClick={() => setActiveTab(t)} className={`btn ${activeTab === t ? "active" : ""}`}>
              {t === "positions" ? "Positions" : t === "scenarios" ? "Scenarios" : "Hedge"}
            </button>
          ))}
        </div>

        {/* Positions Tab */}
        {activeTab === "positions" && (
          <div className="space-y-2">
            <div className="panel p-3">
              <div className="label mb-2">Add Position</div>
              <PositionForm onAdd={addPosition} />
            </div>

            {positions.length > 0 ? (
              <div className="panel p-3">
                <div className="flex justify-between items-center mb-2">
                  <div className="label mb-0">Open Positions ({positions.length})</div>
                  {positions.length > 0 && (
                    <button
                      onClick={() => downloadCSV(
                        `portfolio_${portfolioName}_${new Date().toISOString().slice(0,10)}.csv`,
                        ["symbol","type","strike","expiry","qty","entry_price","entry_iv","underlying_price"],
                        positions.map(p => ({ symbol: p.symbol, type: p.option_type, strike: p.strike, expiry: p.expiry, qty: p.quantity, entry_price: p.entry_price, entry_iv: p.entry_iv, underlying_price: p.underlying_price }))
                      )}
                      className="btn text-[9px] px-2 py-0.5"
                    >Export CSV</button>
                  )}
                </div>
                <table className="w-full text-[11px] mono">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                      <th className="text-left px-2 py-1">Symbol</th>
                      <th className="text-left px-2 py-1">Type</th>
                      <th className="text-right px-2 py-1">Strike</th>
                      <th className="text-left px-2 py-1">Expiry</th>
                      <th className="text-right px-2 py-1">Qty</th>
                      <th className="text-right px-2 py-1">Entry $</th>
                      <th className="text-right px-2 py-1">IV</th>
                      <th className="text-right px-2 py-1">Spot</th>
                      <th className="px-2 py-1"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p, i) => (
                      <tr key={i} className="border-t border-slate-800/60 bar-row">
                        <td className="px-2 py-1 font-bold">{p.symbol}</td>
                        <td className={`px-2 py-1 ${p.option_type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{p.option_type}</td>
                        <td className="text-right px-2 py-1">{p.strike}</td>
                        <td className="px-2 py-1 text-slate-400">{p.expiry}</td>
                        <td className="text-right px-2 py-1">{p.quantity}</td>
                        <td className="text-right px-2 py-1">{p.entry_price}</td>
                        <td className="text-right px-2 py-1 text-slate-400">{(p.entry_iv * 100).toFixed(1)}%</td>
                        <td className="text-right px-2 py-1 text-slate-400">{p.underlying_price}</td>
                        <td className="px-2 py-1">
                          <button onClick={() => removePosition(i)} className="text-rose-400 hover:text-rose-300 text-[10px]" aria-label={`Remove position ${i}`}>✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="panel p-6 text-center text-slate-500 text-[11px]">
                No positions yet. Add your first position above.
              </div>
            )}
          </div>
        )}

        {/* Scenarios Tab */}
        {activeTab === "scenarios" && (
          <div className="space-y-2">              <button onClick={runScenarios} className="btn w-full" disabled={loading}>
              {loading ? "Running…" : "Run Scenario Analysis"}
            </button>
            {scenarios && <ScenarioTable scenarios={scenarios} />}
            {!scenarios && (
              <div className="panel p-4 text-center text-slate-500 text-[10px]">
                Click "Run Scenario Analysis" to see spot/vol shock P&L
              </div>
            )}
            {scenarios?._error && (
              <div className="panel p-3 text-center text-amber-400 text-[10px]">{scenarios._error}</div>
            )}
          </div>
        )}

        {/* Hedge Tab */}
        {activeTab === "hedge" && (
          <div className="space-y-2">              <button onClick={calcHedge} className="btn w-full" disabled={loading}>
              {loading ? "Calculating…" : "Calculate Greek-Neutral Hedge"}
            </button>
            {hedgeResult && <div className="panel p-3"><HedgeResult result={hedgeResult} /></div>}
            {!hedgeResult && (
              <div className="panel p-4 text-center text-slate-500 text-[10px]">
                Click "Calculate Greek-Neutral Hedge" to see gamma/vega neutralization
              </div>
            )}
          </div>
        )}

        {/* Position Sizing */}
        {activeTab === "positions" && (
          <PositionSizing spot={currentSpot} />
        )}

        {/* Quick Actions */}
        {activeTab === "positions" && positions.length > 0 && (
          <div className="panel p-3">
            <div className="label mb-2">Quick Actions</div>
            <div className="flex gap-1">
              <button onClick={runScenarios} className="btn flex-1 text-[10px]" disabled={loading}>Scenarios</button>
              <button onClick={calcHedge} className="btn flex-1 text-[10px]" disabled={loading}>Hedge</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
