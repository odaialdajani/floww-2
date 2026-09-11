/**
 * FlowseekerProBlademap.jsx — Tidehunter Pro v3: Blademap-matched insight pipeline.
 *
 * ONE page, zero page tabs: Board header → four answer cells → screen tabs →
 * Vector (direction board = verdict feed) → Pulse (screened contracts) →
 * Lattice (dealer gamma heatmap for the focused ticker) → trust row → settings.
 * Left sidebar items are in-page anchors.
 *
 * Data — real endpoints only, no demo path:
 *   verdict feed  GET /api/flowseeker/alerts/feed?sort_by=conviction (+ SSE /alerts/stream)
 *   pulse         GET /api/flowseeker/scan (+ /scan/history)
 *   lattice       GET /api/heatmap/{t} (display-scale S²) + GET /api/flowseeker/regime/{t}
 *   vpin stub     GET /api/vpin/{t} or "no feed"  (no /ofi, /lambda, /flowseeker/vpin calls)
 *   trust         GET /api/flowseeker/alerts/quality + GET /api/flowseeker/journal/stats?days=90
 *   drill flow    GET /api/public/chain/{t} → GET /api/flowseeker/chain/{t} fallback
 *
 * Nothing here calls /auto-trade/*, any order route, or any broker path.
 * Plan trade writes client-side floww_trades_v2 only.
 */
import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { BACKEND_URL } from "../../config/api";
import { getSettings } from "../SettingsPanel";
import {
  mkScanRow, streakOf, cleanHistory, tickerRollup, annotateFirstSeen,
  sessionDay, fmtClock, fmtAge, scanRowsToCSV, oiChange,
  fmtUSD, fmtK, fmtIV, scoreGradeOf, pulseState, elapsedClock,
} from "./scanLogic";
import {
  FEED_DAYS, FEED_MIN_CONVICTION, TRADE_NOW_FLOOR, LEVELS_LABEL,
  BUILTIN_SCREENS, PULSE_COLUMNS, PULSE_DEFAULT_COLS,
  parseFeedAlerts, isContextual, stageOf, formatMovePct, targetTravelPct,
  directionOf, ageOf, tradeNowOf, feedBodyOf, oiHeldLabel,
  moneynessPct, applyScreenToScans, applyScreenToAlerts,
  SCAN_FACTS, SCAN_FACT_LABELS, TICKER_FACTS, TICKER_FACT_LABELS, RULE_LIST,
} from "./tideFeed";
import { persistJournalSeeds } from "./journalPlans";
import TidehunterSettings, { loadTide, saveSettings as saveTide } from "./TidehunterSettings";
import "./FlowseekerProBlademap.css";
import { publishScreenContext } from "../../agent/useScreenContext";
import DealerDrilldown from "./DealerDrilldown";
import { dealerSeries, finite } from "./dealerSeries";

const API = `${BACKEND_URL}/api/flowseeker`;
const NOISE_FLOOR = 5;
const ACK_KEY = "th-acked-v1";
const PREFS_KEY = "th-prefs-v1";
const FIRSTSEEN_KEY = "th-firstseen-v1";
const ALERTSEEN_KEY = "th-alertseen-v1";
const OPS = ["≥", "≤", "between", "is"];

function loadFirstSeen() {
  try {
    const s = JSON.parse(localStorage.getItem(FIRSTSEEN_KEY));
    if (s && s.day === sessionDay() && s.map) return s;
  } catch {
    /* private mode — fresh baseline */
  }
  return { day: sessionDay(), map: {} };
}
// Alert dedup lives apart from any display list so clearing a view can never
// re-fire a still-true condition. Pruned to 24h on load.
function loadAlertSeen() {
  try {
    const m = JSON.parse(localStorage.getItem(ALERTSEEN_KEY)) || {};
    const cut = Date.now() - 24 * 3600e3;
    const out = {};
    for (const [k, t] of Object.entries(m)) if (t >= cut) out[k] = t;
    return out;
  } catch {
    return {};
  }
}

// ---------- small helpers ----------
const fmtMoney = (v) => {
  const n = Math.abs(Number(v) || 0);
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
};
const dteOf = (exp) => {
  try {
    const d = Math.round((new Date(exp) - Date.now()) / 86400000);
    return d >= 0 ? d : 0;
  } catch {
    return 0;
  }
};
async function getJSON(url, signal) {
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
function estPrice(strike, iv, expiry) {
  const dte = Math.max(1, dteOf(expiry));
  const ivv = iv > 1 ? iv / 100 : iv || 0.2;
  return Math.max(0.05, strike * ivv * Math.sqrt(dte / 365) * 0.4);
}

// Conviction for drill-flow rows (client-side; the verdict feed uses the
// server's conviction — never mixed).
function rowConviction(p) {
  const cls = String(p.classification || "regular").toLowerCase();
  const pat = cls === "sweep" ? 24 : cls === "unusual" ? 18 : cls === "block" ? 14 : 8;
  const prem = Number(p.premium) || 0;
  const size = Math.min(30, Math.log10(Math.max(1e4, prem) / 1e4) * 9);
  const voi = Number(p.vol_oi_ratio) || 0;
  const stat = Math.min(26, Math.log10(Math.max(1, voi) + 1) * 14);
  const dte = Number(dteOf(p.expiration)) || 0;
  const urg = dte <= 1 ? 14 : dte <= 7 ? 9 : dte <= 30 ? 5 : 2;
  const conv = Math.round(Math.max(20, Math.min(99, pat + size + stat + urg)));
  return { pat: +pat.toFixed(1), size: +size.toFixed(1), stat: +stat.toFixed(1), urg: +urg.toFixed(1), conv };
}

// Map Public API flat contract list to flow-feed row shape. Exported for Jest.
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
    const mid = last || (bid + ask) / 2 || estPrice(Number(c.strike), iv, c.expiry);
    const premium = Math.round(vol * mid * 100);
    const dte = dteOf(c.expiry);
    const cls = premium >= 5e7 ? "block" : dte <= 2 ? "sweep" : "unusual";
    const p = {
      ticker, type: String(c.type || "").toLowerCase(), classification: cls,
      strike: Number(c.strike), expiration: c.expiry, timestamp: Date.now(),
      volume: vol, oi, vol_oi_ratio: voi, iv: iv < 1 ? iv * 100 : iv, premium,
    };
    const cd = rowConviction(p);
    p._conv = cd.conv;
    p._cd = cd;
    rows.push(p);
  }
  rows.sort((a, b) => b.vol_oi_ratio - a.vol_oi_ratio);
  return rows.slice(0, 100);
}

