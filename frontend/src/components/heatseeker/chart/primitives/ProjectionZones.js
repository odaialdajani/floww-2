// B10 scenario projection: positioning scenario, not forecast. Future whitespace
// uses current eligible positioning only, interval-aware extent, no future candles.
export function projectionExtent({ intervalMinutes = 5, periods = 6 } = {}) {
  return Math.max(1, intervalMinutes) * Math.max(1, periods);
}
export function buildProjection({ eligiblePositioning, intervalMinutes = 5 }) {
  if (!eligiblePositioning) return { status: 'unavailable', zones: [] };
  return { status: 'scenario', extentMinutes: projectionExtent({ intervalMinutes }), zones: eligiblePositioning.zones || [], forecast: false };
}
