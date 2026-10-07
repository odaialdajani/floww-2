// Used by the live request path and offline saved-outcome review.
export const REQUEST_FAILURE = "Research request could not start";
export function requestFailureText(status, payload) {
 const detail=typeof payload?.detail==="string"?payload.detail:payload?.error;
 return status===422 && typeof detail==="string" && detail.trim() && detail.length<=500
  ? detail.trim() : REQUEST_FAILURE;
}
