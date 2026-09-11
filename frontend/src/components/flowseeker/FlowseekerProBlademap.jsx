/**
 * FlowseekerProBlademap.jsx — Blademap.ai-style Tidehunter Pro, wired to REAL
 * market data. Phase 5.3 (2026-08-31): live flow feed now tries Public API
 * (/api/public/chain) first, falls back to cvserver (/api/flowseeker/chain).
 *   /api/flowseeker/live  /regime/{t}  /api/vpin/{t} (microstructure router)
 *   /api/heatmap/{t} (real GEX grid)  /api/public/chain/{t} (Phase 5.3)
 * NOTE: /api/flowseeker/ofi/{t} and /lambda/{t} DO NOT EXIST on the backend —
 * the fetches below .catch(() => null) by design; VPIN/λ stay blank until a
 * trade-level feed exists. Vol surface tab removed from the tab strip.
 *
 * Self-contained: scoped CSS (.fsb-root, fsb-* classes), Plotly via CDN.
 * The agent's FlowseekerProTab.jsx is left untouched.
 */
import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { BACKEND_URL } from "../../config/api";
import { mkScanRow, evalAlerts, evalTickerAlerts, streakOf, cleanHistory, tickerRollup, volSigma, annotateFirstSeen, sessionDay, fmtClock, fmtAge, awaySummary, scanRowsToCSV, oiChange, fmtUSD, fmtK, fmtIV, scoreGradeOf, pulseState, elapsedClock, formatFOLLOWStrip, tierOf, selectFires, pickBanner, bizDTE, spreadPosition, overviewStats, equityType, signedOtm, isOpexDay, highlightState, flagSpreadLegs, quoteSkew, stampPollDeltas, contractKey, nearestExpiryPin, rollPooled, pushCapped } from "./scanLogic";
import DarkPoolPanel from "./darkpool/DarkPoolPanel";
import { NetPremiumTrend, StrikeDistribution, VolOiFooter } from "./history/HistoryViews";
import { Checklist, FunnelEmpty } from "./methodology/Methodology";
import Tracker from "./tracker/Tracker";
import ChartModal from "./chart/ChartModal";
import { widenActions, applyFilters, defaultFilterState } from "./filters/filterState";
import { exposureBadgeFor } from "./exposureBadges";
import "./FlowseekerProBlademap.css";

const API = `${BACKEND_URL}/api/flowseeker`;
const NOISE_FLOOR = 5; // ignore day-volume deltas below this many contracts
// Desk noise budget: max tape-visible alerts per rule per hour. The eval
// engines still count EVERY hit (deltas + ⚡badge stay truthful); this only
// caps what reaches the tape. 0 = unlimited (kept for parity with the old
// behavior if a desk wants the flood back).
const ALERT_NOISE_CAP_H = 4;

const PL = {
  paper: "rgba(0,0,0,0)", plot: "rgba(0,0,0,0)", grid: "#ffffff0f", axis: "#ffffff1f",
  text: "#fffffff2", muted: "#ffffff73", font: "11px 'JetBrains Mono', ui-monospace, Consolas, monospace",
  green: "#22c55e", red: "#ef4444", blue: "#38bdf8", purple: "#a267ff", amber: "#e8c96a",
};

// ---------- helpers (formatting/DTE live in ./scanLogic — single source) ----------
async function getJSON(url, signal) {
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
// Rough ATM premium estimate when cvserver isn't quoting bid/ask (per-contract $).
function estPrice(strike, iv, expiry) {
  const dte = Math.max(1, bizDTE(expiry));
  const ivv = iv > 1 ? iv / 100 : (iv || 0.2);
  return Math.max(0.05, strike * ivv * Math.sqrt(dte / 365) * 0.4);
}

// Conviction from the row's own attributes — log-scaled so big premium / vol-oi
// SPREAD across the range instead of all saturating at the same total. Returns
// the 0-100 score plus the 4 components (used by the gauge + radar so they agree).
function rowConviction(p) {
  const cls = String(p.classification || "regular").toLowerCase();
  const pat = cls === "sweep" ? 24 : cls === "unusual" ? 18 : cls === "block" ? 14 : 8;     // 8-24 pattern
  const prem = Number(p.premium) || 0;
  const size = Math.min(30, Math.log10(Math.max(1e4, prem) / 1e4) * 9);                      // 0-30 size (log)
  const voi = Number(p.vol_oi_ratio) || 0;
  const stat = Math.min(26, Math.log10(Math.max(1, voi) + 1) * 14);                          // 0-26 unusualness (log)
  const dte = Number(bizDTE(p.expiration)) || 0;
  const urg = dte <= 1 ? 14 : dte <= 7 ? 9 : dte <= 30 ? 5 : 2;                              // 2-14 urgency
  const conv = Math.round(Math.max(20, Math.min(99, pat + size + stat + urg)));
  return { pat: +pat.toFixed(1), size: +size.toFixed(1), stat: +stat.toFixed(1), urg: +urg.toFixed(1), conv };
}

// Map Public API flat contract list to flow-feed row shape.
// Filters: vol >= 100, vol/oi >= 0.4. Sorts by vol_oi_ratio desc, caps at 100.
// Exported for Jest tests (Phase 5.3).
export function mapPublicChainToRows(contracts, spot, ticker) {
  const rows = [];
  for (const c of contracts) {
    const vol = Number(c.volume) || 0;
    if (vol < NOISE_FLOOR * 20) continue;
    const oi = Number(c.oi) || 0;
    const voi = oi > 0 ? vol / oi : vol / 100;
    if (voi < 0.4) continue;
    const iv = Number(c.iv) || 0;
    const bid = Number(c.bid) || 0;
    const ask = Number(c.ask) || 0;
    const last = Number(c.last) || 0;
    const mid = last || ((bid + ask) / 2) || estPrice(Number(c.strike), iv, c.expiry);
    const premium = Math.round(vol * mid * 100);
    const dte = bizDTE(c.expiry);
    const cls = premium >= 5e7 ? "block" : dte <= 2 ? "sweep" : "unusual";
    // Pulse SIDE inference (BladeMap contract): last trading at/above the
    // quote mid = aggressive lift (ASK), below = hit (BID). No quotes →
    // UNKNOWN (F11: never guess from vol/OI proxy); renders as a dash.
    const midQ = (bid > 0 && ask > 0) ? (bid + ask) / 2 : 0;
    const side = (bid > 0 && ask > 0 && last > 0) ? (last >= midQ ? "ASK" : "BID") : "UNKNOWN";
    const sp = Number(spot) || 0;
    const strikeN = Number(c.strike);
    const otm = sp > 0 && strikeN > 0 ? Math.abs((strikeN - sp) / sp) * 100 : null;
    const p = {
      ticker, type: String(c.type || "").toLowerCase(), classification: cls,
      strike: strikeN, expiration: c.expiry, timestamp: Date.now(),
      volume: vol, oi, vol_oi_ratio: voi, iv: iv < 1 ? iv * 100 : iv, premium,
      mid, side, spot: sp || null, otm,
      bid: bid > 0 ? bid : null, ask: ask > 0 ? ask : null,
      last: last > 0 ? last : null,
    };
    const cd = rowConviction(p);
    p._conv = cd.conv;
    p._cd = cd;
    rows.push(p);
  }
  rows.sort((a, b) => b.vol_oi_ratio - a.vol_oi_ratio);
  return rows.slice(0, 100);
}

// ---------- BladeMap Pulse helpers (Tidehunter Pro tape) ----------
// Mirrors the BladeMap.ai Pulse table contract from the desk reference:
// deterministic SIDE→SIGNAL, 0-10 score, SILVER/GOLDEN/WHALE badges,
// 90-second print aggregation. Exported for Jest tests.

// Conviction 20-99 → BladeMap 0-10 score (1 decimal).
export function pulseScore10(conv) {
  const c = Math.max(20, Math.min(99, Number(conv) || 20));
  return +(c / 10).toFixed(1);
}

// ASK (aggressive lift) → BULLISH, BID (hit) → BEARISH. Matches the
// reference tape on every visible row (CALL or PUT alike). UNKNOWN (no
// quote, F11) stays UNKNOWN — never defaulted to BEARISH.
export function pulseSignal(side) {
  const s = String(side || "").toUpperCase();
  if (s === "ASK") return "BULLISH";
  if (s === "BID") return "BEARISH";
  return "UNKNOWN";
}

// Put-ASK is often protective buying, not directional bullishness. The tape
// keeps the reference BULLISH signal; this flag annotates the ambiguity.
export function pulseHedge(type, side) {
  return String(type || "").toLowerCase().startsWith("p")
    && String(side || "").toUpperCase() === "ASK";
}

// Thresholds read off the reference tape ($899K SILVER vs $950K GOLDEN).
export function pulseBadges(premium) {
  const prem = Number(premium) || 0;
  const b = ["SILVER"];
  if (prem >= 900e3) b.push("GOLDEN");
  if (prem >= 1e6) b.push("WHALE");
  return b;
}

// COST copy in ONE place (Step 1.4 honesty contract): building state shows a
// count, never a number; every state carries the mid-quote-not-executable
// caption. Jest pins the wording so the readout can't silently harden.
export const COST_TITLE = "Mid-quote Roll spread over the pin expiry bucket — quote bounce + quote staleness included. NOT an executable taker cost: always compare live quotes before trading. Needs 30 deltas across the bucket.";
export const COST_CAPTION = "mid-quote, not executable";
export const COST_CAPTION_TITLE = "Mid-quote Roll spread: quote bounce + quote staleness included. NOT an executable taker cost.";
export function costLabel(costRead) {
  if (!costRead) return null;
  if (costRead.building) return { text: `COST building ${costRead.nd}/30`, title: COST_TITLE, caption: COST_CAPTION };
  return { text: `COST ~$${Number(costRead.spread).toFixed(2)}`, title: COST_TITLE, caption: COST_CAPTION };
}

// Sweep/block copy in ONE place (XH-1 honesty contract): snapshot-chain
// classes are size/tenor buckets, not observed executions. The old titles
// ("multi-print burst", "multi-exchange urgency") described mechanisms the
// classifiers never measure — scanTypeOf buckets single-row volume
// (vol>=25000 sweep, vol>=8000 block) and the chain-scan path buckets
// premium/DTE. Jest pins the wording so the labels can't silently harden.
export const FLOW_PROXY_NOTE = "Sweep/Block classes are size/tenor-bucket proxies on snapshot chains (cvserver has no venue tape). Ov-bar NetPrem = 90s rolled tape sum — reconcile if diverged (P0).";
export function flowClassTitle(pcls) {
  const c = String(pcls || "").toUpperCase();
  if (c === "SWEEP") return "Sweep class: size/tenor-bucket proxy — no multi-venue execution observed (no venue tape)";
  if (c === "BLOCK") return "Block class: size-bucket proxy — not an observed block print";
  return c || "REG";
}
export const FILTER_CHIP_TITLES = {
  SWEEP: "Sweep class: size/tenor-bucket proxy — no venue tape",
  BLOCK: "Block class: size-bucket proxy — not an observed block print",
};

// Drop prints older than the Pulse window (trailing-90s tape).
export function pruneBuffer(buf, windowMs = 90e3, now = Date.now()) {
  return (buf || []).filter((r) => now - (Number(r.timestamp) || now) < windowMs);
}

// Aggregate prints into 90-second windows per contract so one hot contract
// renders ONE row (premium summed, print count kept) instead of flooding
// the tape. Prints outside [now-windowMs, now] are excluded. Returns agg
// rows premium-ranked, capped at 50.
export function aggregatePulse(rows, windowMs = 90e3, now = Date.now()) {
  const fresh = (rows || []).filter((r) => now - (Number(r.timestamp) || now) < windowMs);
  const map = new Map();
  for (const r of fresh) {
    const key = `${r.ticker}|${String(r.type || "").toLowerCase()}|${r.strike}|${String(r.expiration || "").slice(0, 10)}`;
    const g = map.get(key);
    const ts = Number(r.timestamp) || now;
    if (!g) {
      map.set(key, { row: r, prem: Number(r.premium) || 0, size: Number(r.volume) || 0, n: 1, ts });
    } else {
      // Same contract seen again inside the window → roll up.
      g.prem += Number(r.premium) || 0;
      g.size += Number(r.volume) || 0;
      g.n += 1;
      if (ts > g.ts) { g.ts = ts; g.row = r; }
    }
  }
  const out = [...map.values()].map((g) => ({ ...g.row, _aggPrem: g.prem, _aggSize: g.size, _aggN: g.n, _aggTs: g.ts }));
  out.sort((a, b) => (b._aggPrem || 0) - (a._aggPrem || 0));
  return out.slice(0, 50);
}

// ---------- cross-symbol scanner (scenner34 BladeMap grid) ----------
// Fallback-loop ticker list only — the live path is the market-wide backend
// /scan endpoint (one call, the whole market). SCAN_UNIVERSE is used solely
// if a per-ticker fallback loop is ever reintroduced; nothing filters or
// alerts by it.
const SCAN_UNIVERSE = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "PLTR", "ENPH", "NFLX", "AVGO", "MU", "COIN", "SMCI"];
// (scanner math — bizDTE/scanTypeOf/scanScoreOf/estimateDelta/approxSpot/mkScanRow
// and the fmt* helpers — lives in ./scanLogic.js, tested in scanLogic.test.js)

const PREFS_KEY = "fsb-scan-prefs-v1";
const ALERTS_KEY = "fsb-scan-alerts-v1";
const ALERTSEEN_KEY = "fsb-scan-alertseen-v1";
// Rule defaults are MERGED over stored prefs — a pref blob saved before a new
// rule existed must not silently disable it. Order = tape-summary display order.
// 2026-09-02 institutional noise pass: SCORE 85→92, WHALE $10M→$25M, SIGMA 4σ→6σ,
// FOLLOW 2d→3d. The chips stay user-toggleable — an existing pref blob keeps its
// saved thresholds (merge only fills keys that don't exist yet), so nobody's
// setup changes under them without a click.
const DEFAULT_RULES = {
  oiconf: true, follow: true, sigma: true, score: true, prime: true, whale: true, zerodte: true,
  scoreMin: 92, whaleMin: 25e6, sigmaMin: 6, followMin: 3,
};
const RULES_ORDER = ["OICONF", "FOLLOW", "SIGMA", "SCORE", "WHALE", "PRIME", "0DTE", "SOURCE"];
const FIRSTSEEN_KEY = "fsb-scan-firstseen-v1";
const LASTSEEN_KEY = "fsb-scan-lastseen-v1";
function loadScanPrefs() {
  try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || {}; } catch { return {}; }
}
// The tape keeps today + yesterday — a 12-hour Dow night shift must not erase
// the session before Nav ever sees it. Older days drop on load.
function loadAlertLog() {
  try {
    const all = JSON.parse(localStorage.getItem(ALERTS_KEY)) || [];
    const keep = new Set([sessionDay(), sessionDay(Date.now() - 86400e3)]);
    return all.filter((a) => !a.day || keep.has(a.day));
  } catch { return []; }
}
function loadFirstSeen() {
  try {
    const s = JSON.parse(localStorage.getItem(FIRSTSEEN_KEY));
    return s && s.day === sessionDay() ? s : { day: sessionDay(), map: {} };
  } catch { return { day: sessionDay(), map: {} }; }
}
// Alert dedup timestamps live SEPARATELY from the display tape: the tape is
// capped at 100 and user-clearable, and if it doubled as the dedup store,
// eviction or Clear would re-fire every still-true long-ttl alert (OI change
// is static all day; σ only grows) in a notification loop. {key: lastFiredMs},
// pruned to 24h on load — the longest rule ttl is 20h.
function loadAlertSeen() {
  try {
    const m = JSON.parse(localStorage.getItem(ALERTSEEN_KEY)) || {};
    const cut = Date.now() - 24 * 3600e3;
    const out = {};
    for (const [k, t] of Object.entries(m)) if (t >= cut) out[k] = t;
    return out;
  } catch { return {}; }
}
// Snapshot the previous visit's last-seen stamp ONCE per page load. Mount
// effects overwrite the key immediately, and StrictMode's dev double-mount
// (or any page-switch remount) would otherwise read its own stamp and always
// see a zero gap — killing the away digest.
const AWAY_FROM = (() => { try { return Number(localStorage.getItem(LASTSEEN_KEY)) || null; } catch { return null; } })();
let awayShownThisLoad = false;   // one digest per page load, not per remount

// Mark rows unseen in the previous refresh (drives the NEW flash + alerts).
// Baseline is per-source-mode: an A<->B path flip resets the baseline instead
// of mass-flagging the other universe's rows as NEW (alert/notification flood).
function markNew(rows, prevKeysRef, mode) {
  const keyOf = (r) => `${r.under}|${r.type}|${r.strike}|${r.exp}`;
  const keys = new Set(rows.map(keyOf));
  const prev = prevKeysRef.current;
  if (prev && prev.mode === mode) {
    for (const r of rows) r._new = !prev.keys.has(keyOf(r));
  }
  prevKeysRef.current = { mode, keys };
  return rows;
}

