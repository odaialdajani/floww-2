// B11 pane reducer: focus owns symbol, 5 link dims, no echo, price off for unlike
// symbols, allowlist-only sync, atomic invalidation, reject late generations.
// B11 extension: layout presets, atomic evidence invalidation on layout change,
// per-instrument sync resolution and a top-level panesReducer for the mounted
// pane manager. All B06-era helper semantics are preserved verbatim.
export const LINK_DIMS = ['interval', 'crosshair', 'time', 'price', 'session'];
export const LAYOUT_PRESETS = [
  { id: 'single', panes: 1 },
  { id: 'split', panes: 2 },
  { id: 'three', panes: 3 },
];
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

// --- B11 mounted-manager operations ---

// Atomic evidence invalidation: every pane's generation advances together, so
// a result computed against the pre-change state is rejected for ALL panes.
export function invalidateAll(panes) {
  return panes.map((p) => ({ ...p, generation: p.generation + 1 }));
}

// Resize to a preset: kept panes keep identity+symbol, new slots appear
// unfocused, and every generation advances (a layout change invalidates the
// previous composition's evidence atomically). Pane 0 holds focus when the
// previous focused pane was removed by the shrink.
export function resizePanes(panes, count, symbol) {
  const base = invalidateAll(panes.slice(0, count));
  const next = [...base];
  while (next.length < count) next.push({ id: `pane-${next.length}`, symbol, focused: false, generation: 1 });
  const hadFocused = next.some((p) => p.focused);
  return next.map((p, i) => ({ ...p, focused: hadFocused ? p.focused : i === 0 }));
}

// Per-instrument sync resolution: a receiving pane applies ONLY allowlisted
// dims of an origin transaction it did not itself emit (no echo), and the
// price dim NEVER crosses unlike symbols. Per-instrument scope/calendar/
// capability stay pane-owned — sync never rewrites instrument identity.
export function resolveSync(origin, target, patch, dims = ['interval', 'session']) {
  if (!origin || origin.id === target.id) return target; // no echo back to the origin
  const allowed = {};
  for (const dim of dims) if (dim in patch) allowed[dim] = patch[dim];
  if ('price' in allowed && !priceLinked(origin, target)) delete allowed.price; // unlike symbols: price links off
  if (!Object.keys(allowed).length) return target;
  return syncState(target, allowed, dims);
}

export function panesReducer(panes, action) {
  switch (action.type) {
    case 'layout': {
      const preset = LAYOUT_PRESETS.find((p) => p.id === action.layout) || LAYOUT_PRESETS[0];
      return resizePanes(panes, preset.panes, action.symbol || (panes[0] && panes[0].symbol) || 'SPY');
    }
    case 'focus':
      return focusPane(panes, action.id, action.symbol);
    case 'sync': {
      const origin = panes.find((p) => p.id === action.origin);
      return panes.map((p) => resolveSync(origin, p, action.patch, action.dims));
    }
    case 'result':
      return panes.map((p) => (p.id === action.id ? applyResult(p, action.result) : p)).filter(Boolean);
    // B12 persistence restore: set pane symbols in order without touching focus
    // or generations — durable layout identity, not a new composition.
    case 'symbols':
      return panes.map((p, i) => (action.symbols && typeof action.symbols[i] === 'string' && action.symbols[i] ? { ...p, symbol: action.symbols[i] } : p));
    default:
      return panes;
  }
}
