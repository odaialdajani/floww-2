// B15 single-cursor replay mirror: known-at algebra, 900/901s eligibility,
// partial versus completed bars, future extrema and later ratios hidden,
// and replay-derived events never feed live caches. Mirrors the algebra of
// backend/services/chart_replay.py; live reads stay server-owned.

// Newest time-eligible reading at the cursor; a late older snapshot never
// rewinds past a newer known-at. Absent entirely before its known-at.
export function visibleSnapshot(snapshots, cursor) {
  const eligible = (snapshots || []).filter((s) => s && s.known_at != null && s.known_at <= cursor);
  if (!eligible.length) return null;
  eligible.sort((a, b) => a.known_at - b.known_at || String(a.id || "").localeCompare(String(b.id || "")));
  return eligible[eligible.length - 1];
}

// 900s eligible, 901s absent; an unknown as-of is never eligible.
export function ageOk(asof, cursor, limit = 900) {
  if (asof == null || cursor == null || limit == null) return false;
  const a = Number(asof), c = Number(cursor), lim = Number(limit);
  if (!Number.isFinite(a) || !Number.isFinite(c) || !Number.isFinite(lim)) return false;
  return 0 <= c - a && c - a <= lim;
}

// Incomplete aggregation of the OWNING bar only (R21-02): the bar is the
// bar_seconds bucket that contains the cursor — [floor(c/bs)*bs, +bs) — so
// events from an earlier bucket never leak into it. Only base events with a
// REAL event_time inside that bucket AND a REAL available_at <= cursor
// contribute; an unknown event_time or available_at never admits the event
// (availability is the server-emitted end_time / window close, never
// invented from the candle's own open time).
export function partialBar(events, cursor, barSeconds = 900) {
  const bs = Number(barSeconds);
  if (!Number.isFinite(bs) || bs <= 0 || cursor == null || !Number.isFinite(Number(cursor))) return null;
  const c = Number(cursor);
  const bucketStart = Math.floor(c / bs) * bs;
  const bucketEnd = bucketStart + bs;
  const inBucket = [];
  const use = [];
  for (const e of events || []) {
    if (!e || e.event_time == null || !Number.isFinite(Number(e.event_time))) continue;
    const et = Number(e.event_time);
    if (et < bucketStart || et >= bucketEnd) continue;
    inBucket.push(e);
    if (e.available_at != null && Number.isFinite(Number(e.available_at)) && Number(e.available_at) <= c) {
      use.push(e);
    }
  }
  if (!inBucket.length) return null;
  const opens = use.filter((e) => "open" in e).map((e) => e.open);
  const closes = use.filter((e) => "close" in e).map((e) => e.close);
  const lastAvailableAt = use.length
    ? Math.max(...use.map((e) => Number(e.available_at)))
    : null;
  return {
    open: opens.length ? opens[0] : null,
    close: closes.length ? closes[closes.length - 1] : null,
    complete: false,
    count: use.length,
    pending: inBucket.length - use.length,
    lastAvailableAt,
    bucketStart,
    bucketEnd,
  };
}

// The bar at the cursor completes only when its window close was EMITTED and
// is available at the cursor (lastAvailableAt >= bucketEnd) with no leg
// still pending; otherwise the bar stays explicitly forming/partial. With
// recorded frames (available_at = end_time = window close) the bar at a
// frame-aligned cursor is honestly always still forming — that is the
// known-at truth, never a rendering convenience.
export function barAt(events, cursor, barSeconds = 900) {
  const partial = partialBar(events, cursor, barSeconds);
  if (!partial) return null;
  const closed = partial.count > 0
    && partial.pending === 0
    && partial.lastAvailableAt != null
    && partial.lastAvailableAt >= partial.bucketEnd;
  return closed ? { ...partial, complete: true } : partial;
}

// Extrema sweep limited to observations at or before the cursor: a future
// bar never extends the historical high/low, and a missing range never
// fabricates one.
export function sweepExtrema(bars, cursor) {
  const eligible = (bars || []).filter((b) => b
    && b.time != null && b.time <= cursor
    && Number.isFinite(b.high) && Number.isFinite(b.low));
  if (!eligible.length) return { status: "unknown", reason: "no eligible bar at cursor" };
  return {
    status: "ok",
    high: Math.max(...eligible.map((b) => b.high)),
    low: Math.min(...eligible.map((b) => b.low)),
    count: eligible.length,
    cursor,
  };
}

// A derived ratio needs both observed legs at or before the cursor; a leg
// in the future leaves the ratio honestly unavailable.
export function historyRatio(a, b, cursor) {
  for (const leg of [a, b]) {
    if (!leg || leg.time == null || leg.time > cursor) return { status: "unavailable", reason: "future or missing leg" };
  }
  if (!Number.isFinite(Number(a.value)) || !Number.isFinite(Number(b.value)) || Number(b.value) === 0) {
    return { status: "unavailable", reason: "not computable at cursor" };
  }
  return { status: "ok", ratio: Number(a.value) / Number(b.value) };
}

// Replay events never enter live caches and vice versa; unknown provenance
// is dropped rather than guessed. Caches stay per-symbol so a cross-symbol
// gap reads as unknown, never as borrowed data.
export function routeEvent(caches, event) {
  const live = (caches && caches.live) || {};
  const replay = (caches && caches.replay) || {};
  if (!event || typeof event !== "object" || event.symbol == null) {
    return { ...caches, live, replay, dropped: event ? [event.id || "unnamed"] : [], reason: "unknown or unmapped origin" };
  }
  const symbol = String(event.symbol);
  const entry = { [event.id || symbol]: { value: event.value != null ? event.value : null, time: event.time != null ? event.time : null } };
  if (event.origin === "live") return { ...caches, live: { ...live, [symbol]: { ...(live[symbol] || {}), ...entry } }, replay, dropped: [] };
  if (event.origin === "replay") return { ...caches, live, replay: { ...replay, [symbol]: { ...(replay[symbol] || {}), ...entry } }, dropped: [] };
  return { ...caches, live, replay, dropped: [event.id || symbol], reason: "unknown origin" };
}

// Server/live provenance on replay cursors never mutates live caches either.
export function reduceCaches(caches, events) {
  return (events || []).reduce((acc, event) => routeEvent(acc, event), caches || { live: {}, replay: {} });
}

// Reader for one symbol and one cache; no cross-symbol substitution.
export function cacheAt(caches, cacheName, symbol) {
  return ((caches || {})[cacheName] || {})[symbol] || null;
}

export function createReplayState(cursor = 0) {
  return { cursor: Number.isFinite(Number(cursor)) ? Number(cursor) : 0, playing: false, caches: { live: {}, replay: {} }, dropped: [] };
}

export function replayStep(state, action) {
  if (!action || typeof action !== "object") return state;
  const cursor = Number(action.cursor);
  switch (action.type) {
    case "seek":
      return Number.isFinite(cursor)
        ? { ...state, cursor, playing: false }
        : state;
    case "play":
      return { ...state, playing: true };
    case "pause":
      return { ...state, playing: false };
    case "admit": {
      const routed = routeEvent(state.caches, action.event);
      const dropped = action.event ? routed.dropped : state.dropped;
      return { ...state, caches: { live: routed.live, replay: routed.replay }, dropped };
    }
    default:
      return state;
  }
}
