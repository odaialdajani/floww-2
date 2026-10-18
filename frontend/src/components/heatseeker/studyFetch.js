/**
 * studyFetch.js — shared fetch + error classification for study cards.
 *
 * Heatseeker study cards call backend routes that can fail in three
 * distinct ways, and each deserves its own user-facing verdict:
 *
 *   1. A typed refusal (HTTP 503 with reason PUBLIC_ONLY_STUDY_UNAVAILABLE):
 *      the backend is REACHABLE and deliberately declining to serve the
 *      study on the active feed. This is a study limitation — never a
 *      connection failure and never a prompt to start a backend/sidecar.
 *   2. An untyped HTTP error (any other 4xx/5xx): the backend answered,
 *      something on the server side went wrong.
 *   3. A network failure (fetch rejected): the backend is genuinely
 *      unreachable.
 *
 * WheelIncomeScreenerPanel implemented this handling first; the seven
 * older study cards collapsed all three into "backend unreachable". This
 * module is the single shared implementation so every card reports
 * failures the same honest way.
 *
 * Backend contract (backend/routes/steal_three.py::_require_legacy_market_data):
 *   {"error": {"status": "unavailable", "reason": "...", "message": "..."},
 *    "status_code": 503, "path": "..."}
 * FastAPI's own HTTPException errors arrive as {"detail": ...}; both
 * shapes are accepted.
 */

export const PUBLIC_ONLY_STUDY_UNAVAILABLE = "PUBLIC_ONLY_STUDY_UNAVAILABLE";

/**
 * Fetch a study route and return its parsed JSON body.
 *
 * On a non-2xx response, reject with a typed Error carrying:
 *   - `reason`: the backend's typed refusal reason when one was sent
 *     (e.g. PUBLIC_ONLY_STUDY_UNAVAILABLE), else null
 *   - `httpStatus`: the HTTP status code, so callers can separate a
 *     reachable backend error from a network failure
 *   - `message`: the backend's message when present, else `HTTP <status>`
 */
export async function fetchStudyJSON(url) {
  const r = await fetch(url);
  if (r.ok) return r.json();
  // A reachable backend can still send a typed refusal; keep its reason
  // so cards say "unavailable on this feed", not "unreachable".
  let reason = null;
  let message = `HTTP ${r.status}`;
  try {
    const body = await r.json();
    const inner = body && (body.error ?? body.detail);
    if (inner && typeof inner === "object") {
      reason = inner.reason || null;
      message = inner.message || message;
    } else if (typeof inner === "string") {
      message = inner;
      if (inner.includes(PUBLIC_ONLY_STUDY_UNAVAILABLE)) reason = PUBLIC_ONLY_STUDY_UNAVAILABLE;
    }
  } catch (e) { /* body not JSON → keep the HTTP status */ }
  const typed = new Error(message);
  typed.reason = reason;
  typed.httpStatus = r.status;
  throw typed;
}

/**
 * Map any caught error to one of the three card states.
 * Returns { kind, reason, httpStatus, message } where kind is:
 *   "study-unavailable" | "server-error" | "offline"
 */
export function classifyStudyError(e) {
  const message = e?.message || String(e);
  const reason = e?.reason || null;
  const httpStatus = e?.httpStatus ?? null;
  const kind = reason
    ? "study-unavailable"
    : httpStatus != null
      ? "server-error"
      : "offline";
  return { kind, reason, httpStatus, message };
}
