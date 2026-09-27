/**
 * Local backend app-key (X-API-Key) for mutating calls.
 *
 * The FastAPI auth middleware rejects every POST/DELETE without the key, and
 * click-to-trade shipped without ever sending it (orders 401'd from birth).
 * The key lives in backend/.env (API_SECRET_KEY); the browser cannot read it,
 * so it is asked once and kept in localStorage (this browser only, never the
 * bundle, never the repo). Empty string = user declined; callers must abort
 * with a clear message instead of firing a doomed request.
 */
const STORE_KEY = "floww_app_key";

function readStored() {
  try {
    return window.localStorage.getItem(STORE_KEY) || "";
  } catch (_) {
    return "";
  }
}

function storeKey(k) {
  try {
    window.localStorage.setItem(STORE_KEY, k);
  } catch (_) {
    /* private mode etc: fall through, key simply won't persist */
  }
}

export function getAppKey() {
  const existing = readStored().trim();
  if (existing) return existing;
  let k = "";
  try {
    k = (window.prompt(
      "Local backend key required (API_SECRET_KEY from backend/.env). " +
      "Stored only in this browser, never sent anywhere except this backend:"
    ) || "").trim();
  } catch (_) {
    k = "";
  }
  if (k) storeKey(k);
  return k;
}

export function clearAppKey() {
  try {
    window.localStorage.removeItem(STORE_KEY);
  } catch (_) {
    /* ignore */
  }
}

/** Headers for mutating backend calls. Returns null when declined. */
export function mutatingHeaders(extra) {
  const k = getAppKey();
  if (!k) return null;
  return { "X-API-Key": k, ...(extra || {}) };
}

/**
 * Raw stored key (no prompt). For transports that cannot take headers
 * (WebSocket URLs) — callers append ?token= when non-empty.
 */
export function storedAppKey() {
  return readStored().trim();
}

/**
 * Headers for authenticated read calls (e.g. brokerage panels).
 * Never prompts: returns null when no key is stored yet, so polling
 * surfaces must not trigger a prompt loop. Callers show a key-missing
 * hint instead.
 */
export function storedAppKeyHeaders(extra) {
  const k = readStored().trim();
  if (!k) return null;
  return { "X-API-Key": k, ...(extra || {}) };
}

/**
 * Append ?token= to a WebSocket URL when a backend key is stored.
 * No prompt (sockets reconnect silently). Returns the URL unchanged
 * when no key is stored — the backend allows that in dev mode.
 */
export function withWsToken(url) {
  const t = storedAppKey();
  if (!t) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(t)}`;
}
