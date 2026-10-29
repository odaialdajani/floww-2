// B23 profile primitives mirror: trade prices bin exactly per tick; POC ties
// resolve downward; the value area expands from the POC with equal adjacent
// expansion upward and stops honestly at sparse gaps; sessions in the future
// never count. TPO-style reads are labeled as approximations, never presented
// as trade-exact volume. Mirrors backend/services/chart_profiles.py.

export function poc(rows) {
  const list = (rows || []).filter((r) => r && typeof r.price === "number");
  if (!list.length) return null;
  const best = Math.max(...list.map((r) => (typeof r.volume === "number" ? r.volume : 0)));
  const tied = list.filter((r) => (typeof r.volume === "number" ? r.volume : 0) === best);
  return tied.reduce((min, r) => (r.price < min.price ? r : min), tied[0]);
}

export function valueArea(rows, pct = 0.7) {
  const list = (rows || []).filter((r) => r && typeof r.price === "number");
  if (!list.length) return { status: "unavailable" };
  const ordered = [...list].sort((a, b) => a.price - b.price);
  const total = ordered.reduce((sum, r) => sum + (typeof r.volume === "number" ? r.volume : 0), 0);
  if (!(total > 0)) return { status: "unavailable" };
  const p = poc(ordered);
  if (!p) return { status: "unavailable" };
  let lo = ordered.findIndex((r) => r === p);
  let hi = lo;
  let acc = ordered[lo].volume;
  const target = total * pct;
  while (acc < target) {
    const up = hi + 1 < ordered.length ? (typeof ordered[hi + 1].volume === "number" ? ordered[hi + 1].volume : 0) : null;
    const dn = lo - 1 >= 0 ? (typeof ordered[lo - 1].volume === "number" ? ordered[lo - 1].volume : 0) : null;
    if (up === null && dn === null) break;
    if (up === null) { lo -= 1; acc += dn; }
    else if (dn === null || up >= dn) { hi += 1; acc += up; }
    else { lo -= 1; acc += dn; }
    if (up === 0 && dn === 0) break;
  }
  return { status: "ok", low: ordered[lo].price, high: ordered[hi].price, attained: acc / total };
}

// Historically correct naked levels: a prior level stays visible from its
// observed session start until the first bar whose range revisits it. An
// unknown range is never proof of untouched, and bars beyond the cursor are
// future sessions that never close a level.
export function nakedLevels(levels, bars, { cursor = null } = {}) {
  // R21-04 mirror: only bars knowable at the cursor close a level, and a
  // level outside every observed bar can NEVER be certified untouched —
  // honest not-claimable (naked: null), matching the backend's
  // level-outside-known-range / not-claimable refusals.
  const knowable = (bars || []).filter((b) => b
    && b.time != null
    && (cursor == null || b.time <= cursor)
    && typeof b.low === "number" && typeof b.high === "number");
  const range = knowable.length
    ? { low: Math.min(...knowable.map((b) => b.low)), high: Math.max(...knowable.map((b) => b.high)) }
    : null;
  const out = [];
  for (const level of (levels || [])) {
    const price = level == null ? null : level.price;
    const start = level == null ? null : level.session_start;
    if (typeof price !== "number" || !start) continue;
    if (!range) {
      out.push({ price, visible_from: start, visible_until: null, naked: null, reason: "not-claimable" });
      continue;
    }
    if (price < range.low || price > range.high) {
      out.push({ price, visible_from: start, visible_until: null, naked: null, reason: "level-outside-known-range" });
      continue;
    }
    let end = null;
    for (const bar of knowable) {
      if (bar.low <= price && price <= bar.high) {
        end = bar.time;
        break;
      }
    }
    out.push({ price, visible_from: start, visible_until: end, naked: end === null });
  }
  return out;
}

// Exact tick bins for classified trades; mispriced or unknown-size trades
// are excluded rather than force-binned.
export function tickRows(trades, tick) {
  const step = Number(tick);
  if (!Number.isFinite(step) || step <= 0) {
    return { status: "unavailable", reason: "bad tick size" };
  }
  const list = Array.isArray(trades) ? trades : [];
  const bins = new Map();
  for (const trade of list) {
    if (!trade || typeof trade !== "object") continue;
    const price = trade.price == null ? NaN : Number(trade.price);
    const size = trade.size == null ? NaN : Number(trade.size);
    if (!Number.isFinite(price) || !Number.isFinite(size)) continue;
    const bin = Math.round(price / step);
    bins.set(bin, (bins.get(bin) || 0) + size);
  }
  if (!bins.size) return { status: "unknown", reason: "no classified trade prices" };
  const rows = [...bins.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([bin, volume]) => ({ bin, price: Number((bin * step).toFixed(10)), volume }));
  return { status: "ok", rows, tick: step, approximation: "tick-bins" };
}

