// Pure scanner math for Tidehunter Pro — no React, no fetch. Tested in scanLogic.test.js.

export const fmtUSD = (v) => { const n = Math.abs(Number(v) || 0); if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`; if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`; return `$${Math.round(n)}`; };
export const fmtK = (v) => { const n = Number(v) || 0; if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`; if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`; return String(Math.round(n)); };
// Local trading-day key (America/Eastern for a Philly desk) — first-seen and
// the alert tape reset at local midnight so each session starts clean.
export function sessionDay(now = Date.now()) {
  const d = new Date(now);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Wall-clock formatter. withSeconds for the alert tape (precise arrivals),
// HH:MM for the scanner's Seen column.
export function fmtClock(ms, withSeconds = false) {
  if (ms == null) return "—";
  return new Date(ms).toLocaleTimeString([], withSeconds
    ? { hour: "2-digit", minute: "2-digit", second: "2-digit" }
    : { hour: "2-digit", minute: "2-digit" });
}

// Compact elapsed age: 45s / 12m / 3h.
export function fmtAge(ms, now = Date.now()) {
  if (ms == null) return "—";
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.round(m / 60)}h`;
}

// Annotate each row with the timestamp its contract was FIRST seen this
// session (answers "what came in when"). seen = { day, map:{key:ms} } persists
// in the caller; the map resets when the local day rolls. Returns { rows, seen }.
export function annotateFirstSeen(rows, seen, now = Date.now()) {
  const day = sessionDay(now);
  const map = (seen && seen.day === day && seen.map) ? { ...seen.map } : {};
  for (const r of rows || []) {
    const key = `${r.under}|${r.type}|${r.strike}|${r.exp}`;
    if (map[key] == null) map[key] = now;
    r.firstSeen = map[key];
  }
  return { rows: rows || [], seen: { day, map } };
}

// IV unit heuristic: decimal IVs legitimately exceed 1 on hot names (1.5 =
// 150%), while pct-style feeds send 20–200 — treat < 3 as decimal, ≥ 3 as pct.
const normIV = (v) => (v == null ? null : (Number(v) >= 3 ? Number(v) / 100 : Number(v)));
export const fmtIV = (v) => (v == null ? "—" : `${(normIV(v) * 100).toFixed(1)}%`);

// Trading-day DTE — weekdays strictly after today (UTC date) through the
// expiry date. Date-boundary based: a Monday expiry reads 1 all weekend and a
// contract expiring today reads 0 regardless of time of day.
export function bizDTE(expStr) {
  if (!expStr) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(expStr));
  if (!m) return null;
  const end = Date.UTC(+m[1], +m[2] - 1, +m[3]);
  const t0 = new Date();
  const today = Date.UTC(t0.getUTCFullYear(), t0.getUTCMonth(), t0.getUTCDate());
  if (end <= today) return 0;
  let d = 0;
  const cap = Math.min(end, today + 800 * 86400000);
  for (let t = today + 86400000; t <= cap; t += 86400000) {
    const wd = new Date(t).getUTCDay();
    if (wd !== 0 && wd !== 6) d++;
  }
  return d;
}

// Flow-type by volume magnitude + vol/OI — the only signals a print-less feed supports.
export function scanTypeOf(r) {
  if (r.vol >= 25000) return "sweep";
  if (r.vol >= 8000) return "block";
  if (r.volOI >= 2) return "unusual";
  if (r.volOI >= 1) return "split";
  return "regular";
}

export const scoreGradeOf = (s) => (s >= 80 ? "crit" : s >= 65 ? "high" : s >= 50 ? "elev" : "norm");

// |delta| estimate from moneyness when the feed omits delta. Logistic squash of
// signed distance-to-spot in ~8%-of-spot units — labeled as an ESTIMATE in the UI.
export function estimateDelta(strike, spot, type) {
  if (!spot || !strike) return null;
  const isCall = String(type || "").toLowerCase().startsWith("c");
  const x = (spot - strike) / (spot * 0.08);
  const d = 1 / (1 + Math.exp(-1.7 * (isCall ? x : -x)));
  const abs = Math.max(0.02, Math.min(0.98, d));
  return isCall ? abs : -abs;
}

// Median strike ≈ spot (chains are built around the money). Fallback-path only.
export function approxSpot(strikes) {
  if (!strikes || !strikes.length) return null;
  const s = [...strikes].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

// Flow Score 0-100 — positioning freshness, size, notional, urgency, OTM lean,
// plus a small gamma-regime nudge when the ticker's regime is known:
// negative gamma amplifies short-dated aggressive flow (dealers chase moves);
// positive gamma pins — fresh positioning (vol/OI ≥ 2) matters more.
export function scanScoreOf(r, regime = null) {
  const dl = Math.abs(r.delta || 0);
  const pos = Math.min(r.volOI / 3, 1);
  const size = Math.min(Math.log(Math.max(r.vol, 1)) / Math.log(50000), 1);
  const notl = Math.min(Math.log(Math.max(r.notional, 1)) / Math.log(50e6), 1);
  const urg = r.dte == null ? 0.3 : (r.dte <= 2 ? 1 : r.dte <= 7 ? 0.7 : r.dte <= 30 ? 0.4 : 0.15);
  const otm = r.delta == null ? 0.3 : Math.max(0, Math.min((0.5 - dl) / 0.4, 1));
  let s = (pos * 0.34 + size * 0.24 + notl * 0.18 + urg * 0.14 + otm * 0.10) * 100;
  let nudge = 0;
  if (regime === "negative" && r.dte != null && r.dte <= 7) nudge = 5;
  else if (regime === "positive" && r.volOI >= 2) nudge = 3;
  s += nudge;
  // Informed-positioning band: 7-90 DTE + vol≥3×OI + ≥$25k premium is where
  // directional bets live (shorter = gamma noise, longer = hedges) — a desk
  // heuristic, NOT from Pan & Poteshman (RFS 2006): that paper finds buyer-open
  // put-call ratios predict returns (low PC → +40bp next day, stronger for
  // high-leverage/OTM), with no DTE band and no volume/OI/premium thresholds.
  // Keep the band as [internal heuristic]; cite P&P only for PC direction.
  let band = 0;
  if (r.dte != null && r.dte >= 7 && r.dte <= 90 && (r.volOI || 0) >= 3 && (r.premium || 0) >= 25e3) band = 4;
  s += band;
  r._parts = { pos: +(pos * 34).toFixed(1), size: +(size * 24).toFixed(1), notl: +(notl * 18).toFixed(1), urg: +(urg * 14).toFixed(1), otm: +(otm * 10).toFixed(1), nudge, band };
  return Math.max(0, Math.min(100, Math.round(s)));
}

// Premium spent estimate (institutions read premium, not contract notional).
// BS-lite ATM price ≈ strike·iv·√(dte/365)·0.4, discounted toward deep OTM by
// |delta| when known, floored at $0.05/contract. Always labeled ~ in the UI —
// there is no quote feed on this data.
export function estPremium(r) {
  const iv = normIV(r.iv);
  if (!iv || !r.strike) return null;
  const dte = Math.max(1, r.dte ?? 5);
  let px = r.strike * iv * Math.sqrt(dte / 365) * 0.4;
  if (r.delta != null) px *= Math.min(1, 0.3 + Math.abs(r.delta) * 1.4);
  px = Math.max(0.05, px);
  return (r.vol || 0) * 100 * px;
}

// Alert engine — pure. Evaluates NEW rows against the enabled rules; a row
// fires at most one alert (first matching rule wins, in priority order).
// Every hit carries a plain-English `why` (a desk explains its alerts) and an
// optional `ttl` — how long ingest should dedupe this key before re-firing.
// The universe is FULLY OPEN: no ticker allowlist — market-wide scans alert
// on any symbol. A legacy `opts.allow` is accepted and ignored (back-compat).
export function evalAlerts(rows, opts = {}) {
  const {
    // Post-tightening gates (2026-09-02 noise pass, enforced Phase 7.1):
    // omitted-opts callers inherit desk gates, never the old loose values.
    minScore = 92,
    whalePremium = 25e6,
    primePremium = 250e3,
    primeVolOI = 5,
    zeroDteScore = 85,
    oiConfPct = 0.30,
    oiConfNotional = 1e6,
    // 2026-09-02 noise pass: per-ticker alert cap per scan. Contract rules
    // fire on NEW rows; a 60-name breadth day can legitimately flag 60 rows
    // — that is data, but 60 notifications is noise. Top-cap keeps the
    // strongest claims per ticker; count stays truthful (engine still
    // evaluated everything). This is a NOTIFICATION throttle, not a universe
    // limit — every ticker is still evaluated.
    perTickerCap = 2,
    enabled = { score: true, whale: true, zerodte: true, oiconf: true, prime: true },
  } = opts;
  // key is rule-namespaced so dedup ttls stay independent across rules — a
  // SCORE fire yesterday afternoon must not suppress this morning's OICONF
  // confirmation on the same contract. ckey keeps the raw contract identity.
  const mkHit = (r, rule, extra) => {
    const ckey = `${r.under}|${r.type}|${r.strike}|${r.exp}`;
    return {
      key: `${rule.toLowerCase()}|${ckey}`, ckey,
      rule, under: r.under, type: r.type, strike: r.strike, exp: r.exp,
      score: r.score, premium: r.premium, notional: r.notional,
      volOI: r.volOI, dte: r.dte, ...extra,
    };
  };
  // Pass 1 — ΔOI confirmation candidates: the one hard "yesterday's flow was
  // real" proof a print-less feed offers (open interest that JUMPED overnight
  // means the positioning held). Doesn't require _new; capped to the top 5 by
  // % build so the tape gets the strongest follow-through, not 50 rows of +30%.
  // ΔOI hygiene parity (server: services/oi_hygiene.py): rows carry a hygiene
  // tag (r.oiChg.tag, shipped on /scan payload as oi_tags) — rollover/expiring
  // contracts are migration artifacts, never "new flow"; earnings-window
  // alerts still fire but the why-string carries the ambiguity tag.
  const hygieneSuffix = (tag) => {
    if (!tag) return "";
    const parts = [];
    if (tag.rollover) parts.push("rollover detected — position migrated expiries, not new flow");
    if (tag.earnings && typeof tag.earnings === "object") {
      if (tag.earnings.unknown) parts.push("earnings window unknown — direction ambiguous");
      else if (tag.earnings.days_to != null) parts.push(`earnings in ${tag.earnings.days_to} session(s) — direction ambiguous`);
    }
    return parts.length ? " [" + parts.join("; ") + "]" : "";
  };
  const cand = [];
  for (const r of rows || []) {
    const tag = (r.oiChg && r.oiChg.tag) || null;
    if (tag && (tag.rollover || tag.expiring)) continue;
    const addNotl = r.oiChg ? r.oiChg.abs * 100 * (r.strike || 0) : 0;
    if (enabled.oiconf && r.oiChg && r.oiChg.pct >= oiConfPct && addNotl >= oiConfNotional) {
      cand.push({ r, addNotl });
    }
  }
  cand.sort((a, b) => b.r.oiChg.pct - a.r.oiChg.pct);
  const topConf = cand.slice(0, 5);
  const inTop = new Set(topConf.map((c) => c.r));
  const out = topConf.map(({ r, addNotl }) => mkHit(r, "OICONF", {
    oiChgPct: r.oiChg.pct,
    why: `OI +${Math.round(r.oiChg.pct * 100)}% overnight (+${fmtK(r.oiChg.abs)} contracts, ${fmtUSD(addNotl)} notional) — prior-day flow HELD as new positioning`
      + hygieneSuffix(r.oiChg && r.oiChg.tag),
    ttl: 20 * 3600e3,
  }));
  // Pass 2 — intraday rules on NEW rows. Rows that won an OICONF slot skip
  // this (one alert per row, strongest claim wins); rows that qualified but
  // ranked 6+ fall through here so their one-shot _new alert isn't swallowed.
  // Side gate on intraday rules: oiconf stays side-agnostic.
  const sideGate = typeof opts.side === "string" && opts.side !== "all"
    ? opts.side : null;
  for (const r of rows || []) {
    if (!r._new || inTop.has(r)) continue;
    if (sideGate && r.type !== sideGate) continue;
    let rule = null, why = null;
    if (enabled.score && r.score >= (enabled.scoreMin ?? minScore)) {
      rule = "SCORE";
      why = `score ${r.score} — vol ${r.volOI >= 99 ? "99+" : (r.volOI ?? 0).toFixed(1)}× OI${r.premium != null ? `, ~${fmtUSD(r.premium)} premium` : ""}${r.dte != null ? `, ${r.dte} DTE` : ""}`;
    } else if (enabled.whale && r.premium != null && r.premium >= (enabled.whaleMin ?? whalePremium)) {
      rule = "WHALE";
      why = `~${fmtUSD(r.premium)} estimated premium on a single line`;
    } else if (enabled.prime && (r.premium ?? 0) >= primePremium && (r.volOI ?? 0) >= primeVolOI) {
      // PRIME — the 55-62% UOA bracket sits BELOW whale size: a $25M+ line
      // is whale flow first. PRIME catches sub-whale mid-cap institutional
      // building that never clears SCORE≥92 (the SNDK gap).
      // Server parity: flow_alerts.eval_institutional Pass 2.
      rule = "PRIME";
      why = `prime print — ~${fmtUSD(r.premium)} premium at ${(r.volOI ?? 0).toFixed(1)}× OI, score ${r.score} (55-62% directional bracket)`;
    } else if (enabled.zerodte && r.dte != null && r.dte <= 1 && r.score >= zeroDteScore && (r.volOI ?? 0) >= 2) {
      rule = "0DTE";
      why = `${r.dte} DTE with score ${r.score} — urgent short-fuse positioning`;
    }
    if (!rule) continue;
    out.push(mkHit(r, rule, { why }));
  }
  // Per-ticker cap — contract rules only, priority order OICONF > SCORE >
  // WHALE > PRIME > 0DTE (mirrors the rule precedence). OICONF pass-1 hits are
  // exempt (already capped at top-5 globally by % build).
  if (perTickerCap > 0) {
    const prio = { SCORE: 0, WHALE: 1, PRIME: 2, "0DTE": 3 };
    const perTicker = new Map();
    const kept = [];
    for (const h of out) {
      if (!prio.hasOwnProperty(h.rule)) { kept.push(h); continue; }   // OICONF etc exempt
      const n = perTicker.get(h.under) || 0;
      if (n >= perTickerCap) continue;
      perTicker.set(h.under, n + 1);
      kept.push(h);
    }
    kept.sort((a, b) => (prio[a.rule] ?? 9) - (prio[b.rule] ?? 9));
    out.length = 0;
    out.push(...kept);
  }
  return out;
}

// Weekend scans record stale duplicates of Friday's cumulative volumes (the
// upstream feed doesn't reset off-hours) — drop Sat/Sun rows before any
// history math. Date-only strings parse as UTC midnight, so getUTCDay is exact.
export function isTradingDay(dateStr) {
  const wd = new Date(`${dateStr}T00:00:00Z`).getUTCDay();
  return wd !== 0 && wd !== 6;
}

// The most recent weekday strictly before dateStr (Mon → prior Fri).
function prevTradingDayOf(dateStr) {
  const t = Date.parse(`${dateStr}T00:00:00Z`);
  for (let k = 1; k <= 4; k++) {
    const d = new Date(t - k * 86400000);
    const wd = d.getUTCDay();
    if (wd !== 0 && wd !== 6) return d.toISOString().slice(0, 10);
  }
  return null;
}

// History hygiene for streaks + sparklines: weekday rows only, and drop
// consecutive EXACT-duplicate rows — a weekday market holiday records the
// prior session's cumulative volumes under its own date (same off-hours
// staleness the weekend filter handles), and identical consecutive real
// volumes are practically impossible at these magnitudes.
export function cleanHistory(days) {
  const out = [];
  for (const d of days || []) {
    if (!d || d.total_vol == null || !isTradingDay(d.date)) continue;
    const p = out[out.length - 1];
    if (p && p.total_vol === d.total_vol && p.call_vol === d.call_vol && p.put_vol === d.put_vol) continue;
    out.push(d);
  }
  return out;
}

// Multi-day persistence — "are they coming back?" days = [{date, total_vol},…]
// ascending (from /scan/history). Baseline = median of PRIOR days only —
// today's row is a partial intraday-cumulative count. Streak = consecutive
// most-recent TRADING days with total_vol ≥ mult × median; a below-threshold
// TODAY is skipped rather than breaking yesterday's streak (the day isn't
// over yet). Calendar continuity is enforced: a missing day means the ticker
// fell out of the scan (a quiet day), so a gap BREAKS the streak — "N straight
// days" must mean literally consecutive sessions. (A holiday's missing row
// also breaks — conservative beats a false persistence claim.)
export function streakOf(days, { mult = 1.5, minDays = 4, today = sessionDay() } = {}) {
  const arr = cleanHistory(days);
  const prior = arr.filter((d) => d.date !== today);
  if (prior.length < minDays) return null;
  const vols = prior.map((d) => d.total_vol).sort((a, b) => a - b);
  const mid = Math.floor(vols.length / 2);
  const median = vols.length % 2 ? vols[mid] : (vols[mid - 1] + vols[mid]) / 2;
  if (!(median > 0)) return null;
  const thr = median * mult;
  let i = arr.length - 1;
  if (arr[i].date === today && arr[i].total_vol < thr) i--;
  let n = 0, lastDate = null;
  for (; i >= 0 && arr[i].total_vol >= thr; i--) {
    if (lastDate && arr[i].date !== prevTradingDayOf(lastDate)) break;
    n++;
    lastDate = arr[i].date;
  }
  return { n, thr: Math.round(thr), median: Math.round(median), mult };
}

// Ticker-level alerts from aggregates — the "definite" tier: both rules
// compare a ticker to its OWN history rather than one snapshot.
//   SIGMA:  today's scan volume ≥ sigmaMin σ above the ticker's multi-day
//           baseline (OptionScannerTWS finding: 4-5σ spikes precede moves).
//   FOLLOW: ≥ followDays consecutive elevated-volume days — persistent
//           positioning; institutions building over days, not one print.
// Hits use the label pathway (no strike) and long ttls so the tape stays signal.
export function evalTickerAlerts(rollup, baselines = {}, streaks = {}, opts = {}) {
  const { sigmaMin = 6, followDays = 2, enabled = { sigma: true, follow: true } } = opts;
  const out = [];
  for (const e of rollup || []) {
    const base = { under: e.under, type: "", strike: "", exp: "", score: e.maxScore ?? null, premium: null, dte: null };
    if (enabled.sigma) {
      const b = baselines[e.under];
      const s = volSigma(e.callVol + e.putVol, b);
      if (s != null && s >= (enabled.sigmaMin ?? sigmaMin)) {
        out.push({
          ...base, key: `sigma|${e.under}`, rule: "SIGMA", sigma: s,
          label: `${e.under} options volume ${s}σ above its ${b.days}-day baseline (${fmtK(e.callVol + e.putVol)} vs ~${fmtK(b.avg)} avg)`,
          ttl: 4 * 3600e3,
        });
      }
    }
    if (enabled.follow) {
      const st = streaks[e.under];
      if (st && st.n >= (enabled.followMin ?? followDays)) {
        out.push({
          ...base, key: `follow|${e.under}`, rule: "FOLLOW", streak: st.n,
          label: `${e.under} elevated options volume ${st.n} straight days (≥${st.mult}× its median) — persistent positioning`,
          ttl: 20 * 3600e3,
        });
      }
    }
  }
  return out;
}

// σ-spike: today's cumulative options volume vs the ticker's baseline of
// prior days' end-of-day volumes (OptionScannerTWS-style anomaly detection —
// their signal was 4-5σ spikes preceding underlying moves). Needs ≥2 days of
// baseline history and a nonzero std; the backend accumulates the baselines.
export function volSigma(totalVol, baseline) {
  if (totalVol == null || !baseline || !baseline.std || (baseline.days || 0) < 2) return null;
  return +(((totalVol - baseline.avg) / baseline.std).toFixed(1));
}

// Next-day open-interest change for one contract — the print-less feed's only
// "was this opening flow?" confirmation. Returns null when there's no prior-day
// record (nothing to compare) or prior OI was 0. { abs, pct } otherwise:
// pct is fractional (0.42 = +42%). A FRESH contract whose OI rose held as new
// positioning; one whose OI fell was intraday churn.
export function oiChange(oi, prevOI) {
  if (prevOI == null || prevOI <= 0 || oi == null) return null;
  const abs = oi - prevOI;
  return { abs, pct: abs / prevOI };
}

// "While you were away" digest — pure. Everything that happened since sinceMs:
// alert counts by rule from the persisted tape, plus the top new contracts
// (first seen after sinceMs) by score. Null when the gap is too short to
// matter or there is nothing to report.
export function awaySummary(alertLog, rows, sinceMs, now = Date.now(), minGapMs = 30 * 60e3) {
  if (sinceMs == null || now - sinceMs < minGapMs) return null;
  const counts = {};
  let nAlerts = 0;
  for (const a of alertLog || []) {
    if (a.t > sinceMs) { counts[a.rule] = (counts[a.rule] || 0) + 1; nAlerts++; }
  }
  const topNew = (rows || [])
    .filter((r) => r.firstSeen != null && r.firstSeen > sinceMs)
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 3);
  if (!nAlerts && !topNew.length) return null;
  return { gapMs: now - sinceMs, counts, nAlerts, topNew };
}

// CSV for the current scanner view (premium is an estimate — header says so).
// Pure string builder so the export is Jest-testable.
const CSV_COLS = [
  ["firstSeen", "seen", (v) => (v == null ? "" : new Date(v).toISOString())],
  ["score", "score"], ["under", "ticker"], ["type", "type"], ["strike", "strike"],
  ["exp", "expiry"], ["dte", "dte"], ["vol", "volume"], ["oi", "oi"],
  ["oiChgPct", "oi_chg_pct", (v) => (v == null ? "" : v.toFixed(4))],
  ["volOI", "vol_oi"], ["premium", "premium_est"], ["notional", "notional"],
  ["iv", "iv"], ["ftype", "flow"], ["arch", "archetype"], ["lean", "lean"], ["regime", "regime"],
];
const csvCell = (v) => {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
export function scanRowsToCSV(rows) {
  const head = CSV_COLS.map(([, label]) => label).join(",");
  const body = (rows || []).map((r) =>
    CSV_COLS.map(([key, , fmt]) => csvCell(fmt ? fmt(r[key]) : r[key])).join(","));
  return [head, ...body].join("\n");
}

// Institutional flow archetype from real fields only (no tape). First match
// wins: WHALE (premium size), LOTTO (deep-OTM short-dated), HEDGE (mid-delta
// long-dated puts — protective duration), FRESH (volume ≥ 3× open interest,
// new positioning). null when nothing distinctive.
export function archetypeOf(r) {
  if (r.premium != null && r.premium >= 10e6) return "WHALE";
  const dl = r.delta == null ? null : Math.abs(r.delta);
  if (dl != null && dl <= 0.15 && r.dte != null && r.dte <= 2) return "LOTTO";
  if (r.type === "put" && dl != null && dl >= 0.25 && dl <= 0.6 && r.dte != null && r.dte >= 30) return "HEDGE";
  // $25k premium floor cuts retail noise (a few cheap OTM contracts spike
  // vol/OI without being a signal); when no estimate exists, don't assume small.
  if ((r.volOI || 0) >= 3 && (r.premium == null || r.premium >= 25e3)) return "FRESH";
  return null;
}

// Per-ticker premium concentration — where the money is. Sorted by total
// estimated premium desc, top-N, with call/put split for a skew read.
export function tickerRollup(rows, top = 8) {
  const m = new Map();
  for (const r of rows || []) {
    const e = m.get(r.under) || {
      under: r.under, prem: 0, callPrem: 0, putPrem: 0,
      callVol: 0, putVol: 0, count: 0, maxScore: 0, regime: null,
    };
    const p = r.premium || 0;
    e.prem += p;
    if (r.type === "call") { e.callPrem += p; e.callVol += r.vol || 0; }
    else { e.putPrem += p; e.putVol += r.vol || 0; }
    e.count++;
    if ((r.score || 0) > e.maxScore) e.maxScore = r.score;
    if (r.regime) e.regime = r.regime;
    m.set(r.under, e);
  }
  const arr = [...m.values()].sort((a, b) => b.prem - a.prem).slice(0, top);
  for (const e of arr) {
    e.callPct = e.prem > 0 ? Math.round((e.callPrem / e.prem) * 100) : 50;
    // Volume-based put/call ratio — Pan & Poteshman (RFS 2006): low P/C
    // predicts outperformance (~40bps next day, >1% next week in their data).
    e.pcr = e.callVol > 0 ? +(e.putVol / e.callVol).toFixed(2) : null;
  }
  return arr;
}

// Build one scanner row. spot enables delta estimation when the feed omits
// delta; regime (from the backend heatmap cache) feeds the score nudge.
export function mkScanRow(under, type, strike, exp, vol, oi, iv, delta, spot = null, regime = null) {
  const stk = Number(strike) || 0;
  const volOI = oi > 0 ? vol / oi : (vol > 0 ? 99 : 0);
  const given = delta == null ? null : Number(delta);
  const est = given == null ? estimateDelta(stk, spot, type) : null;
  const r = {
    under, type: String(type || "").toLowerCase().startsWith("c") ? "call" : "put",
    strike: stk, exp, vol, oi, iv,
    delta: given != null ? given : est,
    deltaEst: given == null && est != null,
    spot, regime,
    volOI, notional: vol * 100 * stk, dte: bizDTE(exp),
  };
  r.premium = estPremium(r);
  r.score = scanScoreOf(r, regime); r.ftype = scanTypeOf(r);
  r.arch = archetypeOf(r);
  return r;
}

// ── Heartbeat HUD helpers (institutional data-freshness read-out) ──
// Three pure functions so the JSX purity doesn't bleed into the component and
// the GREEN phase can pin every UI tier in jest tests. Precedence is fixed:
//   errored > stale+retry > stale > loading > fallback > live-warn > live-fresh
// so a degraded upstream always shown the same colour as the worst condition.

// Compact age formatter for the heartbeat chip. Always in seconds when <60s
// (the heartbeat pulses with a 1s clock tick, not the alert-tape 30min dedup
// cadence); null / negative / non-finite → "—" so a missing age never lies.
export function elapsedClock(ageSec) {
  if (ageSec == null || !Number.isFinite(ageSec) || ageSec < 0) return "—";
  const s = Math.round(ageSec);
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.round(m / 60)}h`;
}