// ---------- component ----------
export default function FlowseekerProBlademap({ active = true, onTrade = null }) {
  const [tab, setTab] = useState("scanner");   // land on the cross-symbol scanner (the hero view)
  const [ticker, setTicker] = useState("SPY");
  const [signals, setSignals] = useState([]);     // merged feed, newest first
  const [flowPaused, setFlowPaused] = useState(false);  // Pulse pause (reference ⏸ button)
  const [flowNonce, setFlowNonce] = useState(0);        // Pulse refresh (reference ⟳ button)
  const [howTo, setHowTo] = useState(false);            // HOW TO READ popover
  const [selected, setSelected] = useState(null);
  const [chartRow, setChartRow] = useState(null);
  const [filter, setFilter] = useState("all");
  // W6 filter depth: equity scope, moneyness, OPEX, strike range.
  const [equity, setEquity] = useState("all");
  const [money, setMoney] = useState("all");
  const [opexOnly, setOpexOnly] = useState(false);
  const [strikeMin, setStrikeMin] = useState("");
  const [strikeMax, setStrikeMax] = useState("");
  // Flow feed time-frame preset: All / 0DTE / 1-7D / Weekly / Monthly / Qtrly / LEAPS
  const [dteFilter, setDteFilter] = useState("all");
  // Pulse tape controls (BladeMap header contract): ticker scope, exclusive
  // DTE band, minimum 0-10 score.
  const [pulseTicker, setPulseTicker] = useState("ALL");
  const [pulseQ, setPulseQ] = useState("");
  // Open universe (2026-09-04): focus the tape on ANY ticker, not a list.
  const focusPulseTicker = useCallback(() => {
    const t = pulseQ.trim().toUpperCase().replace(/^\$/, "");
    if (!t) return;
    setPulseTicker(t);
    setTicker(t);
  }, [pulseQ]);
  const [pulseDte, setPulseDte] = useState("ALL");
  const [pulseScore, setPulseScore] = useState(0);
  const [regime, setRegime] = useState({ label: "—", cls: "chop" });
  const [clock, setClock] = useState("");
  const [plotlyReady, setPlotlyReady] = useState(!!window.Plotly);
  // cross-symbol scanner state (Scanner tab) — filters/sort persist in localStorage.
  // The universe is FULLY OPEN: no allowlists, no My-universe filter, no
  // alert scoping — the market-wide scan alerts on any symbol.
  const prefs = useMemo(loadScanPrefs, []);
  const [scan, setScan] = useState([]);
  const [scanAt, setScanAt] = useState("");
  const [scanSort, setScanSort] = useState(prefs.scanSort || { key: "score", dir: "desc" });
  const [scanTypeF, setScanTypeF] = useState(prefs.scanTypeF || "all");
  const [scanMinVol, setScanMinVol] = useState(prefs.scanMinVol || 0);
  const [scanMinPrem, setScanMinPrem] = useState(prefs.scanMinPrem || 0);
  const [scanMinOI, setScanMinOI] = useState(prefs.scanMinOI || 0);
  const [scanMinScore, setScanMinScore] = useState(prefs.scanMinScore || 0);
  // DTE time-frame preset for the SCAN table too — the flow feed has had this
  // since fe0e9ef; the Scanner lost it in the Simple-mode consolidation. Same
  // presets, same semantics as the flow feed's dteFilter.
  const [scanDteF, setScanDteF] = useState(prefs.scanDteF || "all");
  const [scanQ, setScanQ] = useState("");
  const [scanMeta, setScanMeta] = useState({ mode: null, stale: false, symbols: 0 });
  const [baselines, setBaselines] = useState({});   // {ticker: {avg, std, days}} from /scan
  const [alertScore, setAlertScore] = useState(prefs.alertScore ?? 92);
  // Methodology checklist state — W7 verdict wiring (real state, not no-ops).
  const [checks, setChecks] = useState({});
  const [verdict, setVerdict] = useState(null);
  // Filter pipeline bridge — W6 funnel-empty wiring.
  // Bridges the Blademap inline scan knobs to the unified subtractive filter
  // pipeline so FunnelEmpty can show honest widening actions when the result
  // hits zero — without duplicating filter logic in the scan.
  const fsFilter = useMemo(() => ({
    equityType: { stocks: true, etfs: true, indices: true },
    sweepsOnly: false,
    side: { BID: true, MID: true, ASK: true },
    otm: false,
    itm: false,
    dte0: scanDteF === "0dte",
    opexOnly: false,
    strikeRange: { min: null, max: null },
    oiGrowth: { min: 0 },
    sentiment: { contract: [-100, 100], chain: [-100, 100] },
    absScore: false,
    minPremium: scanMinPrem || 0,
    minScore: scanMinScore || 0,
    dteBand: scanDteF === "all" ? null : scanDteF,
  }), [scanDteF, scanMinPrem, scanMinScore]);
  const [alertRules, setAlertRules] = useState({ ...DEFAULT_RULES, ...(prefs.alertRules || {}) });
  const [history, setHistory] = useState({});   // {ticker: [{date, total_vol, call_vol, put_vol}]} from /scan/history
  const [alertLog, setAlertLog] = useState(loadAlertLog);
  const [suppressedCount, setSuppressedCount] = useState(0);   // noise-budget overflow (truthful, session-scoped)
  // ── Outcome ledger: measured alert quality (per-rule precision/lift) ──
  // Backend joins the alert ledger to forward returns + a matched control
  // cohort; rules below min_alerts come back precision=null → we render
  // "uncalibrated · n=k", never a fabricated hit rate.
  const [outcomes, setOutcomes] = useState(null);
  const [calibration, setCalibration] = useState(null);
  const [outcomesOpen, setOutcomesOpen] = useState(false);
  const loadOutcomes = useCallback(async () => {
    try {
      const d = await getJSON(`${API}/outcomes?days=60`);
      if (d && d.ok) setOutcomes(d);
    } catch { /* ledger cold or bars slow — the strip just stays empty */ }
    try {
      const c = await getJSON(`${API}/model`);
      if (c && c.ok) setCalibration(c);
    } catch { /* model endpoint cold — panel stays empty */ }
  }, []);
  // NOTE: the refreshTick-consuming effect lives BELOW refreshTick's
  // declaration (TDZ: `const` is not usable before its initializer runs).
  // Simple mode (default): institutional alerts + the full quality-gated table,
  // no knobs. ⚙ Advanced reveals the full filter/preset/rule-chip toolkit.
  const [advanced, setAdvanced] = useState(!!prefs.advanced);
  const [alertsOpen, setAlertsOpen] = useState(true);   // the feed IS the product — open by default
  const [alertOrder, setAlertOrder] = useState("new");   // tape order: newest | oldest first
  const [scanSideF, setScanSideF] = useState(prefs.scanSideF || "all");   // Calls/Puts — visible in both modes
  const [away, setAway] = useState(null);                 // "while you were away" digest, null = hidden
  const [notify, setNotify] = useState(!!prefs.notify);
  const [forcing, setForcing] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  // Outcomes/model refresh — declared here because refreshTick is declared
  // above this line (TDZ-safe; the hook reads it in its dependency array).
  useEffect(() => { if (active) loadOutcomes(); }, [active, loadOutcomes, refreshTick]);
  // ── Keyboard navigation: j/k cursor, Enter focus, / search, r refresh ──
  const [kbIdx, setKbIdx] = useState(-1);
  const scanQRef = useRef(null);
  // ── Blademap v3: conviction-ranked feed + calibration + journal stats ──
  const [convFeed, setConvFeed] = useState([]);
  const [convFeedState, setConvFeedState] = useState("loading"); // loading | ready | unavailable
  const [calibBands, setCalibBands] = useState([]);
  const [setupStats, setSetupStats] = useState(null);
  // ── Zenith-style control cluster state (settings + quick filters) ──
  const [showSettings, setShowSettings] = useState(false);
  const [showQuickFilters, setShowQuickFilters] = useState(false);
  const [pollMs, setPollMs] = useState(() => {
    try { return Number(localStorage.getItem("fsb.pollMs")) || 60000; } catch { return 60000; }
  });
  useEffect(() => { try { localStorage.setItem("fsb.pollMs", String(pollMs)); } catch { /* */ } }, [pollMs]);
  const [minScoreQF, setMinScoreQF] = useState(0);
  const [dteRange, setDteRange] = useState([null, null]);
  const prevKeysRef = useRef(null);
  const firstSeenRef = useRef(loadFirstSeen());   // { day, map:{contractKey: firstSeenMs} }
  const notifyRef = useRef(false);
  useEffect(() => { notifyRef.current = notify; }, [notify]);
  const hadDataRef = useRef(false);
  useEffect(() => { hadDataRef.current = scan.length > 0; }, [scan]);

  // Multi-day persistence per ticker (from /scan/history) — the "what are they
  // following" read: n = consecutive elevated-volume days. Refs mirror state so
  // the poll-driven alert ingest sees current values without re-arming.
  const streaks = useMemo(() => {
    const out = {};
    for (const [t, days] of Object.entries(history)) {
      const st = streakOf(days);
      if (st && st.n >= 2) out[t] = st;
    }
    return out;
  }, [history]);
  const streaksRef = useRef({});
  useEffect(() => { streaksRef.current = streaks; }, [streaks]);
  const baselinesRef = useRef({});
  useEffect(() => { baselinesRef.current = baselines; }, [baselines]);

  // Log (and optionally notify) when the scan source flips market↔fallback —
  // a coverage change is something a desk wants to know.
  const lastModeRef = useRef(null);
  const noteSourceFlip = useCallback((mode, symbols) => {
    const prev = lastModeRef.current;
    lastModeRef.current = mode;
    if (prev == null || prev === mode) return;
    const entry = {
      key: `src|${mode}`, rule: "SOURCE",
      under: mode === "market" ? "LIVE" : "FALLBACK",
      type: "", strike: "", exp: "", score: null, premium: null, dte: null,
      label: mode === "market"
        ? `Recovered to market-wide coverage (${symbols} symbols)`
        : `Degraded to ${symbols}-symbol fallback scan`,
      src: mode, day: sessionDay(),
      t: Date.now(), time: fmtClock(Date.now(), true),
    };
    setAlertLog((prevLog) => {
      const next = [entry, ...prevLog].slice(0, 100);
      try { localStorage.setItem(ALERTS_KEY, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
    if (notifyRef.current && document.hidden && "Notification" in window && Notification.permission === "granted") {
      try { new Notification("Scanner source changed", { body: entry.label }); } catch { /* platform quirk */ }
    }
  }, []);
  // Poll effect reads alert config via ref so rule tweaks don't re-arm the interval.
  // Alerting is market-wide: allow=null (whole market), no universe scoping.
  const alertCfgRef = useRef({});
  useEffect(() => {
    alertCfgRef.current = { minScore: alertScore, enabled: alertRules, allow: null, side: scanSideF };
  }, [alertScore, alertRules, scanSideF]);

  useEffect(() => {    try { localStorage.setItem(PREFS_KEY, JSON.stringify({ scanTypeF, scanMinVol, scanMinPrem, scanMinOI, scanMinScore, scanSideF, scanDteF, scanSort, alertScore, alertRules, notify, advanced }));
    } catch { /* private mode — prefs just don't persist */ }
  }, [scanTypeF, scanMinVol, scanMinPrem, scanMinOI, scanMinScore, scanSideF, scanDteF, scanSort, alertScore, alertRules, notify, advanced]);

  // "While you were away" — keep the last-seen stamp current while visible
  // (the previous visit's value was snapshotted at module load, see AWAY_FROM).
  useEffect(() => {
    const stamp = () => { try { localStorage.setItem(LASTSEEN_KEY, String(Date.now())); } catch { /* private mode */ } };
    stamp();
    const id = setInterval(() => { if (!document.hidden) stamp(); }, 60e3);
    document.addEventListener("visibilitychange", stamp);
    window.addEventListener("beforeunload", stamp);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", stamp); window.removeEventListener("beforeunload", stamp); };
  }, []);
  // Build the digest once, when the first scan of this page load lands.
  useEffect(() => {
    if (!scan.length || awayShownThisLoad) return;
    awayShownThisLoad = true;
    setAway(awaySummary(alertLog, scan, AWAY_FROM));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan]);

  // CSV of the CURRENT filtered/sorted view — lands scanner rows in the DVT journal.
  const exportCSV = useCallback((rows) => {
    const blob = new Blob([scanRowsToCSV(rows)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `flowseeker-scan-${sessionDay()}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }, []);

  // Force refresh via the backend's debounced /scan/refresh, then re-poll.
  // Also bumps refreshTick so the Pulse tape (overview rollup + print buffer)
  // refreshes on the Scanner tab — without this, the inline tape surfaces only
  // refresh on the Flow tab's chain poll (L614-697), leaving Scanner-tab tape
  // stale until manual ⟳. The chain call here is the same one the Flow
  // tab would make on next poll; connection-budget impact is one POST per
  // manual refresh, not a new recurring interval.
  //
  // Abort-safety (X4 race-gap closure): a ticker switch or repeated button
  // click must not leave two /scan/refresh in flight against the same session.
  // The ref + AbortController mirrors the ExposureStrip race-safety pattern:
  // the new call aborts the previous one before starting, so a stale response
  // cannot land on the wrong ticker's tape surfaces.
  const refreshAbortRef = useRef(null);
  const forceRefresh = useCallback(async () => {
    if (refreshAbortRef.current) {
      refreshAbortRef.current.abort();
    }
    const ctrl = new AbortController();
    refreshAbortRef.current = ctrl;
    setForcing(true);
    try {
      await fetch(`${API}/scan/refresh?limit=500`, {
        method: "POST",
        signal: ctrl.signal,
      });
      // Wake the Pulse tape on the Scanner tab: bump refreshTick so the
      // [signals] effect (L940-971) re-runs and re-stamps the buffer.
      // The tape's rows come from printBufferRef which is fed by the Flow-tab
      // chain poll; on Scanner tab this re-runs existing queued prints through
      // the tape filters without a new chain fetch.
      setRefreshTick((t) => t + 1);
    } catch (e) {
      if (e.name !== "AbortError") { /* GET below will serve cache */ }
    }
    setForcing(false);
    setRefreshTick((t) => t + 1);
  }, []);

  // Clean up any in-flight refresh when the component unmounts.
  useEffect(() => {
    return () => {
      if (refreshAbortRef.current) refreshAbortRef.current.abort();
    };
  }, []);

  // Browser notifications — opt-in, permission-gated.
  const toggleNotify = useCallback(async () => {
    if (!notify) {
      if (!("Notification" in window)) return;
      let perm = Notification.permission;
      if (perm === "default") perm = await Notification.requestPermission();
      if (perm !== "granted") return;
    }
    setNotify((n) => !n);
  }, [notify]);

  // Append newly triggered alerts to the persistent log. Dedupe is per-key
  // with a per-rule ttl (contract rules 30min default; ΔOI-confirm and
  // ticker-level SIGMA/FOLLOW carry hours-long ttls from the engine) against
  // the standalone alertSeen store — NOT the display tape — so tape eviction
  // or Clear can't re-fire still-true alerts; tape display caps at 100.
  const alertSeenRef = useRef(loadAlertSeen());
  // Mirror of the tape for the noise-budget window counts — reads stay OUTSIDE
  // the setAlertLog updater (updaters must stay pure; StrictMode double-invokes).
  const alertLogRef = useRef(alertLog);
  useEffect(() => { alertLogRef.current = alertLog; }, [alertLog]);
  const ingestAlerts = useCallback((rows, mode) => {
    const cfg = alertCfgRef.current;
    const hits = [
      ...evalAlerts(rows, cfg),
      // Rollup over EVERY ticker in the scan (not the display top-N) — a
      // cheap-option name can be 6σ by volume while ranking low by premium.
      // SIGMA compares today's coverage against baselines recorded from the
      // market-wide path, so it only runs on market-mode scans.
      ...evalTickerAlerts(tickerRollup(rows, 1e9), baselinesRef.current, streaksRef.current,
        { enabled: { ...cfg.enabled, sigma: !!cfg.enabled.sigma && (mode === "market" || mode === "public") }, allow: cfg.allow }),
    ];
    if (!hits.length) return;
    const now = Date.now();
    const seen = alertSeenRef.current;
    const fresh = hits.filter((h) => (seen[h.key] ?? 0) < now - (h.ttl || 30 * 60e3))
      .map((h) => ({ ...h, t: now, time: fmtClock(now, true), src: mode, day: sessionDay(),
        firstSeen: rows.find((r) => `${r.under}|${r.type}|${r.strike}|${r.exp}` === (h.ckey || h.key))?.firstSeen }));
    if (!fresh.length) return;
    // Desk noise budget: after dedup, cap tape-visible fires per rule per
    // hour (ALERT_NOISE_CAP_H). Overflow is counted, not dropped silently —
    // the ⚡ Alerts KPI shows +N held back so the total stays truthful.
    // Suppressed fires STILL get dedup-marked below: the budget limits tape
    // delivery, not evaluation — otherwise a static all-day SIGMA would
    // re-fire every poll and inflate the held-back counter meaninglessly.
    const capped = [];
    let suppressed = 0;
    if (ALERT_NOISE_CAP_H > 0) {
      for (const h of fresh) {
        const rule = String(h.rule || "").toUpperCase();
        const nRecent = alertLogRef.current.filter((a) => a.rule === rule && now - a.t < 3600e3).length
          + capped.filter((a) => a.rule === rule).length;
        if (nRecent >= ALERT_NOISE_CAP_H) { suppressed++; continue; }
        capped.push(h);
      }
    } else {
      capped.push(...fresh);
    }
    if (suppressed) setSuppressedCount((c) => c + suppressed);
    if (!capped.length) return;
    for (const h of fresh) seen[h.key] = now;   // ALL fresh — capped + suppressed
    try { localStorage.setItem(ALERTSEEN_KEY, JSON.stringify(seen)); } catch { /* private mode */ }
    if (notifyRef.current && document.hidden && "Notification" in window && Notification.permission === "granted") {
      try {
        new Notification(`⚡ ${capped.length} flow alert${capped.length > 1 ? "s" : ""}${suppressed ? ` (+${suppressed} held back)` : ""}`, {
          body: capped.slice(0, 3).map((h) => h.label
            ? `${h.rule}: ${h.label}`
            : `${h.rule} ${h.under} ${h.type === "call" ? "C" : "P"}${h.strike}${h.why ? ` — ${h.why}` : ""}`).join("\n"),
        });
      } catch { /* notification constructor can throw on some platforms */ }
    }
    setAlertLog((prev) => {
      const next = [...capped, ...prev].slice(0, 100);
      try { localStorage.setItem(ALERTS_KEY, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  }, []);

  const gaugeRef = useRef(null), radarRef = useRef(null);

  // Plotly CDN
  useEffect(() => {
    if (window.Plotly) { setPlotlyReady(true); return; }
    const s = document.createElement("script");
    s.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
    s.onload = () => setPlotlyReady(true);
    document.head.appendChild(s);
  }, []);

  // clock
  useEffect(() => {
    const id = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(id);
  }, []);

  // ---- live flow feed: Public API (primary) -> cvserver (fallback) ----
  // Phase 5.3: tries /api/public/chain first (Public.com real-time option data);
  // falls back to /api/flowseeker/chain (cvserver day-aggregated) when unavailable.
  useEffect(() => {
    // Feeds the Smart Order Flow tab only — pausing it on the Scanner tab keeps
    // the browser's 6-per-host connection budget free for /scan (chain calls
    // run seconds-slow off-hours and starve the scanner's fetch queue).
    if (!active || tab === "scanner") return;
    let cancelled = false;
    const ctrl = new AbortController();
    const poll = async () => {
      // Path A: Public API chain (primary) — flat contract list with
      // volume/oi/iv/bid/ask/last. Filters: vol >= 100, vol/oi >= 0.4.
      let rows = null;
      let ds = null;                       // data_source: "public_api" | "cvserver"
      try {
        const d = await getJSON(
          `${API}/public/chain/${ticker}?expirations=4&fields=strike,type,expiration,volume,openInterest,impliedVolatility,bid,ask,lastPrice`,
          ctrl.signal,
        );
        if (cancelled) return;
        if (d?.ok && Array.isArray(d.contracts) && d.contracts.length > 0) {
          rows = mapPublicChainToRows(d.contracts, d.spot, ticker);
          ds = "public_api";
        }
      } catch { /* Public API unavailable — fall through to cvserver */ }
      // Path B: cvserver chain (fallback) — nested chain[].strikes[] shape.
      if (!rows) {
        try {
          const d = await getJSON(
            `${API}/chain/${ticker}?fields=oi,volume,iv,bid,ask,lastPrice`,
            ctrl.signal,
          );
          if (cancelled) return;
          const params = d.params || [];
          const vi = (name) => { const i = params.indexOf(name); return i > 0 ? i - 1 : -1; }; // vals skip strike
          const iVol = vi("volume"), iOI = vi("openInterest"), iIV = vi("impliedVolatility");
          const iBid = vi("bid"), iAsk = vi("ask"), iLast = vi("lastPrice");
          const cvRows = [];
          for (const exp of (d.chain || [])) {
            for (const s of (exp.strikes || [])) {
              const strike = s[0];
              for (const [sideU, vals] of [["CALL", s[1] || []], ["PUT", s[2] || []]]) {
                const vol = Number(vals[iVol]) || 0;
                if (vol < NOISE_FLOOR * 20) continue;
                const oi = Number(vals[iOI]) || 0;
                const voi = oi > 0 ? vol / oi : vol / 100;
                if (voi < 0.4) continue;
                const iv = Number(vals[iIV]) || 0;
                const last = Number(vals[iLast]) || 0;
                const bidV = Number(vals[iBid]) || 0;
                const askV = Number(vals[iAsk]) || 0;
                const mid = last || ((bidV + askV) / 2) || estPrice(strike, iv, exp.expiration);
                const premium = Math.round(vol * mid * 100);
                const dte = bizDTE(exp.expiration);
                const cls = premium >= 5e7 ? "block" : dte <= 2 ? "sweep" : "unusual";
                const side = (bidV > 0 && askV > 0 && last > 0) ? (last >= (bidV + askV) / 2 ? "ASK" : "BID") : "UNKNOWN";
                const p = {
                  ticker, type: sideU.toLowerCase(), classification: cls,
                  strike, expiration: exp.expiration, timestamp: Date.now(),
                  volume: vol, oi, vol_oi_ratio: voi, iv: iv < 1 ? iv * 100 : iv,
                  premium, mid, side, spot: null, otm: null,
                  bid: bidV > 0 ? bidV : null, ask: askV > 0 ? askV : null,
                  last: last > 0 ? last : null,
                };
                const cd = rowConviction(p);
                p._conv = cd.conv;
                p._cd = cd;
                cvRows.push(p);
              }
            }
          }
          cvRows.sort((a, b) => b.vol_oi_ratio - a.vol_oi_ratio);
          rows = cvRows.slice(0, 100);
          ds = "cvserver";
        } catch { /* both paths failed — keep last data */ }
      }
      if (rows) {
        setSignals(rows);
        setScanMeta((m) => ({ ...m, data_source: ds }));
      }
    };
    if (flowPaused) return () => { cancelled = true; ctrl.abort(); };
    poll();
    const id = setInterval(poll, 15000);
    return () => { cancelled = true; ctrl.abort(); clearInterval(id); };
  }, [active, ticker, tab, flowPaused, flowNonce]);

  // ---- cross-symbol market scan (Scanner tab, scenner34 grid) ----
  // Market-wide backend /scan endpoint (ONE cvforge screen, the whole market).
  // 100% live cvserver day-volume-vs-OI — no synthetic data.
  useEffect(() => {
    if (!active || tab !== "scanner") return;   // poll only while the Scanner tab is visible
    let cancelled = false;
    let inFlight = false;                        // a slow poll must not overlap a newer one
    const ctrl = new AbortController();
    const run = async () => {
      if (inFlight) return;
      inFlight = true;
      try { await runOnce(); } finally { inFlight = false; }
    };
    const runOnce = async () => {
      // Shared ingest for BOTH scan sources (identical 10 columns).
      const ingestPayload = (d) => {
        const regimes = { ...(d.regimes || {}) };
        // Dealer-regime fill (paid path only): the heatmap regime wins when
        // present; paid gamma walls cover tickers the heatmap cache hasn't
        // seen — same merge the server alert pipeline applies.
        for (const [t, dd] of Object.entries(d.dealer || {})) {
          if (!regimes[t] && dd && (dd.regime === "negative" || dd.regime === "positive")) regimes[t] = dd.regime;
        }
        // Quote-truth extras (paid path only), keyed by contract identity.
        const truth = d.quote_truth || {};
        const prevOI = d.prev_oi || {};
        // ΔOI hygiene tags (server: services/oi_hygiene.py) — keyed by OCC
        // ticker here; expired-today contracts are nulled locally as a
        // fallback when the server predates the tag payload.
        const oiTags = d.oi_tags || {};
        const occTag = (occ) => {
          const t = oiTags[occ];
          if (t) return t;
          const m = typeof occ === "string" && occ.match(/(\d{6})[CP]\d+$/);
          if (m) {
            const ey = 2000 + parseInt(m[1].slice(0, 2), 10);
            const exp = `${ey}-${m[1].slice(2, 4)}-${m[1].slice(4, 6)}`;
            const today = new Date().toISOString().slice(0, 10);
            if (exp <= today) return { expiring: true, rollover: false, earnings: null };
          }
          return null;
        };
        const rows = d.rows.map((r) => {
          const row = mkScanRow(r[0], r[2], r[3], r[4], Number(r[5]) || 0, Number(r[6]) || 0,
            r[7], r[8], Number(r[9]) || null, regimes[r[0]] || null);
          // OCC/OSI contract id rides along for click-to-trade (Alpaca paper
          // needs the exact contract; never synthesized client-side).
          row.osi = typeof r[1] === "string" && r[1] ? r[1] : null;
          // Paid quote truth: true premium replaces the BS estimate for
          // the PRIME/WHALE money gates; NBBO side + velocity ride along
          // for display and future sorting (never fabricated when absent).
          const xt = truth[`${row.under}|${row.type}|${row.strike}|${row.exp}`];
          if (xt) {
            if (xt.premium_true != null && xt.premium_true > 0) row.premium = xt.premium_true;
            if (xt.nbbo_side === "ASK" || xt.nbbo_side === "BID") row.nbbo = xt.nbbo_side;
            if (xt.signed_side === "ASK" || xt.signed_side === "BID") {
              row.signedSide = xt.signed_side;
              if (xt.sign_method === "quote" || xt.sign_method === "tick") row.signMethod = xt.sign_method;
            }
            if (xt.velocity_per_min != null) row.velocity = xt.velocity_per_min;
          }
          // Join yesterday's OI for this exact contract (OCC ticker r[1]).
          const tag = occTag(r[1]);
          row.oiTag = tag || null;   // surface hygiene state even when ΔOI is nulled
          row.oiChg = (tag && (tag.expiring || tag.rollover))
            ? null
            : oiChange(row.oi, prevOI[r[1]]);
          if (row.oiChg && tag) row.oiChg.tag = tag;   // engine + UI consume
          row.oiChgPct = row.oiChg ? row.oiChg.pct : null;   // sortable scalar
          return row;
        });
        const marked = markNew(rows, prevKeysRef, d.source === "public-scan" ? "public" : "market");
        firstSeenRef.current = annotateFirstSeen(marked, firstSeenRef.current).seen;
        try { localStorage.setItem(FIRSTSEEN_KEY, JSON.stringify(firstSeenRef.current)); } catch { /* private mode */ }
        ingestAlerts(marked, d.source === "public-scan" ? "public" : "market");
        setScan(marked);
        const nSyms = new Set(rows.map((x) => x.under)).size;
        if (d.baselines) setBaselines(d.baselines);
        setScanMeta({ mode: "market", stale: !!d.stale, symbols: nSyms,
          age: d.cache_age_seconds ?? 0, retry: d.retry_after_seconds ?? null,
          ttl: d.scan_ttl ?? 60, budget: d.budget ?? null, data_source: d.source === "public-scan" ? "public" : "cvserver", coverage: d.coverage || null });
        noteSourceFlip("market", nSyms);
        setScanAt(new Date().toLocaleTimeString());
        return;   // a 200 with rows[] is authoritative — even when empty
      };
      // Path P (primary, paid): Public universe scan — same 10 columns as
      // /scan plus quote_truth extras (true premium, NBBO side, velocity)
      // and dealer walls, joined below. Falls through to cvserver on ANY
      // failure: the paid feed is primary, cvserver is strict failover.
      try {
        const d = await getJSON(`${API}/scan-public?slice_size=8`, ctrl.signal);
        if (cancelled) return;
        if (d && Array.isArray(d.rows)) { ingestPayload(d); return; }
      } catch (e) {
        if (cancelled || e?.name === "AbortError") return;
        // fall through to the cvserver failover path
      }
      // Path C (failover): cvserver market-wide screen (columns:
      // underlying,ticker,type, strike,exp,day_volume,oi,iv,delta,spot)
      // + per-ticker regimes map.
      try {
        const d = await getJSON(`${API}/scan?limit=500`, ctrl.signal);
        if (cancelled) return;
        if (d && Array.isArray(d.rows)) {
          ingestPayload(d);
          return;   // a 200 with rows[] is authoritative — even when empty
        }
      } catch (e) {
        if (cancelled || e?.name === "AbortError") return;
        // BOTH scan sources failed (paid budget spent AND cvserver
        // rate-limited): keep the last good data stale-marked. The paid
        // path is primary, cvserver is strict failover — there is no
        // client-side chain sweep (it used to burn the hourly budget).
        if (hadDataRef.current) {
          setScanMeta((m) => ({ ...m, stale: true }));
        } else {
          setScanMeta((m) => ({ ...m, err: true }));
        }
      }
    };
    run();
    // Data refreshes on the backend's budgeted cadence (~4 min); a 60s poll
    // re-serves that cache — snappy enough, and free.
    const id = pollMs > 0 ? setInterval(run, Math.max(5000, pollMs)) : null;
    return () => { cancelled = true; ctrl.abort(); if (id) clearInterval(id); };
  }, [active, tab, refreshTick, pollMs]);

  // Conviction v3 sidecar data: backend-ranked feed, calibration report,
  // closed-trade journal stats. Silent-fail — the desk works without them.
  useEffect(() => {
    if (!active) return;
    let alive = true;
    fetch(`${API}/alerts/feed?days=2&sort_by=conviction`).then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!alive) return; setConvFeed(d?.alerts || []); setConvFeedState(d ? "ready" : "unavailable"); })
      .catch(() => { if (alive) setConvFeedState("unavailable"); });
    fetch(`${API}/alerts/quality`).then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive && d) setCalibBands(d.conviction_calibration || []); }).catch(() => {});
    fetch(`${API}/journal/stats?days=90`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive && d) setSetupStats(d); }).catch(() => {});
    return () => { alive = false; };
  }, [active, refreshTick]);


  // ---- daily volume history (sparklines + persistence streaks) ----
  // Mongo-only on the backend (no upstream call) and it changes once a day —
  // one fetch per Scanner-tab visit plus a slow 15-min re-poll is plenty.
  useEffect(() => {
    if (!active || tab !== "scanner") return;
    let cancelled = false;
    const ctrl = new AbortController();
    const load = async () => {
      try {
        const d = await getJSON(`${API}/scan/history?days=14`, ctrl.signal);
        // Ignore empty payloads — a transient Mongo hiccup must not wipe the
        // good history (and with it flames/sparklines) until the next 15-min poll.
        if (!cancelled && d && d.tickers && Object.keys(d.tickers).length) setHistory(d.tickers);
      } catch { /* endpoint missing/cold — sparklines and streaks just stay empty */ }
    };
    load();
    const id = setInterval(load, 15 * 60e3);
    return () => { cancelled = true; ctrl.abort(); clearInterval(id); };
  }, [active, tab]);

  // ---- per-ticker regime pill (only live microstructure left) ----
  // OFI / GEX charts, VPIN, λ removed 2026-09-05 (Nav directive): the
  // endpoints don't exist (.catch null loops every 6s) and the subtab
  // charts rendered empty. Regime drives the topbar pill — that stays.
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    const load = async () => {
      const reg = await getJSON(`${API}/regime/${ticker}`, ctrl.signal).catch(() => null);
      if (cancelled) return;
      const st = String(reg?.current_state || "").toLowerCase();
      const cls = st.includes("trend") || st.includes("bull") ? "up"
        : st.includes("mean") || st.includes("bear") || st.includes("rever") ? "down" : "chop";
      setRegime({ label: reg?.current_state ? `${reg.current_state}${reg.is_warming ? " (warming)" : ""}` : "—", cls });
    };
    load();
    const id = setInterval(load, 6000);
    return () => { cancelled = true; ctrl.abort(); clearInterval(id); };
  }, [ticker, active]);

  // auto-select first signal only (don't steal user clicks)
  useEffect(() => {
    if (!selected && signals.length) selectSignal(signals[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signals]);

  // Left-panel predicate shared by the snapshot list AND the Pulse buffer —
  // one definition so the two views can never disagree on what "filtered" means.
  const leftPass = useCallback((s) => {
    const side = String(s.type || "").toLowerCase().startsWith("c") ? "CALL" : "PUT";
    const cls = String(s.classification || "").toUpperCase();
    const dte = Number(bizDTE(s.expiration)) || 0;
    // DTE preset filter (applied first — narrows the time window)
    switch (dteFilter) {
      case "0dte": if (dte !== 0) return false; break;
      case "1-7d": if (dte < 1 || dte > 7) return false; break;
      case "weekly": if (dte < 1 || dte > 7) return false; break;
      case "monthly": if (dte < 8 || dte > 35) return false; break;
      case "qtrly": if (dte < 36 || dte > 90) return false; break;
      case "leaps": if (dte < 91) return false; break;
      default: break;   // "all" — no DTE filter
    }
    // Classification filter (type/conviction/side)
    switch (filter) {
      case "CALL": return side === "CALL";
      case "PUT": return side === "PUT";
      case "SWEEP": return cls === "SWEEP";
      case "BLOCK": return cls === "BLOCK";
      case "ASK": return String(s.side || "").toUpperCase() === "ASK";
      case "BID": return String(s.side || "").toUpperCase() === "BID";
      case "high": return s._conv >= 80;
      default: break;
    }
    // W6 depth gates: equity scope, signed moneyness, OPEX week, strike range.
    if (equity !== "all" && equityType(s.ticker) !== equity) return false;
    const sotm = signedOtm(s.type, s.strike, s.spot);
    if (money === "OTM" && !(sotm != null && sotm > 0)) return false;
    if (money === "ITM" && !(sotm != null && sotm < 0)) return false;
    if (opexOnly && !isOpexDay(s.expiration)) return false;
    if (strikeMin !== "" && Number(s.strike) < Number(strikeMin)) return false;
    if (strikeMax !== "" && Number(s.strike) > Number(strikeMax)) return false;
    return true;
  }, [filter, dteFilter, equity, money, opexOnly, strikeMin, strikeMax]);

  const filtered = useMemo(() => signals.filter(leftPass), [signals, leftPass]);

  // Trailing-90s print buffer: each poll REPLACES signals, so aggregating the
  // snapshot alone can never show N>1. The buffer keeps every fresh print and
  // expires anything older than the Pulse window (cap 500 for memory).
  // WeakSet dedupes StrictMode double-effect replays of the same objects.
  const printBufferRef = useRef([]);
  const seenPrintsRef = useRef(new WeakSet());
  const prevVolRef = useRef(new Map()); // contract key -> last-seen day volume (burst math)
  const prevMidRef = useRef(new Map()); // contract key -> last-seen mid (drift read)
  const midRingRef = useRef(new Map()); // contract key -> capped mid ring (Roll cost)
  const [pulseTick, setPulseTick] = useState(0);
  useEffect(() => {
    if (!signals.length) return;
    const now = Date.now();
    let buf = pruneBuffer(printBufferRef.current, 90e3, now);
    const fresh = [];
    for (const s of signals) {
      if (seenPrintsRef.current.has(s)) continue;
      seenPrintsRef.current.add(s);
      fresh.push(s);
      buf.push(s);
    }
    // Per-poll snapshot stamping on fresh objects only (StrictMode-safe).
    stampPollDeltas(fresh, prevVolRef.current, prevMidRef.current);
    // Session mid rings for the pooled Roll bucket (cap 60 ≈ 15 min).
    for (const s of fresh) {
      const m = Number(s.mid);
      if (Number.isFinite(m) && m > 0) {
        const key = contractKey(s);
        midRingRef.current.set(key, pushCapped(midRingRef.current.get(key), m, 60));
      }
    }
    // Strategy-leg fingerprints over the full snapshot leg set (heuristic).
    try { flagSpreadLegs(signals); } catch { /* never break the tape */ }
    if (prevVolRef.current.size > 2000) {
      const keep = new Set(buf.map((r) => contractKey(r)));
      for (const k of [...prevVolRef.current.keys()]) if (!keep.has(k)) prevVolRef.current.delete(k);
      for (const k of [...prevMidRef.current.keys()]) if (!keep.has(k)) prevMidRef.current.delete(k);
      for (const k of [...midRingRef.current.keys()]) if (!keep.has(k)) midRingRef.current.delete(k);
    }
    printBufferRef.current = buf.slice(-500);
    setPulseTick((t) => t + 1);
  }, [signals]);

  // Pulse tape: trailing-90s buffer, left filters + BladeMap gates. One row
  // per contract — ticker scope + DTE band + min score gate, ranked by
  // aggregated premium.
  const pulseRows = useMemo(() => {
    const now = Date.now();
    const gated = pruneBuffer(printBufferRef.current, 90e3, now).filter((s) => {
      if (!leftPass(s)) return false;
      if (pulseTicker !== "ALL" && s.ticker !== pulseTicker) return false;
      const dte = Number(bizDTE(s.expiration)) || 0;
      // Exclusive bands (2026-09-05): each preset is a disjoint slice.
      if (pulseDte === "0D" && dte !== 0) return false;
      else if (pulseDte === "1-7D" && (dte < 1 || dte > 7)) return false;
      else if (pulseDte === "8-21D" && (dte < 8 || dte > 21)) return false;
      else if (pulseDte === "22-45D" && (dte < 22 || dte > 45)) return false;
      else if (pulseDte === "45D+" && dte <= 45) return false;
      if (pulseScore > 0 && pulseScore10(s._conv) < pulseScore) return false;
      return true;
    });
    return aggregatePulse(gated, 90e3, now);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pulseTick, leftPass, pulseTicker, pulseDte, pulseScore]);

  // Overview bar rollup over the visible 90s tape (Phase 9 W1 tracer).
  const pulseOv = useMemo(() => overviewStats(pulseRows), [pulseRows]);
  // Pin-risk readout for the single-ticker tape (SHIP-1; multi-ticker ALL
  // has no single expiry to pin to — metric hidden, not averaged).
  const pinRead = useMemo(
    () => (pulseTicker === "ALL" ? null : nearestExpiryPin(pulseRows, pulseTicker)),
    [pulseRows, pulseTicker]
  );
  // Pooled Roll cost over the pin expiry bucket (needs 30 deltas; the poll
  // tick in deps re-runs the memo as rings fill — refs mutate in place).
  const costRead = useMemo(() => {
    if (!pinRead || !pinRead.eligible || !pinRead.exp) return null;
    const rings = [];
    for (const [k, ring] of midRingRef.current) {
      const parts = String(k).split("|");
      if (parts.length === 4 && parts[0].toUpperCase() === String(pulseTicker).toUpperCase() && parts[3] === pinRead.exp) {
        rings.push(ring);
      }
    }
    return rings.length ? rollPooled(rings) : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pulseRows, pulseTick, pulseTicker, pinRead]);

  // scanner: filter + sort + KPI rollup. Simple mode ignores the hidden
  // advanced knobs (a Min-Vol set weeks ago must not silently filter an
  // interface with no visible controls). The universe is fully open — no
  // priority gate, no allowlist: quality gates (SCORE ≥92 / DTE / side /
  // search) do the filtering, not a ticker list.
  // Side + DTE-preset + Min-Prem~/Min-OI apply in BOTH modes (side and DTE
  // are visible controls; the number inputs are advanced-only).
  const scanRows = useMemo(() => {
    const q = (scanQ || "").trim().toUpperCase();
    const dteIn = (r, preset) => {
      const d = r.dte;
      switch (preset) {
        case "0dte": return d === 0;
        case "1-7d": return d >= 1 && d <= 7;
        case "weekly": return d >= 1 && d <= 7;
        case "monthly": return d >= 8 && d <= 35;
        case "qtrly": return d >= 36 && d <= 90;
        case "leaps": return d >= 91;
        default: return true;
      }
    };
    const rows = scan.filter((r) => {
      if (scanSideF !== "all" && r.type !== scanSideF) return false;
      if (!dteIn(r, scanDteF)) return false;
      if (advanced) {
        if (scanTypeF !== "all" && r.type !== scanTypeF) return false;
        if (scanMinVol && r.vol < scanMinVol) return false;
        if (scanMinPrem && (r.premium ?? 0) < scanMinPrem) return false;
        if (scanMinOI && (r.oi ?? 0) < scanMinOI) return false;
        if (scanMinScore && r.score < scanMinScore) return false;
      } else {
        if (scanMinPrem && (r.premium ?? 0) < scanMinPrem) return false;
      }
      if (q && !(r.under || "").toUpperCase().includes(q)) return false;
      // Zenith control-cluster quick filters
      if (minScoreQF > 0 && (r.score ?? 0) < minScoreQF) return false;
      if (dteRange[0] != null && bizDTE(r.exp) != null && bizDTE(r.exp) < dteRange[0]) return false;
      if (dteRange[1] != null && bizDTE(r.exp) != null && bizDTE(r.exp) > dteRange[1]) return false;
      return true;
    });
    const k = scanSort.key, dir = scanSort.dir === "desc" ? -1 : 1;
    rows.sort((a, b) => {
      let av = a[k], bv = b[k];
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      av = av == null ? -Infinity : av; bv = bv == null ? -Infinity : bv;
      return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
    });
    return rows;
  }, [scan, scanSideF, scanDteF, scanTypeF, scanMinVol, scanMinPrem, scanMinOI, scanMinScore, scanQ, scanSort, advanced, minScoreQF, dteRange]);
  // Keyboard nav (scanner tab only, ignored while typing in an input)
  useEffect(() => {
    if (!active || tab !== "scanner") return;
    const onKey = (e) => {
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA")) {
        if (e.key === "Escape") t.blur();
        return;
      }
      if (e.key === "/") { e.preventDefault(); scanQRef.current && scanQRef.current.focus(); return; }
      if (e.key === "r" || e.key === "R") { forceRefresh(); return; }
      const n = scanRows.length;
      if (!n) return;
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setKbIdx((k) => Math.min(n - 1, k + 1)); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setKbIdx((k) => Math.max(0, k - 1)); }
      else if (e.key === "g") { e.preventDefault(); setKbIdx(0); }
      else if (e.key === "G") { e.preventDefault(); setKbIdx(n - 1); }
      else if (e.key === "Enter" && kbIdx >= 0 && scanRows[kbIdx]) {
        setTicker(scanRows[kbIdx].under); setTab("flow");
      } else if (e.key === "Escape") { setKbIdx(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, tab, scanRows, kbIdx, forceRefresh]);


  const scanStats = useMemo(() => {
    let notl = 0, cv = 0, pv = 0, unusual = 0, alerts = 0; const cnt = {};
    for (const r of scanRows) {
      notl += r.notional;
      if (r.type === "call") cv += r.vol; else pv += r.vol;
      if (r.volOI >= 2) unusual++;
      if (r._new && r.score >= alertScore) alerts++;
      cnt[r.under] = (cnt[r.under] || 0) + 1;
    }
    let top = "—", best = 0;
    for (const u of Object.keys(cnt)) if (cnt[u] > best) { best = cnt[u]; top = u; }
    const tv = cv + pv, cpct = tv > 0 ? Math.round((cv / tv) * 100) : 0;
    return { notl, cpct, tv, unusual, alerts, top, best };
  }, [scanRows, alertScore]);

  const sortScan = (k) => setScanSort((s) => (s.key === k
    ? { key: k, dir: s.dir === "desc" ? "asc" : "desc" }
    : { key: k, dir: (k === "under" || k === "type" || k === "ftype") ? "asc" : "desc" }));

  // Premium concentration across the FULL scan (not the filtered view) so the
  // chips stay stable while a chip-click filters the table below them.
  const rollup = useMemo(() => tickerRollup(scan, 8), [scan]);

  // Alert tape summary: per-rule counts + session window (log is newest-first).
  const alertSummary = useMemo(() => {
    const c = {};
    for (const a of alertLog) c[a.rule] = (c[a.rule] || 0) + 1;
    const newest = alertLog.length ? alertLog[0].time : null;
    const oldest = alertLog.length ? alertLog[alertLog.length - 1].time : null;
    return { c, newest, oldest };
  }, [alertLog]);
  // Institutional Heartbeat tier — drives the colored dot + label in the
  // scanbar's Heartbeat chip. Pure helper delegates the precedence rules so
  // the JSX never repeats them; same call backs the title-tooltip.
  const heartbeat = useMemo(() => {
    const hb = pulseState({
      mode: scanMeta.mode, stale: !!scanMeta.stale,
      age: scanMeta.age || 0, retry: scanMeta.retry,
      hasData: scan.length > 0, hasError: !!scanMeta.err,
      ttl: scanMeta.ttl || 60,
    });
    // Budget context on the tooltip — an institutional desk knows its data
    // cadence: X of the plan's hourly cvforge calls spent, next scan ETA.
    const b = scanMeta.budget;
    const next = scanMeta.ttl ? Math.max(0, scanMeta.ttl - (scanMeta.age || 0)) : null;
    hb.hint = `${hb.hint}${next != null ? ` · next scan ~${elapsedClock(next)}` : ""}${b ? ` · ${b.used}/${b.hourly_cap} cvforge calls this hour` : ""}`;
    return hb;
  }, [scanMeta, scan.length]);
  // FOLLOW Leaderboard — the "what are they following" read. Pure helper
  // sorts + clips the streaks map; the JSX renders the result.
  const followStrip = useMemo(() => formatFOLLOWStrip(streaks, { top: 6 }), [streaks]);
  const shownAlerts = useMemo(() => {
    const a = alertOrder === "old" ? [...alertLog].reverse() : alertLog;
    return a.slice(0, 60);
  }, [alertLog, alertOrder]);

  // FIRE Banner — the "definite alert" tier that demands attention. Pure
  // helpers tierOf + selectFires + pickBanner keep the precedence Jest-testable.
  // The banner shows ONE high-tier alert (OICONF / WHALE / FOLLOW≥3d / SIGMA≥5σ
  // / SCORE≥90). User acknowledges OR auto-dismisses 60s after fire.
  const [ackedKeys, setAckedKeys] = useState(() => new Set());
  const ackFire = useCallback((k) => setAckedKeys((m) => { const n = new Set(m); n.add(k); return n; }), []);
  const fires = useMemo(() => selectFires(alertLog, {
    now: Date.now(), ttlMs: 60_000,
    minScoreForFire: alertScore,
    enabled: alertRules,
    allow: null,
    acked: ackedKeys,
  }), [alertLog, alertScore, alertRules, ackedKeys]);
  const fireBanner = useMemo(() => pickBanner(fires), [fires]);
  useEffect(() => {
    if (!fireBanner) return;
    const tid = setTimeout(() => ackFire(fireBanner.key), 60_000);
    return () => clearTimeout(tid);
  }, [fireBanner, ackFire]);


  const SCAN_COLS = [
    ["firstSeen", "Seen", false], ["score", "Score", false], ["under", "Ticker", true], ["type", "C/P", true],
    ["strike", "Strike", false], ["dte", "DTE", false], ["vol", "Volume", false],
    ["oi", "OI", false], ["oiChgPct", "ΔOI", false], ["volOI", "Vol/OI", false], ["premium", "Prem~", false],
    ["notional", "Notional", false],
    ["iv", "IV", false], ["ftype", "Flow", true], ["lean", "Lean", true],
    ["trend", "Trd", false],
  ];
  // Simple mode: the columns a decision needs, nothing else.
  const SIMPLE_KEYS = ["firstSeen", "score", "under", "type", "strike", "dte", "vol", "oiChgPct", "premium", "ftype"];
  const colsShown = advanced ? SCAN_COLS : SCAN_COLS.filter(([k]) => SIMPLE_KEYS.includes(k));

  function selectSignal(p) {
    setSelected(p);
    if (p?.ticker && p.ticker !== ticker) setTicker(p.ticker);
    requestAnimationFrame(() => { drawGauge(p); drawRadar(p); });
  }

  // ---------- charts ----------
  const P = useCallback(() => window.Plotly, []);
  function drawGauge(p) {
    if (!P() || !gaugeRef.current || !p) return;
    const c = p._conv != null ? p._conv : (p._cd ? p._cd.conv : 50);
    const col = c >= 85 ? PL.green : c >= 70 ? PL.blue : c >= 55 ? PL.amber : PL.red;
    P().react(gaugeRef.current, [{
      type: "indicator", mode: "gauge+number", value: c,
      number: { font: { color: "#e6e8ee", size: 30, family: PL.font } },
      gauge: { axis: { range: [0, 100], tickcolor: PL.axis, tickfont: { color: PL.muted, size: 9 } },
        bar: { color: col, thickness: 0.25 }, bgcolor: "rgba(0,0,0,0)", borderwidth: 0,
        steps: [{ range: [0, 55], color: "rgba(255,77,94,0.10)" }, { range: [55, 70], color: "rgba(245,176,66,0.10)" },
          { range: [70, 85], color: "rgba(41,197,224,0.10)" }, { range: [85, 100], color: "rgba(25,210,124,0.10)" }],
        threshold: { line: { color: "#e6e8ee", width: 2 }, thickness: 0.75, value: c } },
    }], { paper_bgcolor: PL.paper, margin: { l: 8, r: 8, t: 14, b: 8 }, height: 190, font: { color: PL.text, family: PL.font } },
    { displayModeBar: false, responsive: true });
  }
  function drawRadar(p) {
    if (!P() || !radarRef.current || !p) return;
    const d = p._cd || { stat: 0, pat: 0, size: 0, urg: 0 };
    const cats = ["Unusualness", "Pattern", "Size", "Urgency"];
    P().react(radarRef.current, [{
      type: "scatterpolar", r: [d.stat, d.pat, d.size, d.urg, d.stat],
      theta: cats.concat([cats[0]]), fill: "toself", fillcolor: "rgba(41,197,224,0.18)",
      line: { color: PL.blue, width: 2 }, marker: { color: PL.blue, size: 4 },
    }], { paper_bgcolor: PL.paper, polar: { bgcolor: "rgba(0,0,0,0)",
        radialaxis: { range: [0, 30], tickfont: { color: PL.muted, size: 8 }, gridcolor: PL.grid, linecolor: PL.axis },
        angularaxis: { tickfont: { color: PL.text, size: 9 }, gridcolor: PL.grid, linecolor: PL.axis } },
      margin: { l: 34, r: 34, t: 12, b: 12 }, height: 190, showlegend: false, font: { family: PL.font } },
    { displayModeBar: false, responsive: true });
  }
  // redraw conviction charts when tab/plotly changes
  useEffect(() => {
    if (!plotlyReady) return;
    if (tab === "flow" && selected) { drawGauge(selected); drawRadar(selected); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, plotlyReady]);

  const sideOf = (p) => (String(p.type || "").toLowerCase().startsWith("c") ? "CALL" : "PUT");
  const typeOf = (p) => String(p.classification || "reg").toUpperCase();

  // ---------- render ----------
  // Focused on institutional smart order flow + cross-symbol scanner.
  // WTI Crude, Stat-Arb Pairs, and Dealer Positioning tabs removed
  // 2026-09-04 (Nav directive: failed experiments). Scanner is the hero.
  const TABS = [
    ["flow", "Smart Order Flow"],
    ["scanner", "Scanner"],
  ];
  return (
    <div className="fsb-root">
      <div className="fsb-topbar">
        <div className="fsb-brand">
          <span className="fsb-logo">◢</span>
          <span className="fsb-brand-name">Tidehunter <span className="fsb-pro">Pro</span></span>
        </div>
        <div className="fsb-tabs">
          {TABS.map(([id, label]) => (
            <button key={id} className={`fsb-tab${tab === id ? " active" : ""}`} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>
        <div className="fsb-meta">
          <span className={`fsb-regime-pill ${regime.cls}`}>{regime.label}</span>
          <span>{clock}</span>
          <button type="button" className="fsb-ctrl" title="Refresh now"
                  onClick={forceRefresh} disabled={forcing}>
            {forcing ? "…" : "↻"}
          </button>
          <div className="fsb-ctrl-wrap">
            <button type="button"
                    className={`fsb-ctrl${(minScoreQF > 0 || dteRange[0] != null || dteRange[1] != null) ? " fsb-ctrl-active" : ""}`}
                    title="Quick filters"
                    onClick={() => { setShowQuickFilters((v) => !v); setShowSettings(false); }}>
              ⧩
            </button>
            {showQuickFilters && (
              <div className="fsb-pop">
                <div className="fsb-pop-title">Quick filters</div>
                <label className="fsb-pop-row">
                  <span>Min score</span>
                  <input type="range" min="0" max="95" step="5" value={minScoreQF}
                         onChange={(e) => setMinScoreQF(Number(e.target.value))} />
                  <b>{minScoreQF || "off"}</b>
                </label>
                <label className="fsb-pop-row">
                  <span>DTE min</span>
                  <input type="number" min="0" style={{ width: 56 }}
                         value={dteRange[0] ?? ""}
                         onChange={(e) => setDteRange([e.target.value === "" ? null : Number(e.target.value), dteRange[1]])} />
                </label>
                <label className="fsb-pop-row">
                  <span>DTE max</span>
                  <input type="number" min="0" style={{ width: 56 }}
                         value={dteRange[1] ?? ""}
                         onChange={(e) => setDteRange([dteRange[0], e.target.value === "" ? null : Number(e.target.value)])} />
                </label>
                <button type="button" className="fsb-pop-clear"
                        onClick={() => { setMinScoreQF(0); setDteRange([null, null]); }}>
                  Clear
                </button>
              </div>
            )}
          </div>
          <div className="fsb-ctrl-wrap">
            <button type="button" className={`fsb-ctrl${pollMs !== 60000 ? " fsb-ctrl-active" : ""}`}
                    title="Settings"
                    onClick={() => { setShowSettings((v) => !v); setShowQuickFilters(false); }}>
              ⚙
            </button>
            {showSettings && (
              <div className="fsb-pop">
                <div className="fsb-pop-title">Display</div>
                <label className="fsb-pop-row">
                  <span>Poll interval</span>
                  <select value={pollMs}
                          onChange={(e) => setPollMs(Number(e.target.value))}>
                    <option value={5000}>5s</option>
                    <option value={15000}>15s</option>
                    <option value={30000}>30s</option>
                    <option value={60000}>60s</option>
                    <option value={0}>Off</option>
                  </select>
                </label>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="fsb-body">
        {/* FLOW VIEW */}
        <div className={`fsb-view fsb-view-flow${tab === "flow" ? " active" : ""}`}>
          {/* left */}
          <div className="fsb-col">
            <div className="fsb-panel">
              <div className="fsb-panel-h">Filters</div>
              <div className="fsb-chips">
                {[["all", "All"], ["CALL", "Calls"], ["PUT", "Puts"], ["SWEEP", "Sweep"], ["BLOCK", "Block"], ["ASK", "Ask"], ["BID", "Bid"], ["high", "≥80"]].map(([v, l]) => (
                  <button key={v} className={`fsb-chip${filter === v ? " active" : ""}`} onClick={() => setFilter(v)} title={FILTER_CHIP_TITLES[v]}>{l}</button>
                ))}
              </div>
              <div className="fsb-panel-h fsb-panel-h-sm" style={{ marginTop: 8 }}>Equity</div>
              <div className="fsb-chips">
                {[["all", "All"], ["STOCK", "Stocks"], ["ETF", "ETFs"], ["INDEX", "Index"]].map(([v, l]) => (
                  <button key={v} className={`fsb-chip fsb-chip-sm${equity === v ? " active" : ""}`} onClick={() => setEquity(v)} title={v === "all" ? "Whole market" : v === "STOCK" ? "Single names only (macro ETF flow excluded)" : v === "ETF" ? "ETF/index-product flow only" : "Index options only"}>{l}</button>
                ))}
              </div>
              <div className="fsb-panel-h fsb-panel-h-sm" style={{ marginTop: 8 }}>Moneyness</div>
              <div className="fsb-chips">
                {[["all", "All"], ["OTM", "OTM"], ["ITM", "ITM"]].map(([v, l]) => (
                  <button key={v} className={`fsb-chip fsb-chip-sm${money === v ? " active" : ""}`} onClick={() => setMoney(v)} title="From spot at print time; rows without spot are excluded when gated">{l}</button>
                ))}
                <button className={`fsb-chip fsb-chip-sm${opexOnly ? " active" : ""}`} onClick={() => setOpexOnly((o) => !o)} title="Only contracts expiring in the monthly OPEX week (third Friday)">OPEX</button>
              </div>
              <div className="fsb-panel-h fsb-panel-h-sm" style={{ marginTop: 8 }}>Strikes</div>
              <div className="fsb-chips">
                <input className="fsb-chip fsb-chip-sm" style={{ width: 64 }} type="number" placeholder="Min" value={strikeMin} onChange={(e) => setStrikeMin(e.target.value)} />
                <input className="fsb-chip fsb-chip-sm" style={{ width: 64 }} type="number" placeholder="Max" value={strikeMax} onChange={(e) => setStrikeMax(e.target.value)} />
              </div>
              <div className="fsb-panel-h fsb-panel-h-sm" style={{ marginTop: 8 }}>DTE</div>
              <div className="fsb-chips">
                {[["all", "All"], ["0dte", "0DTE"], ["1-7d", "1-7D"], ["weekly", "Wk"], ["monthly", "Mo"], ["qtrly", "Qtr"], ["leaps", "LEAPS"]].map(([v, l]) => (
                  <button key={v} className={`fsb-chip fsb-chip-sm${dteFilter === v ? " active" : ""}`} onClick={() => setDteFilter(v)}>{l}</button>
                ))}
              </div>
            </div>
            <div className="fsb-panel">
              <div className="fsb-panel-h">Legend</div>
              <div className="fsb-legend">
                <span><i className="fsb-dot call" /> Call flow</span>
                <span><i className="fsb-dot put" /> Put flow</span>
                <span><i className="fsb-dot sweep" /> Sweep (urgent)</span>
                <span><i className="fsb-dot block" /> Block (large print)</span>
                <span><i className="fsb-dot burst" /> 15s burst &gt; OI</span>
                <span><i className="fsb-dot voloi" /> Vol &gt; OI</span>
              </div>
            </div>
          </div>

          {/* center */}
          <div className="fsb-col">
            <div className="fsb-panel fsb-flow-panel">
              <div className="fsb-panel-h"><span>Live Options Flow</span><span><i className="fsb-live-dot" style={flowPaused ? { background: "#f5b042" } : undefined} /><span className="fsb-muted fsb-small">{flowPaused ? "PAUSED" : "LIVE"} · LAST UPDATED {clock || "—"} · SHOWING {pulseRows.length} PRINTS</span><button className="fsb-iconbtn" title="Refresh now" onClick={() => { setFlowPaused(false); setFlowNonce((n) => n + 1); }}>⟳</button><button className="fsb-iconbtn" title={flowPaused ? "Resume live polling" : "Pause live polling"} onClick={() => setFlowPaused((p) => !p)}>{flowPaused ? "▶" : "⏸"}</button></span></div>
              <div><button className="fsb-howto" onClick={() => setHowTo((h) => !h)}>ⓘ HOW TO READ</button></div>
              {howTo && <div className="fsb-howto-pop">SIDE = inferred print side (last vs mid, no tape — unknown when quotes are missing). SIGNAL follows SIDE: ASK→BULLISH, BID→BEARISH, calls and puts alike. BADGES: SILVER every row; GOLDEN ≥$900K rolled premium; WHALE ≥$1M (tape size tier — not the $25M alert rule). HEDGE? = put bought aggressively, often protection rather than direction. SCORE = conviction/10. PREM subline = 90s rolled premium (print count).</div>}
              <div className="fsb-pulsebar">
                <span className="fsb-ovbar" title="Session rollup over the visible 90s tape (direction = premium-flow proxy, not confirmed buys/sells)">
                  <span className={`fsb-pill ${pulseOv.lean === "Bullish" ? "fsb-sig-bullish" : pulseOv.lean === "Bearish" ? "fsb-sig-bearish" : "fsb-badge-silver"}`}>{pulseOv.lean}</span>
                  <span className="fsb-ovmetric" title="Bullish-leg premium minus bearish-leg premium">Net {pulseOv.netPrem < 0 ? "−" : "+"}{fmtUSD(pulseOv.netPrem)}</span>
                  <span className="fsb-ovmetric" title="Put premium / call premium">P/C {Number.isFinite(pulseOv.pc) ? pulseOv.pc.toFixed(2) : "—"}</span>
                  <span className="fsb-ovmetric" title="Flow imbalance ratio |bull-bear|/(bull+bear)">FIR {pulseOv.fir.toFixed(2)}</span>
                  <span className="fsb-ovmetric" title="Relative volume needs time-of-day baselines">RVOL needs baseline</span>
                  {pinRead ? (
                    <span className="fsb-ovmetric" title={pinRead.eligible ? `Expiry-day pin risk (${pinRead.exp}): distance to max-OI strike, top-3 OI concentration. Unsigned exposure — never direction.` : "Single names pin only on Fridays (weekly expirations); daily read available for SPX/SPY/QQQ/IWM."}>
                      {pinRead.eligible && pinRead.maxOiStrike != null
                        ? `PIN ${pinRead.maxOiStrike} · ${(pinRead.concentration * 100).toFixed(0)}%${pinRead.distPct != null ? ` · ${pinRead.distPct >= 0 ? "+" : ""}${pinRead.distPct.toFixed(1)}%` : ""}`
                        : "PIN Fri-only"}
                    </span>
                  ) : null}
                  {(() => { const cl = costLabel(costRead); return cl ? (
                    <>
                      <span className="fsb-ovmetric" title={cl.title}>
                        {cl.text}
                      </span>
                      <span className="fsb-muted fsb-small" title={COST_CAPTION_TITLE}>{cl.caption}</span>
                    </>
                  ) : null; })()}
                </span>
                <label className="fsb-muted fsb-small">Ticker&nbsp;
                  <input
                    className="fsb-ticker-input"
                    value={pulseQ}
                    onChange={(e) => setPulseQ(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") focusPulseTicker(); }}
                    placeholder="ANY"
                    aria-label="Focus any ticker"
                    data-testid="fsb-ticker-search"
                  />
                  <button className="fsb-chip fsb-chip-sm" onClick={focusPulseTicker} title="Focus tape on any ticker (open universe)">Go</button>
                  {pulseTicker !== "ALL" && (
                    <button className="fsb-chip fsb-chip-sm" onClick={() => { setPulseTicker("ALL"); setPulseQ(""); }} title="Back to all tickers">ALL</button>
                  )}
                </label>
                <span className="fsb-pulsebar-group"><span className="fsb-muted fsb-small">DTE</span>
                  {[["0D", "0D"], ["1-7D", "1-7D"], ["8-21D", "8-21D"], ["22-45D", "22-45D"], ["45D+", "45D+"], ["ALL", "ALL"]].map(([v, l]) => (
                    <button key={v} className={`fsb-chip fsb-chip-sm${pulseDte === v ? " active" : ""}`} onClick={() => setPulseDte(v)}>{l}</button>
                  ))}
                </span>
                <span className="fsb-pulsebar-group"><span className="fsb-muted fsb-small">SCORE</span>
                  {[[0, "ALL"], [3, "3+"], [5, "5+"], [7, "7+"]].map(([v, l]) => (
                    <button key={l} className={`fsb-chip fsb-chip-sm${pulseScore === v ? " active" : ""}`} onClick={() => setPulseScore(v)}>{l}</button>
                  ))}
                </span>
              </div>
              <div className="fsb-scanbar" data-testid="flow-kpi-strip">
                {[
                  ["Feed", pulseTicker === "ALL" ? `ALL · ${ticker}` : pulseTicker, ""],
                  ["Prints", String(pulseRows.length), "b"],
                  ["Net", `${pulseOv.netPrem < 0 ? "−" : "+"}${fmtUSD(pulseOv.netPrem)}`, pulseOv.lean === "Bullish" ? "g" : pulseOv.lean === "Bearish" ? "r" : ""],
                  ["P/C", Number.isFinite(pulseOv.pc) ? pulseOv.pc.toFixed(2) : "—", ""],
                  ["FIR", pulseOv.fir.toFixed(2), ""],
                  ["Source", scanMeta.data_source === "public" ? "LIVE · public" : scanMeta.data_source === "public_api" ? "LIVE · public" : scanMeta.data_source === "cvserver" ? "LIVE · cvserver" : flowPaused ? "PAUSED" : "—", scanMeta.data_source ? "g" : "y"],
                  ["Updated", clock || "—", ""],
                ].map(([l, v, c]) => (
                  <div key={l} className="fsb-skpi"><div className="fsb-skl">{l}</div><div className={`fsb-skv ${c}`}>{v}</div></div>
                ))}
              </div>
              <div className="fsb-flow-wrap">
                <table className="fsb-table fsb-pulse">
                  <thead><tr>
                    <th title="Local time of the latest print in the 90s window">FLOW ET</th><th>SYM</th><th className="num">STRIKE</th><th>C/P</th><th className="num" title="Absolute distance of strike from spot at print time">OTM</th><th>EXP</th><th className="num" title="Trading days to expiry">DTE</th><th className="num" title="Price paid per contract (last print; mid when last is missing)">FILL</th><th title="ASK = lifted the offer (aggressive buy); BID = hit the bid">SIDE</th><th title="Where last traded inside bid-ask: left = bid, right = ask">SPREAD</th><th title="Follows SIDE: ASK→BULLISH, BID→BEARISH">SIGNAL</th><th title="SILVER always; GOLDEN ≥$900K; WHALE ≥$1M rolled premium">BADGES</th><th className="num" title="Conviction mapped 0-10">SCORE</th><th className="num" title="Contracts in the 90s window">SIZE</th><th className="num" title="Rolled premium in the 90s window">PREM</th>
                  </tr></thead>
                  <tbody>
                    {pulseRows.length === 0 && <tr><td colSpan={15} className="fsb-muted" style={{ padding: 14, lineHeight: 1.7 }}>No prints for {pulseTicker === "ALL" ? ticker : pulseTicker} pass the Pulse gates (DTE {pulseDte} · score {pulseScore === 0 ? "ALL" : pulseScore + "+"}).{pulseTicker !== "ALL" && pulseTicker !== ticker ? ` Feed is on ${ticker} — type ${pulseTicker} above and hit Go, then wait one poll.` : " Thin name or market closed? Try SPY/QQQ, widen DTE, or check back at the open. Trailing-90s tape: Public API first, cvserver fallback, ranked by aggregated premium…"}</td></tr>}
                    {pulseRows.map((p, i) => {
                      const conv = p._conv;
                      const score = pulseScore10(conv);
                      const side = String(p.side || (String(p.type || "").toLowerCase().startsWith("c") ? "ASK" : "BID"));
                      const sig = pulseSignal(side);
                      const badges = pulseBadges(p._aggPrem ?? p.premium);
                      const cp = String(p.type || "").toLowerCase().startsWith("c") ? "CALL" : "PUT";
                      const pcls = String(p.classification || "").toUpperCase();
                      const flowIcon = pcls === "SWEEP" ? "⌁ " : pcls === "BLOCK" ? "◫ " : "";
                      const hl = highlightState({ volDelta: p._volDelta, volOI: p.vol_oi_ratio, oi: p.oi });
                      const price = Number(p.mid) || (Number(p.volume) > 0 ? (Number(p.premium) || 0) / (Number(p.volume) * 100) : 0);
                      const fill = Number(p.last) || 0;
                      const sp = spreadPosition(p.bid, p.ask, p.last);
                      const qs = quoteSkew(p.bid, p.ask, p._prevMid);
                      const driftArrow = qs.tag === "UP" ? "▲" : qs.tag === "DOWN" ? "▼" : "";
                      return (
                        <tr key={`${p.ticker}-${p.strike}-${String(p.expiration || "").slice(0, 10)}-${i}`} className={`${selected === p ? "selected" : ""}${hl === "BURST" ? " hl-burst" : hl === "VOL_OI" ? " hl-vol" : ""}`}
                            tabIndex={0} onClick={() => selectSignal(p)}
                            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSignal(p); } }}>
                          <td className="fsb-muted">{fmtClock(p._aggTs ?? p.timestamp, true)}</td>
                          <td className="tk" title={pcls === "SWEEP" || pcls === "BLOCK" ? flowClassTitle(pcls) : typeOf(p)}>{flowIcon}{p.ticker}</td>
                          <td className="num">{Number(p.strike).toFixed(0)}</td>
                          <td className={`fsb-type-${cp.toLowerCase()}`} title={p._strat ? `${p._strat} multi-leg fingerprint (heuristic: matched volumes, no exchange linkage)` : cp}>{p._strat ? "◈" : ""}{cp}</td>
                          <td className="num">{p.otm == null ? "—" : `+${Number(p.otm).toFixed(1)}%`}</td>
                          <td className="fsb-muted">{String(p.expiration || "").slice(0, 10)}</td>
                          <td className="num">{bizDTE(p.expiration)}</td>
                          <td className="num" title={driftArrow ? `Mid ${qs.tag === "UP" ? "up" : "down"} ${Math.abs(qs.driftBp).toFixed(0)}bp vs prior poll (dealer-pressure read, Ho-Stoll-lite)` : undefined}>{driftArrow}{fill > 0 ? fill.toFixed(2) : price > 0 ? price.toFixed(2) : "—"}</td>
                          <td><span className={`fsb-pill fsb-side-${side.toLowerCase()}`}>{side === "UNKNOWN" ? "—" : side}</span></td>
                          <td>{sp.state === "NO_QUOTE" ? <span className="fsb-muted fsb-small" title="No quote — bid/ask unavailable">no quote</span> : sp.state === "LOCKED" ? <span className="fsb-muted fsb-small" title="Locked/crossed spread — no fill">LOCKED</span> : <span className="fsb-spreadbar" title={`last at ${(sp.pos * 100).toFixed(0)}% of bid-ask spread${qs.relSpread != null ? ` · rel spread ${(qs.relSpread * 100).toFixed(2)}%` : ""}`}><span className="fsb-spreadmark" style={{ left: `${(sp.pos * 100).toFixed(1)}%` }} /></span>}</td>
                          <td><span className={`fsb-pill fsb-sig-${sig.toLowerCase()}`}>{sig === "UNKNOWN" ? "—" : sig}</span>{pulseHedge(p.type, side) && <span className="fsb-pill fsb-hedge" title="Put bought aggressively — often a hedge, not directional bullishness">HEDGE?</span>}</td>
                          <td>{badges.map((b) => <span key={b} className={`fsb-pill fsb-badge-${b.toLowerCase()}`} title={b === "WHALE" ? "Tape size tier: ≥$1M rolled premium in 90s — not the $25M alert rule" : b === "GOLDEN" ? "Premium ≥ $900K rolled in 90s" : "Baseline badge: every print starts here"}>{b}</span>)}</td>
                          <td className="num">{score.toFixed(1)}</td>
                          <td className="num">{Number(p._aggSize ?? p.volume) || 0}</td>
                          <td className="num">{fmtUSD(p._aggPrem ?? p.premium)}<div className="fsb-muted fsb-small">90s {fmtUSD(p._aggPrem)} ({p._aggN || 1})</div></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

          {/* Selected signal — full width below the tape (scroll to read) */}
          <div className="fsb-panel">
              <div className="fsb-panel-h">Selected Signal</div>
              {!selected ? <div className="fsb-sel-empty">Click any row to load its conviction profile.</div> : (
                <>
                  <div className="fsb-sel-head">
                    <span className="tk">{selected.ticker}</span>
                    <span className="strike">${Number(selected.strike).toFixed(0)} {sideOf(selected)[0]}</span>
                    <span className="fsb-muted fsb-small">{bizDTE(selected.expiration)}d · {typeOf(selected)}</span>
                    <span className={`fsb-badge ${sideOf(selected) === "CALL" ? "call" : "put"}`}>{sideOf(selected)}</span>
                  </div>
                  <div className="fsb-con-grid">
                    <div ref={gaugeRef} className="fsb-chart small" />
                    <div ref={radarRef} className="fsb-chart small" />
                  </div>
                  <div className="fsb-rationale">
                    <div style={{ marginBottom: 6 }}><strong>{typeOf(selected)} {sideOf(selected)} · {fmtUSD(selected.premium)}</strong> on {selected.ticker}</div>
                    <ul>
                      <li>Classification: {String(selected.classification || "unusual")} — volume/OI positioning proxy (cvserver has no trade-level tape)</li>
                      <li>Vol/OI ratio: {Number(selected.vol_oi_ratio || 0).toFixed(1)}× · est. notional {fmtUSD(selected.premium)}</li>
                      {selected._cd && (
                        <li>Conviction {selected._conv}/99 = pattern {selected._cd.pat} + size {selected._cd.size} + unusualness {selected._cd.stat} + urgency {selected._cd.urg}</li>
                      )}
                    </ul>
                    <div className="fsb-muted fsb-small" style={{ marginTop: 6 }}>Regime: {regime.label}. VPIN toxicity &amp; Kyle-λ price-impact need a trade-level order-flow feed (n/a on snapshot chains) — they populate when a print feed is connected.</div>
                  </div>
                  <div className="fsb-actions">
                    <div className="fsb-panel-h" style={{ marginBottom: 6 }}>Context</div>
                    <ul>
                      <li><span className="tag warn">RISK</span>Paper/educational only — not a trade recommendation.</li>
                    </ul>
                    <button
                      className="fsb-chip"
                      onClick={() => setChartRow(selected)}
                      data-testid="selected-chart-open"
                    >
                      📊 Chart + checklist
                    </button>
                  </div>
                  <ChartModal
                    row={chartRow}
                    open={!!chartRow}
                    onClose={() => setChartRow(null)}
                    history={[]}
                    netPremiumSeries={[]}
                  />
                </>
              )}
            </div>
          </div>
        {/* W8: extras drawer — honest states (fixture-first); only on flow tab, sibling to flow grid */}
        {tab === "flow" && (
          <div className="fsb-panel fsb-drawer" data-testid="flowseeker-drawer">
            <div className="fsb-panel-h"><span>Flow extras</span><span className="fsb-muted fsb-small">honest states · display-only</span></div>
            <div className="fsb-drawer-grid">
              <div className="fsb-drawer-col" data-testid="drawer-tracker">
                <h4 className="fsb-drawer-h">Tracker <span className="fsb-muted fsb-small" title="P/L assumes 1 contract (qty proxy) — real qty not in snapshot feed">qty=1 proxy</span></h4>
                <Tracker />
              </div>
              <div className="fsb-drawer-col" data-testid="drawer-history">
                <h4 className="fsb-drawer-h">History</h4>
                <NetPremiumTrend series={[]} state="ready" />
                <StrikeDistribution buckets={[]} state="ready" />
                <VolOiFooter rows14d={[]} state="ready" />
              </div>
              <div className="fsb-drawer-col" data-testid="drawer-darkpool">
                <h4 className="fsb-drawer-h" title="Off-exchange prints — no side or direction is known">Dark pool</h4>
                <DarkPoolPanel prints={[]} state="ready" />
              </div>
              <div className="fsb-drawer-col" data-testid="drawer-methodology">
                <h4 className="fsb-drawer-h">Methodology</h4>
                <Checklist steps={["NetPrem 5-7D","Underlying $","Contract + IV + RVOL","Strike 1W","Vol/OI 14d","Heatseeker cross-check"]} checks={checks} onToggle={(i) => setChecks((c) => ({ ...c, [i]: !c[i] }))} verdict={verdict} onVerdict={(v) => setVerdict(v)} />
                <div className="fsb-drawer-foot" title="Per-row sort ranking floors: premium $25K, size 150 contracts — rows below floor still sort, only tick to show they ranked lower">Floors: prem $25K · size 150 (ranking only)</div>
              </div>
              {/* W6 funnel-empty — honest widening path when filtered result hits zero */}
              {scanRows.length === 0 && (
                <div className="fsb-drawer-col" data-testid="drawer-funnel-empty">
                  <h4 className="fsb-drawer-h">Filter funnel</h4>
                  <FunnelEmpty beforeCount={scan.length} afterCount={0} actions={widenActions(fsFilter)} onWiden={(a) => {
                    if (a.action === "reset") { setScanDteF("all"); setScanMinPrem(0); setScanMinScore(0); }
                    else if (a.action === "clear_sweep") { /* sweepsOnly not wired yet */ }
                    else if (a.action === "enable_etfs") { /* equityType toggle not wired yet */ }
                    else if (a.action === "lower_premium") { setScanMinPrem(Math.max(0, (fsFilter.minPremium || 0) - 25000)); }
                    else if (a.action === "lower_score") { setScanMinScore(Math.max(0, (fsFilter.minScore || 0) - 5)); }
                    else if (a.action === "clear_dte") { setScanDteF("all"); }
                  }} />
                </div>
              )}
            </div>
            <div className="fsb-drawer-note fsb-muted fsb-small">{FLOW_PROXY_NOTE}</div>
          </div>
        )}
        </div>

        {/* SCANNER VIEW — cross-symbol BladeMap scanner (scenner34 grid) */}
        <div className={`fsb-view${tab === "scanner" ? " active" : ""}`} style={{ gridTemplateColumns: "1fr" }}>
          <div className="fsb-scanwrap">
            <div className="fsb-scanbar">                {[
                  ["Source", scanMeta.mode === "market" ? `LIVE · mkt-wide ·${scanMeta.symbols}` : scanMeta.mode === "fallback" ? `FALLBACK ·${scanMeta.symbols} sym` : "—",
                  scanMeta.stale ? "y" : scanMeta.mode === "market" ? "g" : scanMeta.mode ? "y" : ""],
                ["Contracts", `${scanRows.length} / ${scan.length}${scanRows.length > 200 ? " ·top200" : ""}`, "b"],
                ["Notional Σ", fmtUSD(scanStats.notl), ""],
                ["Call/Put Vol", scanStats.tv > 0 ? `${scanStats.cpct}% / ${100 - scanStats.cpct}%` : "—", scanStats.cpct >= 50 ? "g" : "r"],
                ["Unusual (≥2×)", String(scanStats.unusual), "y"],
                ...((alertRules.scoreMin ?? 92) > 85 || (alertRules.whaleMin ?? 25e6) > 10e6
                  ? [["Quality gate", `SCORE≥${alertRules.scoreMin ?? 92} · WHALE≥$${Math.round((alertRules.whaleMin ?? 25e6) / 1e6)}M · SIGMA≥${alertRules.sigmaMin ?? 6}σ`, "b"]]
                  : []),
                ["⚡ Alerts", `${alertLog.length}${suppressedCount ? ` ·+${suppressedCount} held` : ""}`, alertLog.length ? "r" : "", "Open the alert log — count includes every fire this session; held back = noise-budget overflow that stayed truthful but off the tape"],
                ["Updated",
                  scanMeta.stale
                    ? `STALE${scanMeta.retry ? ` ·retry ${Math.round(scanMeta.retry)}s` : ""} · ${scanAt || "—"}`
                    : `${scanAt || "—"}${scanMeta.age >= 5 ? ` ·data ${scanMeta.age}s` : ""}`,
                  scanMeta.stale ? "y" : "",
                  "Local fetch time · upstream data age (60s server cache; STALE = upstream rate-limited, serving last good scan)"],
                ["Heartbeat",
                  <>
                    <span className={`fsb-pulse ${heartbeat.dot}`} aria-hidden="true" />
                    {scanMeta.mode
                      ? `${heartbeat.label}${heartbeat.tier === "fresh" ? ` ·${scanAt || "—"}` : ""}`
                      : heartbeat.label}
                  </>,
                  heartbeat.dot,
                  heartbeat.tier === "fresh" && scanAt ? `${heartbeat.hint} · last fetch ${scanAt}` : heartbeat.hint],
              ].filter(([l]) => advanced || ["Source", "⚡ Alerts", "Updated", "Heartbeat", "Quality gate"].includes(l))
                .map(([l, v, c, tip]) => (
                <div key={l} className={`fsb-skpi${l === "⚡ Alerts" ? " fsb-skpi-click" : ""}`}
                  onClick={l === "⚡ Alerts" ? () => setAlertsOpen((o) => !o) : undefined}
                  title={tip}>
                  <div className="fsb-skl">{l}</div><div className={`fsb-skv ${c}`}>{v}</div>
                </div>
              ))}
              <button className="fsb-preset fsb-advtoggle"
              title={advanced ? "Back to the simple view — alerts + full flow table" : "Show all filters, presets and alert-rule controls"}
                onClick={() => setAdvanced((a) => !a)}>
                ⚙ {advanced ? "Simple" : "Advanced"}
              </button>
            </div>
            {fireBanner && (
              <div className="fsb-fire-banner" role="alert"
                title={fireBanner.label || fireBanner.why || "Institutional alert"}
                onClick={() => {
                  if (fireBanner.label) {
                    setScanQ(scanQ === fireBanner.under ? "" : fireBanner.under);
                  } else {
                    setTicker(fireBanner.under);
                    setTab("flow");
                  }
                }}>
                <span className="fsb-fire-ring" aria-hidden="true" />
                <span className={`fsb-rulebadge r-${String(fireBanner.rule || "").toLowerCase()}`}>{fireBanner.rule}</span>
                <span className="fsb-fire-t">
                  {fireBanner.under}
                  {!fireBanner.label && (
                    <>
                      {" · "}
                      <span className={fireBanner.type === "call" ? "fsb-tcall" : "fsb-tput"}>
                        {fireBanner.type === "call" ? "CALL" : "PUT"}
                      </span>
                      {" "}{fireBanner.strike} <span className="fsb-sub">{(fireBanner.exp || "").slice(5)}</span>
                    </>
                  )}
                </span>
                <span className="fsb-fire-why">
                  {fireBanner.label || fireBanner.why || " "}
                  {fireBanner.premium != null ? ` · ~${fmtUSD(fireBanner.premium)}` : ""}
                  {fireBanner.sigma != null ? ` · ${fireBanner.sigma}σ` : ""}
                  {fireBanner.streak != null ? ` · ${fireBanner.streak}d streak` : ""}
                </span>
                <span className="fsb-fire-age" title="Auto-dismiss after 60s">{fmtAge(fireBanner.t)}</span>
                <button className="fsb-fire-x" title="Acknowledge — auto-dismisses after 60s anyway"
                  onClick={(e) => { e.stopPropagation(); ackFire(fireBanner.key); }}>✕</button>
              </div>
            )}
            {rollup.length > 0 && (
              <div className="fsb-rollup">
                <span className="fsb-rollup-label">PREM~ FLOW</span>
                {rollup.map((e) => (
                  <button key={e.under} className={`fsb-rollchip${scanQ === e.under ? " on" : ""}`}
                    title={`${e.under}: ~${fmtUSD(e.prem)} est premium · ${e.count} contracts · ${e.callPct}% calls / ${100 - e.callPct}% puts · vol PCR ${e.pcr ?? "—"} (Pan-Poteshman: low P/C historically precedes outperformance) · top score ${e.maxScore}`}
                    onClick={() => setScanQ(scanQ === e.under ? "" : e.under)}>
                    <span className="fsb-rollchip-t">
                      {e.under}
                      {e.regime ? <sup className={`fsb-gtag ${e.regime === "positive" ? "gp" : "gn"}`}>{e.regime === "positive" ? "γ+" : "γ−"}</sup> : null}
                      {streaks[e.under] ? <span className="fsb-streak" title={`${streaks[e.under].n} consecutive elevated-volume days (≥${streaks[e.under].mult}× its ${fmtK(streaks[e.under].median)} daily median) — persistent positioning`}>🔥{streaks[e.under].n}d</span> : null}
                    </span>
                    <span className="fsb-rollchip-p">~{fmtUSD(e.prem)}
                      {e.pcr != null ? <span className={`fsb-pcr${e.pcr <= 0.5 ? " bull" : e.pcr >= 1.5 ? " bear" : ""}`}> PCR {e.pcr.toFixed(2)}</span> : null}
                      {(() => { const s = volSigma(e.callVol + e.putVol, baselines[e.under]); return s != null && s >= 2 ? <span className="fsb-sigma" title={`Today's scan volume is ${s}σ above this ticker's ${baselines[e.under].days}-day baseline`}> {s}σ</span> : null; })()}
                    </span>
                    {cleanHistory(history[e.under]).length >= 3 && (
                      <span className="fsb-spark" aria-hidden="true">
                        {(() => {
                          const ds = cleanHistory(history[e.under]).slice(-10);
                          const mx = Math.max(...ds.map((d) => d.total_vol), 1);
                          return ds.map((d) => (
                            <i key={d.date} className={d.date === sessionDay() ? "t" : ""}
                               style={{ height: `${Math.max(12, Math.round((d.total_vol / mx) * 100))}%` }}
                               title={`${d.date}: ${fmtK(d.total_vol)} vol (${fmtK(d.call_vol)}C/${fmtK(d.put_vol)}P)`} />
                          ));
                        })()}
                      </span>
                    )}
                  <span className="fsb-rollbar"><span className="fsb-rollbar-c" style={{ width: `${e.callPct}%` }} /></span>
                </button>
              ))}
            </div>
            )}
            {followStrip.length > 0 && (
              <div className="fsb-follow-strip">
                <span className="fsb-follow-label">📈 FOLLOWING</span>
                {followStrip.map(({ under, n, mult, median }) => (
                  <button key={under} className={`fsb-follow-chip n-${Math.min(5, n)}${scanQ === under ? " on" : ""}`}
                    title={`${under} elevated-volume ${n} straight days (≥${mult.toFixed(1)}× its ${fmtK(median)} daily median) — click to filter the scan to this ticker`}
                    onClick={() => setScanQ(scanQ === under ? "" : under)}>
                    <span className="fsb-follow-t">{under}</span>
                    <span className="fsb-follow-n">{n}d</span>
                    <span className="fsb-follow-x">{mult.toFixed(1)}×</span>
                  </button>
                ))}
                <span className="fsb-follow-sub">
                  persistent positioning · {followStrip.length} ticker{followStrip.length === 1 ? "" : "s"}
                </span>
              </div>
            )}
            {/* Institutional: side + DTE presets always visible (the lost filter — restored, both modes). */}
            <div className="fsb-scanctrl fsb-scanctrl-always">
              <select value={scanSideF} onChange={(e) => setScanSideF(e.target.value)}>
                <option value="all">All Side</option><option value="call">Calls</option><option value="put">Puts</option>
              </select>
              <span className="fsb-presets">
                {["all", "0dte", "1-7d", "weekly", "monthly", "qtrly", "leaps"].map((p) => (
                  <button key={p} className={`fsb-preset${scanDteF === p ? " on" : ""}`}
                    onClick={() => setScanDteF(p)}>
                    {p === "all" ? "All DTE" : p === "0dte" ? "0DTE" : p === "1-7d" ? "1-7D" : p === "weekly" ? "Wk" : p === "monthly" ? "Mo" : p === "qtrly" ? "Qtr" : "LEAPS"}
                  </button>
                ))}
              </span>
            </div>
            {advanced && <div className="fsb-scanctrl">
              <select value={scanTypeF} onChange={(e) => setScanTypeF(e.target.value)}>
                <option value="all">All Types</option><option value="call">Calls</option><option value="put">Puts</option>
              </select>
              <input type="number" min="0" step="1000" placeholder="Min Vol" value={scanMinVol || ""} onChange={(e) => setScanMinVol(parseFloat(e.target.value) || 0)} />
              <input type="number" min="0" step="250000" placeholder="Min Prem~" value={scanMinPrem || ""} onChange={(e) => setScanMinPrem(parseFloat(e.target.value) || 0)} />
              <input type="number" min="0" step="500" placeholder="Min OI" value={scanMinOI || ""} onChange={(e) => setScanMinOI(parseFloat(e.target.value) || 0)} />
              <input type="number" min="0" max="100" step="5" placeholder="Min Score" value={scanMinScore || ""} onChange={(e) => setScanMinScore(parseFloat(e.target.value) || 0)} />
              <input ref={scanQRef} placeholder="Ticker…  ( / )" value={scanQ} onChange={(e) => setScanQ((e.target.value || "").toUpperCase())} />
              <span className="fsb-presets">
                {[["Top Score", { key: "score", dir: "desc" }], ["Big Money", { key: "notional", dir: "desc" }],
                  ["Unusual", { key: "volOI", dir: "desc" }], ["Short Fuse", { key: "dte", dir: "asc" }],
                  ["New Arrivals", { key: "firstSeen", dir: "desc" }]].map(([l, s]) => (
                  <button key={l} className={`fsb-preset${scanSort.key === s.key && scanSort.dir === s.dir ? " on" : ""}`}
                    onClick={() => setScanSort(s)}>{l}</button>
                ))}
                <button className="fsb-preset fsb-force" disabled={forcing}
                  title="Force refresh — bypasses cache & backoff (server-debounced 10s)"
                  onClick={forceRefresh}>{forcing ? "…" : "⟳ Force"}</button>
                <button className="fsb-preset" disabled={!scanRows.length}
                  title="Download the current filtered view as CSV (premium column is an estimate)"
                  onClick={() => exportCSV(scanRows)}>⤓ CSV</button>
              </span>
              <input className="fsb-alertn" type="number" min="50" max="100" value={alertScore}
                title="Alert when a NEW contract scores ≥ this (drives the SCORE rule)"
                onChange={(e) => {
                  const v = Math.max(50, Math.min(100, parseInt(e.target.value, 10) || 85));
                  setAlertScore(v);
                  // SCORE rule reads enabled.scoreMin first — keep both in sync
                  // so this visible control stays the source of truth.
                  setAlertRules((r) => ({ ...r, scoreMin: v }));
                }} />
              <span className="fsb-scannote">Live cross-symbol flow · cvforge day-volume vs OI. No per-trade tape on this feed — Flow-type = volume-magnitude class; Lean = contract-type bias.</span>
            </div>}
            {/* Outcome ledger — per-rule measured precision/lift vs matched controls.
                The desk trusts hit rates, not scores; this is where thresholds get
                argued from data instead of defaults. precision=null → uncalibrated. */}
            {outcomesOpen && outcomes && (outcomes.per_rule && Object.keys(outcomes.per_rule).length > 0) && (
              <div className="fsb-outcomes">
                <div className="fsb-outcomes-h">
                  <span>📏 Outcome Ledger</span>
                  <span className="fsb-muted fsb-small">
                    hit = |side-signed move| ≥ {outcomes.sigma_k}σ in {outcomes.horizon_sessions} sessions · vs matched controls
                    {calibration && (
                      <> · P(move): <b className={calibration.stage >= 1 ? "" : "fsb-muted"}>{calibration.stage >= 1 ? `stage ${calibration.stage} (${calibration.model_kind || "decile"})` : `uncalibrated · n=${calibration.n}`}</b></>
                    )}
                  </span>
                  <button className="fsb-alertclear" onClick={() => setOutcomesOpen(false)} title="Collapse">—</button>
                </div>
                <table className="fsb-outcometab">
                  <thead><tr>
                    <th>Rule</th><th className="num">n</th><th className="num">Precision</th>
                    <th className="num">Control</th><th className="num">Lift</th><th className="num">95% CI</th><th className="num">MFE/MAE σ</th>
                  </tr></thead>
                  <tbody>
                    {Object.entries(outcomes.per_rule).map(([rule, s]) => (
                      <tr key={rule} className={s.decayed ? "fsb-amber-row" : ""}>
                        <td><span className={`fsb-rulebadge r-${rule.toLowerCase()}`}>{rule}</span>{s.status === "AMBER" ? <span className="fsb-amber-chip" title="rule's recent precision dropped below its own lift line (30d window) — measured decay, review thresholds">⚠ AMBER</span> : null}</td>
                        <td className="num">{s.n_measured}{s.n_censored ? <span className="fsb-muted"> +{s.n_censored}⧗</span> : ""}</td>
                        {s.uncalibrated ? (
                          <td className="num fsb-muted" colSpan={2} title={`only ${s.n_measured} measured alerts — no honest number yet`}>uncalibrated · n={s.n_measured}</td>
                        ) : (
                          <>
                            <td className="num"><b>{Math.round(s.precision * 100)}%</b></td>
                            <td className="num fsb-muted">{s.control_rate != null ? `${Math.round(s.control_rate * 100)}% · ${s.n_controls}` : "—"}</td>
                          </>
                        )}
                        {!s.uncalibrated && (
                          <>
                            <td className={`num ${s.lift != null && s.lift > 0 ? "pos" : s.lift != null && s.lift < 0 ? "neg" : ""}`}>
                              {s.lift != null ? `${s.lift > 0 ? "+" : ""}${Math.round(s.lift * 100)}pp` : "—"}
                            </td>
                            <td className="num fsb-muted">{s.lift_ci ? `[${Math.round(s.lift_ci[0] * 100)}pp, ${Math.round(s.lift_ci[1] * 100)}pp]` : s.precision_ci ? `[${Math.round(s.precision_ci[0] * 100)}%, ${Math.round(s.precision_ci[1] * 100)}%]` : "—"}</td>
                            <td className="num fsb-muted">{s.median_mfe_sigma != null ? `${s.median_mfe_sigma}/${s.median_mae_sigma}` : "—"}</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {outcomes.overall && outcomes.overall.n_measured > 0 && (
                  <div className="fsb-outcomes-f fsb-muted fsb-small">
                    overall {outcomes.overall.precision != null ? `${Math.round(outcomes.overall.precision * 100)}%` : "uncalibrated"} across {outcomes.overall.n_measured} measured alerts · {outcomes.tickers_measured?.length || 0} tickers · ⧗ = censored (window not yet complete — excluded, not zero-filled)
                  </div>
                )}
              </div>
            )}
            {outcomesOpen && !outcomes && (
              <div className="fsb-outcomes fsb-muted" style={{ padding: 10 }}>
                📏 Outcome ledger: measuring alert precision vs matched controls… (fills as the alert ledger accumulates)
              </div>
            )}
            {!outcomesOpen && (
              <button className="fsb-outcomes-collapsed" onClick={() => setOutcomesOpen(true)} title="Show measured alert precision vs matched controls">
                📏 Outcome Ledger — show calibration
              </button>
            )}
            {away && (
              <div className="fsb-away">
                <span className="fsb-away-t">☾ While you were away · {fmtAge(Date.now() - away.gapMs)}</span>
                {away.nAlerts > 0 && (
                  <span className="fsb-alertsummary">
                    {RULES_ORDER.filter((k) => away.counts[k]).map((k) => (
                      <span key={k} className={`fsb-sumtag r-${k.toLowerCase()}`}>{k} {away.counts[k]}</span>
                    ))}
                  </span>
                )}
                {away.topNew.length > 0 && (
                  <span className="fsb-away-new">
                    top new:{" "}
                    {away.topNew.map((r) => (
                      <button key={`${r.under}${r.strike}${r.type}${r.exp}`} className="fsb-awaychip"
                        title={`Score ${r.score} · first seen ${fmtClock(r.firstSeen)} — click to filter`}
                        onClick={() => setScanQ(r.under)}>
                        {r.under} {r.type === "call" ? "C" : "P"}{r.strike} <b>{r.score}</b>
                      </button>
                    ))}
                  </span>
                )}
                <button className="fsb-away-x" title="Dismiss" onClick={() => setAway(null)}>✕</button>
              </div>
            )}
            {alertsOpen && (
              <div className="fsb-alertlog">
                {/* Blademap v3 — conviction calibration + per-setup win rate */}
                {(calibBands.length > 0 || (setupStats?.overall?.n > 0)) && (
                  <div className="fsb-v3strip">
                    {calibBands.map((b) => (
                      <div key={b.band}
                           className={`fsb-v3cell${b.band === "75+" ? " hot" : ""}`}
                           title={`${b.n} alerts · ${b.n_measured} measured · ${b.wins} hits`}>
                        <span className="fsb-v3lbl">{b.band}</span>
                        <span className="fsb-v3val">{b.hit_rate != null ? `${Math.round(b.hit_rate * 100)}%` : "—"}</span>
                        <span className="fsb-v3bar"><i style={{ width: `${Math.round((b.hit_rate || 0) * 100)}%` }} /></span>
                        <span className="fsb-v3n">{b.n_measured}/{b.n}</span>
                      </div>
                    ))}
                    {setupStats?.overall?.n > 0 && Object.entries(setupStats.by_setup || {}).map(([name, s]) => (
                      <div key={name} className={`fsb-v3cell${s.win_rate >= 0.5 ? " hot" : ""}`}
                           title={`journal ${setupStats.days}d · ${name}: ${s.wins}W/${s.losses}L, avg ${(s.avg_return * 100).toFixed(1)}%`}>
                        <span className="fsb-v3lbl">📓 {name}</span>
                        <span className="fsb-v3val">{Math.round(s.win_rate * 100)}%</span>
                        <span className="fsb-v3n">{s.wins}W/{s.losses}L</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="fsb-alertlog-h">
                  <span>🏛 Institutional Alerts · {alertLog.length}</span>
                  {alertLog.length > 0 && (
                    <span className="fsb-alertsummary">
                      {alertSummary.oldest === alertSummary.newest
                        ? alertSummary.newest
                        : `${alertSummary.oldest} → ${alertSummary.newest}`}
                      {RULES_ORDER.filter((k) => alertSummary.c[k]).map((k) => (
                        <span key={k} className={`fsb-sumtag r-${k.toLowerCase()}`}>{k} {alertSummary.c[k]}</span>
                      ))}
                    </span>
                  )}
                  <span className="fsb-rulechips">
                    <button className={`fsb-rulechip${notify ? " on" : ""}`}
                      title="Browser notification when alerts fire while this tab is hidden"
                      onClick={toggleNotify}>🔔 Notify</button>
                    {advanced && <>
                      {[["oiconf", "ΔOI CONF"], ["follow", `FOLLOW ${alertRules.followMin ?? 3}d+`], ["sigma", `SIGMA ≥${alertRules.sigmaMin ?? 6}σ`],
                        ["score", `SCORE≥${alertRules.scoreMin ?? 92}`], ["whale", `WHALE ≥$${Math.round((alertRules.whaleMin ?? 25e6) / 1e6)}M~`], ["prime", "PRIME $250k·5×"], ["zerodte", "0DTE HOT"]].map(([k, lbl]) => (
                        <button key={k} className={`fsb-rulechip${alertRules[k] ? " on" : ""}`}
                          title="Toggle this alert rule"
                          onClick={() => setAlertRules((r) => ({ ...r, [k]: !r[k] }))}>{lbl}</button>
                      ))}
                      <button className="fsb-rulechip" title="Toggle newest-first / oldest-first"
                        onClick={() => setAlertOrder((o) => (o === "new" ? "old" : "new"))}>
                        {alertOrder === "new" ? "⇊ Newest" : "⇈ Oldest"}
                      </button>
                    </>}
                  </span>
                  {advanced && <button className="fsb-alertclear" disabled={!alertLog.length}
                    title="Copy the tape to the clipboard (tab-separated — pastes into Sheets/journal)"
                    onClick={() => {
                      const tsv = alertLog.map((a) => [a.day || "", a.time, a.rule, a.under, a.type, a.strike, a.exp, a.score ?? "", a.premium ?? "", a.label || a.why || ""].join("\t")).join("\n");
                      try { navigator.clipboard.writeText(tsv); } catch { /* clipboard blocked */ }
                    }}>
                    ⧉ Copy
                  </button>}
                  <button className="fsb-alertclear"
                    title="Clear the tape display — fired alerts stay deduped, so still-active conditions won't re-fire"
                    onClick={() => { setAlertLog([]); try { localStorage.removeItem(ALERTS_KEY); } catch { /* noop */ } }}>
                    Clear
                  </button>
                </div>
                {alertLog.length === 0 ? (
                  <div className="fsb-muted" style={{ padding: 10 }}>
                    No alerts yet — rows crossing an enabled rule log here with arrival time, source, and the reason they fired. Confirmation tier: ΔOI CONF = overnight open-interest build proves yesterday's flow held; FOLLOW = 3+ straight days of elevated volume; SIGMA = volume ≥6σ vs the ticker's own baseline. Intraday tier: SCORE ≥92 / WHALE ≥$25M~ / 0DTE on newly arrived contracts (deduped, noise-budget capped at 4/rule/hour). Tape keeps today + yesterday; alerts cover the whole market.
                  </div>
                ) : (
                  <table className="fsb-alerttab">
                    <tbody>
                      {shownAlerts.map((a, i) => (
                        <tr key={`${a.key}-${a.t}-${i}`}
                            title={a.why || undefined}
                            onClick={a.rule === "SOURCE" ? undefined
                              : a.label ? () => setScanQ(scanQ === a.under ? "" : a.under)
                              : () => { setTicker(a.under); setTab("flow"); }}>
                          <td title={a.src === "fallback" ? "fallback scan" : a.src === "market" ? "market-wide scan" : ""}>
                            <span className={`fsb-srcdot ${a.src || ""}`} />
                          </td>
                          <td className="fsb-sub" title={`${fmtAge(a.t)} ago`}>
                            {a.day && a.day !== sessionDay() ? <span className="fsb-daytag">prev</span> : null}{a.time}
                          </td>
                          <td><span className={`fsb-rulebadge r-${a.rule.toLowerCase()}`}>{a.rule}</span></td>
                          {a.label ? (
                            // Ticker-level rows (SIGMA/FOLLOW) + SOURCE flips carry a full
                            // sentence; contract columns don't apply. Click filters the scan.
                            <td className="l fsb-sub" colSpan={4}>{a.label}</td>
                          ) : (
                            <>
                              <td className="l">
                                <span className="tk">{a.under}</span>{" "}
                                <span className={a.type === "call" ? "fsb-tcall" : "fsb-tput"}>{a.type === "call" ? "CALL" : "PUT"}</span>{" "}
                                {a.strike} <span className="fsb-sub">{(a.exp || "").slice(5)}</span>
                                {a.why ? <span className="fsb-why"> · {a.why}</span> : null}
                              </td>
                              <td>{a.score}</td>
                              <td>{a.premium != null ? `~${fmtUSD(a.premium)}` : "—"}</td>
                              <td className="fsb-sub">{fmtAge(a.t)}</td>
                            </>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
            {/* Blademap v3 — top conviction signal cards (backend-ranked) */}
            {active && convFeed.length === 0 && convFeedState === "loading" && (
              <div className="fsb-sigwrap">
                <div className="fsb-sigh">
                  <span className="fsb-sigh-t">◈ Top Conviction</span>
                  <span className="fsb-sigh-s">loading ranked signals…</span>
                </div>
                <div className="fsb-sigcards">
                  {[0, 1, 2, 3].map((n) => (
                    <div key={n} className="fsb-sigcard fsb-skel" aria-hidden="true">
                      <div className="fsb-sig-ring skel-ring" />
                      <div className="fsb-sig-body">
                        <div className="skel-line w60" />
                        <div className="skel-line w40" />
                        <div className="skel-line w75" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {active && convFeed.length === 0 && convFeedState === "unavailable" && (
              <div className="fsb-sigwrap">
                <div className="fsb-sigh">
                  <span className="fsb-sigh-t">◈ Top Conviction</span>
                  <span className="fsb-sigh-s">feed unavailable (backend /alerts/feed) — tape below is live</span>
                  <button className="fsb-chip fsb-chip-sm" onClick={() => { setConvFeedState("loading"); setRefreshTick((t) => t + 1); }}>Retry</button>
                </div>
              </div>
            )}
            {convFeed.length > 0 && (
              <div className="fsb-sigwrap">
                <div className="fsb-sigh">
                  <span className="fsb-sigh-t">◈ Top Conviction</span>
                  <span key={refreshTick} className="fsb-fedotp" title={`feed refreshed · ${convFeed.length} signals`} />
                  <span className="fsb-sigh-s">ranked by Blademap v3 · click to filter</span>
                </div>
                <div className="fsb-sigcards">
                {convFeed.slice(0, 6).map((a) => {
                  const isCall = String(a.type).toLowerCase() === "call";
                  const kl = (() => { try { return a.key_levels_json ? JSON.parse(a.key_levels_json) : null; } catch { return null; } })();
                  const tier = String(a.tier || "").toUpperCase();
                  const bear = String(a.bias || "").toUpperCase().includes("BEAR");
                  const mp = a.move_pct != null ? a.move_pct * 100 : null;
                  return (
                    <div key={a.key} className={`fsb-sigcard${Number(a.conviction) >= 75 ? " hot" : ""} ${
                        (a.conviction ?? 0) >= 75 ? "heat-crit" :
                        (a.conviction ?? 0) >= 60 ? "heat-high" :
                        (a.conviction ?? 0) >= 45 ? "heat-elev" : "heat-norm"}`}
                         title={`${a.why || "conviction " + a.conviction}${kl && kl.invalidation ? ` · invalidation ${kl.invalidation}` : ""} — click to filter ${a.under || a.ticker || ""}`}
                         onClick={() => setScanQ(String(a.under || a.ticker || ""))}>
                      <div className="fsb-sig-ring"
                           style={{ "--pct": `${Math.max(0, Math.min(99, Number(a.conviction) || 0))}` }}
                           title={`conviction ${a.conviction}/99`}>
                        <span>{a.conviction}</span>
                      </div>
                      <div className="fsb-sig-body">
                      <div className="fsb-sig-top">
                        <span className={`fsb-sig-tk ${isCall ? "fsb-tcall" : "fsb-tput"}`}>
                          {a.under || a.ticker} {isCall ? "CALL" : "PUT"} {a.strike}
                        </span>
                        <span className="fsb-sig-badges">
                          {tier && <span className={`fsb-sig-tier t-${tier.toLowerCase()}`}>{tier}</span>}
                          {(() => { const eb = exposureBadgeFor(a.rule, a); return eb ? <span key={eb.rule} className={`fsb-sig-exp e-${eb.rule.toLowerCase()}`} title={eb.title}>{eb.label}</span> : null; })()}
                          <span className="fsb-sig-conv">{a.conviction}</span>
                        </span>
                      </div>
                      <div className="fsb-sig-sub">
                        <span className={bear ? "dn" : "up"}>{bear ? "▼" : "▲"} {a.bias || ""}</span>
                        {a.score != null ? ` · score ${a.score}` : ""}{a.notional ? ` · $${(a.notional / 1e6).toFixed(1)}M` : ""}
                        {a.dte != null ? ` · ${a.dte}d` : ""}
                        {mp != null ? <span className={mp < 0 ? " dn" : " up"}> · {mp >= 0 ? "+" : ""}{mp.toFixed(2)}%</span> : ""}
                      </div>
                      {kl && (kl.stop || kl.target || kl.invalidation) && (
                        <div className="fsb-sig-lv">
                          {kl.entry != null && <span>E {Number(kl.entry).toFixed(2)}</span>}
                          {(kl.stop != null || kl.invalidation != null) && <span className="dn">S {Number(kl.stop ?? kl.invalidation).toFixed(2)}</span>}
                          {kl.target != null && <span className="up">T {Number(kl.target).toFixed(2)}</span>}
                        </div>
                      )}
                      </div>
                    </div>
                  );
                })}
                </div>
              </div>
            )}
            <div className="fsb-scantable">
              {scanMeta.err ? (
                <div className="fsb-muted" style={{ padding: 16 }}>Flow scan fetch failed — not a filter issue. <button className="fsb-chip fsb-chip-sm" onClick={() => { setScanMeta((m) => ({ ...m, err: false })); setRefreshTick((t) => t + 1); }}>Retry</button></div>
              ) : scan.length === 0 ? (
                <div className="fsb-muted" style={{ padding: 16 }}>Scanning market-wide flow{scanMeta.symbols ? ` across ${scanMeta.symbols} symbols` : ""}…</div>
              ) : scanRows.length === 0 ? (
                <div className="fsb-muted" style={{ padding: 16 }}>No contracts pass these filters.</div>
              ) : (
                <table className="fsb-stab">
                  <thead><tr>
                    {colsShown.map(([k, t, l]) => (
                      <th key={k} className={`${l ? "l" : ""}${k === scanSort.key ? " on" : ""}`} onClick={() => sortScan(k)}>
                        {t}{k === scanSort.key ? (scanSort.dir === "desc" ? " ▾" : " ▴") : ""}
                      </th>
                    ))}
                  </tr></thead>
                  <tbody>
                    {scanRows.map((r, i) => {
                      const isCall = r.type === "call";
                      const otm = r.delta == null ? "" : (Math.abs(r.delta) < 0.45 ? "OTM" : "ITM");
                      // POC-style: the single best-score row gets the ★ leader treatment
                      const isTop = i === 0 && scanSort.key === "score" && scanSort.dir === "desc" && (r.score ?? 0) >= 90;
                      return (
                        <tr key={`${r.under}-${r.strike}-${r.type}-${r.exp}-${i}`}
                            className={`${kbIdx === i ? "kbcursor " : ""}${isTop ? "top " : ""}${r.under === ticker ? "sel " : ""}${r._new ? "new " : ""}${r._new && r.score >= alertScore ? "alert" : ""}`.trim()}
                            onClick={() => { setTicker(r.under); setTab("flow"); }}>
                          <td className="fsb-seen" title={r.firstSeen ? `First seen ${fmtClock(r.firstSeen, true)} · ${fmtAge(r.firstSeen)} ago this session` : ""}>
                            {r._new ? <span className="fsb-newdot" title="New this refresh" /> : null}
                            <span className="fsb-sub">{fmtClock(r.firstSeen)}</span>
                          </td>
                          <td><span className={`fsb-sc ${scoreGradeOf(r.score)}`} title={r._parts ? `vol/OI ${r._parts.pos} · size ${r._parts.size} · notional ${r._parts.notl} · urgency ${r._parts.urg} · OTM ${r._parts.otm}${r._parts.nudge ? ` · γ-nudge +${r._parts.nudge}` : ""}` : ""}>{r.score}</span></td>
                          <td className="l"><span className="tk">{r.under}</span>{r.regime ? <sup className={`fsb-gtag ${r.regime === "positive" ? "gp" : "gn"}`}>{r.regime === "positive" ? "γ+" : "γ−"}</sup> : null} <span className="fsb-sub">{(r.exp || "").slice(5)}</span></td>
                          <td className={`l ${isCall ? "fsb-tcall" : "fsb-tput"}`}>{isCall ? "CALL" : "PUT"}</td>
                          <td>{r.strike % 1 === 0 ? r.strike.toFixed(0) : r.strike.toFixed(1)}</td>
                          <td>{r.dte == null ? "—" : `${r.dte}d`}</td>
                          <td>{fmtK(r.vol)}</td>
                          {advanced && <td>{fmtK(r.oi)}</td>}
                          <td className={r.oiChg ? (r.oiChg.pct >= 0 ? "fsb-oiup" : "fsb-oidn") : ""}
                              title={r.oiChg
                                ? `Open interest ${r.oiChg.abs >= 0 ? "+" : ""}${fmtK(r.oiChg.abs)} vs last session (${fmtK(r.oi - r.oiChg.abs)} → ${fmtK(r.oi)})${r.arch === "FRESH" ? (r.oiChg.pct >= 0.1 ? " — FRESH held: new positioning stuck" : r.oiChg.pct <= -0.1 ? " — FRESH faded: intraday churn, OI fell back" : "") : ""}`
                                : (r.oiTag && r.oiTag.expiring) ? "Contract expires today — ΔOI suppressed (OI is about to evaporate; hygiene gate)"
                                : (r.oiTag && r.oiTag.rollover) ? "Rollover detected — position migrated expiries, ΔOI suppressed (not new flow)"
                                : "No prior-day record for this contract yet — ΔOI appears next session"}>
                            {r.oiChg
                              ? `${r.oiChg.pct >= 0 ? "+" : ""}${(r.oiChg.pct * 100).toFixed(0)}%`
                              : (r.oiTag && r.oiTag.expiring) ? <span className="fsb-oitag" title="expires today — ΔOI suppressed">EXP</span>
                              : (r.oiTag && r.oiTag.rollover) ? <span className="fsb-oitag" title="rollover — ΔOI suppressed">ROLL</span>
                              : <span className="fsb-sub">—</span>}
                            {r.oiChg && r.oiChg.tag && r.oiChg.tag.earnings ? (
                              <span className="fsb-oitag fe" title={r.oiChg.tag.earnings.unknown ? "earnings window unknown — direction ambiguous" : `earnings in ${r.oiChg.tag.earnings.days_to} session(s) — direction ambiguous`}>E</span>
                            ) : null}
                          </td>
                          {advanced && <td>{r.volOI >= 99 ? "99+" : `${r.volOI.toFixed(1)}x`}</td>}
                          <td title="Estimated premium spent — no quote feed on cvserver, BS-lite estimate">{r.premium != null ? `~${fmtUSD(r.premium)}` : "—"}</td>
                          {advanced && <td>{fmtUSD(r.notional)}</td>}
                          {advanced && <td>{fmtIV(r.iv)}</td>}
                          <td className="l">
                            <span className={`fsb-flt ${r.ftype}`}>{r.ftype.toUpperCase()}</span>
                            {r.arch ? <span className={`fsb-arch a-${r.arch.toLowerCase()}`} title={
                              r.arch === "WHALE" ? "≥$10M estimated premium" :
                              r.arch === "LOTTO" ? "deep-OTM, ≤2 DTE" :
                              r.arch === "HEDGE" ? "mid-delta long-dated put — protective duration" :
                              "volume ≥ 3× open interest — fresh positioning"
                            }>{r.arch}</span> : null}
                          </td>
                          {advanced && <td className="l"><span className={`fsb-lean ${isCall ? "bull" : "bear"}`}>{isCall ? "▲ BULL" : "▼ BEAR"}</span>{otm ? <span className="fsb-sub"> {r.deltaEst ? "~" : ""}{otm}</span> : null}</td>}
                          {advanced && (() => {
                            const hist = history[r.under] || [];
                            const days = hist.slice(-7);
                            const maxv = Math.max(1, ...days.map((d) => d.total_vol || 0));
                            const stk = (streaks[r.under] && streaks[r.under].n) || 0;
                            return (
                              <td className="fsb-trd" title={`${r.under}: last ${days.length}d volume (elevated-day streak ${stk}d)`}>
                                {days.length > 1 ? days.map((d, di) => (
                                  <i key={di}
                                     className={di === days.length - 1 ? "now" : ""}
                                     style={{ height: `${Math.max(2, Math.round(((d.total_vol || 0) / maxv) * 12))}px` }}
                                     title={`${d.date}: ${((d.total_vol || 0) / 1e6).toFixed(1)}M`} />
                                )) : <span className="fsb-sub">—</span>}
                              </td>
                            );
                          })()}
                          <td>
                            <button
                              className="fsb-chip"
                              title={r.osi ? `Paper-trade ${r.under} ${r.type} ${r.strike} on Alpaca (paper only)` : "No contract id on this row — trade unavailable"}
                              disabled={!r.osi || !onTrade}
                              data-testid={`scan-trade-${r.under}-${r.strike}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                if (onTrade && r.osi) onTrade({
                                  ticker: r.under, strike: r.strike, spot: r.spot,
                                  oi_symbol: r.osi, iv: r.iv, delta: r.delta,
                                  oi: r.oi, dte: r.dte, exp: r.exp,
                                  call_ask: null, call_last: null, put_bid: null, put_last: null,
                                });
                              }}>
                              ⚡Trade
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>

      </div>

      <div className="fsb-foot">
        <span>Live Public API data · GEX/OFI/regime from the decoder backend. VPIN/Kyle-λ need a trade-level feed (n/a on snapshot chains).</span>
        <span>Tidehunter Pro · Blademap layout</span>
      </div>
    </div>
  );
}
