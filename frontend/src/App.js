import React, { useEffect, useMemo, useState, useCallback, useRef } from "react";
import axios from "axios";
import "@/App.css";
import { useAuth } from "./context/AuthContext";

import { fmt, fmtAbs, pctClass, tagFor, TRIAD, DEFAULT_TICKERS } from "./lib/helpers";
import { buildHeatmapQuery } from "./lib/heatmapQuery";
import GridHeatmap from "./components/GridHeatmap";
import DomHeatmap from "./components/DomHeatmap";
import MultiTickerHeatmap from "./components/MultiTickerHeatmap";
import VolumeProfileGrid from "./components/VolumeProfileGrid";
import HeatseekerDashboard from "./components/heatseeker/HeatseekerDashboard";
import GexStrikeTable from "./components/heatseeker/GexStrikeTable";
import BarHeatmap from "./components/BarHeatmap";
import PatternCard from "./components/PatternCard";
import TrinityView from "./components/TrinityView";
import TrinityVolatility from "./components/TrinityVolatility";
import QuickTradePanel from "./components/QuickTradePanel";
import {
  FlipZonesPanel, StackedNodesPanel, TugOfWarPanel, ScenarioPanel,
  RiskDashboardPanel, OpportunitiesPanel, ImpliedMovePanel, VolAnalyticsPanel,
  GreekReferencePanel, UsagePanel, LivePolicyPanel,
} from "./components/SidebarPanels";
import {
  MarketRegimePanel, ImpliedPDFPanel, HedgeImpulsePanel,
  PressureCloudPanel, CharmIntegralPanel,
} from "./components/AdvancedAnalyticsPanel";
import { MlDashboard } from "./components/MlDashboard";
import PortfolioPanel from "./components/PortfolioPanel";
import FlowTicker from "./components/FlowTicker";
import HistoryPanel from "./components/HistoryPanel";
import OptionsChainTable from "./components/OptionsChainTable";
import MultiTimeframeGEXPanel from "./components/MultiTimeframeGEXPanel";
import AlertsPanel from "./components/AlertsPanel";
import UOAPanel from "./components/UOAPanel";
import { useWebSocketGex } from "./hooks/useWebSocketGex";
import { useDebounce } from "./hooks/useDebounce";
import { SettingsPanel } from "./components/SettingsPanel";
import { ShortcutsModal } from "./components/ShortcutsModal";
import { MorningBriefing } from "./components/MorningBriefing";
import { PositionSizing } from "./components/PositionSizing";
import { TradeEntry } from "./components/TradeEntry";
import TradeJournal from "./components/TradeJournal";
import { DashboardSummary } from "./components/DashboardSummary";
import { TradeAnalytics } from "./components/TradeAnalytics";
import { SocialFlowPanel } from "./components/SocialFlowPanel";
import SkylitDashboard from "./components/heatseeker/SkylitDashboard";
import StealThreePreview from "./components/heatseeker/StealThreePreview";
import FlowseekerProBlademap from "./components/flowseeker/FlowseekerProBlademap";
import PublicPanel from "./components/PublicPanel";
import AlertOverlay from "./components/AlertOverlay";
import PWAInstallBanner from "./components/PWAInstallBanner";
import AppShell from "./shell/AppShell";
import { useTheme } from "./context/ThemeContext";
import { autoDecimate } from "./utils/dataDecimator";
import { PAGE_NAMES } from "./shell/navConfig";
import { buildTickerUniverse, normalizeTicker } from "./components/heatseeker/tickerUniverse";

import ToxicityGauge from "./components/ToxicityGauge";
import ErrorBoundary from "./components/ErrorBoundary";
import { RetryButton, ErrorState } from "./components/RetryButton";


