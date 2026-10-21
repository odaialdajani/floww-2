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

// Incomplete aggregation: only base events with event_time<=cursor AND
// available_at<=cursor contribute. A bar is never rendered as complete while
// any leg is still unavailable.
export function partialBar(events, cursor) {
  const use = (events || []).filter((e) => e
    && (e.event_time != null ? e.event_time : 1) <= cursor
    && (e.available_at != null ? e.available_at : 1) <= cursor);
  if (!use.length) return null;
  const opens = use.filter((e) => "open" in e).map((e) => e.open);
  const closes = use.filter((e) => "close" in e).map((e) => e.close);
  return {
    open: opens.length ? opens[0] : null,
    close: closes.length ? closes[closes.length - 1] : null,
    complete: false,
    count: use.length,
  };
}

// Completed only with a known window end at-or-before the cursor AND no
// pending unavailable leg; otherwise the bar stays explicitly partial.
export function barAt(events, cursor, windowEnd = null) {
  const partial = partialBar(events, cursor);
  if (!partial) return null;
  if (windowEnd == null || !(cursor >= windowEnd)) return partial;
  const pending = (events || []).some((e) => e && (e.available_at != null ? e.available_at : 1) > cursor);
  if (pending) return partial;
  return { ...partial, complete: true };
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
