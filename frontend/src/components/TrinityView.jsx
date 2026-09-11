import React, { useEffect, useState, useMemo, useCallback, useRef } from "react";
import axios from "axios";
import { fmt, fmtAbs, TRIAD } from "../lib/helpers";
import { API as BACKEND_API } from "../config/api";
import { fetchPublicChain } from "../lib/publicApi";

const API = BACKEND_API;

/**
 * Triad 3-Panel View — Institutional Redesign
 *
 * Improvements:
 * - Stale-while-revalidate: show cached data instantly, refresh in background
 * - Richer headers: price, change%, King distance, VIX
 * - Strike price column with color-coded heatmap rows
 * - More data per row: OI, IV, delta, volume badges
 * - Quick-trade: click any row to populate trade entry
 * - Timeline bar at bottom
 */

// ── Color scale for heatmap rows ────────────────────────────────────
function rowColors(v, maxAbs) {
  if (v === null || v === undefined || isNaN(v) || v === 0) {
    return { bg: "transparent", text: "#4a5568", barColor: "transparent", badge: null };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;

  if (norm > 0.85 && !isNeg) {
    return {
      bg: `rgba(251,191,36,${0.75 + 0.2 * norm})`, text: "#0a0e1a", barColor: "#fbbf24",
      badge: { text: `+${(norm * 100).toFixed(0)}%`, cls: "trinity-badge-yellow" },
    };
  }
  if (norm > 0.50 && !isNeg) {
    return {
      bg: `rgba(45,212,191,${0.45 + 0.25 * norm})`, text: "#0a0e1a", barColor: "#2dd4bf",
      badge: { text: `+${(norm * 100).toFixed(0)}%`, cls: "trinity-badge-green" },
    };
  }
  if (norm > 0.20 && !isNeg) {
    return { bg: `rgba(45,212,191,${0.15 + 0.15 * norm})`, text: "#6ee7b7", barColor: "#2dd4bf", badge: null };
  }
  if (norm > 0.85 && isNeg) {
    return {
      bg: `rgba(59,130,246,${0.6 + 0.3 * norm})`, text: "#e0f2fe", barColor: "#3b82f6",
      badge: { text: `-${(norm * 100).toFixed(0)}%`, cls: "trinity-badge-blue" },
    };
  }
  if (norm > 0.50 && isNeg) {
    return {
      bg: `rgba(168,85,247,${0.45 + 0.25 * norm})`, text: "#e9d5ff", barColor: "#a855f7",
      badge: { text: `-${(norm * 100).toFixed(0)}%`, cls: "trinity-badge-purple" },
    };
  }
  if (norm > 0.20 && isNeg) {
    return { bg: `rgba(168,85,247,${0.15 + 0.15 * norm})`, text: "#c4b5fd", barColor: "#a855f7", badge: null };
  }
  return {
    bg: isNeg ? "rgba(88,28,135,0.08)" : "rgba(22,78,99,0.08)",
    text: isNeg ? "#8b7fd4" : "#5ebfb0",
    barColor: isNeg ? "#7c3aed" : "#14b8a6",
    badge: null,
  };
}

function fmtGex(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

function fmtOi(v) {
  if (!v) return "—";
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(0) + "K";
  return v.toFixed(0);
}

// Calculate percentage of max abs value
function pctOfMax(v, maxAbs) {
  if (!v || !maxAbs) return 0;
  return Math.abs(v) / maxAbs * 100;
}

const TAG_STYLES = {
  KING: { bg: "rgba(251,191,36,0.15)", border: "rgba(251,191,36,0.4)", text: "#fbbf24" },
  FLR: { bg: "rgba(52,211,153,0.12)", border: "rgba(52,211,153,0.35)", text: "#34d399" },
  CEIL: { bg: "rgba(248,113,113,0.12)", border: "rgba(248,113,113,0.35)", text: "#f87171" },
  GATE: { bg: "rgba(56,189,248,0.12)", border: "rgba(56,189,248,0.35)", text: "#38bdf8" },
  AIR: { bg: "rgba(148,163,184,0.08)", border: "rgba(148,163,184,0.25)", text: "#94a3b8" },
};

const VIEW_MODES = [
  { id: "dom", label: "DOM", icon: "▦" },
  { id: "grid", label: "Grid", icon: "⊞" },
  { id: "bars", label: "Bars", icon: "▤" },
  { id: "chain", label: "Chain", icon: "☰" },
  { id: "list", label: "List", icon: "≡" },
];

const GEX_VEX_MODES = [
  { id: "gex", label: "GEX" },
  { id: "vex", label: "VEX" },
];

// ── Main Triad View ────────────────────────────────────────────────
export default function TrinityView({ onFocusTicker, onTradeSelect }) {
  const [allData, setAllData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState("dom");
  const [gexVexMode, setGexVexMode] = useState("gex");
  const [panelTickers, setPanelTickers] = useState({ "0": "^SPX", "1": "SPY", "2": "QQQ" });
  const [dteFilter, setDteFilter] = useState(3);
  const [lastUpdate, setLastUpdate] = useState(null);
  const cacheRef = useRef({});
  const mountedRef = useRef(true);
  const abortRef = useRef(null);

  // Phase 5.2: fetch a single ticker — Public API first, /api/data fallback.
  const fetchTickerData = useCallback(async (ticker, timeout) => {
    // Try Public API chain endpoint first.
    try {
      const pubRes = await fetchPublicChain(ticker, { timeout: Math.min(timeout, 20000), expirations: dteFilter });
      if (pubRes?.ok && pubRes?.contracts?.length) {
        // Map public chain → triad data shape.
        const contracts = pubRes.contracts || [];
        const strikes = contracts.map(c => ({
          strike: c.strike,
          gex: c.gex,
          call_gex: c.gex >= 0 ? c.gex : 0,
          put_gex: c.gex < 0 ? c.gex : 0,
          iv: c.iv,
          delta: c.delta,
          gamma: c.gamma,
          vega: c.vega,
          theta: c.theta,
          vanna: c.vanna,
          charm: c.charm,
          oi: c.oi,
          total_oi: c.oi,
          volume: c.volume,
          bid: c.bid,
          ask: c.ask,
          dte: c.T ? Math.round(c.T * 365) : null,
          expiry: c.expiry,
          type: c.type,
          moneyness_pct: c.moneyness_pct,
        }));
        const grid = { grid: { "0": {} } };
        for (const c of contracts.slice(0, 200)) {
          const expKey = c.expiry || "2026-09-18";
          if (!grid.grid[expKey]) grid.grid[expKey] = {};
          grid.grid[expKey][String(c.strike)] = {
            gex: c.gex, iv: c.iv, delta: c.delta, charm: c.charm,
            vanna: c.vanna, vex: 0, call_gex: c.gex >= 0 ? c.gex : 0, put_gex: c.gex < 0 ? c.gex : 0,
          };
        }
        const spot = pubRes.spot || 0;
        // Approximate nodes from contract data.
        const netGex = strikes.reduce((s, c) => s + (c.gex || 0), 0);
        const kingStrike = strikes.reduce((best, c) => Math.abs(c.gex || 0) > Math.abs(best?.gex || 0) ? c : best, null);
        return {
          ticker,
          spot,
          change_pct: 0,
          nodes: {
            regime: netGex > 0 ? "positive" : netGex < 0 ? "negative" : "neutral",
            king: kingStrike || null,
            gamma_flip: null,
            floors: [],
            ceilings: [],
            gatekeepers: [],
            air_pockets: [],
            polarity_level: Math.min(1, Math.abs(netGex) / (spot || 1) * 100),
          },
          strikes,
          grid,
          vix: 20,
          expiries_used: [...new Set(contracts.map(c => c.expiry).filter(Boolean))].slice(0, dteFilter),
          data_source: pubRes.data_source || "public_api",
        };
      }
    } catch (pubErr) {
      if (pubErr.name === "AbortError" || pubErr.code === "ERR_CANCELED") throw pubErr;
    }
    // Fallback: merged /api/data (Public API → cvserver → yfinance)
    const res = await axios.get(`${API}/data/${ticker}?expiries=${dteFilter}&mode=day`, { timeout, signal: AbortSignal.timeout(timeout) });
    return res.data;
  }, [dteFilter]);

  // Fetch all 7 tickers concurrently (no waterfall). Panel tickers use the
  // shorter timeout; extras use the longer one. Each resolved ticker is merged
  // into the cache immediately so a single failure never blocks or blanks others.
  const applyTicker = useCallback((ticker, data) => {
    if (!data?.strikes?.length) return;
    cacheRef.current = { ...cacheRef.current, [ticker]: data };
    if (mountedRef.current) setAllData({ ...cacheRef.current });
  }, []);

  const fetchTickers = useCallback((tickers, timeout) =>
    Promise.allSettled(
      tickers.map(t =>
        fetchTickerData(t, timeout).then(r => applyTicker(t, r))
      )
    ), [dteFilter, fetchTickerData, applyTicker]);

  const fetchAll = useCallback(async (isBackground = false) => {
    const panelTickers = ["^SPX", "SPY", "QQQ"];
    const extraTickers = ["^NDX", "IWM", "DIA", "TLT"];

    if (!isBackground) setLoading(true);
    setError(null);

    // Both phases run in parallel; panel results land first because of the
    // shorter timeout, but we never wait for phase 1 before starting phase 2.
    await Promise.all([
      fetchTickers(panelTickers, 8000),
      fetchTickers(extraTickers, 30000),
    ]);

    if (mountedRef.current) {
      setLastUpdate(new Date());
      setLoading(false);
      // If absolutely nothing loaded and no cache, show error
      if (Object.keys(cacheRef.current).length === 0) {
        setError("No data available. Backend may be degraded.");
      }
    }
  }, [dteFilter, fetchTickers]);

  useEffect(() => {
    mountedRef.current = true;
    if (Object.keys(cacheRef.current).length > 0) { setAllData(cacheRef.current); setLoading(false); }
    fetchAll(false);
    // 60s cadence (2026-09-04): each poll fans out to ~7 uncached Public
    // chain fetches (~6 upstream calls each). 30s sustained ~80+/min on a
    // single retail key — 60s halves that alongside the backend 60s chain
    // TTL without visibly aging the Triad view.
    const id = setInterval(() => fetchAll(true), 60000);
    return () => { mountedRef.current = false; clearInterval(id); };
  }, [fetchAll]);

  if (loading && Object.keys(allData).length === 0) {
    return (
      <div className="trinity-loading">
        <div className="trinity-loading-spinner" />
        <span>Loading Triad…</span>
      </div>
    );
  }
  if (error && Object.keys(allData).length === 0) {
    return <div className="trinity-error"><span>⚠</span> Error: {error}<button onClick={() => fetchAll(false)}>Retry</button></div>;
  }

  return (
    <div className="trinity-layout" data-testid="trinity-view">
      <ConfluenceBar data={allData} viewMode={viewMode} onViewModeChange={setViewMode} gexVexMode={gexVexMode} onGexVexChange={setGexVexMode} dteFilter={dteFilter} onDteChange={setDteFilter} lastUpdate={lastUpdate} loading={loading} />
      <div className="trinity-panels">
        {TRIAD.map((defaultTicker, idx) => {
          const currentTicker = panelTickers[idx] || defaultTicker;
          return (
            <TrinityPanel key={idx} ticker={currentTicker} data={allData[currentTicker] || allData[defaultTicker]} viewMode={viewMode} gexVexMode={gexVexMode} loading={loading && !allData[currentTicker]} onFocus={() => onFocusTicker && onFocusTicker(currentTicker)} onTickerChange={(t) => setPanelTickers(prev => ({ ...prev, [idx]: t }))} onTradeSelect={onTradeSelect} />
          );
        })}
      </div>
      <TimelineBar />
    </div>
  );
}

function ConfluenceBar({ data, viewMode, onViewModeChange, gexVexMode, onGexVexChange, dteFilter, onDteChange, lastUpdate, loading }) {
  const { regimes, confluence, hasTickers } = useMemo(() => {
    const tickers = TRIAD.map(t => data[t]).filter(d => d && !d.error);
    const regs = tickers.map(d => d.nodes?.regime).filter(Boolean);
    const conf = regs.length > 0 ? regs.filter(r => r === regs[0]).length / regs.length : 0;
    return { regimes: regs, confluence: conf, hasTickers: tickers.length > 0 };
  }, [data]);
  if (!hasTickers) return null;
  const verdict = confluence === 1 ? "full" : confluence >= 0.66 ? "partial" : "diverge";
  const verdictColor = verdict === "full" ? "trinity-verdict-pos" : verdict === "partial" ? "trinity-verdict-warn" : "trinity-verdict-neg";
  const verdictText = verdict === "full" ? "All three agree. Highest conviction." : verdict === "partial" ? "Two-of-three. Reduced size." : "Disagreement. Wait.";
  const timeStr = lastUpdate ? lastUpdate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : "";
  return (
    <div className="trinity-summary">
      <div className="trinity-summary-left">
        <div className="trinity-stat"><span className="trinity-stat-label">Meridian</span><span className={`trinity-stat-value ${confluence === 1 ? "text-emerald-400" : confluence >= 0.66 ? "text-amber-400" : "text-rose-400"}`}>{(confluence * 100).toFixed(0)}%</span></div>
        <div className="trinity-divider" />
        <div className="trinity-stat"><span className="trinity-stat-label">Regime</span><span className={`trinity-stat-value ${regimes[0] === "positive" ? "text-emerald-400" : regimes[0] === "negative" ? "text-rose-400" : "text-slate-400"}`}>{regimes[0] || "—"}</span></div>
        <div className="trinity-divider" />
        <div className="trinity-stat"><span className="trinity-stat-label">Updated</span><span className="trinity-stat-value text-slate-400" style={{ fontSize: 9 }}>{loading ? "…" : timeStr}</span></div>
      </div>
      <div className="trinity-summary-right">
        <span className={`trinity-verdict ${verdictColor}`}>{verdictText}</span>
        <div className="trinity-view-toggle">{VIEW_MODES.map(vm => (<button key={vm.id} className={`trinity-view-btn${viewMode === vm.id ? " trinity-view-active" : ""}`} onClick={() => onViewModeChange(vm.id)} title={vm.label}><span className="trinity-view-icon">{vm.icon}</span><span className="trinity-view-label">{vm.label}</span></button>))}</div>
        <div className="trinity-gexvex-toggle">{GEX_VEX_MODES.map(m => (<button key={m.id} className={`trinity-gexvex-btn${gexVexMode === m.id ? " trinity-gexvex-active" : ""}`} onClick={() => onGexVexChange(m.id)}>{m.label}</button>))}</div>
        <div className="trinity-dte-toggle">{/* ids are expiry COUNTS sent as ?expiries= — labels describe the practical window */}
        {[[1,"0–1DTE"],[3,"~3DTE"],[7,"1 Week"],[12,"All"]].map(([id,label])=>(<button key={id} className={`trinity-dte-btn${dteFilter===id?" trinity-dte-active":""}`} onClick={()=>onDteChange(id)}>{label}</button>))}</div>
      </div>
    </div>
  );
}

// ── Mini Sparkline ────────────────────────────────────────────────────
function MiniSparkline({ data, spot }) {
  // Generate 20 bars from the strikes data around spot
  const window = useMemo(() => {
    if (!data?.strikes?.length || !spot) return null;
    const strikes = data.strikes;
    const spotIdx = strikes.reduce((best, s, i) =>
      Math.abs(s.strike - spot) < Math.abs(strikes[best].strike - spot) ? i : best, 0);
    const start = Math.max(0, spotIdx - 10);
    const end = Math.min(strikes.length, spotIdx + 10);
    return strikes.slice(start, end);
  }, [data, spot]);
  if (!window) return null;
  const maxGex = Math.max(...window.map(s => Math.abs(s.gex || 0)), 1);
  
  return (
    <span className="trinity-panel-sparkline">
      {window.map((s, i) => {
        const h = Math.max(2, Math.round((Math.abs(s.gex || 0) / maxGex) * 12));
        const isNeg = (s.gex || 0) < 0;
        return <span key={i} className={`trinity-sparkline-bar${isNeg ? " neg" : ""}`} style={{ height: `${h}px` }} />;
      })}
    </span>
  );
}

function TimelineBar() {
  const now = new Date();
  const marketOpen = new Date(); marketOpen.setHours(9, 30, 0, 0);
  const marketClose = new Date(); marketClose.setHours(16, 0, 0, 0);
  const totalMin = (marketClose - marketOpen) / 60000;
  const elapsed = Math.max(0, Math.min(totalMin, (now - marketOpen) / 60000));
  const pct = Math.min(100, (elapsed / totalMin) * 100);
  const formatTime = (d) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return (
    <div className="trinity-timeline">
      <span className="trinity-timeline-label">4:00</span>
      <span className="trinity-timeline-label">OPEN</span>
      <div className="trinity-timeline-track">
        <div className="trinity-timeline-fill" style={{ width: `${pct}%` }} />
        <div className="trinity-timeline-now" style={{ left: `${pct}%` }}>
          <span className="trinity-timeline-now-label">{formatTime(now)}</span>
        </div>
      </div>
      <span className="trinity-timeline-label">20:00</span>
      <span className="trinity-timeline-label">CLOSE</span>
    </div>
  );
}

const PANEL_TICKERS = ["^SPX", "SPY", "QQQ", "^NDX", "IWM", "DIA", "TLT"];

function TrinityPanel({ ticker, data, viewMode, gexVexMode, loading: panelLoading, onFocus, onTickerChange, onTradeSelect }) {
  const [showTickerMenu, setShowTickerMenu] = useState(false);
  const spot = data?.spot;
  const nodes = data?.nodes;
  const gridData = data?.grid?.grid;
  const changePct = data?.change_pct;
  const vixLevel = data?.vix;

  const rows = useMemo(() => {
    if (!data?.strikes) return [];
    const sorted = data.strikes.filter(s => s.strike != null && s.gex != null).sort((a, b) => b.strike - a.strike);
    // Mark top 3 rows by abs GEX (excluding King which already has special styling)
    const byGex = [...sorted].sort((a, b) => Math.abs(b.gex || 0) - Math.abs(a.gex || 0));
    const top3Strikes = new Set(byGex.slice(0, 3).map(s => s.strike));
    return sorted.map(s => ({ ...s, _isTopGex: top3Strikes.has(s.strike) }));
  }, [data]);

  const expiries = useMemo(() => { if (!gridData) return []; return Object.keys(gridData).sort().slice(0, 6); }, [gridData]);

  const gridMaxAbs = useMemo(() => {
    if (!gridData || !expiries.length) return 1;
    let m = 1;
    for (const exp of expiries) { for (const s of Object.keys(gridData[exp] || {})) { const v = Math.abs(gridData[exp][s]?.gex || 0); if (v > m) m = v; } }
    return m;
  }, [gridData, expiries]);

  const maxAbs = useMemo(() => { if (!rows.length) return 1; return Math.max(...rows.map(s => Math.abs(s.gex || 0)), 1); }, [rows]);

  const spotIdx = useMemo(() => {
    if (!spot || !rows.length) return -1;
    let best = 0, bestDist = Math.abs(rows[0].strike - spot);
    for (let i = 1; i < rows.length; i++) { const d = Math.abs(rows[i].strike - spot); if (d < bestDist) { bestDist = d; best = i; } }
    return best;
  }, [rows, spot]);

  const flipStrike = useMemo(() => {
    if (nodes?.gamma_flip) return nodes.gamma_flip;
    let prev = rows[0]?.gex || 0;
    for (let i = 1; i < rows.length; i++) {
      const curr = rows[i]?.gex || 0;
      if ((prev > 0 && curr < 0) || (prev < 0 && curr > 0)) return (rows[i - 1].strike + rows[i].strike) / 2;
      prev = curr;
    }
    return null;
  }, [nodes, rows]);

  const kingStrike = useMemo(() => {
    if (!rows.length) return null;
    let maxVal = 0, kingS = null;
    for (const row of rows) { const v = Math.abs(row.gex || 0); if (v > maxVal) { maxVal = v; kingS = row.strike; } }
    return kingS;
  }, [rows]);

  const kingDistPct = useMemo(() => { if (!kingStrike || !spot) return null; return ((kingStrike - spot) / spot * 100); }, [kingStrike, spot]);

  const netGex = useMemo(() => { if (!rows.length) return 0; return rows.reduce((sum, s) => sum + (s.gex || 0), 0); }, [rows]);
  const [minGex, maxGex] = useMemo(() => { if (!rows.length) return [0, 0]; const g = rows.map(s => s.gex || 0); return [Math.min(...g), Math.max(...g)]; }, [rows]);

  const tags = useMemo(() => {
    const t = [];
    if (kingStrike != null) t.push("KING");
    if (flipStrike != null) t.push("FLR");
    if (nodes?.ceilings?.[0]) t.push("CEIL");
    if (nodes?.gatekeepers?.[0]) t.push("GATE");
    if (nodes?.air_pockets?.[0]) t.push("AIR");
    return t;
  }, [kingStrike, flipStrike, nodes]);

  const domCols = useMemo(() => {
    if (gexVexMode === "vex") return [{key:"call_vex",label:"Call VEX",field:"call_vex"},{key:"vex",label:"Net VEX",field:"vex"},{key:"put_vex",label:"Put VEX",field:"put_vex"},{key:"vomma",label:"Vomma",field:"vomma"},{key:"zomma",label:"Zomma",field:"zomma"}];
    return [{key:"call_gex",label:"Call GEX",field:"call_gex"},{key:"gex",label:"Net GEX",field:"gex"},{key:"put_gex",label:"Put GEX",field:"put_gex"},{key:"vex",label:"VEX",field:"vex"},{key:"charm",label:"Charm",field:"charm"}];
  }, [gexVexMode]);

  const handleRowClick = useCallback((row) => {
    const base = { ticker, strike: row.strike, spot, gex: row.gex, call_gex: row.call_gex, put_gex: row.put_gex, iv: row.iv, oi: row.total_oi, delta: row.delta };
    if (onTradeSelect) onTradeSelect(base);
    // Enrich with live Public.com contract data (OSI + bid/ask/last) so the
    // QuickTradePanel can submit a real order via /api/public/order.
    // Fire-and-forget upgrade: the base selection opens the panel instantly,
    // then we re-emit once Public data arrives (same strike → panel keeps
    // state and just fills in prices). Failure keeps the base selection.
    const front = row.expiry || expiries[0];
    if (onTradeSelect && front) {
      axios.get(
        `${API}/contract/${encodeURIComponent(ticker)}/${row.strike}/${front}`,
        { timeout: 15000 },
      ).then(({ data }) => {
        const contracts = data?.contracts || [];
        const callC = contracts.find((c) => c.type === "call") || contracts[0];
        const putC = contracts.find((c) => c.type === "put") || contracts[1];
        if (!callC && !putC) return;
        onTradeSelect({
          ...base,
          expiry: front,
          iv: base.iv ?? callC?.iv,
          delta: base.delta ?? callC?.delta,
          oi: base.oi ?? (callC?.open_interest ?? 0) + (putC?.open_interest ?? 0),
          oi_symbol: callC?.osi || putC?.osi || null,
          call_bid: callC?.bid, call_ask: callC?.ask, call_last: callC?.last,
          put_bid: putC?.bid, put_ask: putC?.ask, put_last: putC?.last,
        });
      }).catch(() => { /* base selection stands */ });
    }
  }, [ticker, spot, expiries, onTradeSelect]);

  const displayName = ticker.replace("^", "");
  const regime = nodes?.regime || "—";
  const regimeColor = regime === "positive" ? "text-emerald-400" : regime === "negative" ? "text-rose-400" : "text-slate-400";
  const regimeLabel = regime === "positive" ? "positive γ" : regime === "negative" ? "negative γ" : "neutral";

  const renderView = () => {
    if (rows.length === 0) return <div className="trinity-no-data">{panelLoading ? "Loading…" : "No strike data available"}</div>;
    const ma = Math.max(...rows.map(r => Math.abs(r.gex || 0)), 1);
    switch (viewMode) {
      case "dom": return <DOMView rows={rows} domCols={domCols} spotIdx={spotIdx} kingStrike={kingStrike} flipStrike={flipStrike} tags={tags} maxAbs={ma} onRowClick={handleRowClick} />;
      case "chain": return <ChainView rows={rows} spotIdx={spotIdx} kingStrike={kingStrike} flipStrike={flipStrike} onRowClick={handleRowClick} ma={ma} />;
      case "bars": return <BarsView rows={rows} maxAbs={ma} spotIdx={spotIdx} kingStrike={kingStrike} tags={tags} onRowClick={handleRowClick} />;
      case "list": return <ListView rows={rows} maxAbs={ma} spotIdx={spotIdx} kingStrike={kingStrike} flipStrike={flipStrike} onRowClick={handleRowClick} />;
      case "grid": default: return <GridView rows={rows} expiries={expiries} gridData={gridData} gridMaxAbs={gridMaxAbs} spotIdx={spotIdx} flipStrike={flipStrike} kingStrike={kingStrike} onRowClick={handleRowClick} />;
    }
  };

  return (
    <div className="trinity-panel">
      <div className="trinity-panel-header">
        <div className="trinity-ticker-wrap">
          <button className="trinity-ticker-btn" onClick={() => setShowTickerMenu(!showTickerMenu)} title="Switch ticker">{displayName}<span className="trinity-ticker-caret">▾</span></button>
          {showTickerMenu && (<div className="trinity-ticker-menu">{PANEL_TICKERS.map(t=>(<button key={t} className={`trinity-ticker-option${t===ticker?" trinity-ticker-active":""}`} onClick={()=>{onTickerChange(t);setShowTickerMenu(false);}}>{t.replace("^","")}</button>))}</div>)}
        </div>
        <span className="trinity-panel-price">${fmt(spot, spot >= 1000 ? 2 : 2)}</span>
        <MiniSparkline data={data} spot={spot} />
        {changePct != null && (<span className={`trinity-panel-change ${changePct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%</span>)}
        <span className="trinity-live-dot" />
        <span className={`trinity-panel-regime ${regimeColor}`}>{regimeLabel}</span>
      </div>
      <div className="trinity-panel-subheader">
        <span className="trinity-king-dot" /><span className="trinity-king-label">King</span>
        {kingStrike != null && <span className="trinity-king-value">{fmt(kingStrike, 0)}</span>}
        {kingDistPct != null && <span className={`trinity-king-dist ${kingDistPct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{kingDistPct >= 0 ? "+" : ""}{kingDistPct.toFixed(1)}%</span>}
        {vixLevel != null && (<><div className="trinity-divider" /><span className="trinity-stat-label">VIX</span><span className="trinity-stat-value text-amber-400">{fmt(vixLevel, 2)}</span></>)}
        <div className="trinity-tags">{tags.map(tag=>(<span key={tag} className={`trinity-tag trinity-tag-${tag.toLowerCase()}`}>{tag}</span>))}</div>
        <span className={`trinity-net-badge ${netGex >= 0 ? "trinity-net-pos" : "trinity-net-neg"}`}>{fmtGex(netGex)}</span>
      </div>
      <div className="trinity-grid">{renderView()}</div>
      {viewMode === "grid" && (
        <div className="trinity-legend">
          <span className="trinity-legend-label">Scale</span>
          <div className="trinity-legend-bar"><span className="trinity-legend-seg legend-neg-strong" /><span className="trinity-legend-seg legend-neg-weak" /><span className="trinity-legend-seg legend-zero" /><span className="trinity-legend-seg legend-pos-weak" /><span className="trinity-legend-seg legend-pos-strong" /></div>
          <div className="trinity-legend-labels"><span>−</span><span>0</span><span>+</span></div>
        </div>
      )}
      <div className="trinity-footer"><span className="trinity-footer-min">{fmtGex(minGex)}</span><div className="trinity-gradient-bar" /><span className="trinity-footer-max">{fmtGex(maxGex)}</span></div>
      <button className="trinity-focus-btn" onClick={onFocus}>focus →</button>
    </div>
  );
}

function DOMView({ rows, domCols, spotIdx, kingStrike, flipStrike, tags, maxAbs, onRowClick }) {
  const colMaxAbs = useMemo(() => {
    const r = {};
    for (const c of domCols) { let m = 1; for (const row of rows) { const v = Math.abs(row[c.field] || 0); if (v > m) m = v; } r[c.field] = m; }
    return r;
  }, [rows, domCols]);
  let pocF = null, pocA = 0, pocRI = -1, pocCK = null;
  rows.forEach((r, i) => { for (const c of domCols) { const v = Math.abs(r[c.field] || 0); if (v > pocA) { pocA = v; pocRI = i; pocCK = c.key; } } });
  return (
    <div className="trinity-dom-scroll"><table className="trinity-dom-table"><thead><tr className="trinity-dom-header"><th className="trinity-dom-th-price">Strike</th>{domCols.map(c=>(<th key={c.field} className="trinity-dom-th">{c.label}</th>))}<th className="trinity-dom-th">OI</th><th className="trinity-dom-th">IV</th><th className="trinity-dom-th-tags">Tags</th></tr></thead><tbody>
      {rows.map((row, i) => {
        const isC = i === spotIdx, isK = row.strike === kingStrike, isF = flipStrike != null && Math.abs(row.strike - flipStrike) <= (rows[0]?.strike - rows[1]?.strike || 5) / 2, isPR = i === pocRI;
        const rc = rowColors(row.gex, maxAbs);
        return (<tr key={row.strike} className={`trinity-dom-row${isC?" trinity-row-current":""}${isK?" trinity-row-king":""}${isF?" trinity-row-flip":""}${isPR?" trinity-row-king-grid":""}${row._isTopGex && !isK?" trinity-row-top-gex":""}`} style={{background:rc.bg}} onClick={()=>onRowClick&&onRowClick(row)} role="button" tabIndex={0}>
          <td className={`trinity-dom-price${isC?" trinity-price-current":""}`}>{isC&&<span className="trinity-price-arrow" />}{(isK || row._isTopGex) && <span className="trinity-king-star">★</span>}{fmt(row.strike, row.strike >= 1000 ? 0 : 1)}</td>
          {domCols.map(c => { const val = row[c.field] || 0; const cc = rowColors(val, colMaxAbs[c.field]); const isPC = pocCK === c.key && isPR; const pct = pctOfMax(val, colMaxAbs[c.field]); return (<td key={c.field} className={`trinity-dom-cell${isPC?" trinity-grid-poc":""}`} style={{background:isPC?"rgba(251,191,36,0.35)":cc.bg,color:isPC?"#0b1121":cc.text}}>{fmtGex(val)}{pct > 40 && <span className={`trinity-cell-pct${val >= 0 ? " trinity-cell-pct-pos" : " trinity-cell-pct-neg"}`}>{val >= 0 ? "+" : ""}{pct.toFixed(0)}%</span>}</td>); })}
          <td className="trinity-dom-cell trinity-dom-oi">{fmtOi(row.total_oi)}</td>
          <td className="trinity-dom-cell trinity-dom-iv">{row.iv != null ? `${(row.iv * 100).toFixed(1)}%` : "—"}</td>
          <td className="trinity-dom-tags">{tags.map(t=>(<span key={t} className={`trinity-tag trinity-tag-${t.toLowerCase()}`}>{t}</span>))}</td>
        </tr>);
      })}
    </tbody></table></div>
  );
}

function ChainView({ rows, spotIdx, kingStrike, flipStrike, onRowClick, ma }) {
  return (<div className="trinity-chain-scroll"><table className="trinity-chain-table"><thead><tr className="trinity-chain-header"><th className="trinity-chain-th">Strike</th><th className="trinity-chain-th">GEX</th><th className="trinity-chain-th">Call</th><th className="trinity-chain-th">Put</th><th className="trinity-chain-th">OI</th><th className="trinity-chain-th">VEX</th><th className="trinity-chain-th">IV</th><th className="trinity-chain-th">Δ</th><th className="trinity-chain-th">Charm</th></tr></thead><tbody>
    {rows.map((row, i) => {
      const isC = i === spotIdx, isK = row.strike === kingStrike, isF = flipStrike != null && Math.abs(row.strike - flipStrike) <= (rows[0]?.strike - rows[1]?.strike || 5) / 2;
      const rc = rowColors(row.gex, ma);
      return (<tr key={row.strike} className={`trinity-chain-row${isC?" trinity-row-current":""}`} style={{background:rc.bg}} onClick={()=>onRowClick&&onRowClick(row)} role="button" tabIndex={0}>
        <td className={`trinity-chain-price${isC?" trinity-price-current":""}`}>{isC&&<span className="trinity-price-arrow" />}{(isK || row._isTopGex) && <span className="trinity-king-star">★</span>}{fmt(row.strike, row.strike >= 1000 ? 0 : 1)}</td>
        <td className="trinity-chain-cell" style={{color:rc.text}}>{fmtGex(row.gex)}</td>
        <td className="trinity-chain-cell" style={{color:"#6ee7b7"}}>{fmtGex(row.call_gex)}</td>
        <td className="trinity-chain-cell" style={{color:"#c4b5fd"}}>{fmtGex(row.put_gex)}</td>
        <td className="trinity-chain-cell trinity-chain-oi">{fmtOi(row.total_oi)}</td>
        <td className="trinity-chain-cell" style={{color:row.vex>=0?"#6ee7b7":"#c4b5fd"}}>{fmtGex(row.vex)}</td>
        <td className="trinity-chain-cell trinity-chain-iv">{row.iv!=null?`${(row.iv*100).toFixed(1)}%`:"—"}</td>
        <td className="trinity-chain-cell">{row.delta!=null?row.delta.toFixed(2):"—"}</td>
        <td className="trinity-chain-cell" style={{color:row.charm>=0?"#6ee7b7":"#c4b5fd"}}>{fmtGex(row.charm)}</td>
      </tr>);
    })}
  </tbody></table></div>);
}

function BarsView({ rows, maxAbs, spotIdx, kingStrike, tags, onRowClick }) {
  let pocI = -1, pocA = 0;
  rows.forEach((r, i) => { const v = Math.abs(r.gex || 0); if (v > pocA) { pocA = v; pocI = i; } });
  return (<div className="trinity-bars-scroll">
    {rows.map((row, i) => {
      const isC = i === spotIdx, isK = row.strike === kingStrike, isP = i === pocI && !isK;
      const gex = row.gex || 0, pct = maxAbs > 0 ? (Math.abs(gex) / maxAbs) * 100 : 0;
      const rc = rowColors(gex, maxAbs);
      let barColor;
      if (isK) barColor = "linear-gradient(90deg, rgba(251,191,36,0.95), rgba(253,224,71,0.95))";
      else if (isP) barColor = "linear-gradient(90deg, rgba(251,191,36,0.7), rgba(251,191,36,0.4))";
      else if (gex < 0) barColor = "linear-gradient(90deg, rgba(168,85,247,0.6), rgba(168,85,247,0.3))";
      else barColor = "linear-gradient(90deg, rgba(45,212,191,0.6), rgba(45,212,191,0.3))";
      return (<div key={row.strike} className={`trinity-bar-row${isC?" trinity-row-current":""}${isK?" trinity-row-king-bar":""}${isP?" trinity-row-poc-bar":""}`} style={{background:rc.bg}} onClick={()=>onRowClick&&onRowClick(row)} role="button" tabIndex={0}>
        <span className={`trinity-bar-price${isC?" trinity-price-current":""}`}>{isC&&<span className="trinity-price-arrow" />}{isK&&<span className="trinity-king-star-bar">★</span>}{fmt(row.strike, row.strike >= 1000 ? 0 : 1)}</span>
        <div className="trinity-bar-track"><div className="trinity-bar-fill" style={{width:`${Math.min(100,pct)}%`,background:barColor}} /></div>
        <span className="trinity-bar-value" style={{color:rc.text}}>{fmtGex(gex)}</span>
        {rc.badge && <span className={`trinity-badge ${rc.badge.cls}`}>{rc.badge.text}</span>}
      </div>);
    })}
  </div>);
}

function ListView({ rows, maxAbs, spotIdx, kingStrike, flipStrike, onRowClick }) {
  return (<div className="trinity-list-scroll">
    {rows.map((row, i) => {
      const isC = i === spotIdx, isK = row.strike === kingStrike, isF = flipStrike != null && Math.abs(row.strike - flipStrike) <= (rows[0]?.strike - rows[1]?.strike || 5) / 2;
      const gex = row.gex || 0, rc = rowColors(gex, maxAbs), pctV = maxAbs > 0 ? Math.abs(gex / maxAbs) * 100 : 0;
      return (<div key={row.strike} className={`trinity-row${isC?" trinity-row-current":""}${isK?" trinity-row-king":""}${isF?" trinity-row-flip":""}`} style={{background:rc.bg}} onClick={()=>onRowClick&&onRowClick(row)} role="button" tabIndex={0}>
        <span className={`trinity-row-price${isC?" trinity-price-current":""}`}>{isC&&<span className="trinity-price-arrow" />}{(isK || row._isTopGex) && <span className="trinity-king-star">★</span>}{fmt(row.strike, row.strike >= 1000 ? 0 : 1)}</span>
        <span className="trinity-row-pct">{pctV > 15 && (<span className={`trinity-pct-badge${gex>=0?" trinity-pct-pos":" trinity-pct-neg"}`}>{gex>=0?"+":""}{pctV.toFixed(0)}%</span>)}</span>
        <span className="trinity-row-value" style={{color:rc.text}}>{fmtGex(gex)}</span>
        {row.total_oi > 0 && <span className="trinity-row-oi">{fmtOi(row.total_oi)}</span>}
        {row.iv != null && <span className="trinity-row-iv">{(row.iv * 100).toFixed(1)}%</span>}
        {rc.badge && <span className={`trinity-badge ${rc.badge.cls}`}>{rc.badge.text}</span>}
      </div>);
    })}
  </div>);
}

function GridView({ rows, expiries, gridData, gridMaxAbs, spotIdx, flipStrike, kingStrike, onRowClick }) {
  const poc = useMemo(() => {
    if (!gridData || expiries.length === 0) return { pocS: null, pocE: null, pocA: 0 };
    let pocS = null, pocE = null, pocA = 0;
    for (const exp of expiries) { for (const [s, cell] of Object.entries(gridData[exp] || {})) { const v = Math.abs(cell?.gex || 0); if (v > pocA) { pocA = v; pocS = Number(s); pocE = exp; } } }
    return { pocS, pocE, pocA };
  }, [gridData, expiries]);
  if (!gridData || expiries.length === 0) return <div className="trinity-no-data">No grid data available</div>;
  const { pocS, pocE, pocA } = poc;
  const pocN = Math.min(1, pocA / gridMaxAbs);
  return (<div className="trinity-grid-scroll"><table className="trinity-grid-table"><thead><tr className="trinity-grid-header"><th className="trinity-grid-th-price">Strike</th>{expiries.map(e=>(<th key={e} className="trinity-grid-th">{e.slice(5)}</th>))}</tr></thead><tbody>
    {rows.map((row, i) => {
      const isC = i === spotIdx, isF = flipStrike != null && Math.abs(row.strike - flipStrike) <= (rows[0]?.strike - rows[1]?.strike || 5) / 2, isPR = pocS != null && Math.abs(row.strike - pocS) < 0.5;
      const rc = rowColors(row.gex, gridMaxAbs);
      return (<tr key={row.strike} className={`trinity-grid-row${isC?" trinity-row-current":""}${isF?" trinity-row-flip":""}${isPR?" trinity-row-king-grid":""}`} style={{background:rc.bg}} onClick={()=>onRowClick&&onRowClick(row)} role="button" tabIndex={0}>
        <td className={`trinity-grid-price${isC?" trinity-price-current":""}`}>{isC&&<span className="trinity-price-arrow" />}{fmt(row.strike, row.strike >= 1000 ? 0 : 1)}</td>
        {expiries.map(exp => {
          const cv = gridData[exp]?.[row.strike]?.gex || 0, cc = rowColors(cv, gridMaxAbs), isPC = isPR && exp === pocE;
          return (<td key={exp} className={`trinity-grid-cell${isPC?" trinity-grid-poc":""}`} style={{background:isPC?`rgba(251,191,36,${0.25+0.65*pocN})`:cc.bg,color:isPC?"#0b1121":cc.text}} title={`${fmt(row.strike,0)} @ ${exp}: ${fmtGex(cv)}`}>{fmtGex(cv)}</td>);
        })}
      </tr>);
    })}
  </tbody></table></div>);
}