import { BACKEND_URL } from "./config/api";
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
      <div className="flex flex-col gap-1 text-[12px]">
        {rows.length === 0 && <div className="text-slate-500">…</div>}
        {rows.map((r, i) => (
          <div key={i} className="flex justify-between bar-row cursor-pointer" onClick={() => onPick && onPick(r.ticker)}>
            <span className="mono text-amber-300 font-medium">{r.ticker}</span>
            <span className={`${pctClass(r.change)} font-medium`}>{r.change > 0 ? "+" : ""}{r.change}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============ Nodes Table ============
// ============ Ticker Search ============
// Open universe (2026-09-03, Nav-approved): Enter submits free text — any
// symbol, not just the suggestion list. Backend accepts arbitrary tickers.
function TickerSearch({ tickers, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef();
  const filtered = (tickers || []).filter(t => !q || t.toLowerCase().includes(q.toLowerCase())).slice(0, 12);
  const submitFreeText = () => {
    const t = q.trim().toUpperCase().replace(/^\$/, "");
    if (t) { onChange(t); setOpen(false); setQ(""); }
  };
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);
  return (
    <div ref={ref} className="relative">
      <input
        className="mono text-[12px] px-2 py-1 rounded"
        style={{ background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text-primary)", width: 100 }}
        value={q}
        onChange={e => { setQ(e.target.value); setOpen(true); }}
        onKeyDown={e => { if (e.key === "Enter") submitFreeText(); }}
        onFocus={() => setOpen(true)}
        placeholder={value || "SPY"}
      />
      {open && filtered.length > 0 && (
        <div className="absolute top-full mt-1 z-50 rounded-lg overflow-hidden" style={{ background: "var(--panel)", border: "1px solid var(--border)", minWidth: 120 }}>
          {filtered.map(t => (
            <div key={t} className="px-3 py-1.5 cursor-pointer text-[12px] mono bar-row" onClick={() => { onChange(t); setOpen(false); setQ(""); }}
              style={{ color: t === value ? "var(--gold)" : "var(--text-secondary)" }}>
              {t}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============ AlphaPod-style Header ============
function ApHeader({ page, ticker, onTickerChange, tickers, data, onSignOut, userEmail, userTier }) {
  const pageName = PAGE_NAMES[page] || page;
  const isLive = page === "flow-alerts";

  return (
    <header className="ap-header">
      <div className="ap-header-inner">
        {/* Breadcrumb */}
        <div className="ap-breadcrumb">
          <span className="hidden lg:inline" style={{ color: "var(--text-tertiary)" }}>Decoder</span>
          <svg className="hidden lg:block" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--text-quaternary)" }}>
            <path d="M9 18l6-6-6-6"/>
          </svg>
          <span className="truncate font-semibold" title={pageName} style={{ color: "var(--text-primary)" }}>{pageName}</span>
        </div>

        {/* Right side actions */}
        <div className="ap-header-actions">
          {/* Ticker search for relevant pages */}
          {tickers && (page === "heatseeker" || page === "trinity" || page === "skylit" || page === "ticker-analysis") && (
            <TickerSearch
              tickers={[...(tickers.trinity || []), ...(tickers.default || []), ...(tickers.popular || [])]}
              value={ticker}
              onChange={onTickerChange}
            />
          )}

          {/* Live badge */}
          <div className="ap-live-badge" title="Live">
            <span className="dot" />
            <span>Live</span>
          </div>

          {/* Data source indicator */}
          {data?.data_source && (
            <span className="mono text-[10px] uppercase tracking-wider hidden lg:inline" style={{ color: "var(--text-tertiary)" }}>
              {data.data_source}
            </span>
          )}

          {/* User chip */}
          {userEmail && (
            <div className="ap-user-chip">
              <span className="hidden lg:inline" style={{ color: "var(--text-secondary)" }}>{userEmail}</span>
              {userTier && <span className="tier">{userTier}</span>}
            </div>
          )}

          {/* Sign out */}
          <button
            onClick={onSignOut}
            className="ap-icon-btn"
            title="Sign out"
            style={{ color: "var(--text-tertiary)" }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}

// ============ AlphaPod-style Page Placeholders ============
function PagePlaceholder({ title, subtitle }) {
  return (
    <div className="ap-main" style={{ flex: 1 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 24 }}>
        <h1 className="display text-[22px] font-semibold leading-none" style={{ color: "var(--text-primary)", marginBottom: 8 }}>
          {title}
        </h1>
        {subtitle && (
          <p style={{ color: "var(--text-tertiary)", fontSize: 13 }}>
            {subtitle}
          </p>
        )}
        <div className="panel p-6 mt-4" style={{ textAlign: "center" }}>
          <div style={{ color: "var(--text-quaternary)", fontSize: 13 }}>
            This page is under construction. Data will be populated from the backend.
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Dashboard Page ============
function DashboardPage({ ticker, data, livespot }) {
  return (
    <div className="ap-main" style={{ flex: 1 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 24 }}>
        <h1 className="display text-[22px] font-semibold leading-none" style={{ color: "var(--text-primary)", marginBottom: 16 }}>
          Dashboard
        </h1>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
          <div className="panel p-4">
            <div className="label mb-2">Market Overview</div>
            <div className="text-[28px] mono font-bold" style={{ color: "var(--text-primary)" }}>
              {ticker} ${fmt(livespot?.spot ?? data?.spot, 2)}
            </div>
            {data?.nodes?.regime && (
              <div className="mt-2 text-[12px]" style={{ color: data.nodes.regime === "positive" ? "var(--pos)" : "var(--neg)" }}>
                {data.nodes.regime} γ regime
              </div>
            )}
          </div>
          <div className="panel p-4">
            <div className="label mb-2">Key Levels</div>
            {data?.nodes?.king && (
              <div className="text-[13px] mono">
                <div>King: <span style={{ color: "var(--king)" }}>{fmt(data.nodes.king.strike, 0)}</span></div>
                <div>Floor: <span style={{ color: "var(--pos)" }}>{fmt(data.nodes.floors?.[0]?.strike, 0) || "—"}</span></div>
                <div>Ceiling: <span style={{ color: "var(--neg)" }}>{fmt(data.nodes.ceilings?.[0]?.strike, 0) || "—"}</span></div>
              </div>
            )}
          </div>
          <div className="panel p-4">
            <div className="label mb-2">Data Source</div>
            <div className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
              {data?.data_source || "Loading…"}
            </div>
            {data?.asof && (
              <div className="text-[11px] mt-1" style={{ color: "var(--text-quaternary)" }}>
                Last update: {new Date(data.asof).toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Flow Alerts Page (AlphaPod style) ============
function FlowAlertsPage({ ticker, token }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let mounted = true;
    const fetchAlerts = async () => {
      try {
        // Local backend only (AlphaPod egress removed per Freebuff security policy)
        const base = API;
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await axios.get(`${base}/alerts?page=1&page_size=50${ticker && ticker !== "SPY" ? `&ticker=${ticker}` : ""}`, { headers });
        if (mounted) setAlerts(res.data.alerts || res.data || []);
      } catch (e) { /* noop */ }
      if (mounted) setLoading(false);
    };
    fetchAlerts();
    const id = setInterval(fetchAlerts, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, [ticker, token]);

  const filtered = alerts.filter(a => {
    const optType = a.option_type || a.type;
    if (filter === "calls" && optType !== "call" && optType !== "CALL") return false;
    if (filter === "puts" && optType !== "put" && optType !== "PUT") return false;
    if (filter === "bullish" && !["call","CALL"].includes(optType)) return false;
    if (filter === "bearish" && !["put","PUT"].includes(optType)) return false;
    if (filter === "500k" && (a.premium || 0) < 500000) return false;
    if (filter === "1m" && (a.premium || 0) < 1000000) return false;
    if (filter === "sweep" && (a.execution || a.exec_type || a.exec || "").toLowerCase() !== "sweep") return false;
    if (filter === "high" && (a.confidence || a.conf || "").toLowerCase() !== "high") return false;
    if (search && !a.ticker?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const totalPremium = filtered.reduce((s, a) => s + (a.premium || 0), 0);
  const calls = filtered.filter(a => (a.option_type || a.type) === "call" || (a.option_type || a.type) === "CALL").length;
  const puts = filtered.filter(a => (a.option_type || a.type) === "put" || (a.option_type || a.type) === "PUT").length;

  return (
    <div className="ap-main" style={{ flex: 1, padding: 0 }}>
      <div className="flow-alerts-terminal-glass">
        {/* Page header */}
        <div className="fa-page-header">
          <h1>Flow Alerts</h1>
          <div className="flex items-center justify-between gap-2 sm:flex-wrap sm:justify-end">
            <div className="min-w-0 flex-1 sm:flex-none">
              <span className="mono text-[12px]" style={{ color: "var(--text-tertiary)" }}>Today · {new Date().toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}</span>
            </div>
          </div>
        </div>

        {/* Summary stats */}
        <div className="fa-summary-shell">
          <div className="fa-summary-stats">
            <span className="inline-flex items-baseline gap-1.5">
              <span className="fa-summary-stat-value mono" style={{ color: "var(--text-primary)" }}>{filtered.length}</span>
              <span className="fa-summary-stat-label">Alerts</span>
            </span>
            <span className="fa-summary-divider" />
            <span className="inline-flex items-baseline gap-1.5">
              <span className="fa-summary-stat-value mono" style={{ color: "var(--emerald)" }}>{calls}</span>
              <span className="fa-summary-stat-label">Calls</span>
            </span>
            <span className="inline-flex items-baseline gap-1.5">
              <span className="fa-summary-stat-value mono" style={{ color: "var(--red)" }}>{puts}</span>
              <span className="fa-summary-stat-label">Puts</span>
            </span>
            <span className="fa-summary-divider" />
            <span className="inline-flex items-baseline gap-1.5">
              <span className="fa-summary-stat-value mono" style={{ color: "var(--text-primary)" }}>${(totalPremium / 1e6).toFixed(1)}M</span>
              <span className="fa-summary-stat-label">Premium</span>
            </span>
          </div>
        </div>

        {/* Filter bar */}
        <div className="fa-filter-shell">
          <div className="flex flex-wrap items-center gap-2">
            <label className="fa-search-field">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--text-quaternary)", flexShrink: 0 }}>
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
              </svg>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search ticker…" />
            </label>
            <button className={`fa-chip ${filter === "all" ? "active" : ""}`} onClick={() => setFilter("all")}>All Types</button>
            <button className={`fa-chip ${filter === "calls" ? "active" : ""}`} onClick={() => setFilter("calls")}>Calls</button>
            <button className={`fa-chip ${filter === "puts" ? "active" : ""}`} onClick={() => setFilter("puts")}>Puts</button>
            <button className={`fa-chip ${filter === "bullish" ? "active" : ""}`} onClick={() => setFilter("bullish")}>Bullish</button>
            <button className={`fa-chip ${filter === "bearish" ? "active" : ""}`} onClick={() => setFilter("bearish")}>Bearish</button>
            <button className={`fa-chip ${filter === "500k" ? "active" : ""}`} onClick={() => setFilter("500k")}>≥ $500K</button>
            <button className={`fa-chip ${filter === "1m" ? "active" : ""}`} onClick={() => setFilter("1m")}>≥ $1M</button>
            <button className={`fa-chip ${filter === "sweep" ? "active" : ""}`} onClick={() => setFilter("sweep")}>Sweep Only</button>
            <button className={`fa-chip ${filter === "high" ? "active" : ""}`} onClick={() => setFilter("high")}>HIGH Conf</button>
            <button className={`fa-chip`} onClick={() => setFilter("all")}>Reset</button>
          </div>
        </div>

        {/* Alerts table */}
        <div style={{ overflowX: "auto" }}>
          {loading ? (
            <div className="panel p-6" style={{ textAlign: "center", color: "var(--text-quaternary)" }}>
              Loading alerts…
            </div>
          ) : filtered.length === 0 ? (
            <div className="panel p-6" style={{ textAlign: "center", color: "var(--text-quaternary)" }}>
              No alerts match the current filters.
            </div>
          ) : (
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                  {["TIME", "TICKER", "TYPE", "SIDE", "SENTIMENT", "EXEC", "CONTRACT", "SIZE", "OI", "PREMIUM", "SPOT", "RULE", "CONF."].map(h => (
                    <th key={h} className="text-left text-[10px] uppercase tracking-widest font-normal px-3 py-2" style={{ color: "var(--text-quaternary)", cursor: "pointer" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((a, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border-c)", cursor: "pointer" }} className="bar-row">
                    <td className="px-3 py-2 mono" style={{ color: "var(--text-tertiary)" }}>{a.created_at ? new Date(a.created_at).toLocaleTimeString("en-US", {hour:"2-digit",minute:"2-digit"}) : a.time || "—"}</td>
                    <td className="px-3 py-2 mono font-semibold" style={{ color: "var(--text-primary)" }}>{a.ticker || "—"}</td>
                    <td className="px-3 py-2">
                      <span className="mono text-[11px] font-semibold" style={{ color: (a.option_type||"").toUpperCase()==="CALL" ? "var(--emerald)" : "var(--red)" }}>
                        {(a.option_type || a.type || "—").toUpperCase()}
                      </span>
                    </td>
                    <td className="px-3 py-2 mono" style={{ color: (a.side||"").toUpperCase()==="BUY" ? "var(--emerald)" : "var(--red)" }}>{(a.side || "—").toUpperCase()}</td>
                    <td className="px-3 py-2">
                      <span className="text-[10px] uppercase tracking-wider" style={{ color: (a.sentiment||"").toUpperCase()==="BULLISH" ? "var(--emerald)" : (a.sentiment||"").toUpperCase()==="BEARISH" ? "var(--red)" : "var(--text-tertiary)" }}>
                        {a.sentiment || "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--surface-1)", color: "var(--text-secondary)", border: "1px solid var(--border-c)" }}>
                        {a.exec_type || a.execution || "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 mono" style={{ color: "var(--text-secondary)" }}>{a.contract || `$${a.strike||""} ${(a.option_type||"").toUpperCase()} ${a.expiration||""}`}</td>
                    <td className="px-3 py-2 mono" style={{ color: "var(--text-secondary)" }}>{a.size || "—"}</td>
                    <td className="px-3 py-2 mono" style={{ color: "var(--text-tertiary)" }}>{a.open_interest ?? a.oi ?? "—"}</td>
                    <td className="px-3 py-2 mono font-semibold" style={{ color: "var(--text-primary)" }}>
                      {a.premium ? `$${(a.premium / 1000).toFixed(0)}K` : "—"}
                    </td>
                    <td className="px-3 py-2 mono" style={{ color: "var(--text-secondary)" }}>{a.spot_price ? `$${fmt(a.spot_price, 2)}` : "—"}</td>
                    <td className="px-3 py-2">
                      <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>{a.alert_rule || a.rule || "—"}</span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="text-[10px] uppercase tracking-wider font-semibold" style={{
                        color: (a.confidence||"").toUpperCase()==="HIGH" ? "var(--conf-high)" : (a.confidence||"").toUpperCase()==="MED" || (a.confidence||"").toUpperCase()==="MEDIUM" ? "var(--gold)" : "var(--amber)"
                      }}>
                        {a.confidence || "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// ============ Regime Color Helper ============
const regimeColor = (regime) => regime === "positive" ? "text-emerald-400" : regime === "negative" ? "text-rose-400" : "text-slate-400";

// ============ Main App ============
export default function App() {
  const { token, user, isAuthenticated, logout } = useAuth();
  const [page, setPage] = useState(() => {
    try {
      const q = new URLSearchParams(window.location.search).get("page");
      if (q && ["heatseeker", "trinity", "skylit", "flowseeker-pro", "journal", "portfolio"].includes(q)) return q;
    } catch {}
    return "heatseeker";
  });
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
  const [viewMode, setViewMode] = useState("gex");
  const [view, setView] = useState("skylit");
  const [mode, setMode] = useState("day");
  const [filters, setFilters] = useState({ side: "all", lifecycle: "all", magMin: 0 });
  const [expiries, setExpiries] = useState(4);
  const [trinityTab, setTrinityTab] = useState("gex");
  const [dte, setDte] = useState(null);
  const [tickers, setTickers] = useState(null);
  const [advanced, setAdvanced] = useState(null);
  const [advancedLoading, setAdvancedLoading] = useState(true);
  const [advancedError, setAdvancedError] = useState(false);
  const wsGex = useWebSocketGex((page === "heatseeker" || page === "skylit") ? ticker : null);
  const { theme, toggleTheme } = useTheme();
  const [ensembleData, setEnsembleData] = useState(null);
  const [tradeSelection, setTradeSelection] = useState(null);
  // Use auth context for user info
  const userEmail = user?.email || null;
  const userTier = user?.tier || null;

  // Debounced filter values to prevent API spam
  const debouncedMode = useDebounce(mode, 300);
  const debouncedExpiries = useDebounce(expiries, 300);
  const debouncedDte = useDebounce(dte, 300);

  // Fetch tickers — trinity + default + popular, plus the full exchange-listed
  // universe from /api/tickers/all so the ticker bar exposes every tradable name
  // (not just the ~80 featured ones). No separate "universe" model — the same
  // trinity/default/popular shape is retained; popular is expanded to the full
  // Finnhub US equities list (11,220 symbols, capped at 5000 for render perf).
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [basicRes, allRes] = await Promise.all([
          axios.get(`${API}/tickers`),
          axios.get(`${API}/tickers/all?limit=5000`),
        ]);
        if (!mounted) return;
        const allSyms = (allRes.data && allRes.data.tickers) || [];

        // Expand "popular" to the full Finnhub US equities list (capped at 5000
        // for render perf). trinity + default stay as the featured sets; no
        // separate "universe" concept is introduced — the same shape is retained.
        const popularExpanded = allSyms.slice(0, 5000);
        const combined = {
          trinity: basicRes.data?.trinity || [],
          default: basicRes.data?.default || [],
          popular: Array.isArray(popularExpanded)
            ? [...new Set([...popularExpanded])]
            : basicRes.data?.popular || [],
        };
        setTickers(combined);
      } catch (e) {
        console.warn("[App] ticker fetch failed:", e);
      } finally {
        /* no-op */
      }
    })();
    return () => { mounted = false; };
  }, []);

  const [loading, setLoading] = useState(false);

  // Flowseeker signal cards dispatch this to focus the desk ticker.
  useEffect(() => {
    const onFocusTicker = (e) => { if (e.detail?.ticker) setTicker(e.detail.ticker); };
    window.addEventListener("floww:focus-ticker", onFocusTicker);
    return () => window.removeEventListener("floww:focus-ticker", onFocusTicker);
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const qs = buildHeatmapQuery({ expiries: debouncedExpiries, mode: debouncedMode, dte: debouncedDte });
      const res = await axios.get(`${API}/heatmap/${ticker}?${qs}`, { timeout: 30000 });
      setData(res.data); setErr(null);
    } catch (e) {
      let msg = "Failed to load data";
      if (e.code === "ECONNABORTED") {
        msg = "Request timed out. The server may be busy.";
      } else if (e.response) {
        const detail = e.response.data?.detail;
        if (typeof detail === "string") msg = detail;
        else if (Array.isArray(detail) && detail[0]?.msg) msg = detail[0]?.msg;
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
        // Same query as the manual /heatmap fetch — a naked poll here
        // overwrites the user's DTE/Expiries/mode selection with backend
        // defaults on every tick (Round-8 regression).
        const qs = buildHeatmapQuery({ expiries: debouncedExpiries, mode: debouncedMode, dte: debouncedDte });
        const r = await axios.get(`${API}/data/${ticker}?${qs}`);
        if (!cancelled) setData(r.data);
      } catch (e) { if (!cancelled) setErr(e.message); }
    };
    doFetch();
    const id = setInterval(doFetch, refreshMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [ticker, refreshMs, debouncedExpiries, debouncedMode, debouncedDte]);

  // Advanced analytics with in-flight guard
  useEffect(() => {
    let cancelled = false;
    const doFetch = async () => {
      if (cancelled) return;
      setAdvancedLoading(true);
      setAdvancedError(false);
      try {
        const r = await axios.get(`${API}/advanced/${ticker}?expiries=${debouncedExpiries != null ? debouncedExpiries : 4}`);
        if (!cancelled) { setAdvanced(r.data); setAdvancedLoading(false); }
      } catch (e) { if (!cancelled) { setAdvancedError(true); setAdvancedLoading(false); } }
    };
    doFetch();
    const id = setInterval(doFetch, refreshMs * 2);
    return () => { cancelled = true; clearInterval(id); };
  }, [ticker, refreshMs, debouncedExpiries]);

  // Ensemble toxicity polling
  useEffect(() => {
    if (page !== "heatseeker" && page !== "skylit") return;
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
            // T1 (2026-09-07): deduped universe shared with the ticker bar —
            // duplicate concatenation used to trap arrows in a two-symbol loop.
            const all = buildTickerUniverse(tickers);
            if (all.length > 0) {
              setTicker(prev => {
                const idx = all.indexOf(normalizeTicker(prev));
                return idx > 0 ? all[idx - 1] : all[all.length - 1];
              });
            }
          }
          break;
        case "ArrowDown":
          e.preventDefault();
          if (tickers) {
            const all = buildTickerUniverse(tickers);
            if (all.length > 0) {
              setTicker(prev => {
                const idx = all.indexOf(normalizeTicker(prev));
                return idx < all.length - 1 ? all[idx + 1] : all[0];
              });
            }
          }
          break;
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

  const handleSignOut = () => {
    logout();
  };

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
    <AppShell page={page} onNavigate={setPage} userEmail={userEmail} userTier={userTier}>
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: "100vh" }}>
        {/* Alert Overlay - Real-time signal toasts */}
        <AlertOverlay onSignalClick={handleSignalClick} maxVisible={3} />

        {/* PWA Install Banner */}
        <PWAInstallBanner />

        {/* AlphaPod-style Header */}
        <ApHeader
          page={page}
          ticker={ticker}
          onTickerChange={setTicker}
          tickers={tickers}
          data={data}
          onSignOut={handleSignOut}
          userEmail={userEmail}
          userTier={userTier}
        />

        {/* ===== DECODER PAGES ===== */}

        {/* Triad View */}
        {page === "trinity" && (
          <ErrorBoundary>
          <div className="legacy-theme p-4 flex-1 overflow-auto" style={{ position: "relative" }}>
            {/* Sub-tab toggle */}
            <div className="flex gap-2 mb-3">
              <button
                onClick={() => setTrinityTab("gex")}
                className={`tv-subtab ${trinityTab === "gex" ? "on" : ""}`}
              >
                △ GEX Heatmap
              </button>
              <button
                onClick={() => setTrinityTab("vol")}
                className={`tv-subtab ${trinityTab === "vol" ? "on" : ""}`}
              >
                ◈ Volatility (Skew / Term / RR)
              </button>
            </div>
            {trinityTab === "gex" ? (
              <TrinityView onFocusTicker={handleFocusTicker} onTradeSelect={setTradeSelection} />
            ) : (
              <TrinityVolatility ticker={ticker.startsWith("^") ? ticker.slice(1) : ticker} expiries={8} />
            )}
            <QuickTradePanel
              selection={tradeSelection}
              onClose={() => setTradeSelection(null)}
              onSubmit={async (trade) => {
                console.log("[Triad] Trade submitted:", trade);
                // Submit real order to backend if it has an OSI symbol
                if (trade.order_id) {
                  // Already submitted server-side in handleSubmit
                  return;
                }
                if (trade.oi_symbol) {
                  try {
                    const isCall = trade.strategy.includes("call") || trade.strategy === "straddle" || trade.strategy === "iron_condor";
                    const side = trade.strategy.startsWith("buy") ? "BUY" : "SELL";
                    const price = isCall
                      ? (trade.limitPrice ?? trade.call_ask ?? trade.call_last ?? NaN)
                      : (trade.limitPrice ?? trade.put_bid ?? trade.put_last ?? NaN);
                    const limitPriceVal = Number.isFinite(price) ? price : null;
                    // PAPER VENUE (2026-09-06, Nav directive): option clicks
                    // route to Alpaca paper, never the live Public brokerage.
                    // UI journaling happens server-side (source api-alpaca-option).
                    const q = new URLSearchParams({
                      symbol: trade.oi_symbol,
                      qty: String(trade.quantity ?? 1),
                      side: side.toLowerCase(),
                      order_type: limitPriceVal != null ? "limit" : "market",
                      limit_price: String(limitPriceVal ?? 0),
                    });
                    const resp = await fetch(`${API}/alpaca/order/option?${q}`, {
                      method: "POST",
                    });
                    const result = await resp.json();
                    // Alpaca route returns HTTP 200 with an error body on
                    // validation/transport failure — resp.ok alone fakes success
                    // and orphans the local journal row (issue #23).
                    if (!resp.ok || result?.error || result?.detail) throw new Error(result.detail?.message || result.message || result.error || resp.statusText);
                    console.log("[Triad] Order placed:", result);
                  } catch (err) {
                    console.error("[Triad] Order failed:", err);
                    alert("Order failed: " + err.message);
                  }
                }
                setTradeSelection(null);
              }}
            />
          </div>
          </ErrorBoundary>
        )}

        {/* Single Ticker Solstice — Zenith Edition with Left Sidebar */}
        {page === "heatseeker" && (
          <ErrorBoundary>
          <div className="legacy-theme heatseeker-layout">
            {/* Left Sidebar - Filters & Summary (PRESERVED) */}
            <aside className={`heatseeker-sidebar-left ${showLeftSidebar ? 'open' : ''}`}>
              <div className="p-2 space-y-2">
                {/* Ticker Summary */}
                <div className="panel p-3">
                  <div className="flex justify-between items-baseline mb-2">
                    <div className="text-[13px] font-bold tracking-wider">{ticker.replace("^", "")}</div>
                    <div className={`text-[10px] uppercase tracking-widest ${regimeColor(data?.nodes?.regime)}`}>{data?.nodes?.regime || "—"} γ</div>
                  </div>
                  <div className="text-[22px] mono font-bold mt-0.5 flex items-center gap-2" data-testid="spot-price">
                    <span>${fmt(livespot?.spot ?? data?.spot, 2)}</span>
                    {livespot && (
                      <span className="text-[9px] uppercase tracking-widest text-teal-400 flash-pulse">● live</span>
                    )}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">
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
                  <div className="text-slate-500 mb-1 text-[10px]">View</div>
                  <div className="flex gap-1 mb-2">
                    <button onClick={() => setView("skylit")} className={`btn flex-1 ${view === "skylit" || view === "grid" ? "active" : ""}`}>2D Grid</button>
                    <button onClick={() => setView("bar")} className={`btn flex-1 ${view === "bar" ? "active" : ""}`}>Bars</button>
                    <button onClick={() => setView("chain")} className={`btn flex-1 ${view === "chain" ? "active" : ""}`}>Chain</button>
                  </div>
                  <div className="flex gap-1 mb-2">
                    <button onClick={() => setView("multi")} className={`btn flex-1 ${view === "multi" ? "active" : ""}`}>Multi</button>
                    <button onClick={() => setView("profile")} className={`btn flex-1 ${view === "profile" ? "active" : ""}`}>Profile</button>
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

            {/* Main Content — view-switchable: 2D Grid (Zenith) / Bars / Chain / Multi / Profile */}
            <main className="heatseeker-main" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
              {view === "bar" ? (
                <BarHeatmap data={displayData} filters={filters} compact={false} viewMode={viewMode} />
              ) : view === "chain" ? (
                <OptionsChainTable ticker={ticker} spot={livespot?.spot ?? displayData?.spot} />
              ) : view === "multi" ? (
                <MultiTickerHeatmap tickers={tickers} />
              ) : view === "profile" ? (
                <div className="volume-profile-page">
                  <VolumeProfileGrid data={displayData} spot={livespot?.spot ?? displayData?.spot} />
                </div>
              ) : view === "skylit" || view === "grid" ? (
                <SkylitDashboard
                  ticker={ticker}
                  spot={livespot?.spot ?? data?.spot}
                  change={livespot?.change ?? data?.change}
                  changePct={livespot?.change_pct ?? data?.change_pct}
                  data={displayData}
                  tickers={tickers}
                  dte={dte}
                  viewMode={viewMode}
                  onViewModeChange={setViewMode}
                  timeframe={mode === "scalp" ? "1m" : mode === "swing" ? "1h" : "5m"}
                  onTimeframeChange={(tf) => {
                    if (tf === "1m") setMode("scalp");
                    else if (tf === "1h") setMode("swing");
                    else setMode("day");
                  }}
                  expiries={expiries}
                  onExpiriesChange={setExpiries}
                  onTickerChange={setTicker}
                  onRefresh={() => { setErr(null); fetchData(); }}
                  onCellClick={async (strike, colKey, value) => {
                    const row = displayData?.strikes?.find(s => s.strike === strike);
                    let contractData = null;
                    try {
                      const cd = await fetch(
                        `${API}/contract/${ticker}/${strike}/${colKey}`
                      );
                      if (cd.ok) contractData = await cd.json();
                    } catch (_) { /* contract detail optional */ }

                    const callC = contractData?.contracts?.find(c => c.type === 'call')
                      || contractData?.contracts?.[0];
                    const putC = contractData?.contracts?.find(c => c.type === 'put')
                      || contractData?.contracts?.[1];

                    setTradeSelection({
                      ticker, strike, expiry: colKey,
                      spot: livespot?.spot ?? data?.spot,
                      gex: value,
                      iv: row?.iv ?? callC?.iv ?? data?.iv,
                      delta: row?.delta ?? callC?.delta ?? data?.delta,
                      oi: row?.total_oi ?? row?.oi ?? data?.oi
                        ?? (callC?.open_interest ?? 0) + (putC?.open_interest ?? 0),
                      call_gex: row?.call_gex,
                      put_gex: row?.put_gex,
                      vex: row?.vex,
                      charm: row?.charm,
                      oi_symbol: callC?.osi || putC?.osi || null,
                      call_bid: callC?.bid,
                      call_ask: callC?.ask,
                      call_last: callC?.last,
                      put_bid: putC?.bid,
                      put_ask: putC?.ask,
                      put_last: putC?.last,
                    });
                  }}
                  onStrikeClick={(strike) => setTradeSelection({ ticker, strike, spot: livespot?.spot ?? data?.spot })}
                  isLive={!!livespot}
                  regime={data?.nodes?.regime}
                  loading={loading && !data}
                />
              ) : (
                <SkylitDashboard
                  ticker={ticker}
                  spot={livespot?.spot ?? data?.spot}
                  change={livespot?.change ?? data?.change}
                  changePct={livespot?.change_pct ?? data?.change_pct}
                  data={displayData}
                  tickers={tickers}
                  dte={dte}
                  viewMode={viewMode}
                  onViewModeChange={setViewMode}
                  timeframe={mode === "scalp" ? "1m" : mode === "swing" ? "1h" : "5m"}
                  onTimeframeChange={(tf) => {
                    if (tf === "1m") setMode("scalp");
                    else if (tf === "1h") setMode("swing");
                    else setMode("day");
                  }}
                  expiries={expiries}
                  onExpiriesChange={setExpiries}
                  onTickerChange={setTicker}
                  onRefresh={() => { setErr(null); fetchData(); }}
                  onCellClick={async (strike, colKey, value) => {
                    const row = displayData?.strikes?.find(s => s.strike === strike);
                    let contractData = null;
                    try {
                      const cd = await fetch(
                        `${API}/contract/${ticker}/${strike}/${colKey}`
                      );
                      if (cd.ok) contractData = await cd.json();
                    } catch (_) { /* contract detail optional */ }

                    const callC = contractData?.contracts?.find(c => c.type === 'call')
                      || contractData?.contracts?.[0];
                    const putC = contractData?.contracts?.find(c => c.type === 'put')
                      || contractData?.contracts?.[1];

                    setTradeSelection({
                      ticker, strike, expiry: colKey,
                      spot: livespot?.spot ?? data?.spot,
                      gex: value,
                      iv: row?.iv ?? callC?.iv ?? data?.iv,
                      delta: row?.delta ?? callC?.delta ?? data?.delta,
                      oi: row?.total_oi ?? row?.oi ?? data?.oi
                        ?? (callC?.open_interest ?? 0) + (putC?.open_interest ?? 0),
                      call_gex: row?.call_gex,
                      put_gex: row?.put_gex,
                      vex: row?.vex,
                      charm: row?.charm,
                      oi_symbol: callC?.osi || putC?.osi || null,
                      call_bid: callC?.bid,
                      call_ask: callC?.ask,
                      call_last: callC?.last,
                      put_bid: putC?.bid,
                      put_ask: putC?.ask,
                      put_last: putC?.last,
                    });
                  }}
                  onStrikeClick={(strike) => setTradeSelection({ ticker, strike, spot: livespot?.spot ?? data?.spot })}
                  isLive={!!livespot}
                  regime={data?.nodes?.regime}
                  loading={loading && !data}
                />
              )}
            </main>
          </div>
          </ErrorBoundary>
        )}

        {/* Mobile Toggle Bar */}
        {(page === "heatseeker" || page === "skylit") && (
          <div className="mobile-toggle-bar">
            {page === "heatseeker" && (
              <button className={`toggle-btn${showLeftSidebar ? " open" : ""}`} onClick={() => { setShowLeftSidebar(!showLeftSidebar); setShowRightSidebar(false); }}>
                {showLeftSidebar ? "▶ Hide Filters" : "◀ Filters"}
              </button>
            )}
            <button className={`toggle-btn${showRightSidebar ? " open" : ""}`} onClick={() => { setShowRightSidebar(!showRightSidebar); setShowLeftSidebar(false); }}>
              {showRightSidebar ? "Analytics ◀" : "Analytics ▶"}
            </button>
          </div>
        )}

        {/* Zenith — GEX Grid + Analytics Column (legacy skylit page) */}
        {page === "skylit" && (
          <div className="legacy-theme skylit-dashboard">
            <ErrorBoundary>
              <HeatseekerDashboard
                ticker={ticker}
                spot={livespot?.spot ?? data?.spot}
                data={displayData}
                isOffline={data?.data_fallback === true}
                dataAge={data?.stale_age_s != null ? data.stale_age_s * 1000 : null}
                dataFallback={data?.data_fallback === true}
              />
            </ErrorBoundary>
            <aside className="skylit-panels">
              <div className="skylit-panel-grid">
                {page === "skylit" && <MorningBriefing ticker={ticker} spot={livespot?.spot ?? data?.spot} />}
                <DashboardSummary ticker={ticker} spot={livespot?.spot ?? data?.spot} />
                <ScenarioPanel data={data} loading={loading} error={err} />
                <RiskDashboardPanel data={data} loading={loading} error={err} />
                <OpportunitiesPanel data={data} loading={loading} error={err} />
                <ImpliedMovePanel data={data} loading={loading} error={err} />
                <VolAnalyticsPanel data={data} loading={loading} error={err} />
                <MarketRegimePanel data={data} loading={loading} error={!!err} />
                <ImpliedPDFPanel data={data} loading={loading} error={!!err} />
                <HedgeImpulsePanel data={advanced} loading={advancedLoading} error={advancedError} />
                <PressureCloudPanel data={advanced} loading={advancedLoading} error={advancedError} />
                <CharmIntegralPanel data={advanced} loading={advancedLoading} error={advancedError} />
                <MlDashboard ticker={ticker} spot={livespot?.spot ?? data?.spot} />
                <MultiTimeframeGEXPanel ticker={ticker} />
                <AlertsPanel ticker={ticker} />
                <TradeAnalytics ticker={ticker} />
                <UOAPanel ticker={ticker} />
                {page === "skylit" && <FlowTicker ticker={ticker} />}
                <UsagePanel />
                <LivePolicyPanel />
                {page === "skylit" && <PositionSizing ticker={ticker} spot={livespot?.spot ?? data?.spot} />}
                {page === "skylit" && <TradeEntry ticker={ticker} spot={livespot?.spot ?? data?.spot} />}
                <VelocityGauge velocity={data?.velocity} />
                <ToxicityGauge
                  ensemble={ensembleData}
                  onRefresh={() => {
                    axios.get(`${API}/ensemble/state?ticker=${ticker}`).then(r => setEnsembleData(r.data)).catch(() => {});
                  }}
                />
                <GreekReferencePanel />
              </div>
            </aside>
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

        {/* Public Brokerage */}
        {page === "public" && (
          <PublicPanel />
        )}

        {/* Tidehunter Pro Tab */}
        {page === "flowseeker-pro" && (
          <div className="flex-1 overflow-auto">
            <ErrorBoundary>
              <FlowseekerProBlademap active={page === "flowseeker-pro"} onTrade={setTradeSelection} />
            </ErrorBoundary>
          </div>
        )}

        {/* Steal Three Top-3 Preview Page */}
        {page === "steal-three" && (
          <StealThreePreview defaultTicker="SPY" />
        )}

        {/* Quick Trade Panel */}
        {tradeSelection && (page === "heatseeker" || page === "flowseeker-pro") && (
          <QuickTradePanel
            selection={tradeSelection}
            onClose={() => setTradeSelection(null)}
            onSubmit={(trade) => {
              // Direct Public order when the selection carries live contract
              // data (cell clicks via /api/contract). Mirrors the Triad
              // submit path; falls through to paper logging regardless.
              // (2026-09-03, Nav-approved App.js surgical edit.)
              if (trade.oi_symbol && !trade.order_id) {
                (async () => {
                  try {
                    const isCall = trade.strategy.includes("call") || trade.strategy === "straddle" || trade.strategy === "iron_condor";
                    const side = trade.strategy.startsWith("buy") ? "BUY" : "SELL";
                    const price = isCall
                      ? (trade.limitPrice ?? trade.call_ask ?? trade.call_last ?? NaN)
                      : (trade.limitPrice ?? trade.put_bid ?? trade.put_last ?? NaN);
                    const limitPriceVal = Number.isFinite(price) ? price : null;
                    // PAPER VENUE (2026-09-06, Nav directive): option clicks
                    // route to Alpaca paper, never the live Public brokerage.
                    // UI journaling happens server-side (source api-alpaca-option).
                    const q = new URLSearchParams({
                      symbol: trade.oi_symbol,
                      qty: String(trade.quantity ?? 1),
                      side: side.toLowerCase(),
                      order_type: limitPriceVal != null ? "limit" : "market",
                      limit_price: String(limitPriceVal ?? 0),
                    });
                    const resp = await fetch(`${API}/alpaca/order/option?${q}`, {
                      method: "POST",
                    });
                    const result = await resp.json();
                    // Same HTTP200-with-error guard as the Triad handler above.
                    if (!resp.ok || result?.error || result?.detail) throw new Error(result.detail?.message || result.message || result.error || resp.statusText);
                    console.log("[Solstice] Order placed:", result);
                  } catch (err) {
                    console.error("[Solstice] Order failed:", err);
                    alert("Order failed: " + err.message);
                  }
                })();
              }
              // Submit to trade memory endpoint
              axios.post(`${API}/memory/trade`, {
                ...trade,
                source: "quick-trade",
                paper: true,
              }).catch(() => {
                // Silently fail — trade is still logged locally
              });
              setTradeSelection(null);
            }}
          />
        )}

        {/* Footer */}
        <footer className="border-t border-slate-800 px-4 py-2 text-[10px] text-slate-600 flex justify-between flex-shrink-0">
          <span>Data: CVForge cvserver · Databento OPRA · yfinance · Polygon · GEX via Black-Scholes γ</span>
          <span className="hidden md:inline text-slate-700">
            Keys: 1/2/3 pages · G/B/C views · D/S/X modes · E/V/H overlays · ↑↓ tickers · ? shortcuts
          </span>
          <span>Meridian · Institutional Grade · {new Date().getFullYear()}</span>
        </footer>

        {/* Shortcuts Modal */}
        {page === "heatseeker" && (
          <ShortcutsModal />
        )}
      </div>
    </AppShell>
  );
}
