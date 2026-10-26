// CHART-C050 anchor study engine (c050_vwap_anchor_contract v1.0, contracts
// v2.4 — H3 PASS as a contract). ONE ENGINE: this module GENERALIZES THE
// GROUPING KEY ONLY — every cumulative value still comes from
// priceStudies.sessionVwap (Σ(hlc3·v)/Σ(v), flush-at-boundary reset, missing
// volume -> null gap, zero-volume hold, per-multiplier bands). No second
// engine, no new math, no provider calls.
//
// Named resolutions (contract letter 8): timezone = the EXISTING
// America/New_York calendar identity (sessionDay/nyOffsetMinutes
// convention); week = ISO Monday-based week of the NY date; quarter =
// calendar months 1-3/4-6/7-9/10-12.
//
// INHERITED SEMANTIC, pinned (H3 HOLD H1): the existing sessionDay groups by
// NY calendar DAY, so extended-hours bars accumulate into that day's
// cumulative. Every longer anchor INHERITS that behavior — a week anchor
// accumulates all bars (regular + extended) of each NY calendar day in the
// week. A loaded window that misses those bars is measured as 'partial'
// coverage, never silently complete.
//
// No-lookahead by construction: each bar's value uses only that bar and
// earlier bars within its period; values never carry across a boundary.

import { sessionVwap, sessionVwapValues } from './priceStudies';

const ANCHORS = ['session', 'week', 'month', 'quarter', 'year'];

// NY calendar fields of a bar time, via the existing en-CA/NY convention.
function nyParts(time) {
  if (time === null || time === undefined) return null; // new Date(null) is EPOCH — never a real bar
  const d = new Date(time);
  if (!Number.isFinite(d.valueOf())) return null;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).formatToParts(d);
  const get = (t) => parts.find((p) => p.type === t)?.value;
  const out = { year: Number(get('year')), month: Number(get('month')), day: Number(get('day')) };
  if (!Number.isFinite(out.year) || !Number.isFinite(out.month) || !Number.isFinite(out.day)) return null;
  return out;
}

// ISO week (Monday-based) of an NY calendar date.
function isoWeekKey(y, m, d) {
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  const dayNum = (date.getUTCDay() + 6) % 7;            // Mon = 0
  date.setUTCDate(date.getUTCDate() - dayNum + 3);       // this week's Thursday
  const isoYear = date.getUTCFullYear();
  const jan4 = new Date(Date.UTC(isoYear, 0, 4, 12));
  const jan4Day = (jan4.getUTCDay() + 6) % 7;
  const week1Thu = new Date(jan4);
  week1Thu.setUTCDate(jan4.getUTCDate() - jan4Day + 3);
  const week = 1 + Math.round((date - week1Thu) / (7 * 86400000));
  return `${isoYear}-W${String(week).padStart(2, '0')}`;
}

// The generalized grouping key. session === the existing sessionDay key.
export function periodKey(time, anchor) {
  if (!ANCHORS.includes(anchor)) return null; // out-of-enum refuses — never a guessed grouping
  const p = nyParts(time);
  if (!p) return null;
  if (anchor === 'session') return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
  if (anchor === 'month') return `${p.year}-${String(p.month).padStart(2, '0')}`;
  if (anchor === 'quarter') return `${p.year}-Q${Math.ceil(p.month / 3)}`;
  if (anchor === 'year') return `${p.year}`;
  return isoWeekKey(p.year, p.month, p.day);
}

// The NY calendar START of the period a key/time belongs to (for honest
// partial-coverage measurement). Returned as a plain NY date string.
export function periodStartOf(time, anchor) {
  const p = nyParts(time);
  if (!p) return null;
  const pad = (n) => String(n).padStart(2, '0');
  if (anchor === 'session') return `${p.year}-${pad(p.month)}-${pad(p.day)}`;
  if (anchor === 'month') return `${p.year}-${pad(p.month)}-01`;
  if (anchor === 'quarter') return `${p.year}-${pad(((Math.ceil(p.month / 3) - 1) * 3) + 1)}-01`;
  if (anchor === 'year') return `${p.year}-01-01`;
  // week: the Monday of this NY date's ISO week
  const date = new Date(Date.UTC(p.year, p.month - 1, p.day, 12));
  const dayNum = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - dayNum);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

function groupFrames(frames, anchor) {
  const groups = [];
  const index = [];
  let key = null;
  (frames || []).forEach((bar, i) => {
    const k = periodKey(bar?.time, anchor);
    if (k === null) { index.push(null); return; }
    if (key !== null && k !== key) { key = k; groups.push({ key, bars: [bar], at: [i] }); }
    else if (key === null) { key = k; groups.push({ key, bars: [bar], at: [i] }); }
    else { groups[groups.length - 1].bars.push(bar); groups[groups.length - 1].at.push(i); }
  });
  return { groups, index };
}

// Anchored VWAP values aligned to the input frames. anchor 'session' is the
// EXISTING engine byte-for-byte (equivalence is pinned in tests).
export function anchoredVwapValues(frames, opts = {}) {
  const anchor = opts.anchor || 'session';
  if (anchor === 'session') return sessionVwapValues(frames, opts);
  const out = new Array((frames || []).length).fill(null);
  const { groups } = groupFrames(frames, anchor);
  for (const g of groups) {
    const values = sessionVwap(g.bars, opts); // THE engine — same math per period group
    values.forEach((r, i) => { out[g.at[i]] = r.vwap; });
  }
  return out;
}

// Anchored per-frame band sets (one {m, upper, lower} pair per multiplier).
export function anchoredVwapBands(frames, opts = {}) {
  const anchor = opts.anchor || 'session';
  const out = new Array((frames || []).length).fill(null);
  const { groups } = groupFrames(frames, anchor);
  for (const g of groups) {
    const values = sessionVwap(g.bars, opts);
    values.forEach((r, i) => { out[g.at[i]] = r.bands; });
  }
  return out;
}

// Honest loaded-coverage measurement for the LAST period in the window.
// Facts only: the derived NY period boundary and the first loaded bar in
// the period — never an invented pre-window volume, never a silent
// complete-history claim. Fewer than 2 measured bars in the period -> the
// existing null-with-reason semantics (surfaced as minBarsState).
export function anchorCoverage(frames, anchor = 'session') {
  const list = (frames || []).filter((f) => f && periodKey(f.time, anchor) !== null);
  if (!list.length) return { coverage: 'none', groups: 0, anchor };
  const { groups } = groupFrames(list, anchor);
  const last = groups[groups.length - 1];
  const measured = last.bars.filter((b) => typeof b?.volume === 'number' && Number.isFinite(b.volume) && b.volume > 0);
  const periodStart = periodStartOf(last.bars[0].time, anchor);
  const firstBarNy = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(last.bars[0].time));
  return {
    anchor,
    coverage: firstBarNy === periodStart ? 'full' : 'partial',
    periodStart,
    firstBar: last.bars[0].time,
    groups: groups.length,
    firstGroupKey: groups[0].key,
    lastGroupKey: last.key,
    minBarsState: measured.length < 2 ? 'insufficient' : 'ok',
  };
}
