import React, { useEffect, useMemo, useState, useCallback, useRef } from "react";
import axios from "axios";
import "@/App.css";

import { fmt, fmtAbs, pctClass, tagFor, TRINITY, DEFAULT_TICKERS } from "./lib/helpers";
import GridHeatmap from "./components/GridHeatmap";
import BarHeatmap from "./components/BarHeatmap";
import PatternCard from "./components/PatternCard";
import TrinityView from "./components/TrinityView";
import {
  FlipZonesPanel, StackedNodesPanel, TugOfWarPanel, ScenarioPanel,
  RiskDashboardPanel, OpportunitiesPanel, ImpliedMovePanel, VolAnalyticsPanel,
  GreekReferencePanel, UsagePanel, LivePolicyPanel,
} from "./components/SidebarPanels";
import {
  MarketRegimePanel, ImpliedPDFPanel, HedgeImpulsePanel,
  PressureCloudPanel, CharmIntegralPanel,
} from "./components/AdvancedAnalyticsPanel";
import PortfolioPanel from "./components/PortfolioPanel";
import FlowTicker from "./components/FlowTicker";
import HistoryPanel from "./components/HistoryPanel";
import OptionsChainTable from "./components/OptionsChainTable";
import MultiTimeframeGEXPanel from "./components/MultiTimeframeGEXPanel";
import AlertsPanel from "./components/AlertsPanel";
import UOAPanel from "./components/UOAPanel";
import { useWebSocketGex } from "./hooks/useWebSocketGex";
import { useDebounce } from "./hooks/useDebounce";
import { useDataSource } from "./hooks/useDataSource";
import { DataSourceBadge } from "./components/DataSourceBadge";
import { SettingsPanel } from "./components/SettingsPanel";
import { ShortcutsModal } from "./components/ShortcutsModal";
import { MorningBriefing } from "./components/MorningBriefing";
import { PositionSizing } from "./components/PositionSizing";
import { TradeEntry } from "./components/TradeEntry";
import { TradeJournal } from "./components/TradeJournal";
import { DashboardSummary } from "./components/DashboardSummary";
import { TradeAnalytics } from "./components/TradeAnalytics";
import { SocialFlowPanel } from "./components/SocialFlowPanel";
import HeatseekerDashboard from "./components/heatseeker/HeatseekerDashboard";
import AlertOverlay from "./components/AlertOverlay";
import PaperTrade from "./components/PaperTrade";
import PWAInstallBanner from "./components/PWAInstallBanner";
import { useTheme } from "./context/ThemeContext";
import { autoDecimate } from "./utils/dataDecimator";

import ToxicityGauge from "./components/ToxicityGauge";
import ErrorBoundary from "./components/ErrorBoundary";
import { RetryButton, ErrorState } from "./components/RetryButton";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ============ Velocity Gauge ============
function VelocityGauge({ velocity }) {
  if (!velocity) return null;
  const score = velocity.velocity_score || 0;
  const warming = (velocity.snapshots_count || 0) < 3;
  const angle = score * 180 - 90;
  const color = warming ? "#64748b" : score > 0.4 ? "#ef4444" : score > 0.2 ? "#fbbf24" : "#34d399";
  return (
    <div className="panel-2 p-3" data-testid="velocity-gauge">
      <div className="label mb-2">Velocity Mode</div>
      <div className="flex items-center gap-3">
        <svg viewBox="0 0 100 60" width="100" height="60">
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke="#1f2a3a" strokeWidth="6" />
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke={color} strokeWidth="6" strokeDasharray={`${score * 125} 200`} strokeLinecap="round" />
          <line x1="50" y1="55" x2={50 + 35 * Math.cos((angle - 90) * Math.PI / 180)} y2={55 + 35 * Math.sin((angle - 90) * Math.PI / 180)} stroke={color} strokeWidth="2" />
          <circle cx="50" cy="55" r="3" fill={color} />
        </svg>
        <div>
          <div className="text-2xl font-bold mono" style={{ color }}>{warming ? "…" : (score * 100).toFixed(0)}</div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">{warming ? "warming up" : "rate of change"}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
        <div><div className="label">Floor</div><div className={velocity.rolling_floor === "rolling_up" ? "text-emerald-400" : velocity.rolling_floor === "rolling_down" ? "text-rose-400" : "text-slate-400"}>{(velocity.rolling_floor || "stable").replace("_", " ")}</div></div>
        <div><div className="label">Ceiling</div><div className={velocity.rolling_ceiling === "rolling_up" ? "text-emerald-400" : velocity.rolling_ceiling === "rolling_down" ? "text-rose-400" : "text-slate-400"}>{(velocity.rolling_ceiling || "stable").replace("_", " ")}</div></div>
      </div>
    </div>
  );
}

