// B17 brush/fib/risk + presets: fib levels/style, risk geometry analysis-only,
// cap50, false arrows off, recent opacity/color, hidden stays hidden on switch.
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
export function fibPrices(high, low, levels = FIB_LEVELS) {
  return levels.map((r) => ({ ratio: r, price: high - (high - low) * r }));
}
export function riskBox(entry, stop, target, side = 'long') {
  if (![entry, stop, target].every(Number.isFinite)) return null;
  return { entry, stop, target, side, analysisOnly: true };
}
// CHART-C090 (owner-approved 2026-10-24): "Alt+L/S analysis entry/stop/target
// risk box, never broker intent". The three placed anchors are ORDER-INDEPENDENT:
// prices sort by role for the chosen side — long: stop below entry below target;
// short: stop above entry above target; entry is always the middle price. Zero
// risk (entry == stop) or non-finite/short inputs are refused — never an
// invented R-multiple. rMultiple = |target-entry| / |entry-stop| (display math
// only; this is an analysis drawing, never a broker intent).
export function riskLevels(prices, side = 'long') {
  const list = Array.isArray(prices) ? prices.slice() : [];
  if (list.length !== 3 || !list.every(Number.isFinite)) return null;
  const sorted = [...list].sort((a, b) => a - b);
  const [lo, mid, hi] = sorted;
  const box = side === 'short' ? riskBox(mid, hi, lo, 'short') : riskBox(mid, lo, hi, 'long');
  if (!box) return null;
  const risk = Math.abs(box.entry - box.stop);
  if (!(risk > 0)) return null;
  return { ...box, rMultiple: Math.abs(box.target - box.entry) / risk };
}