function loadPrefs() {
  try {
    const prefs = JSON.parse(localStorage.getItem(PREFS_KEY)) || {};
    const oldPoll = localStorage.getItem("fsb.pollMs");
    if (prefs.pollMs == null && oldPoll != null && Number.isFinite(Number(oldPoll)) && Number(oldPoll) >= 0) prefs.pollMs = Number(oldPoll);
    return prefs;
  } catch {
    return {};
  }
}
function loadAcked() {
  try {
    return JSON.parse(localStorage.getItem(ACK_KEY)) || {};
  } catch {
    return {};
  }
}
function dteDays(exp) {
  if (!exp) return null;
  const t = Date.parse(String(exp).length === 10 ? `${exp}T00:00:00` : exp);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.round((t - Date.now()) / 86400000));
}
const STRIPE_SORT_LABEL = {
  all: "Top score", whale: "Big money", oiconf: "ΔOI build", zerodte: "Top score",
  hedge: "Top score", fresh: "Vol/OI", mine: "Top score",
};
const scrollTo = (id) => {
  try {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch {
    /* noop */
  }
};

// ---------- component ----------
export default function FlowseekerProBlademap({ active = true }) {
  const prefs = useMemo(loadPrefs, []);
  const appSettings = useMemo(() => {
    try {
      return getSettings();
    } catch {
      return { defaultTicker: "SPY", colorBlindMode: false };
    }
  }, []);
  const [tide, setTide] = useState(loadTide);
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === "floww_settings") {
        setTide(loadTide());
        try {
          setCbMode(loadTide().colorBlindMode ?? !!getSettings().colorBlindMode);
        } catch {
          /* noop */
        }
      }
    };
    const refresh = () => onStorage({key:"floww_settings"});
    window.addEventListener("storage", onStorage);
    window.addEventListener("floww-settings-changed", refresh);
    return () => { window.removeEventListener("storage", onStorage); window.removeEventListener("floww-settings-changed", refresh); };
  }, []);
  const mode = tide.mode || "trade";
  const setMode = (m) => {
    if (!saveTide({ mode: m })) { window.alert("Layout could not be saved."); return; }
    setTide((t) => ({ ...t, mode: m }));
  };
  const [cbMode, setCbMode] = useState(tide.colorBlindMode ?? !!appSettings.colorBlindMode);

  // focus ticker defaults to floww_settings.defaultTicker, printed on Dealers cell
  const [focusTicker, setFocusTicker] = useState(appSettings.defaultTicker || "SPY");
  const [selectedRow, setSelectedRow] = useState(null);
  const [clock, setClock] = useState("");
  useEffect(() => {
    const id = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(id);
  }, []);

  // ---- verdict feed (poll + SSE share FEED_DAYS / FEED_MIN_CONVICTION) ----
  const [feed, setFeed] = useState([]);
  const [feedAt, setFeedAt] = useState("");
  const [feedErr, setFeedErr] = useState(null);
  const [feedReceived, setFeedReceived] = useState(0);
  const [pendingFeed, setPendingFeed] = useState(null);
  const feedHoverRef = useRef(false);
  const feedFocusRef = useRef(false);
  const notifyRef = useRef(false);
  const prevTopKeyRef = useRef(null);
  const kbActiveRef = useRef(false);
  const applyFeed = useCallback((alerts) => {
    const parsed = parseFeedAlerts(alerts);
    setFeedErr(null);
    if (feedHoverRef.current || feedFocusRef.current || kbActiveRef.current) {
      setPendingFeed({ rows: parsed, received: Date.now() });
    } else {
      setFeed(parsed);
      setFeedReceived(Date.now());
      setPendingFeed(null);
      setFeedAt(new Date().toLocaleTimeString());
    }
  }, []);
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    const qs = new URLSearchParams({ sort_by: "conviction", days: String(FEED_DAYS) });
    let polling = false;
    if (FEED_MIN_CONVICTION != null) qs.set("min_conviction", String(FEED_MIN_CONVICTION));
    const poll = async () => {
      if (polling || cancelled) return;
      polling = true;
      try {
        const d = await getJSON(`${API}/alerts/feed?${qs}`, ctrl.signal);
        if (!cancelled && d) {
          applyFeed(d.alerts || []);
          setFeedErr(null);
        }
      } catch (e) {
        if (!cancelled && e?.name !== "AbortError") setFeedErr("verdict feed unreachable");
      } finally {
        polling = false;
      }
    };
    poll();
    const id = setInterval(poll, 60000);
    // SSE pushes re-rank through the same parser; EventSource guarded for jsdom.
    let es = null;
    try {
      if (typeof EventSource !== "undefined") {
        es = new EventSource(`${API}/alerts/stream?days=${FEED_DAYS}`);
        es.addEventListener("alerts", (ev) => {
          try {
            const d = JSON.parse(ev.data);
            if (!cancelled && d?.alerts) applyFeed(d.alerts);
          } catch {
            /* malformed push — poll covers */
          }
        });
      }
    } catch {
      /* SSE unavailable — poll covers */
    }
    return () => {
      cancelled = true;
      ctrl.abort();
      clearInterval(id);
      try {
        es?.close();
      } catch {
        /* noop */
      }
    };
  }, [active, applyFeed]);

  // ---- pulse scan ----
  const [scan, setScan] = useState([]);
  const [scanAt, setScanAt] = useState("");
  const [pendingScan, setPendingScan] = useState(null);
  const [scanMeta, setScanMeta] = useState({ mode: null, stale: false, symbols: 0 });
  const [baselines, setBaselines] = useState({});
  const [history, setHistory] = useState({});
  const [refreshTick, setRefreshTick] = useState(0);
  const [pollMs, setPollMs] = useState(prefs.pollMs ?? 60000);
  const [universe, setUniverse] = useState(prefs.universe || ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]);
  const [alertScore, setAlertScore] = useState(prefs.alertScore ?? 85);
  const [notify, setNotify] = useState(!!prefs.notify);
  const [alertUnivOnly, setAlertUnivOnly] = useState(prefs.alertUnivOnly ?? true);
  const prevKeysRef = useRef(null);
  const firstSeenRef = useRef(loadFirstSeen());
  const hadDataRef = useRef(false);
  useEffect(() => {
    notifyRef.current = notify;
  }, [notify]);
  useEffect(() => {
    hadDataRef.current = scan.length > 0;
  }, [scan]);

  const markNew = useCallback((rows, m) => {
    const keyOf = (r) => `${r.under}|${r.type}|${r.strike}|${r.exp}`;
    const keys = new Set(rows.map(keyOf));
    const prev = prevKeysRef.current;
    if (prev && prev.mode === m) {
      for (const r of rows) r._new = !prev.keys.has(keyOf(r));
    }
    prevKeysRef.current = { mode: m, keys };
    return rows;
  }, []);

  // Local alert log powers the Changed cell (counts) + rule-builder "Alert rule
  // fired" matching via the same engine the old tape used.
  const [alertLog, setAlertLog] = useState([]);
  const alertSeenRef = useRef(loadAlertSeen());
  const alertCfgRef = useRef({});
  useEffect(() => {
    alertCfgRef.current = { minScore: alertScore, allow: alertUnivOnly ? universe : null };
  }, [alertScore, alertUnivOnly, universe]);
  const ingestScanAlerts = useCallback(
    (rows) => {
      // NOTE: evalAlerts import intentionally dropped — the verdict feed is the
      // server engine now. The Changed cell counts server feed arrivals + newly
      // seen high-score contracts locally (deduped, no notifications here).
      const cfg = alertCfgRef.current;
      const allow = cfg.allow ? new Set(cfg.allow) : null;
      const now = Date.now();
      const seen = alertSeenRef.current;
      const fresh = [];
      for (const r of rows) {
        if (!r._new) continue;
        if (allow && !allow.has(r.under)) continue;
        if ((r.score ?? 0) < (cfg.minScore ?? 85)) continue;
        const key = `score|${r.under}|${r.type}|${r.strike}|${r.exp}`;
        if ((seen[key] ?? 0) >= now - 30 * 60e3) continue;
        seen[key] = now;
        fresh.push({
          key, rule: "SCORE", under: r.under, type: r.type, strike: r.strike,
          exp: r.exp, score: r.score, t: now, time: fmtClock(now, true), day: sessionDay(),
        });
      }
      if (fresh.length) {
        try {
          localStorage.setItem(ALERTSEEN_KEY, JSON.stringify(alertSeenRef.current));
        } catch {
          /* private mode */
        }
        setAlertLog((prev) => [...fresh, ...prev].slice(0, 100));
      }
    },
    [],
  );

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    const runOnce = async () => {
      if (ctrl._polling || cancelled) return;
      ctrl._polling = true;
      try {
        const d = await getJSON(`${API}/scan?limit=300`, ctrl.signal);
        if (cancelled) return;
        if (d && Array.isArray(d.rows)) {
          const regimes = d.regimes || {};
          const prevOI = d.prev_oi || {};
          const rows = d.rows.map((r) => {
            const row = mkScanRow(r[0], r[2], r[3], r[4], Number(r[5]) || 0, Number(r[6]) || 0,
              r[7], r[8], Number(r[9]) || null, regimes[r[0]] || null);
            row.osi = typeof r[1] === "string" ? r[1] : null;
            const quote = (d.quote_truth || {})[`${row.under}|${row.type}|${row.strike}|${row.exp}`];
            row.premiumSource = "estimate";
            if (quote) {
              if (Number.isFinite(quote.premium_true) && quote.premium_true >= 0) {
                row.premium = quote.premium_true;
                row.premiumSource = "quote";
              }
              if (["ASK", "BID"].includes(quote.nbbo_side)) row.nbbo = quote.nbbo_side;
              if (["ASK", "BID"].includes(quote.signed_side)) row.signedSide = quote.signed_side;
              if (["quote", "tick"].includes(quote.sign_method)) row.signMethod = quote.sign_method;
              if (Number.isFinite(quote.velocity_per_min)) row.velocity = quote.velocity_per_min;
            }
            row.oiTag = (d.oi_tags || {})[r[1]] || (row.exp && row.exp <= sessionDay() ? { expiring: true } : null);
            row.oiChg = row.oiTag?.expiring || row.oiTag?.rollover ? null : oiChange(row.oi, prevOI[r[1]]);
            if (row.oiChg && row.oiTag) row.oiChg.tag = row.oiTag;
            row.oiChgPct = row.oiChg ? row.oiChg.pct : null;
            return row;
          });
          markNew(rows, "market");
          firstSeenRef.current = annotateFirstSeen(rows, firstSeenRef.current).seen;
          try {
            localStorage.setItem(FIRSTSEEN_KEY, JSON.stringify(firstSeenRef.current));
          } catch {
            /* private mode */
          }
          ingestScanAlerts(rows);
          const nSyms = new Set(rows.map((x) => x.under)).size;
          if (d.baselines) setBaselines(d.baselines);
          const meta = {
            mode: "market", stale: !!d.stale, symbols: nSyms,
            source: d.source || d.data_source || "Source not supplied",
            received: Date.now(), age: d.cache_age_seconds ?? 0, retry: d.retry_after_seconds ?? null,
            ttl: d.scan_ttl ?? 60, budget: d.budget ?? null,
          };
          if (feedHoverRef.current || feedFocusRef.current || kbActiveRef.current) setPendingScan({ rows, meta });
          else { setScan(rows); setPendingScan(null); setScanMeta(meta); setScanAt(new Date().toLocaleTimeString()); }
        }
      } catch (e) {
        if (cancelled || e?.name === "AbortError") return;
        setScanMeta((m) => ({ ...m, stale: hadDataRef.current, err: !hadDataRef.current }));
      } finally {
        ctrl._polling = false;
      }
    };
    runOnce();
    const id = pollMs > 0 ? setInterval(runOnce, Math.max(5000, pollMs)) : null;
    return () => {
      cancelled = true;
      ctrl.abort();
      if (id) clearInterval(id);
    };
  }, [active, refreshTick, pollMs, markNew, ingestScanAlerts]);



  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    const load = async () => {
      try {
        const d = await getJSON(`${API}/scan/history?days=14`, ctrl.signal);
        if (!cancelled && d?.tickers && Object.keys(d.tickers).length) setHistory(d.tickers);
      } catch {
        /* sparklines and streaks just stay empty */
      }
    };
    load();
    const id = setInterval(load, 15 * 60e3);
    return () => {
      cancelled = true;
      ctrl.abort();
      clearInterval(id);
    };
  }, [active]);

  // ---- dealers cell owns its own always-on fetch: never cold on load ----
  const [dealers, setDealers] = useState({ regime: null, heat: null, at: "", err: false, loading: true });
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    setDealers({ regime: null, heat: null, at: "", err: false, loading: true });
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      const [reg, heat] = await Promise.all([
        getJSON(`${API}/regime/${focusTicker}`, ctrl.signal).catch(() => null),
        getJSON(`${BACKEND_URL}/api/heatmap/${focusTicker}?expiries=6&mode=day`, ctrl.signal).catch(() => null),
      ]);
      if (cancelled) return;
      inFlight = false;
      setDealers({ regime: reg, heat, at: new Date().toLocaleTimeString(), err: !reg && !heat, loading: false });
    };
    load();
    const id = setInterval(load, 60000);
    return () => {
      cancelled = true;
      ctrl.abort();
      clearInterval(id);
    };
  }, [active, focusTicker, refreshTick]);

  // ---- vpin stub (real route) ----
  const [vpin, setVpin] = useState(null);
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    getJSON(`${BACKEND_URL}/api/vpin/${focusTicker}`, ctrl.signal)
      .then((d) => {
        if (!cancelled) setVpin(d);
      })
      .catch(() => {
        if (!cancelled) setVpin(null);
      });
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [active, focusTicker]);

  // ---- trust row ----
  const [calibBands, setCalibBands] = useState([]);
  const [setupStats, setSetupStats] = useState(null);
  useEffect(() => {
    if (!active) return;
    let alive = true;
    fetch(`${API}/alerts/quality?days=30`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d) setCalibBands(d.conviction_calibration || []);
      })
      .catch(() => {});
    fetch(`${API}/journal/stats?days=90`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d) setSetupStats(d);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [active, refreshTick]);

  // ---- drill flow feed (public → cvserver fallback), only while drilling ----
  const [drill, setDrill] = useState(null); // {ticker}
  const [drillRows, setDrillRows] = useState([]);
  const [drillState, setDrillState] = useState("idle");
  const [drillFilter, setDrillFilter] = useState("all");
  const [drillDte, setDrillDte] = useState("all");
  const [drillSel, setDrillSel] = useState(null);
  useEffect(() => {
    if (!active || !drill?.ticker) return;
    const t = drill.ticker;
    setDrillRows([]);
    setDrillSel(null);
    setDrillState("loading");
    let cancelled = false;
    const ctrl = new AbortController();
    const poll = async () => {
      let rows = null;
      try {
        const d = await getJSON(
          `${BACKEND_URL}/api/public/chain/${t}?expirations=4&fields=strike,type,expiration,volume,openInterest,impliedVolatility,bid,ask,lastPrice`,
          ctrl.signal,
        );
        if (cancelled) return;
        if (d?.ok && Array.isArray(d.contracts) && d.contracts.length > 0) {
          rows = mapPublicChainToRows(d.contracts, d.spot, t);
        }
      } catch {
        /* fall through to cvserver */
      }
      if (!rows) {
        try {
          const d = await getJSON(`${API}/chain/${t}?fields=oi,volume,iv,bid,ask,lastPrice`, ctrl.signal);
          if (cancelled) return;
          const params = d.params || [];
          const vi = (name) => {
            const i = params.indexOf(name);
            return i > 0 ? i - 1 : -1;
          };
          const iVol = vi("volume"), iOI = vi("openInterest"), iIV = vi("impliedVolatility");
          const iBid = vi("bid"), iAsk = vi("ask"), iLast = vi("lastPrice");
          const cvRows = [];
          for (const exp of d.chain || []) {
            for (const s of exp.strikes || []) {
              const strike = s[0];
              for (const [sideU, vals] of [["CALL", s[1] || []], ["PUT", s[2] || []]]) {
                const vol = Number(vals[iVol]) || 0;
                if (vol < NOISE_FLOOR * 20) continue;
                const oi = Number(vals[iOI]) || 0;
                const voi = oi > 0 ? vol / oi : vol / 100;
                if (voi < 0.4) continue;
                const iv = Number(vals[iIV]) || 0;
                const last = Number(vals[iLast]) || 0;
                const mid = last || ((Number(vals[iBid]) || 0) + Number(vals[iAsk]) || 0) / 2 || estPrice(strike, iv, exp.expiration);
                const premium = Math.round(vol * mid * 100);
                const dte = dteOf(exp.expiration);
                const cls = premium >= 5e7 ? "block" : dte <= 2 ? "sweep" : "unusual";
                const p = {
                  ticker: t, type: sideU.toLowerCase(), classification: cls,
                  strike, expiration: exp.expiration, timestamp: Date.now(),
                  volume: vol, oi, vol_oi_ratio: voi, iv: iv < 1 ? iv * 100 : iv, premium,
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
        } catch {
          /* keep last data */
        }
      }
      if (!cancelled) { setDrillRows(rows || []); setDrillState(rows == null ? "error" : "ready"); }
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => {
      cancelled = true;
      ctrl.abort();
      clearInterval(id);
    };
  }, [active, drill]);

  // A stable baseline survives both in-app navigation and browser visibility changes.
  const [visitBaseline,setVisitBaseline]=useState(()=>{
    try { return Number(sessionStorage.getItem("th-last-visit")) || Date.now(); } catch { return Date.now(); }
  });
  const lastSeenRef=useRef(visitBaseline);
  useEffect(()=>{
    const leave=()=>{lastSeenRef.current=Date.now();try{sessionStorage.setItem("th-last-visit",String(lastSeenRef.current));}catch{}};
    const returnToPage=()=>setVisitBaseline(lastSeenRef.current);
    const visibility=()=>document.hidden?leave():returnToPage();
    if(active)returnToPage();else leave();
    document.addEventListener("visibilitychange",visibility);
    return ()=>{leave();document.removeEventListener("visibilitychange",visibility);};
  },[active]);

  // ---- screens ----
  const customScreens = tide.screens || [];
  const allScreens = useMemo(
    () => [...BUILTIN_SCREENS, ...customScreens.map((s) => ({ ...s, custom: true }))],
    [customScreens],
  );
  const [screenId, setScreenId] = useState(prefs.screenId || "all");
  const screen = allScreens.find((s) => s.id === screenId) || allScreens[0];
  const [editingScreen, setEditingScreen] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const [showCols, setShowCols] = useState(false);

  // today's knobs (behind Filters disclosure; active ones surface as chips)
  const [knobType, setKnobType] = useState(prefs.knobType ?? "all");
  const [knobMinVol, setKnobMinVol] = useState(prefs.knobMinVol ?? 0);
  const [knobMinScore, setKnobMinScore] = useState(prefs.knobMinScore ?? 0);
  const [knobQ, setKnobQ] = useState(prefs.knobQ ?? "");
  const [knobDteMin, setKnobDteMin] = useState(prefs.knobDteMin ?? null);
  const [knobDteMax, setKnobDteMax] = useState(prefs.knobDteMax ?? null);
  const [universeOnly, setUniverseOnly] = useState(prefs.universeOnly ?? false);
  const [sortPreset, setSortPreset] = useState(prefs.sortPreset || { key: "score", dir: "desc" });
  const [feedOrder, setFeedOrder] = useState(prefs.feedOrder ?? "conviction");
  const [showHistory, setShowHistory] = useState(false);
  // Rule visibility chips (⋯ menu): hide whole rule families from the feed
  // and the Changed counts. Visibility only — the server engine still fires.
  const [hiddenRules, setHiddenRules] = useState(prefs.hiddenRules ?? []);
  const toggleRule = useCallback((rule) => {
    setHiddenRules((h) => (h.includes(rule) ? h.filter((r) => r !== rule) : [...h, rule]));
  }, []);
  const [acked, setAcked] = useState(loadAcked);
  const [planned, setPlanned] = useState({});
  const [forcing, setForcing] = useState(false);
  const [kbIdx, setKbIdx] = useState(-1);
  const applyPendingReadings = () => {
    if (pendingFeed) { setFeed(pendingFeed.rows); setFeedReceived(pendingFeed.received); setFeedAt(new Date(pendingFeed.received).toLocaleTimeString()); }
    if (pendingScan) { setScan(pendingScan.rows); setScanMeta(pendingScan.meta); setScanAt(new Date(pendingScan.meta.received).toLocaleTimeString()); }
    setPendingScan(null); setPendingFeed(null); setKbIdx(-1); kbActiveRef.current = false;
  };
  const knobQRef = useRef(null);
  useEffect(() => {
    try { localStorage.setItem("fsb.pollMs", String(pollMs)); localStorage.setItem(PREFS_KEY, JSON.stringify({pollMs, universe, alertScore, notify, alertUnivOnly, screenId, knobType, knobMinVol, knobMinScore, knobQ, knobDteMin, knobDteMax, universeOnly, sortPreset, feedOrder, hiddenRules})); }
    catch { /* Preference changes remain usable but are not marked saved. */ }
  }, [pollMs, universe, alertScore, notify, alertUnivOnly, screenId, knobType, knobMinVol, knobMinScore, knobQ, knobDteMin, knobDteMax, universeOnly, sortPreset, feedOrder, hiddenRules]);

  const ack = useCallback((key) => {
    setAcked((m) => {
      const n = { ...m, [key]: Date.now() };
      try {
        localStorage.setItem(ACK_KEY, JSON.stringify(n));
      } catch {
        /* private mode */
      }
      return n;
    });
  }, []);

  const tickerFacts = useMemo(() => {
    const roll = tickerRollup(scan, 1e9);
    const out = {};
    for (const e of roll) {
      const st = streakOf(history[e.under] || []);
      out[e.under] = {
        premConc: e.prem,
        pcr: e.pcr,
        sigma: null,
        streak: st ? st.n : 0,
        streakMult: st ? st.mult : null,
        streakMedian: st ? st.median : null,
      };
    }
    for (const alert of feed) {
      const observed = Date.parse(alert.asof_ts || "");
      const ticker = alert.under || alert.ticker;
      if (String(alert.rule).toUpperCase() === "SIGMA" && Number.isFinite(alert.sigma) &&
          Number.isFinite(observed) && Date.now() - observed >= 0 && Date.now() - observed <= 900000) {
        out[ticker] = { ...out[ticker], sigma: alert.sigma };
      }
    }
    return out;
  }, [scan, history, feed, clock]);

  const screenedScans = useMemo(() => {
    let rows = applyScreenToScans(scan, screen, { universe, tickerFacts, alerts: feed });
    const q = knobQ.trim().toUpperCase();
    rows = rows.filter((r) => {
      if (universeOnly && !universe.includes(r.under)) return false;
      if (knobType !== "all" && r.type !== knobType) return false;
      if (knobMinVol && r.vol < knobMinVol) return false;
      if (knobMinScore && r.score < knobMinScore) return false;
      if (q && !(r.under || "").toUpperCase().includes(q)) return false;
      const dd = dteDays(r.exp);
      if (knobDteMin != null && (dd == null || dd < knobDteMin)) return false;
      if (knobDteMax != null && (dd == null || dd > knobDteMax)) return false;
      return true;
    });
    const k = sortPreset.key, dir = sortPreset.dir === "desc" ? -1 : 1;
    rows = [...rows].sort((a, b) => {
      let av = a[k], bv = b[k];
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      av = av == null ? -Infinity : av;
      bv = bv == null ? -Infinity : bv;
      return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
    });
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan, screen, universe, tickerFacts, feed, universeOnly, knobType, knobMinVol, knobMinScore, knobQ, knobDteMin, knobDteMax, sortPreset]);

  const screenedFeed = useMemo(
    () => applyScreenToAlerts(feed, screen, { universe, scanRows: scan, tickerFacts }).filter(a => {
      const ticker=a.under || a.ticker, type=String(a.type || "").toLowerCase();
      if(universeOnly && !universe.includes(ticker))return false;
      if(knobType!=="all" && type!==knobType)return false;
      if(knobQ && !String(ticker).toUpperCase().includes(knobQ.trim().toUpperCase()))return false;
      const row=scan.find(r=>r.under===ticker && r.type===type && r.exp===a.exp && Number(r.strike)===Number(a.strike));
      if(knobMinVol && (!row || row.vol<knobMinVol))return false;
      if(knobMinScore && (!row || row.score<knobMinScore))return false;
      const dd=dteDays(a.exp);
      if(knobDteMin!=null && (dd==null || dd<knobDteMin))return false;
      if(knobDteMax!=null && (dd==null || dd>knobDteMax))return false;
      return true;
    }),
    [feed, screen, universe, scan, tickerFacts, universeOnly, knobType, knobQ, knobMinVol, knobMinScore, knobDteMin, knobDteMax],
  );
  const visibleFeed = useMemo(() => {
    const scope = alertUnivOnly ? screenedFeed.filter((a) => universe.includes(a.under || a.ticker)) : screenedFeed;
    const ruleOk = (a) => !hiddenRules.includes(String(a.rule || "").toUpperCase());
    const live = (showHistory ? scope : scope.filter((a) => !acked[a.key])).filter(ruleOk);
    if (feedOrder === "new") {
      return [...live].sort((a, b) => Date.parse(b.asof_ts || 0) - Date.parse(a.asof_ts || 0));
    }
    return live;
  }, [screenedFeed, alertUnivOnly, universe, showHistory, acked, feedOrder, hiddenRules]);

  const elapsedScanAge = (scanMeta.age || 0) + (scanMeta.received ? (Date.now() - scanMeta.received) / 1000 : 0);
  const withheld = feedErr || !feedReceived || Date.now() - feedReceived > 120000 ? "Alert feed is unavailable or out of date" : null;
  // Per-rule counts for the Vector header (the old tape's session summary).
  const ruleCounts = useMemo(() => {
    const c = {};
    for (const a of screenedFeed) {
      const r = String(a.rule || "").toUpperCase();
      if (r) c[r] = (c[r] || 0) + 1;
    }
    return c;
  }, [screenedFeed]);
  const bestFeed = useMemo(
    () => [...visibleFeed].sort((a, b) => (b.conviction ?? 0) - (a.conviction ?? 0))[0] || null,
    [visibleFeed],
  );
  const tradeNow = withheld ? null : tradeNowOf(visibleFeed, TRADE_NOW_FLOOR);
  useEffect(() => {
    const top = tradeNow;
    if (!top) return;
    const observed = Date.parse(top.asof_ts || "");
    const previous = prevTopKeyRef.current;
    prevTopKeyRef.current = { key: top.key, observed };
    if (!previous || previous.key === top.key || !(observed > previous.observed)) return;
    if (!notifyRef.current || !document.hidden || !("Notification" in window) || Notification.permission !== "granted") return;
    try {
      const dir = directionOf(top);
      new Notification(`Trade now: ${top.under} ${top.strike}${String(top.type || "").toUpperCase()[0] || ""}`, {
        body: `${dir.arrow} ${dir.word} · ${top.conviction} conviction · ${top.why || top.rule}`,
      });
    } catch { /* Notification support varies by browser. */ }
  }, [tradeNow]);
  const feedBody = feedBodyOf(visibleFeed, tradeNow);

  const heartbeat = useMemo(() => {
    const hb = pulseState({
      mode: scanMeta.mode, stale: !!scanMeta.stale,
      age: elapsedScanAge, retry: scanMeta.retry,
      hasData: scan.length > 0, hasError: !!scanMeta.err,
      ttl: scanMeta.ttl || 60,
    });
    const b = scanMeta.budget;
    if (hb.label === "LIVE") hb.label = "AVAILABLE";
    const next = scanMeta.ttl ? Math.max(0, scanMeta.ttl - elapsedScanAge) : null;
    hb.hint = `${hb.hint}${next != null ? ` · next scan ~${elapsedClock(next)}` : ""}${b ? ` · ${b.used}/${b.hourly_cap} calls this hour` : ""}`;
    return hb;
  }, [scanMeta, scan.length, elapsedScanAge]);

  // ---- answer cells ----
  const moneyFacts = useMemo(() => {
    const roll = tickerRollup(screenedScans, 8);
    const top = roll.slice(0, 3);
    const sigmas = {};
    for (const a of screenedFeed) {
      if (String(a.rule || "").toUpperCase() === "SIGMA" && a.sigma != null) sigmas[a.under] = a.sigma;
    }
    return { roll, top, sigmas };
  }, [screenedScans, screenedFeed]);

  const changedFacts = useMemo(() => {
    const keys=new Set(screenedScans.map(r=>`${r.under}|${r.type}|${r.strike}|${r.exp}`));
    const local=alertLog.filter(a=>a.t>visitBaseline && keys.has(`${a.under}|${a.type}|${a.strike}|${a.exp}`) && !hiddenRules.includes(String(a.rule || "").toUpperCase()));
    const changed=visibleFeed.filter(a=>Date.parse(a.asof_ts || "")>visitBaseline);
    return {n:local.length+changed.length,scope:local.length,feedNew:changed.length};
  },[alertLog,screenedScans,visibleFeed,hiddenRules,visitBaseline]);

  const dealersFacts = useMemo(() => {
    const reg = dealers.regime || {};
    const flip = finite(reg.gamma_flip);
    const spot = finite(dealers.heat?.spot);
    const dist = spot != null && flip != null && flip > 0 ? (spot - flip) / flip * 100 : null;
    const total = reg.total_gex;
    const short = total != null ? total < 0 : null;
    return { reg, flip, dist, total, short, at: dealers.at, err: dealers.err };
  }, [dealers]);

  // ---- market tape: one line under the cards ----
  const tape = useMemo(() => {
    let notl = 0, cv = 0, pv = 0, unusual = 0;
    for (const r of screenedScans) {
      notl += r.notional || 0;
      if (r.type === "call") cv += r.vol || 0;
      else pv += r.vol || 0;
      if ((r.volOI || 0) >= 2) unusual++;
    }
    const tv = cv + pv;
    return { notl, tv, cpct: tv > 0 ? Math.round((cv / tv) * 100) : null, unusual };
  }, [screenedScans]);

  const degradedLine = useMemo(() => {
    if (scanMeta.err) return "feed unreachable · retrying";
    if (scanMeta.stale) return `stale · next slot in ${elapsedClock(scanMeta.retry ?? scanMeta.ttl ?? 60)}`;
    if (scanMeta.mode === "fallback" || !scanMeta.mode) return "waiting on market-wide scan";
    if ((scanMeta.budget?.used ?? 0) >= (scanMeta.budget?.hourly_cap ?? Infinity)) return "hourly budget spent · serving cache";
    return null;
  }, [scanMeta]);

  // ---- actions ----
  const doDrill = useCallback((row) => {
    const ticker = typeof row === "string" ? row : row?.under || row?.ticker;
    setSelectedRow(typeof row === "object" ? row : null);
    if (ticker) setFocusTicker(ticker);
    setDrill({ ticker });
    setDrillSel(null);
    if (mode === "monitor") setMode("trade");
    setTimeout(() => {
      const panel = document.getElementById("dealer-drilldown");
      panel?.scrollIntoView?.({ block: "nearest" });
      panel?.focus();
    }, 0);
  }, [mode]);
  const doWatch = useCallback((ticker) => {
    if (!ticker) return;
    setUniverse((u) => (u.includes(ticker) ? u : [...u, ticker]));
  }, []);
  const doPlan = useCallback((a) => {
    if (!a || isContextual(a)) return;
    const dir = directionOf(a);
    const seed = {
      ticker: a.under || a.ticker,
      type: String(a.type || "call").toLowerCase(),
      action: dir.cls === "bear" ? "sell" : "buy",
      strike: a.strike,
      expiry: a.exp,
      entry_date: sessionDay(),
      entry_price: null,
      underlying_reference: a.levels?.entry ?? a.est_entry ?? null,
      contract_id: a.osi || a.contract_id || null,
      stop: a.levels?.invalidation ?? null,
      target: a.levels?.target ?? null,
      setup: "tidehunter-verdict",
      conviction: a.conviction ?? null,
      why: a.why || "",
      source: "tidehunter-manual",
    };
    try {
      persistJournalSeeds([seed]);
      setPlanned((p) => ({ ...p, [a.key]: true }));
    } catch {
      window.alert("Your plan could not be saved. Check browser storage and try again.");
    }
  }, []);
  const forceRefresh = useCallback(async () => {
    setForcing(true);
    try {
      await fetch(`${API}/scan/refresh?limit=300`, { method: "POST" });
    } catch {
      /* GET below serves cache */
    }
    setForcing(false);
    setRefreshTick((t) => t + 1);
  }, []);
  const exportCSV = useCallback((rows) => {
    const blob = new Blob([scanRowsToCSV(rows)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `tidehunter-scan-${sessionDay()}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }, []);
  const toggleNotify = useCallback(async () => {
    if (!notify) {
      if (!("Notification" in window)) return;
      let perm = Notification.permission;
      if (perm === "default") {
        try {
          perm = await Notification.requestPermission();
        } catch {
          return;
        }
      }
      if (perm !== "granted") return;
    }
    setNotify((n) => !n);
  }, [notify]);
  const copyFeed = useCallback(() => {
    const tsv = visibleFeed
      .map((a) => [a.asof_ts || "", a.rule, a.under || a.ticker, a.type, a.strike, a.exp, a.conviction ?? "", a.bias || "", a.why || ""].join("\t"))
      .join("\n");
    try {
      navigator.clipboard.writeText(tsv);
    } catch {
      /* clipboard blocked */
    }
  }, [visibleFeed]);
  const clearDismissed = useCallback(() => {
    setAcked({});
    try {
      localStorage.removeItem(ACK_KEY);
    } catch {
      /* noop */
    }
  }, []);

  // ---- screen CRUD (built-ins are editable copies) ----
  const saveCustomScreen = useCallback((s) => {
    if(!s.id)s={...s,id:`custom-${Date.now()}-${Math.random().toString(36).slice(2,8)}`};
    const list = [...(loadTide().screens || [])];
    const i = list.findIndex((x) => x.id === s.id);
    if (i >= 0) list[i] = s;
    else list.push(s);
    if (!saveTide({ screens: list })) { window.alert("Screen could not be saved."); return; }
    setTide((t) => ({ ...t, screens: list }));
    setScreenId(s.id);
    setEditingScreen(null);
  }, []);
  const deleteCustomScreen = useCallback((id) => {
    const list = (loadTide().screens || []).filter((x) => x.id !== id);
    if (!saveTide({ screens: list })) { window.alert("Screen could not be saved."); return; }
    setTide((t) => ({ ...t, screens: list }));
    setScreenId("all");
    setEditingScreen(null);
  }, []);

  // ---- pulse columns per mode ----
  const colsForMode = tide.columns?.[mode] || (mode === "research" ? null : PULSE_DEFAULT_COLS);
  const visibleCols = colsForMode || PULSE_COLUMNS.map((c) => c.key);
  const setVisibleCols = (keys) => {
    const columns = { ...(tide.columns || {}), [mode]: keys };
    if (!saveTide({ columns })) { window.alert("Columns could not be saved."); return; }
    setTide((t) => ({ ...t, columns }));
  };

  // ---- keyboard nav (pulse) ----
  useEffect(() => {
    if (!active) return;
    const onKey = (e) => {
      const t = e.target;
      if (t?.closest?.('button,a,summary,tr,[role="button"],[role="dialog"],[contenteditable="true"]')) return;
      if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA")) {
        if (e.key === "Escape") t.blur();
        return;
      }
      if (e.key === "/") {
        e.preventDefault();
        knobQRef.current?.focus();
        return;
      }
      if (e.key === "r" || e.key === "R") {
        forceRefresh();
        return;
      }
      const n = screenedScans.length;
      if (!n) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        kbActiveRef.current = true; // verdict feed holds its order while navigating
        setKbIdx((k) => Math.min(n - 1, k + 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        kbActiveRef.current = true;
        setKbIdx((k) => Math.max(0, k - 1));
      } else if (e.key === "g") {
        e.preventDefault();
        kbActiveRef.current = true;
        setKbIdx(0);
      } else if (e.key === "G") {
        e.preventDefault();
        kbActiveRef.current = true;
        setKbIdx(n - 1);
      } else if (e.key === "Enter" && kbIdx >= 0 && screenedScans[kbIdx]) {
        doDrill(screenedScans[kbIdx]);
      } else if (e.key === "Escape") {
        setKbIdx(-1);
        kbActiveRef.current = false;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, screenedScans, kbIdx, forceRefresh, doDrill]);
  useEffect(() => {
    setKbIdx(-1);
    kbActiveRef.current = false;
  }, [screenId, knobQ]);

  const sortScan = (k) => {
    setSortPreset((s) => {
      if (s.key === k) return { key: k, dir: s.dir === "desc" ? "asc" : "desc" };
      const asc = k === "under" || k === "type" || k === "exp";
      return { key: k, dir: asc ? "asc" : "desc" };
    });
  };

  // The map and detail consume one displayed scope and preserve missing cells.
  const dealerData = useMemo(() => dealerSeries(dealers.heat, dealersFacts.flip), [dealers.heat, dealersFacts.flip]);
  const sourceTime = dealers.heat?.event_time || dealers.heat?.observed_at;
  const sourceMs = sourceTime ? Date.parse(sourceTime) : NaN;
  const dealerStale = !!dealers.heat?.stale || !Number.isFinite(sourceMs) || Date.now() - sourceMs > 120000;
  const lattice = useMemo(() => {
    const h = dealers.heat || {};
    const cellValues = dealerData.strikes.flatMap(s => dealerData.expiries.map(e => dealerData.valueAt(s,e))).filter(v=>v!=null);
    const maxAbs = Math.max(0,...cellValues.map(Math.abs));
    const cls = v => {
      if (v == null || !maxAbs) return "c0";
      const f=Math.abs(v)/maxAbs,lvl=f>0.66?3:f>0.33?2:f>0.02?1:0;
      return `${v<0?"n":"p"}${lvl}`;
    };
    return { expiries:dealerData.expiries,strikes:dealerData.strikes,val:dealerData.valueAt,cls,
      spot:dealerData.spot,callWall:h.nodes?.ceilings?.[0]?.strike ?? null,
      putWall:h.nodes?.floors?.[0]?.strike ?? null,maxPain:h.max_pain ?? h.nodes?.max_pain ?? null,
      ok:dealerData.hasData };
  }, [dealers.heat,dealerData]);

  useEffect(()=>{
    if(!active)return;
    publishScreenContext({page:"flowseeker-pro",ticker:focusTicker,dte:"all",mode,
      selectedContract:selectedRow?.osi || selectedRow?.ckey || null,
      selectedExpiry:selectedRow?.exp || selectedRow?.expiration || null,selectedStrike:selectedRow?.strike ?? null,
      expiryRange:[knobDteMin,knobDteMax],expiries:dealerData.expiries,
      observedAt:sourceTime || null});
  },[active,focusTicker,mode,selectedRow,knobDteMin,knobDteMax,dealerData,dealers.heat]);

  const drillFiltered = useMemo(() => drillRows.filter((p) => {
    const side = String(p.type || "").toLowerCase().startsWith("c") ? "CALL" : "PUT";
    const cls = String(p.classification || "").toUpperCase();
    const dte = Number(dteOf(p.expiration)) || 0;
    switch (drillDte) {
      case "0dte": if (dte !== 0) return false; break;
      case "1-7d": if (dte < 1 || dte > 7) return false; break;
      case "monthly": if (dte < 8 || dte > 35) return false; break;
      case "qtrly": if (dte < 36 || dte > 90) return false; break;
      case "leaps": if (dte < 91) return false; break;
      default: break;
    }
    switch (drillFilter) {
      case "CALL": return side === "CALL";
      case "PUT": return side === "PUT";
      case "SWEEP": return cls === "SWEEP";
      case "BLOCK": return cls === "BLOCK";
      case "high": return p._conv >= 80;
      default: return true;
    }
  }), [drillRows, drillFilter, drillDte]);

  const activeChips = [];
  if (knobType !== "all") activeChips.push(["Type", knobType]);
  if (knobMinScore > 0) activeChips.push(["Score", `≥${knobMinScore}`]);
  if (knobMinVol > 0) activeChips.push(["Vol", `≥${fmtK(knobMinVol)}`]);
  if (knobDteMin != null || knobDteMax != null) activeChips.push(["DTE", `${knobDteMin ?? 0}–${knobDteMax ?? "∞"}`]);
  if (universeOnly) activeChips.push(["Universe", `${universe.length} names`]);

  const sectionOrder = tide.sectionOrder || ["board", "vector", "pulse", "lattice", "trust"];
  const pulseRowCap = mode === "trade" ? 8 : mode === "monitor" ? 14 : 30;
  const feedCap = mode === "research" ? 5 : mode === "monitor" ? 6 : 8;

  const renderVerdictRow = (a, pinned = false) => {
    const ctx = isContextual(a);
    const dir = directionOf(a);
    const st = stageOf(a);
    const travel = targetTravelPct(a);
    const lv = a.levels || {};
    return (
      <tr
        key={a.key}
        className={`${pinned ? "pinned" : ""} ${ctx ? "contextual" : dir.cls}`}
        data-testid={pinned ? "trade-now-row" : undefined}
        onClick={ctx ? undefined : () => doDrill(a)}
        title={ctx ? (a.why || a.rule) : `${a.why || a.rule} — click to drill ${a.under || a.ticker}`}
      >
        <td className="l">
          <span className="sym">{a.under || a.ticker}</span>
          {pinned && <span className="sub">pinned · trade now</span>}
          {!pinned && a.rule && <span className="sub">{a.rule}</span>}
        </td>
        <td className="l">
          {ctx ? <span className="lo">ticker-level</span> : (
            <>{a.strike} {String(a.type || "").toUpperCase()} · {(a.exp || "").slice(5)} <span className="sub">{a.dte != null ? `${a.dte} DTE` : ""}{moneynessPct(a.under_price, a.strike) ? ` · ${moneynessPct(a.under_price, a.strike)}` : ""}</span></>
          )}
        </td>
        <td className="l">
          {ctx
            ? <span className="dir lo">— NO DIRECTION</span>
            : <span className={`dir ${dir.cls}`}>{dir.arrow} {dir.word}</span>}
        </td>
        <td className="l">
          <span className="stage" title={a.rule === "OICONF" ? "Overnight OI held" : a.rule === "FOLLOW" || a.rule === "SIGMA" ? "Repeated days or σ spike" : "Fresh print"}>
            <span className="d">
              {[1, 2, 3].map((i) => (
                <React.Fragment key={i}>
                  {i > 1 && <s className={i <= st.n ? "f" : ""} />}
                  <i className={i <= st.n ? "f" : ""} />
                </React.Fragment>
              ))}
            </span>
            <small>{st.label} · {st.n}/3</small>
          </span>
        </td>
        <td className="l">
          <span className="conf" title={`conviction ${a.conviction}/99 · tier ${a.tier || "—"}`}>
            <b>{a.conviction}</b>
            <span className="bar"><i style={{ width: `${Math.max(0, Math.min(100, Number(a.conviction) || 0))}%` }} /></span>
            <small>{a.tier || "—"}</small>
          </span>
        </td>
        <td className="l">
          <span className="state">
            <b>{a.why || a.rule}</b>
            {a.context?.activity_summary && <small>{a.context.activity_summary}</small>}
            {a.context?.dealer_positioning && <small>{a.context.dealer_positioning}</small>}
            {!ctx && (a.context?.institutional_indicators || []).slice(0, 3).map((ind) => (
              <span key={ind} className="pl silver" style={{ marginRight: 4 }}>{ind}</span>
            ))}
          </span>
        </td>
        <td>{ctx ? <span className="lo">—</span> : <span className="lv">{lv.entry ?? a.est_entry ?? "—"}</span>}</td>
        <td>
          {ctx ? (
            <span className="lvwrap lo">—</span>
          ) : (
            <span className="lvwrap"><span className="lv dn">{lv.invalidation ?? "—"}</span></span>
          )}
          <span className="acts">
            <button type="button" className="act" onClick={(e) => { e.stopPropagation(); doDrill(a); }}>Drill</button>
            {!ctx && (
              <>
                <button type="button" className="act" onClick={(e) => { e.stopPropagation(); doWatch(a.under || a.ticker); }}>Watch</button>
                {planned[a.key]
                  ? <span className="act p" title="Saved to the journal drafts (client-side only)">Planned ✓</span>
                  : <button type="button" className="act p" title="Save to journal drafts — nothing is sent to a broker" onClick={(e) => { e.stopPropagation(); doPlan(a); }}>Plan</button>}
                <button type="button" className="act" onClick={(e) => { e.stopPropagation(); ack(a.key); }}>Ack</button>
              </>
            )}
          </span>
        </td>
        <td>{ctx ? <span className="lo">—</span> : <span className="lv up">{lv.target ?? "—"}</span>}</td>
        <td className={Number(a.move_pct) < 0 ? "dn" : "up"}>
          {ctx || a.move_pct == null ? <span className="lo">—</span> : (
            <>{formatMovePct(a.move_pct)}{travel != null && <span className="sub"> {travel}% of target</span>}</>
          )}
          <span className="sub" style={{ display: "block" }}>{ageOf(a)} ago</span>
        </td>
      </tr>
    );
  };

  const pulseCell = (r, key) => {
    switch (key) {
      case "firstSeen": return <span className="fsb-sub">{fmtClock(r.firstSeen)}{r._new && " ·new"}</span>;
      case "under": return <span className="sym">{r.under}</span>;
      case "strike": return r.strike % 1 === 0 ? r.strike.toFixed(0) : r.strike.toFixed(1);
      case "type": return String(r.type || "").toUpperCase();
      case "exp": return (r.exp || "").slice(5);
      case "dte": return r.dte == null ? "—" : `${r.dte}d`;
      case "ftype": return <span className={`pl ${(r.ftype || "").toLowerCase()}`}>{(r.ftype || "").toUpperCase()}</span>;
      case "arch": return r.arch ? <span className="pl gold">{r.arch}</span> : <span className="lo">—</span>;
      case "score": return (
        <b title={r._parts ? `vol/OI ${r._parts.pos} · size ${r._parts.size} · notional ${r._parts.notl} · urgency ${r._parts.urg} · OTM ${r._parts.otm}${r._parts.nudge ? ` · γ-nudge +${r._parts.nudge}` : ""}${r._parts.band ? " · informed band +4" : ""}` : undefined}>
          {r.score}
        </b>
      );
      case "vol": return fmtK(r.vol);
      case "oi": return fmtK(r.oi);
      case "oiChgPct": return r.oiChg ? (
        <span className={r.oiChg.pct >= 0 ? "up" : "dn"} title={`OI ${r.oiChg.abs >= 0 ? "+" : ""}${fmtK(r.oiChg.abs)} vs prior session`}>
          {(r.oiChg.pct >= 0 ? "+" : "") + (r.oiChg.pct * 100).toFixed(0)}% {oiHeldLabel(r.oiChgPct)}
        </span>
      ) : <span className="lo">{r.oiTag?.expiring ? "Expiring - change withheld" : r.oiTag?.rollover ? "Rollover - change withheld" : "— no prior day"}</span>;
      case "volOI": return r.volOI >= 99 ? "99+" : `${(r.volOI || 0).toFixed(1)}x`;
      case "premium": return <span title={r.premiumSource === "quote" ? "Premium from observed quote" : "Estimated premium — no quote feed on this data"}>{r.premiumSource === "quote" ? "" : "~"}{fmtUSD(r.premium)}</span>;
      case "notional": return fmtUSD(r.notional);
      case "iv": return fmtIV(r.iv);
      case "delta": return r.delta == null ? "—" : `${r.deltaEst ? "~" : ""}${Number(r.delta).toFixed(2)}`;
      case "trend": {
        const days = cleanHistory(history[r.under] || []).slice(-7);
        if (days.length < 2) return <span className="lo">—</span>;
        const maxv = Math.max(1, ...days.map((d) => d.total_vol || 0));
        return (
          <span className="th-trend" title={`${r.under}: last ${days.length}d volume`}>
            {days.map((d, di) => (
              <i
                key={di}
                className={di === days.length - 1 ? "now" : ""}
                style={{ height: `${Math.max(2, Math.round(((d.total_vol || 0) / maxv) * 12))}px` }}
                title={`${d.date}: ${fmtK(d.total_vol)} vol`}
              />
            ))}
          </span>
        );
      }
      default: return String(r[key] ?? "—");
    }
  };

  return (
    <div className="th-root" data-mode={mode} data-cb={cbMode ? "on" : "off"} data-testid="tide-root">
      <div className="th-shell">
        <aside className="th-side" aria-label="Sections">
          <div className="th-brand"><i>◢</i><b>Tidehunter Pro</b></div>
          <button type="button" className="th-nav" onClick={() => scrollTo("board")}>Board</button>
          <button type="button" className="th-nav" onClick={() => scrollTo("vector")}>Vector · direction</button>
          <button type="button" className="th-nav" onClick={() => scrollTo("pulse")}>Pulse · live flow</button>
          <button type="button" className="th-nav" onClick={() => doDrill(focusTicker)}>Lattice · positioning</button>
          <button type="button" className="th-nav" onClick={() => scrollTo("trust")}>Trust</button>

          <button type="button" className="th-nav" onClick={() => scrollTo("settings")}>Settings</button>
          <span className="th-sp" />
          <div className="th-st">
            <span><b>{scanMeta.err ? "UNAVAILABLE" : !scanMeta.mode ? "LOADING" : scanMeta.stale ? "STALE" : "AVAILABLE"}</b> <span className={`dot ${heartbeat.dot}`} />{scanMeta.source || "Source not supplied"} · {scanMeta.symbols || "—"} symbols</span>
            <span>{scanMeta.budget ? `${scanMeta.budget.used}/${scanMeta.budget.hourly_cap} calls this hour` : "budget n/a"}{scanMeta.ttl ? ` · next scan ~${elapsedClock(Math.max(0, scanMeta.ttl - elapsedScanAge))}` : ""}</span>
            <span>Order-flow imbalance, price impact: no feed</span>
          </div>
        </aside>

        <div className="th-content">
          <div className="th-topbar">
            <label className="th-pill" title="Focused ticker — drives the Dealers cell and Lattice">
              <span className="k">Ticker</span>
              <select
                className="th-tickersel" value={focusTicker}
                onChange={(e) => { setFocusTicker(e.target.value); setSelectedRow(null); setDrill(null); setDrillSel(null); setDrillRows([]); }}
                aria-label="Focused ticker"
              >
                {Array.from(new Set([focusTicker, ...universe])).map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <button type="button" className="th-pill" title="Jump to the screener" onClick={() => scrollTo("screens")}>
              <span className="k">Screen</span><span className="v">{screen.label}</span><span className="c">▾</span>
            </button>
            <span className="th-sp" />
            <span className="th-pill th-regime" title={heartbeat.hint}>
              <span className={`dot ${heartbeat.dot}`} />
              <span className="v">{dealersFacts.reg.current_state || "—"}{dealersFacts.reg.is_warming ? " · warming" : ""}</span>
            </span>
            <button type="button" className="th-icb" title="Refresh now" onClick={forceRefresh} disabled={forcing}>
              {forcing ? "…" : "↻"}
            </button>
            <button type="button" className="th-icb" title="Settings" onClick={() => scrollTo("settings")}>⚙</button>
          </div>

          <div className="th-page">
            {/* ===== ORDERED SECTIONS ===== */}
            {sectionOrder.map((sec) => {
              if (sec === "board") return (<React.Fragment key="board">
            {/* ===== BOARD ===== */}
            <div className="th-sec" id="board">
              <div className="th-ph">
                <div>
                  <h1>Board</h1>
                  <div className="th-meta">
                    <b>{scanMeta.err ? "UNAVAILABLE" : !scanMeta.mode ? "LOADING" : scanMeta.stale ? "STALE" : "AVAILABLE"}</b>
                    <span className="k">Last updated</span><span>{scanAt || feedAt || "—"}</span>
                    <span className="k">Showing</span><span>{screenedScans.length} contracts · {visibleFeed.length} signals · {screen.label}</span>
                    <span className="k">{clock}</span>
                  </div>
                </div>
                <div className="th-seg">
                  <span className="lbl">Layout</span>
                  <div className="th-segbar">
                    {(["trade", "monitor", "research"]).map((m) => (
                      <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}>{m}</button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="th-answers">
                <button type="button" className="th-ans top" data-testid="cell-trade" onClick={() => scrollTo("vector")}>
                  <span className="q"><span className="lbl">Trade now</span><span className="tag">{screen.label}</span></span>
                  {withheld ? (
                    <span className="v">Verdict withheld · {withheld}</span>
                  ) : tradeNow ? (
                    <>
                      <span className="v">
                        {`${tradeNow.under || tradeNow.ticker} ${tradeNow.strike}${String(tradeNow.type || "").toUpperCase()[0] || ""} · ${directionOf(tradeNow).word} · ${tradeNow.dte ?? dteDays(tradeNow.exp) ?? "expiry unknown"}${tradeNow.dte != null || dteDays(tradeNow.exp) != null ? "d" : ""} — ${tradeNow.conviction} conviction`}
                      </span>
                      <span className="s">
                        <b className={directionOf(tradeNow).cls === "bear" ? "dn" : "up"}>{directionOf(tradeNow).arrow} {directionOf(tradeNow).word}</b>
                        <span>{tradeNow.why}</span>
                        {tradeNow.levels && <span>Entry <b>{tradeNow.levels.entry}</b> · Stop <b>{tradeNow.levels.invalidation}</b> · Target <b>{tradeNow.levels.target}</b></span>}
                        {tradeNow.move_pct != null && <span>Moved <b>{formatMovePct(tradeNow.move_pct)}</b>{targetTravelPct(tradeNow) != null && ` · ${targetTravelPct(tradeNow)}% of target`}</span>}
                      </span>
                      <span className="f">fired {ageOf(tradeNow)} ago · {LEVELS_LABEL}{tradeNow.under_price && tradeNow.strike ? ` · ${moneynessPct(tradeNow.under_price, tradeNow.strike)}` : ""}</span>
                    </>
                  ) : (
                    <>
                      <span className="v">
                        {visibleFeed.length && bestFeed
                          ? `No eligible trade · highest reading ${bestFeed.conviction} ${bestFeed.under || bestFeed.ticker || ""}`
                          : "Server feed empty — ranking client-side"}
                      </span>
                      <span className="f">{feedErr || `${scan.length} contracts screened · needs a fresh, complete contract and ${TRADE_NOW_FLOOR}+ conviction`}</span>
                    </>
                  )}
                  {degradedLine && <span className="f warn">{degradedLine}</span>}
                </button>

                <button type="button" className="th-ans" data-testid="cell-money" onClick={() => scrollTo("pulse")}>
                  <span className="q"><span className="lbl">Money building</span><span className="tag">{screen.label}</span></span>
                  {moneyFacts.top.length ? (
                    <>
                      <span className="v">{moneyFacts.top[0].under} · where money is building · ~{fmtUSD(moneyFacts.top[0].prem)} est. premium</span>
                      <span className="s">
                        {moneyFacts.top.map((e) => (
                          <span
                            key={e.under}
                            title={`${e.under}: ~${fmtUSD(e.prem)} est premium · ${e.count} contracts · ${e.callPct}% calls / ${100 - e.callPct}% puts · top score ${e.maxScore}`}
                          >
                            {e.under} ~{fmtUSD(e.prem)}
                            <span className="sub"> {e.callPct}% calls</span>
                            {e.regime ? <b> {e.regime === "positive" ? "γ+" : "γ−"}</b> : null}
                            {e.pcr != null ? ` · PCR ${e.pcr}` : ""}
                            {moneyFacts.sigmas[e.under] != null ? ` · ${moneyFacts.sigmas[e.under]}σ server-confirmed` : ""}
                            {tickerFacts[e.under]?.streak >= 2 ? ` · ${tickerFacts[e.under].streak}d streak ≥${tickerFacts[e.under].streakMult}×` : ""}
                            {(() => {
                              const ds = cleanHistory(history[e.under] || []).slice(-10);
                              if (ds.length < 3) return null;
                              const mx = Math.max(1, ...ds.map((d) => d.total_vol || 0));
                              return (
                                <span className="th-spark" aria-hidden="true" title={`${e.under}: last ${ds.length} sessions volume`}>
                                  {ds.map((d) => (
                                    <i
                                      key={d.date}
                                      style={{ height: `${Math.max(12, Math.round(((d.total_vol || 0) / mx) * 100))}%` }}
                                      title={`${d.date}: ${fmtK(d.total_vol)} vol`}
                                    />
                                  ))}
                                </span>
                              );
                            })()}
                          </span>
                        ))}
                      </span>
                      <span className="f">premium is an estimate · σ from server SIGMA alerts only</span>
                    </>
                  ) : (
                    <><span className="v">No concentration read yet</span><span className="f">waiting on the market-wide scan</span></>
                  )}
                  {degradedLine && <span className="f warn">{degradedLine}{scanMeta.stale ? " · σ/ΔOI unavailable while stale" : ""}</span>}
                </button>

                <button type="button" className="th-ans" data-testid="cell-changed" onClick={() => scrollTo("vector")}>
                  <span className="q"><span className="lbl">Changed since you looked</span><span className="tag">{screen.label}</span></span>
                  <span className="v">{changedFacts.n ? `${changedFacts.n} new readings` : "Nothing new"} since {fmtClock(visitBaseline)}</span>
                  <span className="s">{changedFacts.feedNew} alerts · {changedFacts.scope} new screened contracts</span>
                  <span className="f">Current screen only · re-arms on return</span>
                  {degradedLine && <span className="f warn">{degradedLine}</span>}
                </button>

                <button type="button" className="th-ans" data-testid="cell-dealers" onClick={() => doDrill(focusTicker)}>
                  <span className="q"><span className="lbl">Dealers · {focusTicker}</span><span className="tag">focused</span></span>
                  {dealersFacts.err ? (
                    <><span className="v">{focusTicker} · {dealers.loading ? "GEX loading…" : "dealer data unavailable"}</span><span className="f">regime + heatmap fetch in flight</span></>
                  ) : (
                    <>
                      <span className="v">
                        {dealersFacts.short == null ? "Dealer read pending" : dealersFacts.short ? "Short gamma" : "Long gamma"}
                        {dealersFacts.flip != null && ` · flip $${dealersFacts.flip}`}
                        {dealersFacts.dist != null && ` · ${Math.abs(dealersFacts.dist).toFixed(1)}% ${dealersFacts.dist > 0 ? "above" : "below"}`}
                      </span>
                      <span className="s">
                        <span>{dealersFacts.dist == null ? "Spot distance unavailable" : dealersFacts.dist < 0 ? "Spot below flip" : dealersFacts.dist > 0 ? "Spot above flip" : "Spot at flip"}</span>
                        <span>regime <b>{dealersFacts.reg.current_state || "—"}</b></span>
                        {dealersFacts.reg.vol_env && <span>vol <b>{dealersFacts.reg.vol_env}</b></span>}
                      </span>
                      <span className="f">display-scale gamma · refreshed {dealersFacts.at || "—"}</span>
                    </>
                  )}
                  {dealerStale && <span className="f warn">Dealer source is stale or its observation time is unknown</span>}
                </button>
              </div>
            </div>

            {/* ===== MARKET TAPE — one line under the cards ===== */}
            <div className="th-tape" data-testid="market-tape" title={heartbeat.hint}>
              <span>Contracts <b>{screenedScans.length}/{scan.length}</b></span>
              <span>Notional Σ <b>{fmtUSD(tape.notl)}</b><span className="sub"> est.</span></span>
              <span>Call/Put <b>{tape.cpct == null ? "—" : `${tape.cpct}%/${100 - tape.cpct}%`}</b><span className="sub"> vol</span></span>
              <span>Unusual ≥2× <b>{tape.unusual}</b></span>
              <span><span className={`dot ${heartbeat.dot}`} />{heartbeat.label}
                {scanMeta.budget ? ` · ${scanMeta.budget.used}/${scanMeta.budget.hourly_cap} calls this hour` : ""}
                {scanMeta.ttl ? ` · next ~${elapsedClock(Math.max(0, scanMeta.ttl - elapsedScanAge))}` : ""}
              </span>
              <span>Updated <b>{scanMeta.stale ? `STALE · ${scanAt || "—"}` : scanAt || "—"}</b>
                {elapsedScanAge >= 5 ? ` · cached ${elapsedClock(elapsedScanAge)} ago` : ""}
              </span>
              <span>Source <b>{scanMeta.source || "—"}</b></span>
              <span>{clock}</span>
            </div>

            {/* ===== SCREENS ===== */}
            <div className="th-screens" id="screens" data-testid="screens">
              <div className="th-segbar" role="tablist" aria-label="Screens">
                {allScreens.map((s) => (
                  <button
                    key={s.id} type="button" role="tab" aria-selected={screenId === s.id}
                    aria-pressed={screenId === s.id}
                    onClick={() => setScreenId(s.id)}
                  >
                    {s.label}
                    <small>{s.custom ? applyScreenToScans(scan, s, { universe, tickerFacts }).length : ""}</small>
                  </button>
                ))}
              </div>
              <button type="button" className="th-chipb" onClick={() => { setEditingScreen(screen.custom ? {...screen,saved:true} : { id: `custom-${Date.now()}`, copyOf:screen.id, label: `${screen.label} copy`, rule: "ANY", conditions: [], custom: true }); setShowFilters(false); setShowMore(false); }}>
                ✎ Edit screen
              </button>
              <button type="button" className="th-chipb" onClick={() => { setShowFilters((v) => !v); setShowMore(false); setEditingScreen(null); }}>
                Filters{activeChips.length ? ` · ${activeChips.length}` : ""}
              </button>
              {activeChips.map(([k, v]) => <span key={k} className="th-fchip">{k} <b>{v}</b></span>)}
              <button type="button" className="th-chipb" onClick={() => { setShowMore((v) => !v); setShowFilters(false); setEditingScreen(null); }}>⋯</button>

              {showFilters && (
                <div className="th-disc" data-testid="filters-panel">
                  <span className="lbl">Type</span>
                  <select value={knobType} onChange={(e) => setKnobType(e.target.value)}>
                    <option value="all">All</option><option value="call">Calls</option><option value="put">Puts</option>
                  </select>
                  <input className="w70" type="number" min="0" placeholder="Min vol" value={knobMinVol || ""} onChange={(e) => setKnobMinVol(Number(e.target.value) || 0)} />
                  <input className="w70" type="number" min="0" placeholder="Min score" value={knobMinScore || ""} onChange={(e) => setKnobMinScore(Number(e.target.value) || 0)} />
                  <input ref={knobQRef} className="w110" placeholder="Ticker  ( / )" value={knobQ} onChange={(e) => setKnobQ((e.target.value || "").toUpperCase())} />
                  <span className="lbl">DTE</span>
                  <input className="w70" type="number" min="0" placeholder="min" value={knobDteMin ?? ""} onChange={(e) => setKnobDteMin(e.target.value === "" ? null : Number(e.target.value))} />
                  <input className="w70" type="number" min="0" placeholder="max" value={knobDteMax ?? ""} onChange={(e) => setKnobDteMax(e.target.value === "" ? null : Number(e.target.value))} />
                  <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <input type="checkbox" checked={universeOnly} onChange={(e) => setUniverseOnly(e.target.checked)} /> My universe
                  </label>
                  <input
                    className="w170" defaultValue={universe.join(",")} placeholder="Universe…"
                    title="Comma-separated tickers"
                    onBlur={(e) => {
                      const u = (e.target.value || "").toUpperCase().split(/[,\s]+/).filter(Boolean);
                      if (u.length) setUniverse(u);
                    }}
                  />
                  <span className="lbl">Alert ≥</span>
                  <input className="w70" type="number" min="50" max="100" value={alertScore} onChange={(e) => setAlertScore(Math.max(50, Math.min(100, parseInt(e.target.value, 10) || 85)))} />
                  <span className="th-brk" />
                  <span className="lbl">Sort</span>
                  {[["Top score", { key: "score", dir: "desc" }], ["Big money", { key: "notional", dir: "desc" }],
                    ["Unusual", { key: "volOI", dir: "desc" }], ["Short fuse", { key: "dte", dir: "asc" }],
                    ["New arrivals", { key: "firstSeen", dir: "desc" }]].map(([l, s]) => (
                    <button key={l} type="button" className={`th-chipb${sortPreset.key === s.key && sortPreset.dir === s.dir ? " on" : ""}`} onClick={() => setSortPreset(s)}>{l}</button>
                  ))}
                  <span className="lbl">Poll</span>
                  <select value={pollMs} onChange={(e) => setPollMs(Number(e.target.value))}>
                    <option value={5000}>5s</option><option value={15000}>15s</option>
                    <option value={30000}>30s</option><option value={60000}>60s</option><option value={0}>Off</option>
                  </select>
                  <button type="button" className="th-chipb" onClick={forceRefresh}>⟳ Force</button>
                  <button type="button" className="th-chipb" disabled={!screenedScans.length} onClick={() => exportCSV(screenedScans)}>⤓ CSV</button>
                  <button
                    type="button" className="th-chipb"
                    title="Reset type, volume, score, ticker, DTE and universe filters to off"
                    onClick={() => { setKnobType("all"); setKnobMinVol(0); setKnobMinScore(0); setKnobQ(""); setKnobDteMin(null); setKnobDteMax(null); setUniverseOnly(false); }}
                  >
                    Reset filters
                  </button>
                </div>
              )}
              {showMore && (
                <div className="th-disc" data-testid="more-menu">
                  <button type="button" className={`th-chipb${notify ? " on" : ""}`} onClick={toggleNotify}>🔔 Notify{notify ? " on" : ""}</button>
                  <button type="button" className={`th-chipb${alertUnivOnly ? " on" : ""}`} onClick={() => setAlertUnivOnly((v) => !v)}>🎯 Alerts scoped to universe</button>
                  <span className="th-rulechips" title="Hide whole rule families from the feed and Changed counts">
                    {RULE_LIST.map((r) => (
                      <button
                        key={r} type="button"
                        className={`th-chipb${hiddenRules.includes(r) ? "" : " on"}`}
                        onClick={() => toggleRule(r)}
                      >
                        {r}
                      </button>
                    ))}
                  </span>
                  <button type="button" className="th-chipb" onClick={() => setFeedOrder((o) => (o === "conviction" ? "new" : "conviction"))}>
                    Feed · {feedOrder === "conviction" ? "conviction rank" : "newest first"}
                  </button>
                  <button type="button" className="th-chipb" onClick={copyFeed}>⧉ Copy feed</button>
                  <button type="button" className="th-chipb" onClick={clearDismissed}>Clear dismissed</button>
                  <button type="button" className="th-chipb" onClick={() => setShowHistory((v) => !v)}>Show history · {Object.keys(acked).length}</button>
                </div>
              )}
              {editingScreen && (
                <ScreenBuilder
                  initial={editingScreen}
                  onSave={saveCustomScreen}
                  onDelete={deleteCustomScreen}
                  onCancel={() => setEditingScreen(null)}
                />
              )}
            </div>

              </React.Fragment>);
              if (sec === "vector") {
                return (
                  <div className="th-sec" id="vector" key="vector">
                    <div className="th-sh">
                      <h2>Vector</h2>
                      <span className="th-meta"><b>{scanMeta.err ? "UNAVAILABLE" : !scanMeta.mode ? "LOADING" : scanMeta.stale ? "STALE" : "AVAILABLE"}</b> direction board · ranked by conviction · {visibleFeed.length} in screen · {screen.label}</span>
                      <span className="th-sp" />
                      <span className="th-rulecounts" title="Signals per rule in this screen">
                        {Object.entries(ruleCounts).map(([k, v]) => <span key={k} className="th-fchip">{k} <b>{v}</b></span>)}
                      </span>
                      {(pendingFeed || pendingScan) && (
                        <button type="button" className="th-chipb on" onClick={applyPendingReadings}>
                          Apply new readings
                        </button>
                      )}
                    </div>
                    <div
                      className="th-tbl" data-testid="vector-feed"
                      onMouseEnter={() => { feedHoverRef.current = true; }}
                      onMouseLeave={() => { feedHoverRef.current = false; }}
                      onFocusCapture={() => { feedFocusRef.current = true; }}
                      onBlurCapture={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) feedFocusRef.current = false; }}
                    >
                      {withheld ? (
                        <div className="th-empty">Verdict withheld · {withheld}</div>
                      ) : visibleFeed.length === 0 ? (
                        <div className="th-empty">{feedErr || "No signals in this screen yet — verdict feed is polling."}</div>
                      ) : (
                        <table>
                          <thead><tr>
                            <th className="l">Symbol</th><th className="l">Contract</th><th className="l">Direction</th>
                            <th className="l">Stage</th><th className="l">Conviction</th><th className="l">State</th>
                            <th>Price</th><th>Invalidation</th><th>Target</th><th>Moved</th>
                          </tr></thead>
                          <tbody>
                            {tradeNow && renderVerdictRow(tradeNow, true)}
                            {feedBody.slice(0, showHistory ? 50 : feedCap).map((a) => renderVerdictRow(a))}
                          </tbody>
                        </table>
                      )}
                      <div className="th-tblfoot">
                        <span>Stage: Early = fresh print · Building = FOLLOW/SIGMA · Confirmed = OICONF</span>
                        <span>{LEVELS_LABEL} — edit before you plan</span>
                        <span>Plan writes a journal note only · nothing is sent to a broker</span>
                      </div>
                    </div>
                  </div>
                );
              }
              if (sec === "pulse") {
                return (
                  <div className="th-sec" id="pulse" key="pulse">
                    <div className="th-sh">
                      <h2>Pulse</h2>
                      <span className="th-meta"><b>{scanMeta.err ? "UNAVAILABLE" : !scanMeta.mode ? "LOADING" : scanMeta.stale ? "STALE" : "AVAILABLE"}</b> screened contracts · {screenedScans.length} of {scan.length} · {screen.label}</span>
                      <span className="th-sp" />
                      {(pendingFeed || pendingScan) && <button type="button" className="th-chipb on" onClick={applyPendingReadings}>Apply new readings</button>}
                      <button type="button" className="th-chipb" aria-pressed={showCols} onClick={() => setShowCols((v) => !v)}>
                        Columns · {visibleCols.length} of {PULSE_COLUMNS.length}
                      </button>
                    </div>
                    {showCols && (
                      <div className="th-disc" data-testid="column-chooser">
                        {PULSE_COLUMNS.map((c) => (
                          <label key={c.key} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                            <input
                              type="checkbox"
                              checked={visibleCols.includes(c.key)}
                              onChange={(e) => {
                                const next = e.target.checked
                                  ? [...visibleCols, c.key]
                                  : visibleCols.filter((k) => k !== c.key);
                                setVisibleCols(PULSE_COLUMNS.map((x) => x.key).filter((k) => next.includes(k)));
                              }}
                            />
                            {c.label}
                          </label>
                        ))}
                        <button type="button" className="th-chipb" onClick={() => setVisibleCols([...PULSE_DEFAULT_COLS])}>Reset to 10 default</button>
                      </div>
                    )}
                    <div className="th-tbl" data-testid="pulse-table" onMouseEnter={() => { feedHoverRef.current = true; }} onMouseLeave={() => { feedHoverRef.current = false; }} onFocusCapture={() => { feedFocusRef.current = true; }} onBlurCapture={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) feedFocusRef.current = false; }}>
                      {scan.length === 0 ? (
                        <div className="th-empty">
                          {scanMeta.err ? "Scan unreachable — backend /scan failing, retrying." : "Scanning market flow…"}
                          {scanMeta.retry ? ` Next slot in ${elapsedClock(scanMeta.retry)}.` : ""}
                        </div>
                      ) : screenedScans.length === 0 ? (
                        <div className="th-empty">No contracts pass this screen.</div>
                      ) : (
                        <table className="th-stab">
                          <thead><tr>
                            {PULSE_COLUMNS.filter((c) => visibleCols.includes(c.key)).map((c) => (
                              <th key={c.key} className={`l${sortPreset.key === c.key ? " on" : ""}`} onClick={() => sortScan(c.key)}>
                                {c.label}{sortPreset.key === c.key ? (sortPreset.dir === "desc" ? " ▾" : " ▴") : ""}
                              </th>
                            ))}
                          </tr></thead>
                          <tbody>
                            {screenedScans.slice(0, pulseRowCap).map((r, i) => {
                              const isCall = r.type === "call";
                              const isTop = i === 0 && sortPreset.key === "score" && sortPreset.dir === "desc" && (r.score ?? 0) >= 90;
                              return (
                                <tr
                                  key={`${r.under}-${r.strike}-${r.type}-${r.exp}-${i}`}
                                  className={`${kbIdx === i ? "kbcursor " : ""}${isTop ? "top" : ""}${r._new ? "new" : ""}`}
                                  onClick={() => doDrill(r)}
                                >
                                  {PULSE_COLUMNS.filter((c) => visibleCols.includes(c.key)).map((c) => (
                                    <td key={c.key} className={c.key === "score" ? scoreGradeOf(r.score) : ""}>
                                      {c.key === "firstSeen" && r._new ? <span className="th-newdot" title="New this refresh" /> : null}
                                      {pulseCell(r, c.key)}
                                      {c.key === "under" && (
                                        <span className="sub"> {(r.exp || "").slice(5)}{isCall ? " · CALL" : " · PUT"}</span>
                                      )}
                                    </td>
                                  ))}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      )}
                      <div className="th-tblfoot">
                        <span><kbd>j</kbd><kbd>k</kbd> move</span><span><kbd>Enter</kbd> drill</span>
                        <span><kbd>/</kbd> ticker</span><span><kbd>r</kbd> force refresh</span>
                        <span>ΔOI held = positioning stuck · faded = intraday churn</span>
                      </div>
                    </div>
                  </div>
                );
              }
              if (sec === "lattice") {
                return (
                  <div className="th-sec" id="lattice" key="lattice">
                    <div className="th-sh">
                      <h2>Lattice · {focusTicker}</h2>
                      <span className="th-meta"><b>{dealers.loading ? "LOADING" : dealersFacts.err ? "UNAVAILABLE" : dealerStale ? "STALE / TIME UNKNOWN" : "AVAILABLE"}</b> dealer positioning · display-scale gamma · refreshed {dealersFacts.at || "—"}</span>
                    </div>
                    <div className="th-lat" data-testid="lattice">
                      <div className="th-lath">
                        <div className="th-chips">
                          <span className="th-mchip">Spot<b>{lattice.spot ?? "—"}</b></span>
                          <span className="th-mchip">Flip<b>{dealersFacts.flip ?? "—"}</b></span>
                          <span className="th-mchip">Dist<b>{dealersFacts.dist != null ? `${dealersFacts.dist.toFixed(2)}%` : "—"}</b></span>
                          <span className="th-mchip">Net gamma<b>{dealersFacts.total != null ? fmtMoney(dealersFacts.total) : "—"}</b></span>
                          <span className="th-mchip">Shown gamma<b>{dealerData.total != null ? fmtMoney(dealerData.total) : "—"}</b></span>
                          <span className="th-mchip">Regime<b>{dealersFacts.reg.current_state || "—"}</b></span>
                          {dealersFacts.reg.vol_env && <span className="th-mchip">Vol<b>{dealersFacts.reg.vol_env}</b></span>}
                        </div>
                      </div>
                      <div className="th-keys">
                        <span className="lbl">Key levels</span>
                        <span className="th-key">Gamma flip<b>{dealersFacts.flip ?? "—"}</b></span>
                        <span className="th-key">Call wall<b>{lattice.callWall ?? "—"}</b></span>
                        <span className="th-key">Put wall<b>{lattice.putWall ?? "—"}</b></span>
                        <span className="th-key">Max pain<b>{lattice.maxPain ?? "—"}</b></span>
                      </div>
                      {lattice.ok ? (
                        <>
                          <div className="th-grid" style={{ gridTemplateColumns: `70px repeat(${lattice.expiries.length}, minmax(85px, 1fr))` }} role="table" aria-label={`Net gamma by strike for ${focusTicker}`}>
                            <div className="th-hd">Strike ↓</div>
                            {lattice.expiries.map((e) => <div key={e} className="th-hd">{String(e).slice(5)}</div>)}
                            {lattice.strikes.map((s) => (
                              <React.Fragment key={s}>
                                <div className="th-sk">{s}</div>
                                {lattice.expiries.map((e) => {
                                  const v = lattice.val(s, e);
                                  return (
                                    <div key={`${s}${e}`} className={`th-c ${lattice.cls(v)}${lattice.spot === s ? " spot" : ""}`} title={`${s} · ${e}: ${v == null ? "Unavailable" : fmtMoney(v)}`}>
                                      {v == null ? "—" : fmtMoney(v)}
                                    </div>
                                  );
                                })}
                              </React.Fragment>
                            ))}
                          </div>
                          <div className="th-latfoot">
                            <span>Long gamma dampens moves · short gamma amplifies</span>
                            <span>Display-scale gamma only — never mixed with the model-feature scale</span>
                          </div>
                        </>
                      ) : (
                        <div className="th-empty">{focusTicker} · {dealers.loading ? "GEX loading…" : "dealer data unavailable"}</div>
                      )}
                    <DealerDrilldown ticker={focusTicker} series={dealerData} regime={dealersFacts.reg} loading={dealers.loading} error={dealers.err} stale={dealerStale} colorBlind={cbMode} />
                      <div className="th-drill" data-testid="drill">
                        <div className="th-drill-h">
                          <span>Drill · {drill?.ticker || focusTicker} available options activity</span>
                          {!drill && (
                            <button type="button" className="th-chipb" onClick={() => setDrill({ ticker: focusTicker })}>Open drill</button>
                          )}
                          {drill && (
                            <button type="button" className="th-chipb" onClick={() => { setDrill(null); setDrillRows([]); }}>Close</button>
                          )}
                          <span className="th-chips-inline">
                            {[["all", "All"], ["CALL", "Calls"], ["PUT", "Puts"], ["SWEEP", "Sweep"], ["BLOCK", "Block"], ["high", "≥80"]].map(([v, l]) => (
                              <button key={v} type="button" className={`th-chip${drillFilter === v ? " on" : ""}`} onClick={() => setDrillFilter(v)}>{l}</button>
                            ))}
                          </span>
                          <span className="th-chips-inline">
                            {[["all", "All"], ["0dte", "0DTE"], ["1-7d", "1-7D"], ["monthly", "Mo"], ["qtrly", "Qtr"], ["leaps", "LEAPS"]].map(([v, l]) => (
                              <button key={v} type="button" className={`th-chip${drillDte === v ? " on" : ""}`} onClick={() => setDrillDte(v)}>{l}</button>
                            ))}
                          </span>
                          <span className="th-legendline">Classification estimates: sweep = short expiry; block = large premium. Neither proves a routed sweep or negotiated trade. Unusual = high volume versus open interest.</span>
                        </div>
                        {drill ? (
                          drillFiltered.length === 0 ? (
                            <div className="th-empty">{drillState === "loading" ? `Loading unusual options activity for ${drill.ticker}…` : drillState === "error" ? `Flow unavailable for ${drill.ticker}` : `No contracts match for ${drill.ticker}`}</div>
                          ) : (
                            <table className="th-dtab">
                              <thead><tr>
                                <th className="l">Ticker</th><th className="l">Type</th><th className="l">Side</th><th>Strike</th>
                                <th>DTE</th><th>Day $</th><th>V/OI</th><th>Conv</th>
                              </tr></thead>
                              <tbody>
                                {drillFiltered.slice(0, 40).map((p, i) => (
                                  <tr
                                    key={`${p.ticker}-${p.timestamp}-${i}`}
                                    className={drillSel === p ? "sel" : ""}
                                    tabIndex={0}
                                    onClick={() => { setDrillSel(p); setSelectedRow(p); }}
                                    onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ev.stopPropagation(); setDrillSel(p); setSelectedRow(p); } }}
                                  >
                                    <td className="l sym">{p.ticker}</td>
                                    <td className="l lo">{String(p.classification || "—").toUpperCase()}</td>
                                    <td className={`l ${String(p.type).toLowerCase().startsWith("c") ? "up" : "dn"}`}>{String(p.type).toUpperCase()}</td>
                                    <td>{Number(p.strike).toFixed(0)}</td>
                                    <td>{dteOf(p.expiration)}d</td>
                                    <td>{fmtMoney(p.premium)}</td>
                                    <td>{Number(p.vol_oi_ratio || 0).toFixed(1)}</td>
                                    <td>{p._conv}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )
                        ) : (
                          <div className="th-empty">Drill opens from any card, feed row, or table row.</div>
                        )}
                        {drillSel && (
                          <div className="th-sel">
                            <b>{drillSel.ticker} ${Number(drillSel.strike).toFixed(0)} {String(drillSel.type).toUpperCase()}</b>
                            <span> conviction {drillSel._conv}/99 = pattern {drillSel._cd.pat} + size {drillSel._cd.size} + unusualness {drillSel._cd.stat} + urgency {drillSel._cd.urg}</span>
                            <span> classification {drillSel.classification} · vol/OI {Number(drillSel.vol_oi_ratio || 0).toFixed(1)}x · est. notional {fmtMoney(drillSel.premium)}</span>
                          </div>
                        )}
                        <div className="th-micro">
                          <span>VPIN {vpin?.vpin != null ? Number(vpin.vpin).toFixed(3) : "— no feed"}</span>
                          <span>Order imbalance — unavailable</span>
                          <span data-testid="spread-cost-state">Spread-cost history unavailable · mid-quote estimates are not executable costs.</span>
                          <span>Price impact — unavailable</span>
                          <span className="th-risk">Paper/educational only — not a trade recommendation.</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              }
              if (sec === "trust") {
                return (
                  <div className="th-sec" id="trust" key="trust">
                    <div className="th-sh"><h2>Is it working?</h2>
                      <span className="th-meta">hit = moved ≥0.5% in the claimed direction · 30-day window · journal 90 days</span>
                    </div>
                    <div className="th-stats" data-testid="trust-row">
                      {(calibBands.length ? calibBands : [{ band: "<50" }, { band: "50-59" }, { band: "60-74" }, { band: "75+" }]).map((b) => {
                        const thin = (b.n_measured ?? 0) < 10;
                        return (
                          <div key={b.band} className={`th-stat${thin ? " thin" : ""}`} title={`${b.n ?? 0} alerts · ${b.n_measured ?? 0} measured${thin ? " · too few to trust" : ""}`}>
                            <span className="lbl">{b.band} conviction</span>
                            <b>{b.hit_rate != null ? `${Math.round(b.hit_rate * 100)}%` : "—"}<small>n {b.n_measured ?? 0}{thin ? " · too few" : ""}</small></b>
                            <span className="bar"><i style={{ width: `${Math.round((b.hit_rate || 0) * 100)}%` }} /></span>
                          </div>
                        );
                      })}
                      {setupStats && setupStats.overall?.n > 0
                        ? Object.entries(setupStats.by_setup || {}).slice(0, 2).map(([name, s]) => {
                          const n = (s.wins ?? 0) + (s.losses ?? 0);
                          return (
                            <div key={name} className={`th-stat${n < 10 ? " thin" : ""}`} title={`journal 90d · ${name}: ${s.wins}W/${s.losses}L${s.avg_return != null ? `, avg ${(s.avg_return * 100).toFixed(1)}%` : ""}`}>
                              <span className="lbl">Journal · {name}</span>
                              <b>{Math.round((s.win_rate || 0) * 100)}%<small>{s.wins}W/{s.losses}L{n < 10 ? " · too few" : ""}</small></b>
                              <span className="bar"><i style={{ width: `${Math.round((s.win_rate || 0) * 100)}%` }} /></span>
                            </div>
                          );
                        })
                        : (
                          <div className="th-stat thin" title="no closed journaled trades in 90d">
                            <span className="lbl">Journal</span>
                            <b>—<small>no closed trades</small></b>
                            <span className="bar"><i style={{ width: "0%" }} /></span>
                          </div>
                        )}
                    </div>
                  </div>
                );
              }
              return null;
            })}

            {/* ===== SETTINGS ===== */}
            <div className="th-sec" id="settings">
              <div className="th-sh"><h2>Settings</h2>
                <span className="th-meta">saved in floww Settings · this browser · follows the app&apos;s existing store</span>
              </div>
              <div className="th-set" data-testid="settings-table">
                <table>
                  <thead><tr><th className="l">Screen</th><th>Rules</th><th className="l">Type</th><th className="l">Default sort</th><th className="l">Status</th><th /></tr></thead>
                  <tbody>
                    {allScreens.map((s) => (
                      <tr key={s.id} className={s.id === screenId ? "sel" : ""}>
                        <td className="l sym">{s.label}</td>
                        <td>{s.custom ? (s.conditions || []).length + 1 : RULE_LIST.length}</td>
                        <td className="l">{s.custom ? "mine" : "built-in"}</td>
                        <td className="l">{s.custom ? "Top score" : (STRIPE_SORT_LABEL[s.id] || "Top score")}</td>
                        <td className="l">{s.id === screenId ? "Active" : "Ready"}</td>
                        <td className="l">
                          {s.custom ? (
                            <>
                              <button type="button" className="th-chipb" onClick={() => setEditingScreen({ ...s })}>edit</button>{" "}
                              <button type="button" className="th-chipb" onClick={() => deleteCustomScreen(s.id)}>delete</button>
                            </>
                          ) : (
                            <button
                              type="button" className="th-chipb"
                              onClick={() => setEditingScreen({
                                id: `custom-${Date.now()}`, label: `${s.label} (copy)`,
                                rule: "ANY", conditions: [], custom: true, copyOf: s.id,
                              })}
                            >
                              copy
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="th-setin">
                  <TidehunterSettings />
                </div>
              </div>
            </div>
          </div>

          <div className="th-foot">
            <span>Market source: {scanMeta.source || "not supplied"} · Dealer estimates use the available chain.</span>
            <span>Tidehunter Pro · market research</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- rule-builder screen editor ----------
function ConditionRows({conditions,onChange}) {
  const replace=(i,value)=>onChange(conditions.map((c,j)=>j===i?value:c));
  return conditions.map((c,i)=><div className="th-rule" key={i}>
    {Array.isArray(c.conditions) ? <div>
      <select aria-label={`Group ${i+1} match`} value={c.join || "AND"} onChange={e=>replace(i,{...c,join:e.target.value})}>
        <option value="AND">Match all</option><option value="OR">Match any</option>
      </select>
      <ConditionRows conditions={c.conditions} onChange={children=>replace(i,{...c,conditions:children})}/>
      <button type="button" onClick={()=>replace(i,{...c,conditions:[...c.conditions,{fact:"score",op:"≥",value:"70"}]})}>Add condition to group</button>
    </div> : <>
      <select value={c.fact} onChange={e=>replace(i,{...c,fact:e.target.value})} aria-label={`Fact ${i+1}`}>
        {[...SCAN_FACTS,...TICKER_FACTS].map(f=><option key={f} value={f}>{SCAN_FACT_LABELS[f] || TICKER_FACT_LABELS[f] || f}</option>)}
      </select>
      <select value={c.op} onChange={e=>replace(i,{...c,op:e.target.value})} aria-label={`Operator ${i+1}`}>
        {OPS.map(o=><option key={o}>{o}</option>)}
      </select>
      <input value={c.value} onChange={e=>replace(i,{...c,value:e.target.value})} aria-label={`Value ${i+1}`}/>
    </>}
    <button type="button" onClick={()=>onChange(conditions.filter((_,j)=>j!==i))} aria-label={`Remove condition ${i+1}`}>Remove</button>
  </div>);
}
function ScreenBuilder({ initial, onSave, onDelete, onCancel }) {
  const [label,setLabel]=useState(initial.label || "My screen");
  const [rule,setRule]=useState(initial.rule || "ANY");
  const [conditions,setConditions]=useState(initial.conditions || []);
  const validList=rows=>rows.every(c=>Array.isArray(c.conditions) ? c.conditions.length>0 && validList(c.conditions) : c.fact && c.op && String(c.value ?? "").trim()!=="");
  const valid=label.trim() && validList(conditions);
  const save=duplicate=>onSave({...initial,id:duplicate?undefined:initial.id,label:label.trim()+(duplicate?" copy":""),rule,conditions,custom:true,saved:true});
  return <div className="th-rb" data-testid="rule-builder">
    <label>Screen name <input value={label} onChange={e=>setLabel(e.target.value)} aria-label="Screen name"/></label>
    <p>Match all conditions and groups below. Missing readings do not match.</p>
    <ConditionRows conditions={conditions} onChange={setConditions}/>
    <label>Also require alert rule <select value={rule} onChange={e=>setRule(e.target.value)} aria-label="Alert rule fired">
      <option value="ANY">Any rule</option>{RULE_LIST.map(r=><option key={r}>{r}</option>)}
    </select></label>
    <div className="th-rb-ft">
      <button type="button" onClick={()=>setConditions(c=>[...c,{fact:"score",op:"≥",value:"70"}])}>+ condition</button>
      <button type="button" onClick={()=>setConditions(c=>[...c,{join:"OR",conditions:[{fact:"score",op:"≥",value:"70"}]}])}>+ group</button>
      {initial.saved && <button type="button" onClick={()=>onDelete(initial.id)}>Delete</button>}
      {initial.saved && <button type="button" disabled={!valid} onClick={()=>save(true)}>Duplicate</button>}
      <button type="button" onClick={onCancel}>Cancel</button>
      <button type="button" disabled={!valid} onClick={()=>save(false)}>Save screen</button>
    </div>
  </div>;
}
