import React, { useEffect, useState, useMemo, useRef, useCallback } from "react";
import axios from "axios";
import { fmtAbs, pctClass } from "../lib/helpers";
import { formatStrike, formatGreek } from "../lib/marketDisplay";
import { API } from "../config/api";
import { fetchPublicChain } from "../lib/publicApi";

// API endpoints
const CHAIN_API = `${API}/chain`;          // /api/chain?ticker=SPY — merged path (Public API → cvserver → yfinance)

// Sort options
const SORT_OPTIONS = [
  { v: "strike", l: "Strike" }, { v: "expiry", l: "Expiry" },
  { v: "oi", l: "OI" }, { v: "volume", l: "Vol" },
  { v: "iv", l: "IV" }, { v: "delta", l: "Delta" },
  { v: "gamma", l: "Gamma" }, { v: "gex", l: "GEX" },
  { v: "vanna", l: "Vanna" }, { v: "charm", l: "Charm" },
];

/**
 * Transform a public-chain response into the rows shape the table expects.
 * Public API returns {contracts: [...]} with floww-shaped contract dicts
 * (same fields the adapter produces: type, strike, expiry, T, iv, delta,
 * gamma, oi, volume, gex, vanna, charm, moneyness_pct, ...).
 */
function chainRespToRows(resp) {
  if (!resp) return null;
  const contracts = resp.contracts || resp.rows || [];
  const finite = value => typeof value === "number" && Number.isFinite(value) ? value : null;
  return {
    rows: contracts.map(c => ({
      type: c.type === "call" || c.type === "put" ? c.type : null,
      strike: finite(c.strike),
      expiry: c.expiry,
      dte: finite(c.dte) ?? (finite(c.T) !== null ? Math.round(c.T * 365) : null),
      iv: finite(c.iv),
      delta: finite(c.delta),
      gamma: finite(c.gamma),
      oi: finite(c.oi),
      volume: finite(c.volume),
      gex: finite(c.gex),
      vanna: finite(c.vanna),
      charm: finite(c.charm),
      moneyness_pct: finite(c.moneyness_pct),
      bid: finite(c.bid),
      ask: finite(c.ask),
    })),
    count: resp.n_contracts ?? resp.count ?? contracts.length,
    expiries: resp.expiries || [],
    spot: resp.spot,
    ticker: resp.ticker,
    data_source: resp.data_source,
  };
}