// Heartbeat tier — drives the colored dot + label in the scanbar "Heartbeat"
// chip. green=live pulse with age≤30s, yellow=ok-age OR fallback OR slow,
// red=stale+retry OR errored. tier.hint is the title-tooltip explaining WHY;
// the component renders just .dot (CSS class) + .label.
// ttl = the backend's budgeted refresh cadence (scan_ttl from /scan). Data as
// old as the cadence is HEALTHY on a request-capped plan — fresh/slow bounds
// scale with it. Defaults preserve the original 30s/90s bounds.
export function pulseState({ mode, stale, age = 0, retry = null, hasData = false, hasError = false, ttl = 60 } = {}) {
  const freshBound = Math.max(30, ttl * 0.5);
  const slowBound = Math.max(90, ttl * 1.5);
  if (hasError) return { dot: "r", label: "ERRORED", tier: "err", hint: "last poll threw — keeping last good scan" };
  if (stale && retry != null) return { dot: "r", label: `STALE ·retry ${elapsedClock(retry)}`, tier: "err", hint: "upstream rate-limited or hourly budget spent — retrying after the duration shown" };
  if (stale) return { dot: "y", label: "STALE", tier: "warn", hint: "data is the last good scan — upstream is back-pressured" };
  if (!hasData && !mode) return { dot: "y", label: "LOADING", tier: "warn", hint: "first poll in flight — no prior data to show" };
  if (mode === "fallback") return { dot: "y", label: "FALLBACK", tier: "warn", hint: "upstream market-wide unavailable — scanning 18-symbol universe locally" };
  if (mode === "market" && age <= freshBound) return { dot: "g", label: "LIVE", tier: "fresh", hint: `market-wide scan · ${elapsedClock(age)} since last poll` };
  if (mode === "market" && age <= slowBound) return { dot: "y", label: "LIVE ·slow", tier: "warn", hint: `market-wide scan · ${elapsedClock(age)} since last poll (target ≤${elapsedClock(freshBound)})` };
  return { dot: "y", label: `LIVE ·${elapsedClock(age)}`, tier: "warn", hint: `market-wide scan · ${elapsedClock(age)} since last poll` };
}

