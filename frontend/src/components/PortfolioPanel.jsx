import React, { useState, useCallback, useEffect, useRef } from "react";
import axios from "axios";
import { fmt, fmtAbs, pctClass } from "../lib/helpers";
import { BACKEND_URL, API } from "../config/api";

// BACKEND_URL and API imported from config/api.js

const describeError = (error) =>
  error?.response?.data?.detail || error?.message || "request failed";

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
  const [scenarioStatus, setScenarioStatus] = useState(null);
  const [hedgeStatus, setHedgeStatus] = useState(null);
  const [readState, setReadState] = useState({
    phase: "idle", generation: 0, bookGeneration: 0, pricedGeneration: 0, message: null,
  });
  const [actionStatus, setActionStatus] = useState(null);
  const readGeneration = useRef(0);

  const currentSpot = parseFloat(spotInput) || spot || 0;
  const currentIv = parseFloat(ivInput) || 0.15;

  const readStoredBook = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/portfolio/${portfolioName}`);
      const data = res?.data;
      if (!data || typeof data !== "object") {
        return { ok: false, missing: false, error: new Error("stored book response was empty") };
      }
      if (!Array.isArray(data.positions)) {
        return { ok: false, missing: false, error: new Error("stored book carried no positions list") };
      }
      return { ok: true, positions: data.positions, revision: data.book_revision };
    } catch (e) {
      return { ok: false, missing: e?.response?.status === 404, error: e };
    }
  }, [portfolioName]);

  const readPricedBook = useCallback(async () => {
    if (!currentSpot) return { ok: false, skipped: true, error: null };
    try {
      const res = await axios.get(`${API}/portfolio/${portfolioName}`, {
        params: { spot: currentSpot, iv: currentIv },
      });
      return { ok: true, data: res?.data };
    } catch (e) {
      return { ok: false, skipped: false, error: e };
    }
  }, [portfolioName, currentSpot, currentIv]);

  const refreshPortfolio = useCallback(async () => {
    const generation = readGeneration.current + 1;
    readGeneration.current = generation;
    setReadState((state) => ({ ...state, phase: "loading", generation, message: null }));
    const [stored, priced] = await Promise.all([readStoredBook(), readPricedBook()]);
    if (generation !== readGeneration.current) return;
    if (stored.ok) {
      setPositions(stored.positions.map((position, index) => ({
        ...position, serverIndex: index, bookRevision: stored.revision,
      })));
      if (priced.ok && (!stored.revision || priced.data?.book_revision !== stored.revision)) {
        priced.ok = false;
        priced.error = new Error("The priced read belongs to another stored-book revision; refresh to price the current rows");
      }
      if (priced.ok) setPortfolioData(priced.data);
      setReadState((state) => ({
        ...state,
        phase: priced.ok ? "ready" : "priced_failed",
        generation,
        bookGeneration: generation,
        pricedGeneration: priced.ok ? generation : state.pricedGeneration,
        message: priced.ok ? null : describeError(priced.error),
      }));
      return;
    }
    if (stored.missing) {
      setPositions([]);
      setPortfolioData(null);
      setReadState((state) => ({
        ...state,
        phase: "empty",
        generation,
        bookGeneration: 0,
        pricedGeneration: 0,
        message: "the stored portfolio is gone, so the priced values were cleared",
      }));
      return;
    }
    setReadState((state) => ({ ...state, phase: "error", generation, message: describeError(stored.error) }));
  }, [readStoredBook, readPricedBook]);

  const refreshRef = useRef(null);
  refreshRef.current = refreshPortfolio;
  useEffect(() => {
    refreshRef.current?.();
  }, []);

  const addPosition = async (posData) => {
    setLoading(true);
    setActionStatus(null);
    try {
      await axios.post(`${API}/portfolio/${portfolioName}/position`, posData);
      setActionStatus({ type: "ok", message: "Position added to the stored book." });
      await refreshPortfolio();
    } catch (e) {
      setActionStatus({ type: "error", message: describeError(e) });
      console.error("Failed to add position:", e);
    }
    setLoading(false);
  };

  const removePosition = async (position) => {
    setLoading(true);
    setActionStatus(null);
    try {
      if (!position?.bookRevision) {
        setActionStatus({ type: "error", message: "Refresh the stored book before removing a position." });
        await refreshPortfolio();
        return;
      }
      await axios.delete(`${API}/portfolio/${portfolioName}/position/${position.serverIndex}`, {
        params: { expected_revision: position.bookRevision },
      });
      setActionStatus({ type: "ok", message: "Position removed from the stored book." });
      await refreshPortfolio();
    } catch (e) {
      setActionStatus({ type: "error", message: describeError(e) });
      await refreshPortfolio();
      console.error("Failed to remove position:", e);
    } finally {
      setLoading(false);
    }
  };

  const runScenarios = async () => {
    setLoading(true);
    setScenarioStatus(null);
    try {
      const res = await axios.get(`${API}/portfolio/${portfolioName}/scenario`, {
        params: { spot: currentSpot, iv: currentIv },
      });
      setScenarios(res.data.scenarios);
      setScenarioStatus({ type: "ok", message: `Scenario analysis complete — ${res.data.scenarios?.length || 0} scenarios computed` });
      setActiveTab("scenarios");
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || "Scenario analysis failed";
      setScenarioStatus({ type: "error", message: msg });
      setScenarios(null);
      console.error("Scenario failed:", e);
    }
    setLoading(false);
  };

  const calcHedge = async () => {
    if (positions.length === 0) return;
    setLoading(true);
    setHedgeStatus(null);
    try {
      const strikes = [...new Set(positions.map((p) => p.strike))];
      const expiries = [...new Set(positions.map((p) => p.expiry))];
      const hedgeOptions = [];
      for (const s of strikes.slice(0, 2)) {
        for (const exp of expiries.slice(0, 1)) {
          hedgeOptions.push({ strike: s, expiry: exp, type: "call", iv: currentIv });
          hedgeOptions.push({ strike: s, expiry: exp, type: "put", iv: currentIv });
        }
      }
      const res = await axios.post(`${API}/portfolio/${portfolioName}/hedge`, {
        spot: currentSpot,
        iv: currentIv,
        hedge_options: hedgeOptions.slice(0, 4),
      });
      setHedgeResult(res.data);
      if (res.data.error) {
        setHedgeStatus({ type: "error", message: res.data.error });
      } else {
        setHedgeStatus({ type: "ok", message: "Hedge calculation complete" });
      }
      setActiveTab("hedge");
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || "Hedge calculation failed";
      setHedgeStatus({ type: "error", message: msg });
      setHedgeResult(null);
      console.error("Hedge calc failed:", e);
    }
    setLoading(false);
  };

  // The endpoint returns a typed P&L object (status, reason, coverage,
  // multiplier provenance). A legacy bare number is still tolerated, but its
  // missing fields stay unavailable instead of rendering as undefined/zero.
  const rawPnl = portfolioData?.pnl;
  const pnl = typeof rawPnl === "number"
    ? { status: "partial", reason: "LEGACY_TOTAL_ONLY", total_pnl: rawPnl, pct_pnl: null,
        pct_reason: "NO_ENTRY_VALUE", total_entry_value: null, total_current_value: null,
        coverage: null }
    : rawPnl;
  const greeks = portfolioData?.greeks;
  const foreignSymbols = [...new Set(
    positions.filter((p) => p.symbol && ticker && p.symbol !== ticker).map((p) => p.symbol),
  )];
  const staleRows = readState.phase === "error" && readState.bookGeneration > 0
    && readState.bookGeneration < readState.generation;
  const readStateText = readState.phase === "loading"
    ? `Reading stored book · read #${readState.generation}…`
    : readState.phase === "empty"
      ? `No stored portfolio · read #${readState.generation}${readState.message ? ` — ${readState.message}` : ""}`
      : readState.phase === "error"
        ? `Stored book read failed · read #${readState.generation}${readState.message ? ` — ${readState.message}` : ""}${staleRows ? ` — showing rows from read #${readState.bookGeneration}` : ""}${readState.pricedGeneration > 0 && readState.pricedGeneration < readState.generation ? ` — showing priced values from read #${readState.pricedGeneration}` : ""}`
        : readState.phase === "priced_failed"
          ? `Stored book · read #${readState.generation} · priced read failed${readState.message ? ` — ${readState.message}` : ""}${readState.pricedGeneration > 0 && readState.pricedGeneration < readState.generation ? ` — showing priced values from read #${readState.pricedGeneration}` : ""}`
          : readState.phase === "ready"
            ? `Stored book · read #${readState.generation}`
            : "Stored book · not read yet";
  const money = (value, { sign = false, percent = false } = {}) => {
    if (value === null || value === undefined) return "unavailable";
    return `${sign && value > 0 ? "+" : ""}${percent ? `${value}%` : fmt(value, 0)}`;
  };

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

        <div className="text-[10px] text-slate-500" data-testid="portfolio-read-state">{readStateText}</div>
        {actionStatus && (
          <div
            className={`panel p-2 text-[10px] ${actionStatus.type === "error" ? "text-rose-400" : "text-emerald-400"}`}
            data-testid="portfolio-action-status"
          >
            {actionStatus.message}
          </div>
        )}

        {/* P&L Summary */}
        {pnl && (
          <div className="panel p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="label mb-0">P&L · model-priced</div>
              {pnl.status !== "ok" && (
                <div className="text-[10px] text-slate-400">
                  unavailable{pnl.reason ? ` · ${pnl.reason}` : ""}
                </div>
              )}
            </div>
            <div className="grid grid-cols-4 gap-3 text-center">
              <div>
                <div className="label">Total P&L</div>
                <div className={`text-xl mono font-bold ${pnl.total_pnl > 0 ? "text-emerald-400" : pnl.total_pnl < 0 ? "text-rose-400" : "text-slate-300"}`}>
                  {money(pnl.total_pnl, { sign: true })}
                </div>
              </div>
              <div>
                <div className="label">P&L %</div>
                <div className={`text-xl mono font-bold ${pctClass(pnl.pct_pnl)}`}>
                  {money(pnl.pct_pnl, { sign: true, percent: true })}
                </div>
              </div>
              <div>
                <div className="label">Entry Value</div>
                <div className="text-lg mono text-slate-300">{money(pnl.total_entry_value)}</div>
              </div>
              <div>
                <div className="label">Current Value</div>
                <div className="text-lg mono text-slate-300">{money(pnl.total_current_value)}</div>
              </div>
            </div>
            {pnl.coverage && (
              <div className="mt-2 text-[10px] text-slate-500 text-center">
                {pnl.coverage.priced} priced · {pnl.coverage.skipped} skipped ·{" "}
                {pnl.coverage.stored} stored
              </div>
            )}
            {Array.isArray(portfolioData?.skipped) && portfolioData.skipped.length > 0 && (
              <div className="mt-1 text-[10px] text-amber-400/80 text-center">
                skipped: {portfolioData.skipped.map((s) => `${s.symbol || "position"} (${s.reason})`).join(", ")}
              </div>
            )}
            {portfolioData?.valuation_basis && (
              <div className="mt-1 text-[10px] text-slate-500 text-center">
                {portfolioData.valuation_basis} · not a broker mark
              </div>
            )}
          </div>
        )}

        {portfolioData && (
          <div className="text-[10px] text-slate-500 text-center" data-testid="portfolio-valuation-note">
            priced at spot {fmt(portfolioData.spot ?? currentSpot, 2)} · iv {((portfolioData.iv ?? currentIv) * 100).toFixed(1)}% · one spot for the whole stored book
            {foreignSymbols.length > 0 ? ` · ${foreignSymbols.join(", ")} not in ${ticker}` : ""} · not a per-position mark
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
                {positions.length > 0 && positions.some((p) => !p.bookRevision) && (
                  <div className="text-[10px] text-amber-400/80 mb-1" data-testid="portfolio-removal-unavailable">
                    Refresh to read the stored book before removing a position.
                  </div>
                )}
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
                    {positions.map((p) => (
                      <tr key={`${p.bookRevision || "unversioned"}-${p.serverIndex}`} className="border-t border-slate-800/60 bar-row">
                        <td className="px-2 py-1 font-bold">{p.symbol}</td>
                        <td className={`px-2 py-1 ${p.option_type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{p.option_type}</td>
                        <td className="text-right px-2 py-1">{p.strike}</td>
                        <td className="px-2 py-1 text-slate-400">{p.expiry}</td>
                        <td className="text-right px-2 py-1">{p.quantity}</td>
                        <td className="text-right px-2 py-1">{p.entry_price}</td>
                        <td className="text-right px-2 py-1 text-slate-400">{(p.entry_iv * 100).toFixed(1)}%</td>
                        <td className="text-right px-2 py-1 text-slate-400">{p.underlying_price}</td>
                        <td className="px-2 py-1">
                          <button
                            onClick={() => removePosition(p)}
                            disabled={loading || !p.bookRevision}
                            title={p.bookRevision ? "Remove this position if the stored book is unchanged" : "Refresh the stored book first"}
                            className="text-rose-400 hover:text-rose-300 text-[10px] disabled:text-slate-600 disabled:cursor-not-allowed"
                            aria-label={`Remove position ${p.symbol} ${p.option_type} ${p.strike} ${p.expiry}`}
                          >✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className={`panel p-6 text-center text-[11px] ${readState.phase === "error" ? "text-rose-400/80" : "text-slate-500"}`}>
                {readState.phase === "error"
                  ? "The stored book could not be read. Open positions are unknown until a read succeeds."
                  : readState.phase === "loading"
                    ? "Reading the stored book…"
                    : readState.phase === "empty"
                      ? "No stored portfolio yet. Add a position to create it."
                      : "No positions yet. Add your first position above."}
              </div>
            )}
          </div>
        )}

        {/* Scenarios Tab */}
        {activeTab === "scenarios" && (
          <div className="space-y-2">
            <button onClick={runScenarios} className="btn w-full" disabled={loading || positions.length === 0}>
              {loading ? "Running…" : "Run Scenario Analysis"}
            </button>
            {scenarioStatus && (
              <div className={`panel p-2.5 text-[10px] border ${scenarioStatus.type === "error" ? "border-rose-500/30 text-rose-400 bg-rose-500/5" : "border-emerald-500/30 text-emerald-400 bg-emerald-500/5"}`}>
                {scenarioStatus.type === "error" ? "⚠ " : "✓ "}{scenarioStatus.message}
              </div>
            )}
            {scenarios && <ScenarioTable scenarios={scenarios} />}
            {!scenarios && !scenarioStatus && positions.length > 0 && (
              <div className="panel p-4 text-center text-slate-500 text-[10px]">
                Click "Run Scenario Analysis" to see spot/vol shock P&L
              </div>
            )}
          </div>
        )}

        {/* Hedge Tab */}
        {activeTab === "hedge" && (
          <div className="space-y-2">
            <button onClick={calcHedge} className="btn w-full" disabled={loading || positions.length === 0}>
              {loading ? "Calculating…" : "Calculate Greek-Neutral Hedge"}
            </button>
            {hedgeStatus && (
              <div className={`panel p-2.5 text-[10px] border ${hedgeStatus.type === "error" ? "border-rose-500/30 text-rose-400 bg-rose-500/5" : "border-emerald-500/30 text-emerald-400 bg-emerald-500/5"}`}>
                {hedgeStatus.type === "error" ? "⚠ " : "✓ "}{hedgeStatus.message}
              </div>
            )}
            {hedgeResult && <div className="panel p-3"><HedgeResult result={hedgeResult} /></div>}
            {!hedgeResult && !hedgeStatus && positions.length > 0 && (
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
            {scenarioStatus && (
              <div className={`mt-1.5 p-1.5 text-[9px] rounded ${scenarioStatus.type === "error" ? "bg-rose-500/10 text-rose-400" : "bg-emerald-500/10 text-emerald-400"}`}>
                Scenarios: {scenarioStatus.message}
              </div>
            )}
            {hedgeStatus && (
              <div className={`mt-1.5 p-1.5 text-[9px] rounded ${hedgeStatus.type === "error" ? "bg-rose-500/10 text-rose-400" : "bg-emerald-500/10 text-emerald-400"}`}>
                Hedge: {hedgeStatus.message}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
