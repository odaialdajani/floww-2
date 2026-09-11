// tideFeed.js — pure Tidehunter Pro helpers: verdict-feed parsing, model-level
// math, built-in screens + rule builder, pulse column defs. No React, no fetch.
// Tested in tideFeed.test.js. scanLogic.js stays untouched.

export const FEED_DAYS = 7;
export const FEED_MIN_CONVICTION = null; // pinned across poll + SSE paths
export const TRADE_NOW_FLOOR = 75;

// Model levels are constants of spot (flow_alerts.py _INVALIDATION_PCT etc).
export const STOP_PCT = 0.025;
export const TARGET_POS_PCT = 0.035;
export const TARGET_NEG_PCT = 0.055;
export const LEVELS_LABEL = "model levels · ±2.5% stop / ±3.5% target of spot (±5.5% short-γ)";

export const RULE_LIST = ["OICONF", "FOLLOW", "SIGMA", "SCORE", "WHALE", "0DTE", "SOURCE"];

// 17 screenable contract facts = 18 mkScanRow keys + oiChgPct, minus deltaEst/spot.
export const SCAN_FACTS = [
  "under", "type", "strike", "exp", "vol", "oi", "iv", "delta",
  "regime", "volOI", "notional", "dte", "premium", "score", "ftype", "arch",
  "oiChgPct",
];
export const SCAN_FACT_LABELS = {
  under: "Ticker", type: "Call/put", strike: "Strike", exp: "Expiry",
  vol: "Volume", oi: "Open interest", iv: "IV", delta: "Delta",
  regime: "Dealer γ sign", volOI: "Vol / OI", notional: "Notional",
  dte: "DTE", premium: "Est. premium", score: "Score", ftype: "Flow type",
  arch: "Archetype", oiChgPct: "ΔOI vs prior session (%)",
};
// 4 ticker facts for the rule builder.
export const TICKER_FACTS = ["premConc", "pcr", "sigma", "streak"];
export const TICKER_FACT_LABELS = {
  premConc: "Ticker premium concentration",
  pcr: "Put/call ratio",
  sigma: "σ vs baseline",
  streak: "Elevated-volume streak (days)",
};

// Pulse columns: all 17 facts; 10 default. Saved per layout mode.
export const PULSE_COLUMNS = [
  { key: "firstSeen", label: "Seen" },
  { key: "under", label: "Sym" },
  { key: "strike", label: "Strike" },
  { key: "type", label: "C/P" },
  { key: "exp", label: "Exp" },
  { key: "dte", label: "DTE" },
  { key: "ftype", label: "Type" },
  { key: "arch", label: "Signal" },
  { key: "score", label: "Score" },
  { key: "vol", label: "Size" },
  { key: "oiChgPct", label: "ΔOI" },
  { key: "premium", label: "Prem" },
  { key: "oi", label: "OI" },
  { key: "volOI", label: "Vol/OI" },
  { key: "notional", label: "Notional" },
  { key: "iv", label: "IV" },
  { key: "delta", label: "Delta" },
  // Derived (not a screen fact): 7-day volume trend from /scan/history.
  { key: "trend", label: "Trend", derived: true },
];
export const PULSE_DEFAULT_COLS = [
  "firstSeen", "under", "type", "strike", "dte", "vol",
  "oiChgPct", "premium", "ftype", "score",
];

