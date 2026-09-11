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
