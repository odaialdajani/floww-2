// B11 pane reducer: focus owns symbol, 5 link dims, no echo, price off for unlike
// symbols, allowlist-only sync, atomic invalidation, reject late generations.
export const LINK_DIMS = ['interval', 'crosshair', 'time', 'price', 'session'];
export function createPanes(count = 1, symbol = 'SPY') {
  return Array.from({ length: count }, (_, i) => ({ id: `pane-${i}`, symbol, focused: i === 0, generation: 0 }));
}
export function focusPane(panes, id, symbol) {
  return panes.map((p) => p.id === id
    ? { ...p, focused: true, symbol: symbol || p.symbol, generation: p.generation + 1 }
    : { ...p, focused: false });
}
export function shouldEcho(tx, originId) { return tx.origin !== originId; }
export function priceLinked(a, b) { return a.symbol === b.symbol; }
export function syncState(pane, patch, allowlist = ['interval', 'session']) {
  const next = { ...pane };
  for (const k of Object.keys(patch)) {
    if (allowlist.includes(k)) next[k] = patch[k];
  }
  next.generation += 1;
  return next;
}
export function applyResult(pane, result) {
  if (!result || result.generation !== pane.generation) return pane;
  if (result.removed) return null;
  return { ...pane, data: result.data };
}