// ── FIRE Banner helpers (Upgrade C — sticky top banner for high-priority alert fires) ──
// 3 pure functions so the sticky FIRE banner never repeats the institutional
// "definite alert" precedence in JSX — helpers test the tiering, the component
// renders + ticks the 60s auto-dismiss + ack button. The slate of rules that
// qualify as high-tier mirrors Upgrade-C's spec: OICONF (overnight OI confirmed)
// + WHALE (≥$10M premium) + FOLLOW ≥3d + SIGMA ≥5σ + SCORE ≥90 (floor bumped
// over the 85 default to keep the banner for "definite" only).

// Classify a single alert hit into the banner-eligible tier.
//   high = banner candidate (rule + threshold)
//   med  = loud but not definite enough for the sticky banner (e.g. SCORE 88)
//   off  = user-toggled this rule off in the chips (caller should filter upstream)
// tierOf is intentionally hit-only — it inspects the hit's own data + the
// caller-provided minScoreForFire (defaults to 90 so a user with alertScore=70
// still keeps the banner off their SCORE-low band).
export function tierOf(hit, { minScoreForFire = 90 } = {}) {
  if (!hit || !hit.rule) return "off";
  switch (hit.rule) {
    case "OICONF": return "high";
    case "WHALE": return "high";
    case "FOLLOW":
      return Number.isFinite(Number(hit.streak)) && Number(hit.streak) >= 3 ? "high" : "med";
    case "SIGMA":
      return Number.isFinite(Number(hit.sigma)) && Number(hit.sigma) >= 5 ? "high" : "med";
    case "SCORE":
      return Number.isFinite(Number(hit.score)) && Number(hit.score) >= minScoreForFire ? "high" : "med";
    default: return "med";   // 0DTE, SOURCE — too noisy for the sticky banner
  }
}

