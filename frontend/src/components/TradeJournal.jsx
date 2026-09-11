import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { isTradeClosed, tradePnl, tradeOutcome } from "./tradeMath";
import { API } from "../config/api";


// Date-part normalization for merge dedupe: server rows carry full ISO
// timestamps (YYYY-MM-DDTHH:MM:SS) while local rows store date-only.
// Comparing raw strings duplicated every ticket; comparing date-parts
// dedupes identical tickets while keeping distinct-day tickets apart.
export function journalDateKey(v) {
  if (v == null) return "";
  return String(v).slice(0, 10);
}

export function journalKeysEqual(a, b) {
  const pick = (t) => [
    String(t?.ticker || "").replace("^", "").toUpperCase(),
    t?.type, t?.action,
    String(t?.strike ?? ""),
    journalDateKey(t?.expiry),
    journalDateKey(t?.entry_date),
  ].join("|");
  return pick(a) === pick(b);
}


// ─── Trade Form Modal ─────────────────────────────────────────────────────────
function TradeForm({ trade, onSave, onCancel, ticker, spot }) {
  const [form, setForm] = useState(trade || {
    ticker: ticker || "SPY",
    type: "call",
    action: "buy",
    strike: "",
    expiry: "",
    quantity: "1",
    entry_price: "",
    exit_price: "",
    entry_date: new Date().toISOString().slice(0, 10),
    exit_date: "",
    notes: "",
    gex_regime: "",
    setup: "",
    tags: "",
  });

  const update = (key, val) => setForm(prev => ({ ...prev, [key]: val }));

  const pnl = useMemo(() => {
    const entry = parseFloat(form.entry_price) || 0;
    const exit = parseFloat(form.exit_price) || 0;
    const qty = parseInt(form.quantity) || 1;
    if (!entry || !exit) return null;
    return (exit - entry) * qty * 100 * (form.action === "buy" ? 1 : -1);
  }, [form.entry_price, form.exit_price, form.quantity, form.action]);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onCancel}>
      <div className="bg-[#0f1219] border border-slate-700/50 rounded-xl p-5 w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-200">{trade?.id ? "Edit Trade" : "New Trade"}</h3>
          <button onClick={onCancel} className="text-slate-500 hover:text-slate-300 text-lg">✕</button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Ticker" value={form.ticker} onChange={v => update("ticker", v.toUpperCase())} autoFocus />
          <Field label="Type" value={form.type} onChange={v => update("type", v)} select options={["call","put"]} />
          <Field label="Action" value={form.action} onChange={v => update("action", v)} select options={["buy","sell"]} />
          <Field label="Strike" value={form.strike} onChange={v => update("strike", v)} type="number" />
          <Field label="Expiry" value={form.expiry} onChange={v => update("expiry", v)} type="date" />
          <Field label="Qty" value={form.quantity} onChange={v => update("quantity", v)} type="number" />
          <Field label="Entry $" value={form.entry_price} onChange={v => update("entry_price", v)} type="number" step="0.01" />
          <Field label="Exit $" value={form.exit_price} onChange={v => update("exit_price", v)} type="number" step="0.01" />
          <Field label="Entry Date" value={form.entry_date} onChange={v => update("entry_date", v)} type="date" />
          <Field label="Exit Date" value={form.exit_date} onChange={v => update("exit_date", v)} type="date" />
          <Field label="GEX Regime" value={form.gex_regime} onChange={v => update("gex_regime", v)} select options={["","positive_gamma","negative_gamma","transitioning"]} />
          <Field label="Setup" value={form.setup} onChange={v => update("setup", v)} placeholder="e.g., IC at walls" />
        </div>

        <div className="mt-3">
          <label className="text-[10px] text-slate-500 uppercase tracking-wider">Notes</label>
          <textarea value={form.notes} onChange={e => update("notes", e.target.value)}
            placeholder="Trade thesis, what you learned..."
            className="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg px-3 py-2 text-xs text-slate-200 h-20 resize-none mt-1 focus:border-sky-500/50 outline-none" />
        </div>

        {pnl !== null && (
          <div className={`mt-3 rounded-lg p-2 text-center text-sm font-bold ${pnl >= 0 ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-rose-500/10 text-rose-400 border border-rose-500/20"}`}>
            P&L: {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
          </div>
        )}

        <div className="flex gap-2 mt-4">
          <button onClick={onCancel} className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs text-slate-400">Cancel</button>
          <button onClick={() => onSave(form)} className="flex-1 py-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-xs text-white font-medium">
            {trade?.id ? "Update" : "Save Trade"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", select, options, ...props }) {
  return (
    <div>
      <label className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</label>
      {select ? (
        <select value={value} onChange={e => onChange(e.target.value)}
          className="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg px-2 py-1.5 text-xs text-slate-200 mt-1 focus:border-sky-500/50 outline-none">
          {options.map(o => <option key={o} value={o}>{o || "—"}</option>)}
        </select>
      ) : (
        <input type={type} value={value} onChange={e => onChange(e.target.value)}
          className="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg px-2 py-1.5 text-xs text-slate-200 mt-1 focus:border-sky-500/50 outline-none"
          {...props} />
      )}
    </div>
  );
}

// ─── Trade Card ───────────────────────────────────────────────────────────────
/**
 * LevelStatus — Blademap v3: for auto-seeded cards carrying key_levels,
 * show the live position of the underlying between stop and target.
 * The card's entry_price is the OPTION premium; key_levels are on the
 * UNDERLYING. Progress = (underlying − entry) / (target − entry),
 * clamped 0–100%. Underlying spot rides in via trade._spot when the
 * journal feed provides it; without a live spot we render the static
 * levels rail so the desk still sees the plan.
 */
function LevelStatus({ trade }) {
  const kl = trade.key_levels;
  if (!kl || kl.entry == null) return null;
  const bull = (trade.type || "call") === "call";
  const span = Math.abs(kl.target - kl.entry) || 1;
  const spot = Number(trade._spot);
  let pct = null, label = "OPEN";
  if (Number.isFinite(spot)) {
    const prog = bull ? (spot - kl.entry) / span : (kl.entry - spot) / span;
    pct = Math.max(-20, Math.min(120, prog * 100));
    if (bull ? spot <= kl.invalidation : spot >= kl.invalidation) label = "STOP ZONE";
    else if (bull ? spot >= kl.target : spot <= kl.target) label = "TARGET HIT";
  }
  return (
    <span className="fsp-ls" title={`Plan: entry $${kl.entry} · stop $${kl.invalidation} · target $${kl.target}`}>
      <span className="fsp-ls-rail">
        <i className="fsp-ls-stop" />
        <i className="fsp-ls-fill" style={pct != null ? { width: `${Math.max(0, Math.min(100, pct))}%` } : undefined} />
        <i className="fsp-ls-tgt" />
      </span>
      {pct != null && (
        <b className={label === "TARGET HIT" ? "text-emerald-400" : label === "STOP ZONE" ? "text-rose-400" : "text-slate-400"}>
          {label}
        </b>
      )}
    </span>
  );
}

function TradeCard({ trade, onEdit, onDelete, onClose }) {
  const [exitPrice, setExitPrice] = useState("");
  const [expanded, setExpanded] = useState(false);

  const entry = parseFloat(trade.entry_price) || 0;
  const exit = parseFloat(trade.exit_price) || 0;
  const isClosed = isTradeClosed(trade);
  const pnl = isClosed ? tradePnl(trade) : null;
  const pnlPct = isClosed && entry > 0 ? ((exit - entry) / entry * 100 * (trade.action === "buy" ? 1 : -1)) : null;

  return (
    <div className={`rounded-lg border transition-all ${isClosed ? (pnl >= 0 ? "border-emerald-500/20 bg-emerald-500/5" : "border-rose-500/20 bg-rose-500/5") : "border-slate-700/30 bg-slate-800/20"}`}>
      <div className="p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${trade.type === "call" ? "bg-teal-500/20 text-teal-400" : "bg-purple-500/20 text-purple-400"}`}>
              {trade.type.toUpperCase()}
            </span>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${trade.action === "buy" ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"}`}>
              {trade.action.toUpperCase()}
            </span>
            <span className="text-xs font-medium text-slate-200">{trade.ticker}</span>
            <span className="text-[10px] text-slate-500 mono">{trade.strike}</span>
            {trade.expiry && <span className="text-[10px] text-slate-600">{trade.expiry}</span>}
            <span className="text-[10px] text-slate-600">x{trade.quantity}</span>
            {trade.key_levels && !isClosed && <LevelStatus trade={trade} />}
          </div>
          <div className="flex items-center gap-2">
            {pnl !== null && (
              <span className={`text-sm font-bold mono ${pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {pnl >= 0 ? "+" : ""}${pnl.toFixed(0)}
                {pnlPct !== null && <span className="text-[9px] ml-1">({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%)</span>}
              </span>
            )}
            <button onClick={() => setExpanded(!expanded)} className="text-slate-500 hover:text-slate-300 text-[10px]">
              {expanded ? "▲" : "▼"}
            </button>
          </div>
        </div>

        {expanded && (
          <div className="mt-2 pt-2 border-t border-slate-700/30 space-y-1">
            <div className="grid grid-cols-3 gap-2 text-[10px]">
              <div><span className="text-slate-500">Entry:</span> <span className="mono text-slate-300">${entry.toFixed(2)}</span></div>
              {isClosed && <div><span className="text-slate-500">Exit:</span> <span className="mono text-slate-300">${exit.toFixed(2)}</span></div>}
              <div><span className="text-slate-500">Date:</span> <span className="text-slate-300">{trade.entry_date}</span></div>
            </div>
            {trade.gex_regime && <div className="text-[10px]"><span className="text-slate-500">GEX:</span> <span className="text-amber-400">{trade.gex_regime.replace(/_/g, " ")}</span></div>}
            {trade.setup && <div className="text-[10px]"><span className="text-slate-500">Setup:</span> <span className="text-slate-300">{trade.setup}</span></div>}
            {trade.key_levels && (
              <div className="text-[10px] flex gap-3">
                <span className="text-slate-500">Plan:</span>
                <span className="mono text-slate-300">entry ${trade.key_levels.entry}</span>
                <span className="mono text-rose-400">stop ${trade.key_levels.invalidation}</span>
                <span className="mono text-emerald-400">target ${trade.key_levels.target}</span>
              </div>
            )}
            {trade.notes && <div className="text-[10px] text-slate-400 italic mt-1">{trade.notes}</div>}
            <div className="flex gap-1 mt-2">
              {!isClosed && (
                <>
                  <input type="number" step="0.01" value={exitPrice} onChange={e => setExitPrice(e.target.value)}
                    placeholder="Exit $" className="flex-1 bg-slate-800/50 border border-slate-700/50 rounded px-2 py-1 text-[10px] text-slate-200" />
                  <button onClick={() => onClose(trade.id, parseFloat(exitPrice) || 0)}
                    className="px-2 py-1 bg-emerald-600/20 text-emerald-400 rounded text-[10px] hover:bg-emerald-600/30">Close</button>
                </>
              )}
              <button onClick={() => onEdit(trade)} className="px-2 py-1 bg-slate-700/50 text-slate-400 rounded text-[10px] hover:bg-slate-700">Edit</button>
              <button onClick={() => onDelete(trade.id)} className="px-2 py-1 bg-rose-500/10 text-rose-400 rounded text-[10px] hover:bg-rose-500/20">Delete</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main Journal Component ───────────────────────────────────────────────────
export default function TradeJournal({ ticker }) {
  const [trades, setTrades] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingTrade, setEditingTrade] = useState(null);
  const [filterTicker, setFilterTicker] = useState("");
  const [filterStatus, setFilterStatus] = useState("all"); // all | open | closed
  const [sortBy, setSortBy] = useState("date"); // date | pnl | ticker
  const loadedRef = useRef(false);

  // Load from localStorage, then merge server-persisted auto-journal rows.
  // Server rows (source flowseeker-auto) survive localStorage clears and
  // sync across devices; local manual entries always win their own slot.
  // Merge keys are date-normalized: server writes full ISO timestamps while
  // local rows store date-only, which previously duplicated every ticket.
  useEffect(() => {
    let cancelled = false;
    const loadServer = async () => {
      try {
        const saved = localStorage.getItem("floww_trades_v2");
        if (saved) setTrades(JSON.parse(saved));
      } catch (e) { console.error("TradeJournal load failed:", e); }
      try {
        const res = await fetch(`${API}/flowseeker/journal/trades?days=365`);
        if (!res.ok) return;
        const data = await res.json();
        const server = data.trades || [];
        if (cancelled || server.length === 0) return;
        setTrades(prev => {
          const fresh = server
            .filter(s => !prev.some(t => journalKeysEqual(t, s)))
            .map((s, i) => ({ ...s, id: `srv-${Date.now()}-${i}`, created_at: s.created_at }));
          return fresh.length ? [...fresh, ...prev] : prev;
        });
      } catch (e) { /* server store unreachable — localStorage is the fallback */ }
    };
    loadServer();
    // Tickets confirmed in another tab/panel land without refresh.
    // Skipped while the edit modal is open so a refetch can't revert
    // the row being edited mid-keystroke.
    const onStorage = (e) => { if (e.key === "floww_trades_v2" && !showForm) loadServer(); };
    const onFocus = () => { if (!showForm) loadServer(); };
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", onFocus);
    };
  }, [showForm]);

  // Save to localStorage
  useEffect(() => {
    if (loadedRef.current) {
      localStorage.setItem("floww_trades_v2", JSON.stringify(trades));
    } else if (trades.length > 0) {
      loadedRef.current = true;
    }
  }, [trades]);

  const handleSave = useCallback((form) => {
    if (editingTrade?.id) {
      setTrades(prev => prev.map(t => t.id === editingTrade.id ? { ...form, id: editingTrade.id, updated_at: new Date().toISOString() } : t));
    } else {
      setTrades(prev => [{ ...form, id: Date.now(), created_at: new Date().toISOString() }, ...prev]);
    }
    setShowForm(false);
    setEditingTrade(null);
  }, [editingTrade]);

  const handleDelete = useCallback((id) => {
    setTrades(prev => prev.filter(t => t.id !== id));
  }, []);

  const handleClose = useCallback((id, exitPrice) => {
    setTrades(prev => prev.map(t =>
      t.id === id ? { ...t, exit_price: exitPrice, exit_date: new Date().toISOString().slice(0, 10) } : t
    ));
  }, []);

  const handleEdit = useCallback((trade) => {
    setEditingTrade(trade);
    setShowForm(true);
  }, []);

  // Computed data
  const { openTrades, closedTrades, stats, dailyPnl, tickerList } = useMemo(() => {
    // Closed = has an exit date OR any exit price (incl. "0" total loss). The
    // old exit_price>0 test dropped total-loss closes into "open", erasing the
    // loss from every stat below.
    const open = trades.filter(t => !isTradeClosed(t));
    const closed = trades.filter(isTradeClosed);

    const totalPnl = closed.reduce((sum, t) => sum + tradePnl(t), 0);

    const wins = closed.filter(t => tradeOutcome(t) === "win");
    const losses = closed.filter(t => tradeOutcome(t) === "loss");  // scratch excluded from both

    const decided = wins.length + losses.length;
    const winRate = decided > 0 ? (wins.length / decided * 100) : 0;
    const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + tradePnl(t), 0) / wins.length : 0;
    const avgLoss = losses.length > 0 ? losses.reduce((s, t) => s + tradePnl(t), 0) / losses.length : 0;

    const daily = {};
    closed.forEach(t => {
      const date = t.exit_date || t.entry_date || "unknown";
      daily[date] = (daily[date] || 0) + tradePnl(t);
    });
    const dailyPnl = Object.entries(daily).sort((a, b) => b[0].localeCompare(a[0])).slice(0, 14).reverse();

    const tickerSet = new Set(trades.map(t => t.ticker));

    return {
      openTrades: open,
      closedTrades: closed,
      stats: { totalPnl, winRate, avgWin, avgLoss, totalTrades: trades.length, openCount: open.length, closedCount: closed.length, wins: wins.length, losses: losses.length },
      dailyPnl,
      tickerList: Array.from(tickerSet).sort(),
    };
  }, [trades]);

  // Filtered + sorted trades
  const filteredTrades = useMemo(() => {
    let list = filterStatus === "open" ? openTrades : filterStatus === "closed" ? closedTrades : trades;
    if (filterTicker) list = list.filter(t => t.ticker === filterTicker);
    if (sortBy === "pnl") list = [...list].sort((a, b) => {
      const pnlA = isTradeClosed(a) ? tradePnl(a) : 0;
      const pnlB = isTradeClosed(b) ? tradePnl(b) : 0;
      return pnlB - pnlA;
    });
    return list;
  }, [trades, openTrades, closedTrades, filterTicker, filterStatus, sortBy]);

  const maxDailyPnl = dailyPnl.length > 0 ? Math.max(...dailyPnl.map(([, v]) => Math.abs(v)), 1) : 1;

  return (
    <div className="flex h-full">
      {/* Left Panel — Stats & Filters */}
      <div className="w-64 flex-shrink-0 border-r border-slate-800/50 bg-[#0b0d12] p-3 space-y-3 overflow-y-auto">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-200">Journal</h2>
          <button onClick={() => { setEditingTrade(null); setShowForm(true); }}
            className="text-[10px] px-2 py-1 bg-sky-600 hover:bg-sky-500 rounded text-white font-medium">+ Add</button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-2">
          <StatCard label="Total P&L" value={`$${stats.totalPnl >= 0 ? "+" : ""}${stats.totalPnl.toFixed(0)}`} color={stats.totalPnl >= 0 ? "emerald" : "rose"} />
          <StatCard label="Win Rate" value={`${stats.winRate.toFixed(0)}%`} color={stats.winRate >= 50 ? "emerald" : "amber"} />
          <StatCard label="Avg Win" value={`+$${stats.avgWin.toFixed(0)}`} color="emerald" />
          <StatCard label="Avg Loss" value={`$${stats.avgLoss.toFixed(0)}`} color="rose" />
          <StatCard label="Open" value={stats.openCount.toString()} color="amber" />
          <StatCard label="Closed" value={`${stats.wins}W / ${stats.losses}L`} color="slate" />
        </div>

        {/* Daily P&L */}
        {dailyPnl.length > 0 && (
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Daily P&L</div>
            <div className="flex items-end gap-0.5 h-16">
              {dailyPnl.map(([date, pnl]) => {
                const isPos = pnl >= 0;
                const height = Math.min(100, Math.abs(pnl) / maxDailyPnl * 100);
                return (
                  <div key={date} className="flex-1 flex flex-col items-center gap-0.5 group relative">
                    <div className="absolute -top-5 hidden group-hover:block bg-slate-800 border border-slate-700 rounded px-1 py-0.5 text-[7px] mono z-10 whitespace-nowrap">
                      {isPos ? "+" : ""}${pnl.toFixed(0)}
                    </div>
                    <div className={`w-full rounded-sm min-h-[2px] ${isPos ? "bg-emerald-500/60" : "bg-rose-500/60"}`} style={{ height: `${Math.max(height, 4)}%` }} />
                    <div className="text-[6px] text-slate-600 truncate w-full text-center" title={date}>{date.slice(5)}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="space-y-2">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">Filters</div>
          <div className="flex gap-1">
            {["all","open","closed"].map(s => (
              <button key={s} onClick={() => setFilterStatus(s)}
                className={`flex-1 text-[10px] py-1 rounded ${filterStatus === s ? "bg-sky-600/20 text-sky-400" : "bg-slate-800/50 text-slate-500"}`}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
          {tickerList.length > 1 && (
            <select value={filterTicker} onChange={e => setFilterTicker(e.target.value)}
              className="w-full bg-slate-800/50 border border-slate-700/50 rounded px-2 py-1 text-[10px] text-slate-200">
              <option value="">All Tickers</option>
              {tickerList.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          )}
          <select value={sortBy} onChange={e => setSortBy(e.target.value)}
            className="w-full bg-slate-800/50 border border-slate-700/50 rounded px-2 py-1 text-[10px] text-slate-200">
            <option value="date">Sort by Date</option>
            <option value="pnl">Sort by P&L</option>
          </select>
        </div>

        {/* Export */}
        {trades.length > 0 && (
          <button onClick={() => {
            const csv = ["ticker,type,action,strike,expiry,qty,entry_price,exit_price,entry_date,exit_date,pnl,notes",
              ...trades.map(t => {
                const pnl = isTradeClosed(t) ? tradePnl(t).toFixed(2) : "";
                return [t.ticker, t.type, t.action, t.strike, t.expiry, t.quantity, t.entry_price, t.exit_price, t.entry_date, t.exit_date, pnl, `"${(t.notes||"").replace(/"/g,'""')}"`].join(",");
              })
            ].join("\n");
            const blob = new Blob([csv], { type: "text/csv" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = `trades_${new Date().toISOString().slice(0,10)}.csv`; a.click();
          }} className="w-full text-[10px] py-1.5 bg-slate-800/50 hover:bg-slate-700/50 rounded text-slate-400">
            ↓ Export CSV
          </button>
        )}
      </div>

      {/* Right Panel — Trade List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {filteredTrades.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 text-sm gap-2">
            <div className="text-2xl">📝</div>
            <div>{trades.length === 0 ? "No trades yet" : "No trades match filters"}</div>
            <div className="text-[10px] text-slate-600">{trades.length === 0 ? "Click + Add to record your first trade" : "Try adjusting your filters"}</div>
          </div>
        ) : (
          filteredTrades.map(trade => (
            <TradeCard key={trade.id} trade={trade} onEdit={handleEdit} onDelete={handleDelete} onClose={handleClose} />
          ))
        )}
      </div>

      {/* Form Modal */}
      {showForm && (
        <TradeForm trade={editingTrade} onSave={handleSave} onCancel={() => { setShowForm(false); setEditingTrade(null); }} ticker={ticker} />
      )}
    </div>
  );
}

function StatCard({ label, value, color }) {
  const colorMap = {
    emerald: "text-emerald-400",
    rose: "text-rose-400",
    amber: "text-amber-400",
    slate: "text-slate-300",
  };
  return (
    <div className="bg-slate-800/30 rounded-lg p-2 text-center">
      <div className="text-[9px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`text-sm font-bold mono ${colorMap[color] || "text-slate-300"}`}>{value}</div>
    </div>
  );
}
