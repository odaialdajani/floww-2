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
export function buildHeatmapQuery({ expiries, mode, dte, scalp, expiryScope } = {}) {
  const parts = [
    `expiries=${expiries != null ? expiries : 4}`,
    `mode=${mode || "day"}`,
  ];
  if (expiryScope === "next") parts.push("expiry_scope=next");
  else if (dte != null) parts.push(`dte=${dte}`);
  if (scalp != null) parts.push(`scalp=${scalp ? "true" : "false"}`);
  return parts.join("&");
}

// The legacy /data alias has no expiry_scope parameter. Next must poll the
// admitted /heatmap endpoint rather than silently returning the loaded scope.
export function heatmapReadPath(ticker, {poll = false, expiryScope = "loaded"} = {}) {
  return `${poll && expiryScope !== "next" ? "data" : "heatmap"}/${encodeURIComponent(ticker)}`;
}

// Query identity for snapshot-linked selection (F19): generation id + scope.
export function heatmapQueryKey({ ticker, expiries, mode, dte, scalp, expiryScope }) {
  return [ticker, expiries ?? 4, mode || "day", expiryScope === "next" ? "next" : dte ?? "-", scalp ? "scalp" : "oi"].join("|");
}