// Initial balance is the opening period range — an explicitly approximate,
// bar-resolution read; observations beyond the cursor are never included.
export function initialBalance(bars, { periods = 2, cursor = null } = {}) {
  const eligible = (bars || []).filter((b) => b
    && b.time != null
    && (cursor == null || b.time <= cursor)
    && typeof b.low === "number" && typeof b.high === "number");
  const used = eligible.slice(0, Math.max(0, periods));
  if (!used.length) return { status: "unknown", reason: "no eligible opening bars" };
  const bounds = {
    low: Math.min(...used.map((b) => b.low)),
    high: Math.max(...used.map((b) => b.high)),
  };
  // R21-04 mirror: a truncated opening window is never "ok" — the backend
  // refuses opening-history-truncated; the client names the same honesty
  // and keeps the observed bounds attached for the honest display.
  if (used.length < periods) {
    return { status: "incomplete", reason: "opening-history-truncated",
      ...bounds, periods: used.length, expectedPeriods: periods,
      approximation: "bar-resolution" };
  }
  return { status: "ok", ...bounds, periods: used.length, approximation: "bar-resolution" };
}

// B23 TPO periods — BAR-RESOLUTION approximation only: group the bars
// knowable at the cursor into fixed 30-minute periods, each contributing its
// own high/low range and a letter. A bar's activity is its whole period's;
// this is never tick-true TPO and the label says so. Bars beyond the cursor
// never join a period; nothing knowable is honest unavailable.
export function tpoPeriods(bars, { periodMinutes = 30, cursor = null } = {}) {
  const eligible = (bars || []).filter((b) => b
    && b.time != null
    && (cursor == null || Number(b.time) <= Number(cursor))
    && typeof b.low === "number" && typeof b.high === "number");
  if (!eligible.length) return { status: "unavailable", reason: "no eligible bars known at the cursor" };
  const periodMs = periodMinutes * 60000;
  const groups = new Map();
  for (const b of eligible) {
    const start = Math.floor(Number(b.time) / periodMs) * periodMs;
    if (!groups.has(start)) groups.set(start, { start, low: Infinity, high: -Infinity, bars: 0 });
    const g = groups.get(start);
    g.low = Math.min(g.low, b.low);
    g.high = Math.max(g.high, b.high);
    g.bars += 1;
  }
  const periods = [...groups.values()].sort((a, b) => a.start - b.start)
    .map((g, i) => ({ ...g, letter: String.fromCharCode(65 + (i % 26)) }));
  return { status: "ok", periods, periodMinutes, approximation: "bar-resolution",
    note: "bar-resolution TPO approximation — a bar is its whole period; never tick-true TPO" };
}

// B23 session zones — BAR-RESOLUTION envelope of the bars knowable at the
// cursor: high/low plus the first/last KNOWN bar times. A partial session
// describes only what is known; open/close stay honestly absent when the
// bars carry none (missing is never zero).
export function sessionZones(bars, { cursor = null } = {}) {
  const eligible = (bars || []).filter((b) => b
    && b.time != null
    && (cursor == null || Number(b.time) <= Number(cursor))
    && typeof b.low === "number" && typeof b.high === "number");
  if (!eligible.length) return { status: "unavailable", reason: "no eligible bars known at the cursor" };
  // H3 hardening: the envelope is order-independent — sort by time so
  // first/last KNOWN are the true min/max even for unsorted callers.
  eligible.sort((a, b) => Number(a.time) - Number(b.time));
  const highs = eligible.map((b) => b.high);
  const lows = eligible.map((b) => b.low);
  return {
    status: "ok",
    approximation: "bar-resolution",
    high: Math.max(...highs),
    low: Math.min(...lows),
    bars: eligible.length,
    firstKnownTime: Number(eligible[0].time),
    lastKnownTime: Number(eligible[eligible.length - 1].time),
    open: typeof eligible[0].open === "number" ? eligible[0].open : null,
    close: typeof eligible[eligible.length - 1].close === "number" ? eligible[eligible.length - 1].close : null,
    note: "zones cover only bars knowable at the cursor — a partial session is not the whole session",
  };
}
