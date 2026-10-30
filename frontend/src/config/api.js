/**
 * API configuration — supports both local backend and AlphaPod API proxy.
 *
 * REACT_APP_BACKEND_URL — FastAPI backend origin. UNSET in production builds:
 * the app is served behind Caddy which reverse-proxies /api and /ws, so we
 * use same-origin (window.location.origin) and everything "just works" on
 * localhost:3000, a LAN host, or https://your.domain with zero rebuild config.
 * Set REACT_APP_BACKEND_URL=http://localhost:8000 only for dev against a
 * non-proxied backend.
 */
// NOTE: CRA's webpack replaces process.env.REACT_APP_* with literals and terser
// constant-folds `envVar || window.location.origin` at BUILD time — baking
// localhost into the bundle (verified twice in main.*.js, even through helper
// functions and globalThis lookups). The only reliable escape hatch: a Function
// constructor, which terser never evaluates. Fallback keeps SSR/tests working.
let computedOrigin;
try {
  // eslint-disable-next-line no-new-func
  computedOrigin = new Function("return typeof window!==\"undefined\" && window.location && window.location.origin || \"\";")();
} catch (e) {
  computedOrigin = "";
}

// The managed desktop build is opened from loopback, but the same build is
// also opened from a phone on the Mac's LAN address. Deriving the API host
// from the page host keeps one build working on both without baking a LAN IP:
// 127.0.0.1/localhost -> the managed loopback backend, any other host -> the
// same host on the managed backend port. An explicit REACT_APP_* origin still
// wins (dev/proxy deployments, tests).
export function backendBaseFor(origin) {
  if (!origin || !/^https?:\/\//i.test(origin)) return "http://localhost:8000";
  let host;
  try { host = new URL(origin).hostname; } catch (e) { return "http://localhost:8000"; }
  if (host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]") {
    return "http://127.0.0.1:8213";
  }
  return `http://${host}:8213`;
}

export const BACKEND_BASE =
  process.env.REACT_APP_BACKEND_URL ||
  process.env.REACT_APP_STEAL_THREE_BASE ||
  process.env.REACT_APP_API_BASE ||
  backendBaseFor(computedOrigin);

export const BACKEND_URL = BACKEND_BASE;
export const API = `${BACKEND_BASE}/api`;
export const ALPHAPOD_API = process.env.REACT_APP_API_URL || "https://api.alphapodtrading.com";
export const USE_ALPHAPOD_PROXY = process.env.REACT_APP_ALPHAPOD_PROXY === "true";
