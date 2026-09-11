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
 * Fetch the full listed universe page by page (T2). `get` is an
 * axios-compatible getter `(url) => Promise<{data}>` so tests inject fakes.
 * Stops at `has_more === false`, on error, or at the safety caps. Returns
 * `{ symbols, pages, total }`; empty symbols on total failure (callers keep
 * the featured-only sets as fallback).
 */
export const UNIVERSE_PAGE_LIMIT = 5000;
export const UNIVERSE_MAX_SYMBOLS = 12000;
export const UNIVERSE_MAX_PAGES = 8;

export async function fetchFullUniverse(get, baseUrl) {
  const symbols = [];
  let pages = 0;
  let total = 0;
  for (let page = 1; page <= UNIVERSE_MAX_PAGES; page += 1) {
    let data;
    try {
      const res = await get(
        `${baseUrl}/tickers/all?limit=${UNIVERSE_PAGE_LIMIT}&page=${page}`
      );
      data = (res && res.data) || {};
    } catch (_) {
      break; // transport failure: keep what we have (possibly nothing)
    }
    const batch = Array.isArray(data.tickers) ? data.tickers : [];
    if (batch.length === 0) break;
    symbols.push(...batch);
    pages += 1;
    total = Number(data.total) || total;
    if (data.has_more !== true) break;
    if (symbols.length >= UNIVERSE_MAX_SYMBOLS) break;
  }
  return { symbols: symbols.slice(0, UNIVERSE_MAX_SYMBOLS), pages, total };
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
