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
  const out = [];
  for (const level of (levels || [])) {
    const price = level == null ? null : level.price;
    const start = level == null ? null : level.session_start;
    if (typeof price !== "number" || !start) continue;
    let end = null;
    for (const bar of (bars || [])) {
      if (cursor != null && (!(bar != null && bar.time != null) || bar.time > cursor)) break;
      const low = bar == null ? null : bar.low;
      const high = bar == null ? null : bar.high;
      if (typeof low === "number" && typeof high === "number" && low <= price && price <= high) {
        end = bar.time != null ? bar.time : null;
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
  return {
    status: "ok",
    low: Math.min(...used.map((b) => b.low)),
    high: Math.max(...used.map((b) => b.high)),
    periods: used.length,
    approximation: "bar-resolution",
  };
}