// Select banner-eligible fires from the (already-dedup'd by alertSeen) alertLog.
// Returns the subset tagged _tier="high" sorted banner-priority. Defensive on
// each axis: respects per-rule enabled flags (universe is fully open — no
// allowlist) and drops entries older than ttlMs
// (alertLog is already deduped, but TTL handling stays here for stub tests).
// acked accepts either a Set<string> or a plain {key: ms} object.
export function selectFires(alertLog, opts = {}) {
  const { now = Date.now(), ttlMs = 60_000, minScoreForFire = 90, enabled, acked } = opts;
  const ackedSet = acked instanceof Set ? acked : new Set(Object.keys(acked || {}));
  const enabledMap = enabled || {};
  const out = [];
  for (const hit of alertLog || []) {
    if (!hit || !hit.key) continue;
    if (ackedSet.has(hit.key)) continue;
    const rl = String(hit.rule || "").toLowerCase();
    // enabled-map is keyed by lowercase rule names (oiconf / whale / zerodte etc)
    if (enabledMap[rl] === false) continue;
    if (hit.t != null && now - hit.t > ttlMs) continue;
    const t = tierOf(hit, { minScoreForFire });
    if (t !== "high") continue;
    out.push({ ...hit, _tier: t });
  }
  out.sort(firePriorityCompare);
  return out;
}

