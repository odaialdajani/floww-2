// Single source of truth for the heatmap data query string.
//
// BOTH data paths must use this — the 25s polling effect (`/api/data/{ticker}`)
// and the manual-refresh fetch (`/api/heatmap/{ticker}`) — otherwise the poll
// overwrites the user's DTE/Expiries/mode selection with backend defaults
// (the Round-8 "controls don't work" regression).
//
// F07: `mode=scalp` alone never implied backend volume weighting — the backend
// branch depends on the explicit `scalp=true` boolean AND emits a real 2D grid
// (server fix). Horizon, lookback, display and weighting are independent:
//   - mode: day | swing | scalp (display horizon/band)
//   - scalp: boolean (volume-weighted engine + 0DTE force)
//   - metric: gex | gross | dadgex | activity (client-selected overlay; server
//     basis stays explicit via exposure_basis)
// `dte` uses a `!= null` check: 0 (0DTE) is a real value and must be sent.
export function buildHeatmapQuery({ expiries, mode, dte, scalp } = {}) {
  const parts = [
    `expiries=${expiries != null ? expiries : 4}`,
    `mode=${mode || "day"}`,
  ];
  if (dte != null) parts.push(`dte=${dte}`);
  if (scalp != null) parts.push(`scalp=${scalp ? "true" : "false"}`);
  return parts.join("&");
}

// Query identity for snapshot-linked selection (F19): generation id + scope.
export function heatmapQueryKey({ ticker, expiries, mode, dte, scalp }) {
  return [ticker, expiries ?? 4, mode || "day", dte ?? "-", scalp ? "scalp" : "oi"].join("|");
}