// ============ Top Movers ============
function Movers({ onPick }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    let mounted = true;
    const f = async () => {
      try { const res = await axios.get(`${API}/movers?limit=12`); if (mounted) setRows(res.data.results || []); } catch (e) { /* noop */ }
    };
    f();
    const id = setInterval(f, 60000);
    return () => { mounted = false; clearInterval(id); };
  }, []);
  return (
    <div className="panel p-3" data-testid="movers-panel">
      <div className="label mb-2">Top Movers (prev session %)</div>
      <div className="flex flex-col gap-1 text-[11px]">
        {rows.length === 0 && <div className="text-slate-500">…</div>}
        {rows.map((r) => (
          <button key={r.ticker} data-testid={`mover-${r.ticker}`} onClick={() => onPick && onPick(r.ticker)} className="flex justify-between items-center px-2 py-1 hover:bg-slate-800/40 rounded">
            <span className="font-bold w-14 text-left">{r.ticker}</span>
            <span className="mono text-slate-400 w-20 text-right">${fmt(r.close, 2)}</span>
            <span className={`mono w-16 text-right ${pctClass(r.pct)}`}>{r.pct >= 0 ? "+" : ""}{r.pct}%</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ============ Nodes Table ============
function NodesTable({ data }) {
  const [sortKey, setSortKey] = useState("mag");
  const [sortDir, setSortDir] = useState("desc");
  if (!data?.nodes) return null;
  const spot = data.spot;
  const all = (data.strikes || []).map((s) => {
    const role = s.strike === data.nodes.king?.strike ? "King" : data.nodes.floors?.some(f => f.strike === s.strike) ? "Floor" : data.nodes.ceilings?.some(f => f.strike === s.strike) ? "Ceiling" : data.nodes.gatekeepers?.some(f => f.strike === s.strike) ? "Gatekeeper" : null;
    return { ...s, role, mag: Math.abs(s.gex), dist: Math.abs(s.strike - spot) / spot * 100 };
  }).filter(s => s.role || s.mag > 0);
  const sorted = [...all].sort((a, b) => { const va = a[sortKey], vb = b[sortKey]; if (va == null) return 1; if (vb == null) return -1; return sortDir === "desc" ? vb - va : va - vb; });
  const head = (k, l) => (
    <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1 cursor-pointer hover:text-teal-400" onClick={() => { setSortKey(k); setSortDir(d => sortKey === k && d === "desc" ? "asc" : "desc"); }}>
      {l}{sortKey === k ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
    </th>
  );
  return (
    <div className="panel p-3" data-testid="nodes-table">
      <div className="label mb-2">Structural Nodes</div>
      <div className="overflow-y-auto" style={{ maxHeight: 280 }}>
        <table className="w-full text-[11px] mono">
          <thead className="sticky top-0" style={{ background: "var(--panel)" }}>
            <tr>
              {head("strike", "Strike")}
              <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1">Role</th>
              {head("mag", "|GEX|")}
              {head("gex", "Net")}
              {head("dist", "Δ Spot")}
              {head("taps", "Taps")}
              <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1">Life</th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 30).map((s) => (
              <tr key={s.strike} className="bar-row border-t border-slate-800/60">
                <td className="px-2 py-1 font-bold text-slate-200">{fmt(s.strike, 0)}</td>
                <td className="px-2 py-1">{s.role && <span className={`tag ${s.role === "King" ? "king" : s.role === "Floor" ? "floor" : s.role === "Ceiling" ? "ceiling" : "gate"}`}>{s.role}</span>}</td>
                <td className="px-2 py-1 text-slate-300">{fmtAbs(s.mag)}</td>
                <td className={`px-2 py-1 ${s.gex > 0 ? "text-emerald-400" : "text-rose-400"}`}>{s.gex > 0 ? "+" : ""}{fmtAbs(s.gex)}</td>
                <td className="px-2 py-1 text-slate-500">{s.dist.toFixed(2)}%</td>
                <td className="px-2 py-1 text-slate-500">{s.taps}</td>
                <td className="px-2 py-1"><span className={tagFor(s.lifecycle)}>{s.lifecycle}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============ Drilldown ============
function Drilldown({ ticker, expiry, strike, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    const params = new URLSearchParams();
    if (expiry) params.set("expiry", expiry);
    if (strike) params.set("strike", strike);
    axios.get(`${API}/contract/${encodeURIComponent(ticker)}?${params.toString()}`).then(r => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [ticker, expiry, strike]);
  if (!data && !loading) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }} onClick={onClose}>
      <div className="panel p-4 max-w-4xl w-[90%] max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()} data-testid="drilldown-modal">
        <div className="flex justify-between items-center mb-3">
          <div><div className="label">Contract Drilldown</div><div className="text-lg font-bold">{ticker} {strike ? `· ${strike}` : ""} {expiry ? `· ${expiry}` : ""}</div></div>
          <button onClick={onClose} className="btn" data-testid="drilldown-close">close ✕</button>
        </div>
        {loading && <div className="text-slate-500">loading…</div>}
        {data && (
          <div>
            <div className="text-[11px] text-slate-500 mb-2">Spot {fmt(data.spot, 2)} · {data.count} contracts · source {data.data_source}</div>
            {data.count === 0 ? (
              <div className="text-slate-500 text-xs py-8 text-center">No contracts at this strike × expiry combination.</div>
            ) : (
              <table className="w-full text-[11px] mono">
                <thead className="text-slate-500 text-[10px] uppercase tracking-widest">
                  <tr>
                    <th className="text-left px-2 py-1">Type</th><th className="text-left px-2 py-1">Strike</th><th className="text-left px-2 py-1">Expiry</th>
                    <th className="text-right px-2 py-1">OI</th><th className="text-right px-2 py-1">Volume</th><th className="text-right px-2 py-1">IV</th>
                    <th className="text-right px-2 py-1">Δ</th><th className="text-right px-2 py-1">Γ</th><th className="text-right px-2 py-1">GEX</th><th className="text-left px-2 py-1">Src</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i} className="bar-row border-t border-slate-800/60">
                      <td className={`px-2 py-1 ${r.type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{r.type}</td>
                      <td className="px-2 py-1 font-bold">{fmt(r.strike, 0)}</td>
                      <td className="px-2 py-1 text-slate-400">{r.expiry}</td>
                      <td className="px-2 py-1 text-right">{fmt(r.oi, 0)}</td>
                      <td className="px-2 py-1 text-right text-slate-500">{fmt(r.volume, 0)}</td>
                      <td className="px-2 py-1 text-right text-slate-400">{(r.iv * 100).toFixed(1)}%</td>
                      <td className="px-2 py-1 text-right text-slate-400">{r.delta?.toFixed(3)}</td>
                      <td className="px-2 py-1 text-right text-slate-500">{r.gamma?.toFixed(5)}</td>
                      <td className={`px-2 py-1 text-right ${r.gex > 0 ? "text-emerald-400" : "text-rose-400"}`}>{fmtAbs(r.gex)}</td>
                      <td className="px-2 py-1 text-[10px] text-slate-600">{r.oi_source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ============ Ticker Search / Autocomplete ============
function TickerSearch({ tickers, value, onChange }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef(null);
  const ref = useRef(null);

  const filtered = useMemo(() => {
    const q = query.toUpperCase().replace("^", "");
    if (!q) return tickers.slice(0, 10);
    return tickers.filter(t => t.toUpperCase().replace("^", "").includes(q)).slice(0, 10);
  }, [query, tickers]);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <input
        ref={inputRef}
        value={open ? query : value.replace("^", "")}
        onChange={e => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => { setQuery(""); setOpen(true); }}
        onKeyDown={e => {
          if (e.key === "Enter" && filtered.length > 0) {
            onChange(filtered[0]);
            setOpen(false);
            inputRef.current?.blur();
          }
          if (e.key === "Escape") { setOpen(false); inputRef.current?.blur(); }
        }}
        placeholder="Search ticker…"
        className="btn"
        style={{ padding: "4px 8px", width: 120 }}
      />
      {open && filtered.length > 0 && (
        <div className="absolute top-full left-0 mt-1 w-40 rounded border border-slate-700 shadow-xl z-50 overflow-hidden" style={{ background: "var(--panel)" }}>
          {filtered.map(t => (
            <button
              key={t}
              onClick={() => { onChange(t); setOpen(false); setQuery(""); }}
              className="block w-full text-left px-3 py-1.5 text-[11px] hover:bg-slate-700/60 transition-colors"
              style={{ background: t === value ? "var(--bg-2)" : "transparent" }}
            >
              <span className="font-bold">{t.replace("^", "")}</span>
              {t.startsWith("^") && <span className="text-slate-500 ml-1 text-[9px]">IDX</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ============ Regime Color Helper ============
const regimeColor = (regime) => regime === "positive" ? "text-emerald-400" : regime === "negative" ? "text-rose-400" : "text-slate-400";

// ============ Main App ============
export default function App() {
  const [page, setPage] = useState("trinity");
  const [ticker, setTicker] = useState(() => {
    try { return localStorage.getItem("floww_settings") ? JSON.parse(localStorage.getItem("floww_settings")).defaultTicker || "SPY" : "SPY"; } catch { return "SPY"; }
  });
  const [refreshMs, setRefreshMs] = useState(() => {
    try { return localStorage.getItem("floww_settings") ? JSON.parse(localStorage.getItem("floww_settings")).refreshMs || 25000 : 25000; } catch { return 25000; }
  });
  const [data, setData] = useState(null);
  const [livespot, setLivespot] = useState(null);
  const [err, setErr] = useState(null);
  const [showLeftSidebar, setShowLeftSidebar] = useState(false);
  const [showRightSidebar, setShowRightSidebar] = useState(false);
  const [view, setView] = useState("grid");
  const [viewMode, setViewMode] = useState("gex");
  const [mode, setMode] = useState("day");
  const [filters, setFilters] = useState({ side: "all", lifecycle: "all", magMin: 0 });
  const [expiries, setExpiries] = useState(4);
  const [dte, setDte] = useState(null);
  const [drilldown, setDrilldown] = useState(null);
  const [tickers, setTickers] = useState(null);
  const [advanced, setAdvanced] = useState(null);
  const wsGex = useWebSocketGex(page === "heatseeker" ? ticker : null);
  const { theme, toggleTheme } = useTheme();
  const [ensembleData, setEnsembleData] = useState(null);
  const dataSource = useDataSource({ pollIntervalMs: 30000 });

  // Debounced filter values to prevent API spam
  const debouncedMode = useDebounce(mode, 300);
  const debouncedExpiries = useDebounce(expiries, 300);
  const debouncedDte = useDebounce(dte, 300);

  // Fetch tickers
  useEffect(() => { axios.get(`${API}/tickers`).then(r => setTickers(r.data)).catch(() => {}); }, []);

  const [loading, setLoading] = useState(false);

  // Fetch heatmap data
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const dteParam = debouncedDte != null ? `&dte=${debouncedDte}` : "";
      const res = await axios.get(`${API}/heatmap/${ticker}?expiries=${debouncedExpiries}&mode=${debouncedMode}${dteParam}`, { timeout: 30000 });
      setData(res.data); setErr(null);
    } catch (e) {
      let msg = "Failed to load data";
      if (e.code === "ECONNABORTED") {
        msg = "Request timed out. The server may be busy.";
      } else if (e.response) {
        const detail = e.response.data?.detail;
        if (typeof detail === "string") msg = detail;
        else if (Array.isArray(detail) && detail[0]?.msg) msg = detail[0].msg;
        else if (detail?.error) msg = detail.error;
        else if (typeof detail === "object") msg = JSON.stringify(detail);
      } else if (e.request) {
        msg = "Network error. Check your connection.";
      }
      setErr(msg);
    } finally {
      setLoading(false);
    }
  }, [ticker, debouncedExpiries, debouncedMode, debouncedDte]);

  // Fetch advanced analytics
  const fetchAdvanced = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/advanced/${ticker}?expiries=${debouncedExpiries}`);
      setAdvanced(res.data);
    } catch (e) { /* noop */ }
  }, [ticker, debouncedExpiries]);

  // Auto-dismiss errors after 10s
  useEffect(() => {
    if (!err) return;
    const id = setTimeout(() => setErr(null), 10000);
    return () => clearTimeout(id);
  }, [err]);

  // Main data fetch with in-flight guard
  useEffect(() => {
    let cancelled = false;
    const doFetch = async () => {
      if (cancelled) return;
      try {
        const r = await axios.get(`${API}/data/${ticker}`);
        if (!cancelled) setData(r.data);
      } catch (e) { if (!cancelled) setErr(e.message); }
    };
    doFetch();
    const id = setInterval(doFetch, refreshMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [ticker, refreshMs]);

  // Advanced analytics with in-flight guard
  useEffect(() => {
    let cancelled = false;
    const doFetch = async () => {
      if (cancelled) return;
      try {
        const r = await axios.get(`${API}/advanced/${ticker}`);
        if (!cancelled) setAdvanced(r.data);
      } catch (e) { if (!cancelled) {} }
    };
    doFetch();
    const id = setInterval(doFetch, refreshMs * 2);
    return () => { cancelled = true; clearInterval(id); };
  }, [ticker, refreshMs]);

  // Ensemble toxicity polling
  useEffect(() => {
    if (page !== "heatseeker") return;
    let cancelled = false;
    const fetchEnsemble = async () => {
      try {
        const r = await axios.get(`${API}/ensemble/state?ticker=${ticker}`);
        if (!cancelled) setEnsembleData(r.data);
      } catch (e) { /* noop */ }
    };
    fetchEnsemble();
    const id = setInterval(fetchEnsemble, 10000);
    return () => { cancelled = true; clearInterval(id); };
  }, [ticker, page]);

  // Live spot polling with in-flight guard
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      try {
        const r = await axios.get(`${API}/spot/${ticker}`);
        if (!cancelled) setLivespot(r.data);
      } catch (e) { if (!cancelled) {} }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, [ticker]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;
      if (e.metaKey || e.ctrlKey) return;

      switch (e.key) {
        case "1": setPage("trinity"); break;
        case "2": setPage("heatseeker"); break;
        case "3": setPage("portfolio"); break;
        case "4": setPage("journal"); break;
        case "5": setPage("dashboard"); break;
        case "6": setPage("papertrade"); break;
        case "g": setView("grid"); break;
        case "b": setView("bar"); break;
        case "c": setView("chain"); break;
        case "j": setPage("journal"); break;
        case "d": setMode("day"); break;
        case "s": setMode("swing"); break;
        case "x": setMode("scalp"); break;
        case "e": setViewMode("gex"); break;
        case "v": setViewMode("vex"); break;
        case "h": setViewMode("charm"); break;
        case "ArrowUp":
          e.preventDefault();
          if (tickers) {
            const all = [...(tickers.trinity || []), ...(tickers.default || []), ...(tickers.popular || [])];
            const idx = all.indexOf(ticker);
            if (idx > 0) setTicker(all[idx - 1]);
          }
          break;
        case "ArrowDown":
          e.preventDefault();
          if (tickers) {
            const all = [...(tickers.trinity || []), ...(tickers.default || []), ...(tickers.popular || [])];
            const idx = all.indexOf(ticker);
            if (idx < all.length - 1) setTicker(all[idx + 1]);
          }
          break;
        default: break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [tickers, ticker]);

  const spotDelta = livespot?.spot && data?.spot ? livespot.spot - data.spot : 0;

  const handleFocusTicker = (t) => { setTicker(t === "^SPX" ? "SPX" : t); setPage("heatseeker"); };

  // Handle alert signal click -> navigate to Atlas tab
  const handleSignalClick = useCallback((alert) => {
    if (alert.ticker) {
      setTicker(alert.ticker);
      setPage("heatseeker");
    }
  }, []);

  // Decimate data for performance
  const displayData = useMemo(() => {
    if (!data) return data;
    if (!data.strikes || data.strikes.length < 2000) return data;
    return {
      ...data,
      strikes: autoDecimate(data.strikes, 5000),
    };
  }, [data]);

  return (
    <div className="App">
      {/* Alert Overlay - Real-time signal toasts */}
      <AlertOverlay onSignalClick={handleSignalClick} maxVisible={3} />

      {/* PWA Install Banner */}
      <PWAInstallBanner />

      {/* Header */}
      <header className="app-header">
        <div className="nav-tabs">
          <button onClick={() => setPage("trinity")} className={`btn ${page === "trinity" ? "active" : ""}`}>Trinity</button>
          <button onClick={() => setPage("heatseeker")} className={`btn ${page === "heatseeker" ? "active" : ""}`}>Heatseeker</button>
          <button onClick={() => setPage("skylit")} className={`btn ${page === "skylit" ? "active" : ""}`}>Skylit</button>
          <button onClick={() => setPage("portfolio")} className={`btn ${page === "portfolio" ? "active" : ""}`}>Portfolio</button>
          <button onClick={() => setPage("journal")} className={`btn ${page === "journal" ? "active" : ""}`}>Journal</button>
          <button onClick={() => setPage("swarmspx")} className={`btn ${page === "swarmspx" ? "active" : ""}`}>SwarmSPX</button>
          <button onClick={() => setPage("dashboard")} className={`btn ${page === "dashboard" ? "active" : ""}`}>Dashboard</button>
          <button onClick={() => setPage("papertrade")} className={`btn ${page === "papertrade" ? "active" : ""}`}>PaperTrade</button>
        </div>
        <div className="header-right">
          {tickers && (
            <TickerSearch
              tickers={[...(tickers.trinity || []), ...(tickers.default || []), ...(tickers.popular || [])]}
              value={ticker}
              onChange={setTicker}
            />
          )}
          <div className="hidden-mobile">
            <DataSourceBadge
              source={dataSource.source || data?.data_source || null}
              delaySeconds={dataSource.delaySeconds ?? data?.delay_seconds ?? null}
              badgeStatus={
                data?.data_fallback === true
                  ? "cached"
                  : dataSource.badgeStatus === "offline" && data?.data_source
                  ? data?.data_source === "alphavantage"
                    ? "delayed"
                    : "live"
                  : dataSource.badgeStatus
              }
            />
          </div>
          {/* Theme Toggle */}
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
        </div>
      </header>

      {/* Trinity View */}
      {page === "trinity" && (
        <div className="p-4 flex-1 overflow-auto">
          <TrinityView onFocusTicker={handleFocusTicker} />
        </div>
      )}

      {/* Single Ticker Heatseeker */}
      {page === "heatseeker" && (
        <div className="heatseeker-layout">
          {/* Left Sidebar - Filters & Summary */}
          <aside className={`heatseeker-sidebar-left ${showLeftSidebar ? 'open' : ''}`}>
            <div className="p-2 space-y-2">
              {/* Ticker Summary */}
              <div className="panel p-3">
                <div className="flex justify-between items-baseline">
                  <div className="text-lg font-bold tracking-wider">{ticker.replace("^", "")}</div>
                  <div className={`text-xs uppercase tracking-widest ${regimeColor(data?.nodes?.regime)}`}>{data?.nodes?.regime || "—"} γ</div>
                </div>
                <div className="text-2xl mono mt-1" data-testid="spot-price">
                  ${fmt(livespot?.spot ?? data?.spot, 2)}
                  {livespot && data?.spot && Math.abs(spotDelta) > 0.01 && (
                    <span className={`ml-2 text-xs ${spotDelta > 0 ? "text-emerald-400" : "text-rose-400"}`} data-testid="spot-delta">
                      {spotDelta > 0 ? "▲" : "▼"} {Math.abs(spotDelta).toFixed(2)}
                    </span>
                  )}
                  {livespot && <span className="ml-2 text-[9px] uppercase tracking-widest text-teal-500 flash-pulse">● live</span>}
                </div>
                <div className="text-[10px] text-slate-500">
                  {data?.expiries_used?.length ? `${data.expiries_used.length} exp · ${data.expiries_used[0]} → ${data.expiries_used.slice(-1)[0]}` : ""}
                </div>
                {err && (
                  <ErrorState
                    error={err}
                    onRetry={() => { setErr(null); fetchData(); }}
                    title="Data load failed"
                  />
                )}
                {loading && !data && (
                  <div className="text-sky-400 text-[11px] mt-2 bg-sky-500/10 rounded px-2 py-1.5 flex items-center gap-2 border border-sky-500/20">
                    <span className="inline-block w-2 h-2 bg-sky-400 rounded-full animate-pulse" />
                    Loading market data…
                  </div>
                )}
                <div className="dotted-divider my-3" />
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div><div className="label">King</div><div className="mono text-amber-300">{fmt(data?.nodes?.king?.strike, 0)}</div></div>
                  <div><div className="label">|GEX|</div><div className="mono">{fmtAbs(data?.nodes?.king?.gex)}</div></div>
                  <div><div className="label">Top Floor</div><div className="mono text-emerald-400">{fmt(data?.nodes?.floors?.[0]?.strike, 0) || "—"}</div></div>
                  <div><div className="label">Top Ceiling</div><div className="mono text-rose-400">{fmt(data?.nodes?.ceilings?.[0]?.strike, 0) || "—"}</div></div>
                  <div><div className="label">Polarity</div><div className="mono text-sky-300">{data?.nodes?.polarity_level ? fmt(data.nodes.polarity_level, 1) : "—"}</div></div>
                  <div><div className="label">Gatekeepers</div><div className="mono">{data?.nodes?.gatekeepers?.length || 0}</div></div>
                </div>

                {/* Live GEX WebSocket indicator */}
                <div className="dotted-divider my-2" />
                <div className="flex items-center justify-between text-[9px]">
                  {wsGex.connected ? (
                    <span className="text-teal-400 font-bold flash-pulse">● LIVE GEX</span>
                  ) : wsGex.reconnectAttempt > 0 ? (
                    <span className="text-amber-400">⟳ Reconnecting ({wsGex.reconnectAttempt})</span>
                  ) : (
                    <span className="text-slate-500">○ Disconnected</span>
                  )}
                </div>
                {wsGex.connected && wsGex.data && (
                  <>
                    <div className="flex items-center justify-between text-[9px]">
                      <span className="text-slate-500">{new Date(wsGex.data.asof).toLocaleTimeString()}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px] mt-1">
                      <div className="flex justify-between"><span className="text-slate-500">Spot</span><span className="mono text-slate-300">${fmt(wsGex.data.spot, 2)}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">Total GEX</span><span className={`mono ${wsGex.data.total_gex > 0 ? "text-emerald-400" : "text-rose-400"}`}>{wsGex.data.total_gex > 0 ? "+" : ""}{fmtAbs(wsGex.data.total_gex)}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">King</span><span className="mono text-amber-300">{wsGex.data.king ? fmt(wsGex.data.king.strike, 0) : "—"}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">Regime</span><span className={`mono ${regimeColor(wsGex.data.regime)}`}>{wsGex.data.regime || "—"}</span></div>
                    </div>
                  </>
                )}
              </div>

              {/* Filters */}
              <div className="panel p-3">
                <div className="label mb-2">View</div>
                <div className="flex gap-1 mb-2">
                  <button onClick={() => setView("grid")} className={`btn flex-1 ${view === "grid" ? "active" : ""}`}>2D Grid</button>
                  <button onClick={() => setView("bar")} className={`btn flex-1 ${view === "bar" ? "active" : ""}`}>Bars</button>
                  <button onClick={() => setView("chain")} className={`btn flex-1 ${view === "chain" ? "active" : ""}`}>Chain</button>
                </div>
                <div className="text-slate-500 mb-1 text-[10px]">Mode</div>
                <div className="flex gap-1 mb-2">
                  {["day", "swing", "scalp"].map(m => (
                    <button key={m} onClick={() => setMode(m)} className={`btn flex-1 ${mode === m ? "active" : ""}`}>{m.toUpperCase()}</button>
                  ))}
                </div>
                <div className="flex gap-1 mb-2">
                  {["gex", "vex", "charm"].map(m => (
                    <button key={m} onClick={() => setViewMode(m)} className={`btn flex-1 ${viewMode === m ? "active" : ""}`}>{m.toUpperCase()}</button>
                  ))}
                </div>
                <div className="text-slate-500 mb-1 text-[10px]">DTE</div>
                <div className="flex gap-1 mb-2">
                  {[{l:"0DTE",v:0},{l:"1DTE",v:1},{l:"Week",v:7},{l:"All",v:null}].map(({l,v}) => (
                    <button key={l} onClick={() => setDte(v)} className={`btn flex-1 ${dte === v ? "active" : ""}`}>{l}</button>
                  ))}
                </div>
                <div className="text-slate-500 mb-1 text-[10px]">Expiries</div>
                <div className="flex gap-1">
                  {[2,4,6,8,12].map(n => (
                    <button key={n} onClick={() => setExpiries(n)} className={`btn flex-1 ${expiries === n ? "active" : ""}`}>{n}</button>
                  ))}
                </div>
              </div>

              <Movers onPick={(t) => setTicker(t)} />
              <HistoryPanel ticker={ticker} />
              <SettingsPanel
                refreshMs={refreshMs}
                onRefreshMsChange={setRefreshMs}
                defaultTicker={ticker}
                onDefaultTickerChange={setTicker}
              />
            </div>
          </aside>

          {/* Main Content - Heatmap */}
          <main className="heatseeker-main">
            <div className="panel m-2 p-3 flex-1 flex flex-col overflow-hidden">
              <div className="flex justify-between items-center mb-2 flex-shrink-0">
                <div>
                  <div className="label">Heatseeker · {viewMode === "vex" ? "VEX" : viewMode === "charm" ? "Charm" : "GEX"} {view === "grid" ? "Grid (Strike × Expiry)" : "Bars"}</div>
                  <div className="text-[10px] text-slate-500">
                    {viewMode === "vex" ? "Amber = positive vanna · Pink = negative vanna" : viewMode === "charm" ? "Cyan = positive charm · Violet = negative charm" : "Teal (Pika) = positive γ · Purple (Barney) = negative · Yellow-green = King"}
                  </div>
                </div>
                <div className="flex gap-2 text-[10px]">
                  <span className="tag king">KING</span>
                  <span className="tag floor">FLOOR</span>
                  <span className="tag ceiling">CEIL</span>
                  <span className="tag gate">GATE</span>
                  <span className="tag air">AIR</span>
                </div>
              </div>
              <div className="flex-1 overflow-hidden heatmap-scroll-container">
                <ErrorBoundary>
                  {displayData ? (
                    view === "chain"
                      ? <OptionsChainTable ticker={ticker} spot={livespot?.spot ?? displayData?.spot} />
                      : view === "grid"
                      ? <GridHeatmap data={displayData} filters={filters} onCellClick={(s, e) => setDrilldown({ ticker, expiry: e, strike: s })} viewMode={viewMode} />
                      : <BarHeatmap data={displayData} filters={filters} compact={false} viewMode={viewMode} />
                  ) : (
                    <div className="text-slate-500 text-xs p-6 text-center">Loading…</div>
                  )}
                </ErrorBoundary>
              </div>
            </div>
          </main>

          {/* Right Sidebar - Analytics Panels */}
          <aside className={`heatseeker-sidebar-right ${showRightSidebar ? 'open' : ''}`}>
            <div className="p-2 space-y-2">
              {page === "heatseeker" && <MorningBriefing ticker={ticker} spot={livespot?.spot ?? data?.spot} />}
              <DashboardSummary ticker={ticker} spot={livespot?.spot ?? data?.spot} />
              <FlipZonesPanel data={data} />
              <StackedNodesPanel data={data} />
              <TugOfWarPanel data={data} />
              <ScenarioPanel data={data} />
              <RiskDashboardPanel data={data} />
              <OpportunitiesPanel data={data} />
              <ImpliedMovePanel data={data} />
              <VolAnalyticsPanel data={data} />
              <MarketRegimePanel data={data} />
              <ImpliedPDFPanel data={data} />
              <HedgeImpulsePanel data={advanced} />
              <PressureCloudPanel data={advanced} />
              <CharmIntegralPanel data={advanced} />
              <MultiTimeframeGEXPanel ticker={ticker} />
              <AlertsPanel ticker={ticker} />
              <TradeAnalytics ticker={ticker} />
              <UOAPanel ticker={ticker} />
              {page === "heatseeker" && <FlowTicker ticker={ticker} />}
              <UsagePanel />
              <LivePolicyPanel />
              {page === "heatseeker" && <PositionSizing ticker={ticker} spot={livespot?.spot ?? data?.spot} />}
              {page === "heatseeker" && <TradeEntry ticker={ticker} spot={livespot?.spot ?? data?.spot} />}

              <div className="panel p-3" data-testid="patterns-panel">
                <div className="label mb-2">Patterns Detected</div>
                <div className="space-y-2">
                  {data?.patterns?.length ? data.patterns.map((p, i) => <PatternCard key={i} p={p} />) : (
                    <div className="text-slate-500 text-xs">No textbook pattern. A+ setups only.</div>
                  )}
                </div>
              </div>

              <VelocityGauge velocity={data?.velocity} />
              <ToxicityGauge
                ensemble={ensembleData}
                onRefresh={() => {
                  axios.get(`${API}/anomaly/ensemble/state?ticker=${ticker}`).then(r => setEnsembleData(r.data)).catch(() => {});
                }}
              />
              {data && <NodesTable data={data} />}

              {data?.nodes?.air_pockets?.length > 0 && (
                <div className="panel p-3" data-testid="air-pockets-panel">
                  <div className="label mb-2">Air Pockets</div>
                  <div className="space-y-1 text-[11px]">
                    {data.nodes.air_pockets.map((a, i) => (
                      <div key={i} className="flex justify-between text-slate-400">
                        <span className="mono">{fmt(a.low, 0)} – {fmt(a.high, 0)}</span>
                        <span className="text-slate-500">w {a.width} · mid {fmt(a.mid, 0)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="text-[10px] text-slate-600 mt-2 italic">Pathways, not targets.</div>
                </div>
              )}

              <GreekReferencePanel />
            </div>
          </aside>
        </div>
      )}

      {/* Mobile Toggle Bar */}
      {page === "heatseeker" && (
        <div className="mobile-toggle-bar">
          <button className="toggle-btn" onClick={() => { setShowLeftSidebar(!showLeftSidebar); setShowRightSidebar(false); }}>
            ◀ Filters
          </button>
          <button className="toggle-btn" onClick={() => { setShowRightSidebar(!showRightSidebar); setShowLeftSidebar(false); }}>
            Analytics ▶
          </button>
        </div>
      )}

      {/* Skylit Heatseeker */}
      {page === "skylit" && (
        <div className="flex-1 overflow-auto">
          <ErrorBoundary>
            <HeatseekerDashboard
              ticker={ticker}
              spot={livespot?.spot ?? data?.spot}
              isOffline={data?.data_fallback === true}
              dataAge={data?.stale_age_s != null ? data.stale_age_s * 1000 : null}
              dataFallback={data?.data_fallback === true}
            />
          </ErrorBoundary>
        </div>
      )}

      {/* Portfolio View */}
      {page === "portfolio" && (
        <PortfolioPanel ticker={ticker} spot={livespot?.spot ?? data?.spot} />
      )}

      {/* Trade Journal */}
      {page === "journal" && (
        <TradeJournal ticker={ticker} />
      )}

      {/* SwarmSPX Neural Intelligence */}
      {page === "swarmspx" && (
        <div className="flex-1 overflow-hidden" style={{ display: "flex", flexDirection: "column" }}>
          <iframe
            src="http://localhost:8099/"
            style={{ flex: 1, border: "none", width: "100%", height: "100%" }}
            title="SwarmSPX Neural Intelligence"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          />
        </div>
      )}

      {/* Dashboard (Agent Hub + Vol Surface + Toxicity + more) */}
      {page === "dashboard" && (
        <div className="flex-1 overflow-hidden" style={{ display: "flex", flexDirection: "column" }}>
          <iframe
            src="http://localhost:8000/dashboard/"
            style={{ flex: 1, border: "none", width: "100%", height: "100%" }}
            title="Confluence Decoder Dashboard"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          />
        </div>
      )}

      {/* Paper Trading Agent */}
      {page === "papertrade" && (
        <PaperTrade ticker={ticker} spot={livespot?.spot ?? data?.spot} />
      )}

      {/* Drilldown Modal */}
      {drilldown && <Drilldown {...drilldown} onClose={() => setDrilldown(null)} />}

      {/* Footer */}
      <footer className="border-t border-slate-800 px-4 py-2 text-[10px] text-slate-600 flex justify-between flex-shrink-0">
        <span>Data: Databento OPRA (OI) · yfinance (IV) · Polygon (aggs). GEX via Black-Scholes γ.</span>
        <span className="hidden md:inline text-slate-700">
          Keys: 1/2/3 pages · G/B/C views · D/S/X modes · E/V/H overlays · ↑↓ tickers · ? shortcuts
        </span>
        <span>Confluence Decoder · Institutional Grade · {new Date().getFullYear()}</span>
      </footer>

      {/* Shortcuts Modal */}
      {page === "heatseeker" && (
        <ShortcutsModal />
      )}
    </div>
  );
}