// Priority comparator for banner rendering. Lower number = higher rank;
// ties (same rule) broken by t desc so the newest fire bumps its peer. The
// map is re-allocated per call so callers who add a new rule just have to
// patch the table — the comparator is private to this module.
function firePriorityCompare(a, b) {
  const pr = { OICONF: 0, WHALE: 1, FOLLOW: 2, SIGMA: 3, SCORE: 4, "0DTE": 5 };
  const pa = pr[a.rule] ?? 99, pb = pr[b.rule] ?? 99;
  if (pa !== pb) return pa - pb;
  return (Number(b.t) || 0) - (Number(a.t) || 0);
}

// Pick the single banner to render. MVP = top fire per priority order. Null
// when nothing qualifies. Re-sorts defensively using the same priority
// comparator selectFires applies so callers can pass either the already-sorted
// output of selectFires OR a raw subset (e.g. from a stub test) without
// breaking the OICONF > WHALE > FOLLOW > SIGMA > SCORE precedence.
export function pickBanner(fires, _prev = null, _opts = {}) {
  if (!Array.isArray(fires) || fires.length === 0) return null;
  const sorted = [...fires].sort(firePriorityCompare);
  return sorted[0];
}

// FOLLOW Leaderboard — turn the streaks map (from the JSX useMemo) into a
// rendering-stable, sorted, top-N-clipped list. Sort: streak-days desc, then
// mult desc (stronger conviction first when days tie), then ticker ASCII so
// the strip stays deterministic across reloads. Single-day / NaN streaks are
// filtered out by the caller, but we double-check here so a bad shape can't
// leak into the strip. Empty / non-object input → [].
export function formatFOLLOWStrip(streaks, { top = 6 } = {}) {
  if (!streaks || typeof streaks !== "object") return [];
  const arr = [];
  for (const [under, st] of Object.entries(streaks)) {
    if (!st || !Number.isFinite(st.n) || st.n < 2) continue;
    arr.push({
      under,
      n: st.n,
      mult: Number(st.mult) || 1.5,
      median: Number(st.median) || 0,
      thr: Number(st.thr) || 0,
    });
  }
  arr.sort((a, b) => (b.n - a.n) || (b.mult - a.mult) || a.under.localeCompare(b.under));
  return arr.slice(0, Math.max(0, top));
}

