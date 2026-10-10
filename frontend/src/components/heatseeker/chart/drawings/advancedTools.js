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