function safeJSON(text) {
  if (text == null || text === "") return null;
  if (typeof text === "object") return text;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// Parse one raw feed row: key_levels_json + context_json were never parsed by
// the old UI. Returns the row with .levels + .context attached (null-safe).
export function parseAlert(a) {
  if (!a) return a;
  return {
    ...a,
    levels: safeJSON(a.key_levels_json) || safeJSON(a.key_levels),
    context: safeJSON(a.context_json) || safeJSON(a.context),
  };
}
export function parseFeedAlerts(alerts) {
  return (alerts || []).map(parseAlert);
}

// Rows with null bias or null strike (SIGMA / STRATEGY / SOURCE) are
// contextual: sentence only, no levels, no direction arrow, Drill only.
export function isContextual(a) {
  if (!a) return true;
  return !["BULLISH", "BEARISH"].includes(String(a.bias).toUpperCase()) || a.strike == null || a.strike === "";
}
export function isDirectional(a) {
  return !isContextual(a);
}

// Stage dots: Early = fresh print, Building = FOLLOW/SIGMA, Confirmed = OICONF.
export function stageOf(a) {
  const rule = String(a?.rule || "").toUpperCase();
  if (rule === "OICONF") return { label: "Confirmed", n: 3 };
  if (rule === "FOLLOW" || rule === "SIGMA") return { label: "Building", n: 2 };
  return { label: "Early", n: 1 };
}

// move_pct is already a percent — never multiply by 100.
export function formatMovePct(movePct) {
  if (movePct == null || Number.isNaN(Number(movePct))) return "—";
  const v = Number(movePct);
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

// % of target travelled = move_pct ÷ target distance (fraction of spot).
export function targetTravelPct(a) {
  if (a?.move_pct == null) return null;
  const mp = Number(a.move_pct);
  const lv = a?.levels;
  if (!Number.isFinite(mp) || !lv || lv.entry == null || lv.target == null) return null;
  const entry = Number(lv.entry);
  const target = Number(lv.target);
  if (!(entry > 0)) return null;
  const distPct = ((target - entry) / entry) * 100;
  if (!Number.isFinite(distPct) || distPct === 0) return null;
  return Math.round((mp / Math.abs(distPct)) * 100);
}

export function directionOf(a) {
  const b = String(a?.bias || "").toUpperCase();
  if (b.includes("BEAR")) return { arrow: "▼", word: "BEARISH", cls: "bear" };
  if (b.includes("BULL")) return { arrow: "▲", word: "BULLISH", cls: "bull" };
  return { arrow: "—", word: "NO DIRECTION", cls: "" };
}

export function ageOf(a, now = Date.now()) {
  const ts = a?.asof_ts ? Date.parse(a.asof_ts) : null;
  if (ts == null || Number.isNaN(ts)) return "—";
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.round(m / 60)}h`;
}

// Trade-now = top directional row ≥ floor by conviction; pinned header row,
// excluded from the feed body.
export function tradeNowOf(alerts, floor = TRADE_NOW_FLOOR, now = Date.now(), maxAgeMs = 15 * 60 * 1000) {
  const today = new Intl.DateTimeFormat("en-CA", {timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(now));
  const dir = (alerts || []).filter(a => {
    const age = now - Date.parse(a.asof_ts || "");
    const expiry = Date.parse(`${a.exp}T12:00:00Z`);
    return isDirectional(a) && !!(a.under || a.ticker) && ["call","put"].includes(String(a.type).toLowerCase())
      && Number.isFinite(Number(a.strike)) && Number(a.strike) > 0
      && Number.isFinite(expiry) && new Date(expiry).toISOString().slice(0,10) === a.exp && a.exp >= today
      && /^\d{4}-\d{2}-\d{2}$/.test(a.exp || "") && Number.isFinite(Number(a.conviction))
      && Number.isFinite(age) && age >= -60000 && age <= maxAgeMs;
  });
  if (!dir.length) return null;
  const top = [...dir].sort((a, b) => (b.conviction ?? 0) - (a.conviction ?? 0))[0];
  return (top?.conviction ?? 0) >= floor ? top : null;
}
export function feedBodyOf(alerts, tradeNow) {
  if (!tradeNow) return alerts || [];
  return (alerts || []).filter((a) => a.key !== tradeNow.key);
}

// Verdict withholds when the scan is stale beyond twice its ttl.
export function verdictWithheld(scanMeta) {
  if (!scanMeta?.stale) return false;
  const age = scanMeta.age ?? 0;
  const ttl = scanMeta.ttl ?? 60;
  return age > 2 * ttl;
}

export function scanFreshness(meta, now = Date.now()) {
  const age = Number.isFinite(meta?.age) && meta.age >= 0 && Number.isFinite(meta?.received)
    ? meta.age + Math.max(0, now - meta.received) / 1000 : null;
  const ttl = Number.isFinite(meta?.ttl) && meta.ttl > 0 ? meta.ttl : 60;
  const stale = !!meta?.stale || (age != null && age > 2 * ttl);
  const status = meta?.err ? "UNAVAILABLE" : !meta?.mode ? "LOADING" : stale ? "STALE" : age == null ? "AGE UNKNOWN" : "AVAILABLE";
  return {age, stale, status};
}

// ΔOI read: held = positioning stuck, faded = intraday churn.
export function oiHeldLabel(oiChgPct) {
  if (oiChgPct == null) return "— no prior day";
  return oiChgPct >= 0 ? "held" : "faded";
}

// Moneyness of the alert's under_price vs strike, as a signed % string.
export function moneynessPct(underPrice, strike) {
  const u = Number(underPrice);
  const k = Number(strike);
  if (!(u > 0) || !(k > 0)) return null;
  const pct = ((u - k) / k) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

// ── Screens ─────────────────────────────────────────────────────────────
// Built-ins filter AND rank every section. rank: [key, dir] over scan rows;
// alertRank over feed rows. matchAlert keeps the feed coherent with the screen.
function byScoreDesc(a, b) {
  return (b.score ?? 0) - (a.score ?? 0);
}
export const BUILTIN_SCREENS = [
  {
    id: "all", label: "All flow",
    matchScan: () => true, matchAlert: () => true,
    rankScan: byScoreDesc, rankAlert: (a, b) => (b.conviction ?? 0) - (a.conviction ?? 0),
  },
  {
    id: "whale", label: "Whale blocks",
    matchScan: (r) => (r.premium ?? 0) >= 1e6 || r.ftype === "block" || r.arch === "WHALE",
    matchAlert: (a) => (a.premium ?? 0) >= 1e6 || String(a.rule || "").toUpperCase() === "WHALE",
    rankScan: (a, b) => (b.premium ?? 0) - (a.premium ?? 0),
    rankAlert: (a, b) => (b.premium ?? 0) - (a.premium ?? 0),
  },
  {
    id: "oiconf", label: "OI-confirmed",
    matchScan: (r) => (r.oiChgPct ?? 0) >= 0.2,
    matchAlert: (a) => String(a.rule || "").toUpperCase() === "OICONF" || (a.oi_chg_pct ?? 0) >= 0.2,
    rankScan: (a, b) => (b.oiChgPct ?? 0) - (a.oiChgPct ?? 0),
    rankAlert: (a, b) => (b.conviction ?? 0) - (a.conviction ?? 0),
  },
  {
    id: "zerodte", label: "0DTE lottos",
    matchScan: (r) => r.dte != null && r.dte <= 1,
    matchAlert: (a) => a.dte != null && a.dte <= 1,
    rankScan: byScoreDesc,
    rankAlert: (a, b) => (b.conviction ?? 0) - (a.conviction ?? 0),
  },
  {
    id: "hedge", label: "Hedges",
    matchScan: (r) => r.arch === "HEDGE" || (r.type === "put" && r.dte != null && r.dte >= 30),
    matchAlert: (a) => String(a.type || "").toLowerCase().startsWith("p") && a.dte != null && a.dte >= 30,
    rankScan: byScoreDesc,
    rankAlert: (a, b) => (b.conviction ?? 0) - (a.conviction ?? 0),
  },
  {
    id: "fresh", label: "Fresh positioning",
    matchScan: (r) => r.arch === "FRESH" || (r.volOI ?? 0) >= 3,
    matchAlert: (a) => (a.vol_oi ?? 0) >= 3,
    rankScan: (a, b) => (b.volOI ?? b.vol_oi ?? 0) - (a.volOI ?? a.vol_oi ?? 0),
    rankAlert: (a, b) => (b.conviction ?? 0) - (a.conviction ?? 0),
  },
  {
    id: "mine", label: "My universe",
    matchScan: (r, ctx) => (ctx?.universe || []).includes(r.under),
    matchAlert: (a, ctx) => (ctx?.universe || []).includes(a.under || a.ticker),
    rankScan: byScoreDesc,
    rankAlert: (a, b) => (b.conviction ?? 0) - (a.conviction ?? 0),
  },
];

// Rule-builder evaluation for custom screens. Conditions AND together:
// {fact, op, value} where fact ∈ SCAN_FACTS ∪ TICKER_FACTS, op ∈ ≥/≤/between/is.
// rule: one of RULE_LIST or null. tickerCtx: {premConc, pcr, sigma, streak} for r.under.
export function factValueOf(r, fact, tickerCtx) {
  if (fact === "oiChgPct") return r.oiChgPct ?? null;
  if (TICKER_FACTS.includes(fact)) return tickerCtx?.[fact] ?? null;
  return r[fact] ?? null;
}
function conditionRange(value) {
  const range=/^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*(?:,|–|-)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*$/i.exec(String(value ?? ""));
  return range ? range.slice(1).map(Number) : null;
}
export function migrateScreenUnits(screen) {
  if(!screen || screen.ruleUnitsVersion===2)return screen;
  const percent=value=>String(Number((Number(value)*100).toPrecision(15)));
  const migrate=condition=>{
    if(Array.isArray(condition?.conditions))return {...condition,conditions:condition.conditions.map(migrate)};
    if(condition?.fact!=="oiChgPct")return condition;
    if(condition.op==="between") {
      const range=conditionRange(condition.value);
      return range?.every(Number.isFinite)?{...condition,value:range.map(percent).join(",")}:condition;
    }
    return String(condition.value ?? "").trim() && Number.isFinite(Number(condition.value))
      ? {...condition,value:percent(condition.value)}:condition;
  };
  return {...screen,ruleUnitsVersion:2,conditions:(screen.conditions || []).map(migrate)};
}
export function testCondition(r, cond, tickerCtx) {
  if (Array.isArray(cond.conditions)) {
    if (!cond.conditions.length) return false;
    return cond.join === "OR" ? cond.conditions.some(c=>testCondition(r,c,tickerCtx)) : cond.conditions.every(c=>testCondition(r,c,tickerCtx));
  }
  const v = factValueOf(r, cond.fact, tickerCtx);
  if (v == null) return false;
  const scale=cond.fact === "oiChgPct" ? 100 : 1;
  const num = String(cond.value ?? "").trim() ? Number(cond.value) / scale : NaN;
  const str = String(cond.value ?? "").toUpperCase();
  switch (cond.op) {
    case "≥":
      if (typeof v === "string" || !Number.isFinite(num)) return false;
      return Number(v) >= num;
    case "≤":
      if (typeof v === "string" || !Number.isFinite(num)) return false;
      return Number(v) <= num;
    case "between": {
      const range=conditionRange(cond.value);
      if(!range)return false;
      const [lo, hi] = range.map(value=>value/scale);
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) return false;
      return Number(v) >= Math.min(lo, hi) && Number(v) <= Math.max(lo, hi);
    }
    case "is":
      if(scale!==1)return Number.isFinite(num) && typeof v === "number" && v===num;
      return String(v).toUpperCase() === str;
    default:
      return false;
  }
}
export function matchCustomScan(r, screen, tickerCtx, alerts = []) {
  if (!screen) return true;
  if (screen.rule && screen.rule !== "ANY") {
    const rule = String(screen.rule).toUpperCase();
    const fired = alerts.some(a => String(a.rule || "").toUpperCase() === rule &&
      (a.under || a.ticker) === r.under && String(a.type || "").toLowerCase() === String(r.type).toLowerCase() &&
      a.strike != null && Number(a.strike) === Number(r.strike) && a.exp === r.exp);
    if (!fired) return false;
  }
  return (screen.conditions || []).every((c) => testCondition(r, c, tickerCtx));
}
export function applyScreenToScans(rows, screen, ctx) {
  const s = screen || BUILTIN_SCREENS[0];
  const copied = BUILTIN_SCREENS.find(b=>b.id===s.copyOf);
  const match = s.custom
    ? (r) => (!copied || copied.matchScan(r,ctx)) && matchCustomScan(r, s, ctx?.tickerFacts?.[r.under], ctx?.alerts)
    : (r) => s.matchScan(r, ctx);
  const out = (rows || []).filter(match);
  out.sort(s.rankScan || byScoreDesc);
  return out;
}
export function applyScreenToAlerts(alerts, screen, ctx) {
  const s = screen || BUILTIN_SCREENS[0];
  if (s.custom) {
    const copied=BUILTIN_SCREENS.find(b=>b.id===s.copyOf);
    return (alerts || []).filter(a=>{
      if(copied && !copied.matchAlert(a,ctx))return false;
      if(s.rule && s.rule!=="ANY" && String(a.rule || "").toUpperCase()!==String(s.rule).toUpperCase())return false;
      const scan=(ctx?.scanRows || []).find(r=>r.under===(a.under || a.ticker) && r.type===a.type && Number(r.strike)===Number(a.strike) && r.exp===a.exp);
      const facts={...scan,...a,under:a.under || a.ticker};
      return (s.conditions || []).every(c=>testCondition(facts,c,ctx?.tickerFacts?.[facts.under]));
    });
  }
  return (alerts || []).filter((a) => s.matchAlert(a, ctx)).sort(s.rankAlert);
}