// ---------- W1 tracer: spread position + overview bar (Phase 9) ----------
// Spread position: where last traded inside [bid, ask]. 0 = at bid, 1 = at ask.
// Returns {pos, state, side, label}: state NO_QUOTE when bid/ask/last missing or zero,
// LOCKED when bid/ask present but crossed/locked (ask<=bid) — never a guessed number (C4).
// side/label: BID (pos<=0.33) / MID (0.33<pos<0.67) / ASK (pos>=0.67) / NO_QUOTE|LOCKED.
export function spreadPosition(bid, ask, last) {
  const b = Number(bid), a = Number(ask), l = Number(last);
  // Missing or zero quotes → NO_QUOTE (never guess)
  if (!Number.isFinite(b) || !Number.isFinite(a) || !Number.isFinite(l)
    || b <= 0 || a <= 0 || l <= 0) {
    return { pos: null, state: "NO_QUOTE", side: "NO_QUOTE", label: "NO_QUOTE" };
  }
  // Crossed/locked spread (ask<=bid) → LOCKED distinct from NO_QUOTE
  if (a <= b) {
    return { pos: null, state: "LOCKED", side: "LOCKED", label: "LOCKED" };
  }
  const pos = Math.max(0, Math.min(1, (l - b) / (a - b)));
  let side;
  if (pos <= 0.33) side = "BID";
  else if (pos < 0.67) side = "MID";
  else side = "ASK";
  return { pos, state: "OK", side, label: side };
}

// Overview bar rollup over Pulse rows. Direction proxy (snapshot chains carry
// no bought/sold flags): bullish leg = (call&ASK)|(put&BID), bearish leg =
// (call&BID)|(put&ASK). FIR = |bull-bear|/(bull+bear); Lean gated at 0.3 (H1).
// RVOL needs baselines we don't have → always honest-empty here (H2 daily
// resolution lands with B1 cadence).
export function overviewStats(rows) {
  let bull = 0, bear = 0, callPrem = 0, putPrem = 0, n = 0;
  for (const r of rows || []) {
    const prem = Number(r._aggPrem ?? r.premium) || 0;
    if (prem <= 0) continue;
    const isCall = String(r.type || "").toLowerCase().startsWith("c");
    const ask = String(r.side || "").toUpperCase() === "ASK";
    if ((isCall && ask) || (!isCall && !ask)) bull += prem;
    else bear += prem;
    if (isCall) callPrem += prem; else putPrem += prem;
    n += 1;
  }
  const total = bull + bear;
  const fir = total > 0 ? Math.abs(bull - bear) / total : 0;
  const netPrem = bull - bear;
  const pc = callPrem > 0 ? putPrem / callPrem : (putPrem > 0 ? Infinity : 0);
  const lean = fir >= 0.3 ? (netPrem > 0 ? "Bullish" : netPrem < 0 ? "Bearish" : "Neutral") : "Neutral";
  return { bullPrem: bull, bearPrem: bear, netPrem, callPrem, putPrem, fir, pc, lean, n, rvol: null };
}

// ---------- W6 filter depth (Phase 9) ----------
// Equity-type triple toggle: static map, no vendor needed. ETF macro flow
// separated from single-name conviction per the Academy.
const ETF_SET = new Set(["SPY", "QQQ", "IWM", "DIA", "TLT", "XLF", "XLE", "XLK", "XLV", "XLI", "XLU", "XLB", "XLY", "XLP", "XLC", "XLRE", "XBI", "XHB", "XME", "XOP", "XRT", "SMH", "SOXX", "ARKK", "ARKG", "TQQQ", "SQQQ", "UPRO", "SPXU", "SPXS", "SPXL", "QLD", "QID", "DDM", "DXD", "DIA", "UDOW", "SDOW", "TMF", "TMV", "TNA", "TZA", "FAS", "FAZ", "NUGT", "DUST", "USO", "UNG", "GLD", "SLV", "GDX", "HYG", "LQD", "IEF", "SHY", "TIP", "EEM", "EFA", "FXI", "EWJ", "EWZ", "INDA", "VTI", "VOO", "VEA", "VWO", "VNQ", "SCHD", "JEPI", "JEPQ", "QQQM", "SPYV", "SPYG", "IVV", "VO", "VB", "VUG", "VTV"]);
const IDX_SET = new Set(["SPX", "NDX", "RUT", "VIX", "DJX", "OEX", "XEO", "NQX"]);
export function equityType(ticker) {
  const t = String(ticker || "").toUpperCase();
  if (IDX_SET.has(t)) return "INDEX";
  if (ETF_SET.has(t)) return "ETF";
  return "STOCK";
}

// Signed moneyness from spot (our stored otm is absolute): + means OTM.
export function signedOtm(type, strike, spot) {
  const k = Number(strike), s = Number(spot);
  if (!k || !s) return null;
  const isCall = String(type || "").toLowerCase().startsWith("c");
  return isCall ? (k - s) / s : (s - k) / s;
}

// Signed side → (side, bias): the frontend mirror of the server's desk
// matrix (services/public_scanner.py side_bias, fed by Lee-Ready
// flow_signing on the backend). ASK = buyer lifted, BID = seller hit;
// unknown (or anything else) stays unlabeled FLOW — parity tested on the
// same 5 contracts both sides (scanLogic.test.js ↔ test_public_advantage).
export function signedBias(type, signedSide) {
  const t = String(type || "").toLowerCase().startsWith("c") ? "call" : "put";
  if (signedSide === "ASK") return { side: "BUY", bias: t === "call" ? "BULLISH" : "BEARISH" };
  if (signedSide === "BID") return { side: "SELL", bias: t === "call" ? "BEARISH" : "BULLISH" };
  return { side: "FLOW", bias: null };
}

// OPEX = third Friday of the month (standard US equity expiry week).
// Date-only inputs parse at local noon to dodge UTC-midnight timezone shift.
export function isOpexDay(dateLike) {
  const s = String(dateLike || "");
  const d = new Date(s.length === 10 ? `${s}T12:00:00` : s);
  if (Number.isNaN(d.getTime())) return false;
  const y = d.getFullYear(), m = d.getMonth();
  const first = new Date(y, m, 1);
  const offset = (5 - first.getDay() + 7) % 7; // days to first Friday
  return d.getDate() === 1 + offset + 14;
}