export default function OptionsChainTable({ ticker }) {
  const [loadedChain, setChain] = useState(null);
  // Hide the previous ticker during the render before its replacement fetch starts.
  const chain = loadedChain?.requestTicker === ticker ? loadedChain : null;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expiry, setExpiry] = useState("");
  const [moneyness, setMoneyness] = useState("all");
  const [minOi, setMinOi] = useState(100);
  const [sortBy, setSortBy] = useState("strike");
  const [sortDir, setSortDir] = useState("asc");
  const [side, setSide] = useState("all"); // all, calls, puts
  const [dteMax, setDteMax] = useState(null);

  useEffect(() => {
    let mounted = true;
    const controller = new AbortController();
    setExpiry("");

    const fetchChain = async () => {
      setLoading(true);
      setError(null);
      try {
        // Phase 5.1: try direct Public API endpoint first.
        // Falls back to merged /api/chain if Public API unavailable.
        let chainData = null;

        try {
          chainData = await fetchPublicChain(ticker, { signal: controller.signal });
          if (mounted && chainData) {
            chainData = chainRespToRows(chainData);
          }
        } catch (pubErr) {
          if (pubErr.name === "AbortError" || pubErr.code === "ERR_CANCELED") throw pubErr;
          // Public API failed — fall through to merged endpoint
        }

        // Fallback: merged /api/chain (Public API → cvserver → yfinance)
        if (!mounted) return;
        if (!chainData) {
          try {
            const mergedRes = await axios.get(
              `${CHAIN_API}/${ticker}`,
              { signal: controller.signal, timeout: 30000 }
            );
            if (mounted) {
              const mergedData = chainRespToRows(mergedRes.data);
              chainData = mergedData || { rows: [], count: 0, expiries: [], spot: 0, ticker: ticker.toUpperCase(), data_source: "unknown" };
            }
          } catch (mergedErr) {
            if (mergedErr.name === "AbortError" || mergedErr.code === "ERR_CANCELED") throw mergedErr;
            if (mounted) setError(`Chain fetch failed: ${mergedErr.message}`);
          }
        }

        if (mounted && chainData) setChain({ ...chainData, requestTicker: ticker });
      } catch (err) {
        if (err.name === "AbortError" || err.code === "ERR_CANCELED") return;
        if (mounted) console.error("Chain fetch failed:", err);
      }
      if (mounted) setLoading(false);
    };

    fetchChain();
    return () => {
      mounted = false;
      controller.abort();
    };
  }, [ticker]);

  const filtered = useMemo(() => {
    if (!chain?.rows) return [];
    const currentSpot = chain.spot;
    const rows = chain.rows.filter(r => {
      if (side === "calls" && r.type !== "call") return false;
      if (side === "puts" && r.type !== "put") return false;
      if (expiry && r.expiry !== expiry) return false;
      if (minOi > 0 && (r.oi === null || r.oi < minOi)) return false;
      if (dteMax !== null && (r.dte === null || r.dte > dteMax)) return false;
      if (moneyness !== "all") {
        if (!Number.isFinite(currentSpot) || currentSpot <= 0 || r.strike === null || !r.type) return false;
        if (moneyness === "atm") return Math.abs(r.strike - currentSpot) / currentSpot <= 0.01;
        const intrinsic = r.type === "call" ? currentSpot - r.strike : r.strike - currentSpot;
        if (moneyness === "itm" && intrinsic <= 0) return false;
        if (moneyness === "otm" && intrinsic >= 0) return false;
      }
      return true;
    });
    return rows.sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      // Unavailable values remain last in both directions, never treated as zero.
      if (av == null) return bv == null ? 0 : 1;
      if (bv == null) return -1;
      const order = typeof av === "string" ? av.localeCompare(bv) : av - bv;
      return sortDir === "asc" ? order : -order;
    });
  }, [chain, side, expiry, minOi, dteMax, moneyness, sortBy, sortDir]);

  const toggleSort = (col) => {
    if (sortBy === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortBy(col); setSortDir("desc"); }
  };

  const sortArrow = (col) => {
    if (sortBy !== col) return " ";
    return sortDir === "asc" ? " ↑" : " ↓";
  };

  const ROW_HEIGHT = 22;
  const VISIBLE_ROWS = 40;
  const BUFFER = 10;
  const scrollRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);

  const totalHeight = filtered.length * ROW_HEIGHT;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER);
  const endIdx = Math.min(filtered.length, startIdx + VISIBLE_ROWS + BUFFER * 2);
  const visibleRows = useMemo(() => filtered.slice(startIdx, endIdx), [filtered, startIdx, endIdx]);
  const offsetY = startIdx * ROW_HEIGHT;

  const onScroll = useCallback((e) => {
    setScrollTop(e.target.scrollTop);
  }, []);

  // Reset scroll when filters change
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [side, moneyness, expiry, dteMax, minOi, sortBy, sortDir, ticker]);

  if (loading && !chain) return <div className="panel p-3 text-slate-500 text-xs">Loading chain…</div>;

  return (
    <div className="panel p-2">
      <div className="label mb-2">Options Chain {chain ? `(${filtered.length}/${chain.count})` : ""}</div>
      {error && <div role="alert">{error}</div>}

      {/* Filters */}
      <div className="flex flex-wrap gap-1 mb-2">
        {["all", "calls", "puts"].map(s => (
          <button key={s} onClick={() => setSide(s)} className={`btn text-[9px] px-1.5 py-0.5 ${side === s ? "active" : ""}`}>{s.toUpperCase()}</button>
        ))}
        <select value={moneyness} onChange={e => setMoneyness(e.target.value)} className="btn text-[9px] px-1 py-0.5">
          <option value="all">All</option>
          <option value="itm">ITM</option>
          <option value="otm">OTM</option>
          <option value="atm">ATM (within 1%)</option>
        </select>
        <select value={expiry} onChange={e => setExpiry(e.target.value)} className="btn text-[9px] px-1 py-0.5">
          <option value="">All Expiries</option>
          {chain?.expiries?.map(e => <option key={e} value={e}>{e}</option>)}
        </select>
        <input type="number" value={dteMax ?? ""} onChange={e => setDteMax(e.target.value === "" ? null : Number(e.target.value))}
          className="btn text-[9px] px-1 py-0.5 w-16" placeholder="Max DTE" min={0} max={365} />
        <input type="number" value={minOi} onChange={e => setMinOi(Number(e.target.value))}
          className="btn text-[9px] px-1 py-0.5 w-16" placeholder="Min OI" />
        <select value={sortBy} onChange={e => setSortBy(e.target.value)} className="btn text-[9px] px-1 py-0.5">
          {SORT_OPTIONS.map(o => <option key={o.v} value={o.v}>Sort: {o.l}</option>)}
        </select>
        <button onClick={() => setSortDir(d => d === "asc" ? "desc" : "asc")} className="btn text-[9px] px-1.5 py-0.5">
          {sortDir === "asc" ? "↑" : "↓"}
        </button>
        {chain?.rows?.length > 0 && (
          <button onClick={() => {
            const cols = ["type","strike","expiry","dte","iv","delta","gamma","oi","volume","gex","vanna","charm","moneyness_pct"];
            const header = cols.join(",");
            const rows = filtered.map(r => cols.map(c => r[c] ?? "").join(",")).join("\n");
            const blob = new Blob([header + "\n" + rows], {type: "text/csv"});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = `${ticker}_chain_${new Date().toISOString().slice(0,10)}.csv`;
            a.click(); URL.revokeObjectURL(url);
          }} className="btn text-[9px] px-1.5 py-0.5">CSV</button>
        )}
      </div>

      {/* Table with virtual scrolling */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="overflow-auto text-[9px]"
        style={{ maxHeight: VISIBLE_ROWS * ROW_HEIGHT + 40 }}
      >
        <div style={{ height: totalHeight, position: "relative" }}>
          <table className="w-full border-collapse" style={{ position: "absolute", top: offsetY }}>
            <thead className="sticky top-0" style={{ background: "var(--panel)" }}>
              <tr>
                <th className="text-left px-1 py-0.5 text-slate-500">Type</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("strike")}>K{sortArrow("strike")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("expiry")}>Exp{sortArrow("expiry")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500">DTE</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("iv")}>IV{sortArrow("iv")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("delta")}>Δ{sortArrow("delta")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("gamma")}>Γ{sortArrow("gamma")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("oi")}>OI{sortArrow("oi")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("volume")}>Vol{sortArrow("volume")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("gex")}>GEX{sortArrow("gex")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("vanna")}>Vanna{sortArrow("vanna")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("charm")}>Charm{sortArrow("charm")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500">Moneyness</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r, i) => {
                const actualIdx = startIdx + i;
                const isCall = r.type === "call";
                const gexClass = r.gex > 0 ? "text-teal-400" : r.gex < 0 ? "text-purple-400" : "text-slate-500";
                const nearSpot = Number.isFinite(chain.spot) && chain.spot > 0 && r.strike !== null
                  && Math.abs(r.strike - chain.spot) / chain.spot < 0.01;
                return (
                  <tr key={actualIdx} style={{ height: ROW_HEIGHT }} className={`${nearSpot ? "bg-slate-700/30" : ""} hover:bg-slate-700/20`}>
                    <td className={`px-1 py-0.5 font-bold ${isCall ? "text-teal-400" : "text-purple-400"}`}>{isCall ? "C" : r.type === "put" ? "P" : "—"}</td>
                    <td className="text-right px-1 py-0.5 mono">{formatStrike(r.strike)}</td>
                    <td className="text-right px-1 py-0.5 text-slate-400">{r.expiry?.slice(5)}</td>
                    <td className="text-right px-1 py-0.5 text-slate-400">{r.dte ?? "—"}</td>
                    <td className="text-right px-1 py-0.5 mono">{r.iv != null ? (r.iv * 100).toFixed(1) + "%" : "—"}</td>
                    <td className="text-right px-1 py-0.5 mono">{r.delta != null ? r.delta.toFixed(2) : "—"}</td>
                    <td className="text-right px-1 py-0.5 mono">{r.gamma != null ? r.gamma.toFixed(4) : "—"}</td>
                    <td className="text-right px-1 py-0.5">{r.oi >= 1000 ? (r.oi / 1000).toFixed(1) + "K" : r.oi ?? "—"}</td>
                    <td className="text-right px-1 py-0.5">{r.volume >= 1000 ? (r.volume / 1000).toFixed(1) + "K" : r.volume ?? "—"}</td>
                    <td className={`text-right px-1 py-0.5 mono ${gexClass}`}>{fmtAbs(r.gex)}</td>
                    <td className="text-right px-1 py-0.5 mono">{formatGreek(r.vanna)}</td>
                    <td className="text-right px-1 py-0.5 mono">{formatGreek(r.charm)}</td>
                    <td className={`text-right px-1 py-0.5 mono ${pctClass(r.moneyness_pct)}`}>{r.moneyness_pct != null ? (r.moneyness_pct > 0 ? "+" : "") + r.moneyness_pct.toFixed(1) + "%" : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
