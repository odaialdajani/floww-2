/**
 * tickerUniverse — T1 single-source ticker contract (2026-09-07).
 *
 * One case-normalized, order-preserving deduped list shared by the ticker
 * bar (buttons/count/search), the control-bar position + arrows, and the
 * App.js keyboard arrows. Accepts the production object shape
 * { trinity, default, popular }, a plain array (legacy call sites), or
 * null/empty (callers apply their own fallback sets).
 */

export const RENDER_CAP = 500;
export const SUGGEST_CAP = 12;

export function normalizeTicker(t) {
  return String(t).trim().toUpperCase().replace(/^\$/, "");
}

export function dedupePreserveOrder(arr) {
  const seen = new Set();
  const out = [];
  for (const t of arr || []) {
    const k = normalizeTicker(t);
    if (!k) continue;
    if (!seen.has(k)) { seen.add(k); out.push(k); }
  }
  return out;
}

export function buildTickerUniverse(tickers) {
  if (!tickers) return [];
  if (Array.isArray(tickers)) return dedupePreserveOrder(tickers);
  return dedupePreserveOrder([
    ...(tickers.trinity || []),
    ...(tickers.default || []),
    ...(tickers.popular || []),
  ]);
}

/** Filter-before-slice: search the full universe, cap only the suggestions. */
export function searchUniverse(universe, query, limit = SUGGEST_CAP) {
  const q = String(query || "").trim().toUpperCase();
  if (!q) return { matches: [], total: 0 };
  const hits = (universe || []).filter((t) => t.includes(q));
  return { matches: hits.slice(0, limit), total: hits.length };
}

/**
 * Step through the universe with wrap. Unknown current ticker wraps from
 * the boundary (forward -> first, back -> last) — pinned contract, covered
 * by SkylitControlBar tests. Returns an index into list.
 */
export function stepIndex(list, current, dir) {
  if (!list || list.length === 0) return -1;
  const idx = list.indexOf(normalizeTicker(current));
  if (idx === -1) return dir > 0 ? 0 : list.length - 1;
  return (idx + dir + list.length) % list.length;
}