// ---------- Highlighting (Phase 9 W3-partial; Academy article 4) ----------
// Snapshot chains carry day-volume + prior-close OI, but NOT single-print size.
// Honest mapping: VOL>OI (purple) is exact. SIZE>OI cannot fire without prints,
// so the loud tier is a 15s volume BURST bigger than entire OI (yellow) —
// labeled burst, never "Size>OI".
export function highlightState({ volDelta, volOI, oi }) {
  const o = Number(oi) || 0;
  const dv = Number(volDelta) || 0;
  const voi = Number(volOI) || 0;
  if (o > 0 && dv > o) return "BURST";
  if (voi >= 1) return "VOL_OI";
  return "NONE";
}

// ---------- Strategy-leg port (Phase 9 W2; mirrors backend flow_quality) ----------
// Same fingerprints: vertical = same ticker+exp+type, different strikes, volume
// ratio within 0.7–1.43x with 1000-contract floor each leg; straddle/strangle =
// opposite types, strikes within 5%, matched volumes. Tags r._strat with
// "VERT?" or "STRADDLE?" (heuristic — no multi-exchange leg linkage). Returns count.
const SPREAD_LO = 0.7, SPREAD_HI = 1 / 0.7, SPREAD_VOL_FLOOR = 1000, STRADDLE_TOL = 0.05;
export function flagSpreadLegs(rows) {
  let n = 0;
  const byTE = new Map();
  for (const r of rows || []) {
    const k = `${r.ticker}|${String(r.expiration || "").slice(0, 10)}`;
    if (!byTE.has(k)) byTE.set(k, []);
    byTE.get(k).push(r);
  }
  const ratioOk = (a, b) => {
    const va = Number(a.volume) || 0, vb = Number(b.volume) || 0;
    if (va < SPREAD_VOL_FLOOR || vb < SPREAD_VOL_FLOOR) return false;
    const q = va / vb;
    return q >= SPREAD_LO && q <= SPREAD_HI;
  };
  for (const legs of byTE.values()) {
    if (legs.length < 2) continue;
    for (let i = 0; i < legs.length; i++) {
      for (let j = i + 1; j < legs.length; j++) {
        const a = legs[i], b = legs[j];
        if (!ratioOk(a, b)) continue;
        const ta = String(a.type || "").toLowerCase(), tb = String(b.type || "").toLowerCase();
        const ka = Number(a.strike) || 0, kb = Number(b.strike) || 0;
        let tag = null;
        if (ta === tb && ka !== kb) tag = "VERT?";
        else if (ta !== tb && ka > 0 && kb > 0
          && Math.abs(ka - kb) / Math.max(ka, kb) <= STRADDLE_TOL) tag = "STRADDLE?";
        if (!tag) continue;
        for (const leg of [a, b]) {
          if (!leg._strat) { leg._strat = tag; n += 1; }
        }
      }
    }
  }
  return n;
}

// ---------- Wave-2 SHIP engine (pure; synthesis tidehunter-wave2-synthesis.md) ----------
// Conventions: IVs normalized by the same <3-decimal rule as fmtIV. Delta
// interpolation never extrapolates (null outside observed range). Rows with
// estimated deltas (deltaEst) degrade interpolation — callers preferring
// precision should pre-filter; helpers stay honest and compute anyway.

// Linear-interpolate IV at a target delta across same-type contracts.
// Returns null with <2 usable points or target outside observed delta range.
export function interpDeltaIV(rows, targetDelta, type) {
  const t = String(type || "").toLowerCase().startsWith("c") ? "call" : "put";
  const pts = [];
  for (const r of rows || []) {
    if (String(r.type || "").toLowerCase() !== t) continue;
    const d = Number(r.delta), v = Number(r.iv);
    if (!Number.isFinite(d) || r.iv == null) continue;
    const iv = Number(v) >= 3 ? Number(v) / 100 : Number(v);
    if (iv <= 0) continue;
    pts.push([d < 0 ? d : (t === "put" ? -d : d), iv]); // signed delta
  }
  if (pts.length < 2) return null;
  // Signed delta: calls +d, puts −|d|.
  const signed = pts.map(([d, iv]) => [d, iv]).sort((a, b) => a[0] - b[0]);
  const x = Number(targetDelta);
  if (x < signed[0][0] || x > signed[signed.length - 1][0]) return null;
  for (let i = 0; i < signed.length - 1; i++) {
    const [x0, y0] = signed[i], [x1, y1] = signed[i + 1];
    if (x >= x0 && x <= x1) {
      if (x1 === x0) return y0;
      return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
    }
  }
  return null;
}

// Single-expiry skew levels (XZZ smirk, C-W spread, Yan slope, convexity).
// Pass rows for ONE expiry (front liquid monthly); nulls where uncomputable.
export function skewLevels(rows) {
  const put = (d) => interpDeltaIV(rows, d, "put");
  const call = (d) => interpDeltaIV(rows, d, "call");
  const p20 = put(-0.2), p50 = put(-0.5), p80 = put(-0.8), c50 = call(0.5);
  const sub = (a, b) => (a == null || b == null ? null : a - b);
  return {
    smirk: sub(p20, c50),          // XZZ: IVput(-0.2) − IVcall(0.5)
    cwSpread: sub(c50, p50),       // Cremers-Weinbaum: IVcall(0.5) − IVput(-0.5)
    yanSlope: sub(p20, p50),       // Yan: IVput(-0.2) − IVput(-0.5)
    convexity: p20 == null || p80 == null || c50 == null
      ? null : p20 + p80 - 2 * c50,
  };
}

// Expiry-day pin risk from one snapshot: max-OI strike, top-3 concentration,
// 0DTE-OI share not computable here (needs multi-expiry view — caller joins).
export function pinRisk(rows, spot) {
  const byStrike = new Map();
  let total = 0;
  for (const r of rows || []) {
    const oi = Number(r.oi) || 0;
    if (oi <= 0) continue;
    const k = Number(r.strike) || 0;
    byStrike.set(k, (byStrike.get(k) || 0) + oi);
    total += oi;
  }
  if (!byStrike.size || total <= 0) return null;
  const ranked = [...byStrike.entries()].sort((a, b) => b[1] - a[1]);
  const top3 = ranked.slice(0, 3).reduce((s, [, v]) => s + v, 0);
  const s = Number(spot);
  return {
    maxOiStrike: ranked[0][0],
    maxOi: ranked[0][1],
    concentration: top3 / total,
    totalOi: total,
    distPct: Number.isFinite(s) && s > 0 ? ((ranked[0][0] - s) / s) * 100 : null,
  };
}

