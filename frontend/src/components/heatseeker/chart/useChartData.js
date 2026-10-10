// B05 generation-safe shared chart data hook (pure helpers + hook contract).
// Abort stale generations, dedupe pane queries, badge stale/cache/budget/outage,
// reconnect backfill replaces corrections (never merges into live cache silently).
let generation = 0;
const inflight = new Map();
export function nextGeneration() { generation += 1; return generation; }
export function currentGeneration() { return generation; }
export function dedupeKey({ symbol, interval, session, scope }) {
  return [symbol, interval, session, scope].join('|');
}
export function isStale(resultGen, activeGen) { return resultGen !== activeGen; }
export function badgeFor({ stale, cached, budget, outage }) {
  if (outage) return 'outage';
  if (budget) return 'budget-exhausted';
  if (stale) return 'stale';
  if (cached) return 'cached';
  return 'live';
}
export function registerQuery(key, gen) {
  inflight.set(key, gen);
  return gen;
}
export function shouldApply(key, gen) { return inflight.get(key) === gen && gen === currentGeneration(); }
export function backfillReplace(current, correction) {
  if (!correction || correction.generation !== currentGeneration()) return current;
  return correction.data;
}