// Ho-Stoll-lite quote read: relative spread always; direction needs a reference.
// DOWN = mid shifted down vs prevMid (dealer-long pressure), UP = inverse.
// Without prevMid there is no direction — tag LEVEL, never a fabricated side.
export function quoteSkew(bid, ask, prevMid = null) {
  const b = Number(bid), a = Number(ask);
  if (!Number.isFinite(b) || !Number.isFinite(a) || a <= b || b <= 0) {
    return { mid: null, relSpread: null, driftBp: null, tag: "NOQUOTE" };
  }
  const mid = (a + b) / 2;
  const relSpread = (a - b) / mid;
  const pm = Number(prevMid);
  if (!Number.isFinite(pm) || pm <= 0) return { mid, relSpread, driftBp: null, tag: "LEVEL" };
  const driftBp = ((mid - pm) / pm) * 1e4;
  const tag = Math.abs(driftBp) < 1 ? "FLAT" : driftBp < 0 ? "DOWN" : "UP";
  return { mid, relSpread, driftBp, tag };
}

// Midpoint drift over oldest→newest mids (reservation-price proxy).
export function midDrift(mids) {
  const xs = (mids || []).map(Number).filter(Number.isFinite);
  if (xs.length < 2 || xs[0] <= 0) return null;
  return { driftPct: ((xs[xs.length - 1] - xs[0]) / xs[0]) * 100, n: xs.length };
}

// ---------- Per-poll snapshot stamping (skip lists: SHIP-4/6) ----------
// Shared contract key so buffer, volume-delta, and mid tracking agree.
export function contractKey(r) {
  return `${r.ticker}|${String(r.type || "").toLowerCase()}|${r.strike}|${String(r.expiration || "").slice(0, 10)}`;
}
// Stamps FRESH signals only (never re-stamp: StrictMode double-effects and
// repeat polls would zero the deltas). Day volume is cumulative; a drop =
// data reset → delta unknown (0), mid map untouched.
export function stampPollDeltas(signals, prevVol, prevMid) {
  for (const s of signals || []) {
    const key = contractKey(s);
    const pv = prevVol.get(key);
    s._volDelta = pv == null ? 0 : Math.max(0, (Number(s.volume) || 0) - pv);
    prevVol.set(key, Number(s.volume) || 0);
    s._prevMid = prevMid.has(key) ? prevMid.get(key) : null;
    const m = Number(s.mid);
    if (Number.isFinite(m) && m > 0) prevMid.set(key, m);
  }
  return signals;
}

// ---------- Pin-risk readout (SHIP-1; CL-06 gate) ----------
// Daily expirations verified only for SPX/SPXW/SPY/QQQ/IWM/XSP — every other
// name is Friday-only (single-name equity options expire weekly). Nearest
// expiry group scoped to the ticker; spot from first row carrying one.
const PIN_DAILY = new Set(["SPX", "SPXW", "SPY", "QQQ", "IWM", "XSP"]);
export function nearestExpiryPin(rows, ticker, nowMs = Date.now()) {
  const t = String(ticker || "").toUpperCase();
  const scoped = (rows || []).filter(
    (r) => String(r.ticker || "").toUpperCase() === t && Number(r.oi) > 0
  );
  if (!scoped.length) return null;
  if (!PIN_DAILY.has(t) && new Date(nowMs).getDay() !== 5) {
    return { eligible: false, reason: "Fri-only" };
  }
  const exps = [...new Set(
    scoped.map((r) => String(r.expiration || "").slice(0, 10)).filter(Boolean)
  )].sort();
  if (!exps.length) return null;
  const group = scoped.filter((r) => String(r.expiration || "").slice(0, 10) === exps[0]);
  const withSpot = group.find((r) => Number(r.spot) > 0);
  const pin = pinRisk(group, withSpot ? withSpot.spot : null);
  if (!pin) return null;
  return { eligible: true, exp: exps[0], ...pin };
}

// ---------- Roll 1984 effective spread (SHIP-7 engine; ROLL-01..08) ----------
// s = 2*sqrt(-cov(dP_t, dP_{t+1})). Defined ONLY for negative autocovariance;
// cov >= 0 → truncated (spread 0, truncated:true) per ROLL-02. Measures
// quoted-bounce + staleness on snapshots, NOT taker cost (ROLL-07). Needs
// ~30+ mids for a non-degenerate read (ROLL-05) — callers show n.
export function rollSpread(mids) {
  const xs = (mids || []).map(Number).filter((v) => Number.isFinite(v) && v > 0);
  if (xs.length < 3) return { spread: null, n: xs.length, truncated: false };
  const d = [];
  for (let i = 1; i < xs.length; i++) d.push(xs[i] - xs[i - 1]);
  const mu = d.reduce((a, b) => a + b, 0) / d.length;
  let cov = 0;
  for (let i = 0; i < d.length - 1; i++) cov += (d[i] - mu) * (d[i + 1] - mu);
  cov /= d.length - 1;
  if (cov >= 0) return { spread: 0, n: xs.length, truncated: true };
  return { spread: 2 * Math.sqrt(-cov), n: xs.length, truncated: false };
}

// Capped push for per-contract mid rings (Roll history; caller persists).
export function pushCapped(ring, v, cap = 60) {
  const r = Array.isArray(ring) ? ring : [];
  const x = Number(v);
  if (Number.isFinite(x) && x > 0) r.push(x);
  while (r.length > cap) r.shift();
  return r;
}

// ---------- Pooled Roll bucket (SHIP-7 wiring; ROLL-08) ----------
// Aggregates dP covariance across contracts in one expiry bucket. Deltas are
// concatenated per-ring (one spurious joint adjacency per ring — negligible
// past ~30 deltas, documented not hidden). Under 30 deltas → building state,
// never a number.
export function rollPooled(rings) {
  const deltas = [];
  let nMid = 0;
  for (const ring of rings || []) {
    const xs = (Array.isArray(ring) ? ring : [])
      .map(Number).filter((v) => Number.isFinite(v) && v > 0);
    nMid += xs.length;
    for (let i = 1; i < xs.length; i++) deltas.push(xs[i] - xs[i - 1]);
  }
  if (deltas.length < 30) {
    return { spread: null, n: nMid, nd: deltas.length, building: true, truncated: false };
  }
  const mu = deltas.reduce((a, b) => a + b, 0) / deltas.length;
  let cov = 0;
  for (let i = 0; i < deltas.length - 1; i++) cov += (deltas[i] - mu) * (deltas[i + 1] - mu);
  cov /= deltas.length - 1;
  if (cov >= 0) {
    return { spread: 0, n: nMid, nd: deltas.length, building: false, truncated: true };
  }
  return { spread: 2 * Math.sqrt(-cov), n: nMid, nd: deltas.length, building: false, truncated: false };
}
