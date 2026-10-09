// EXPOSURE-02: the REST snapshot and the websocket stream are separate
// readings (different expiry scope, formula path, coverage and clocks).
// These pure helpers label the stream with its own identity and name an
// explicit separation note when the two disagree — instead of letting them
// read as one contradictory signal. Unknown stays unknown, never zero.

export function streamScopeLabel(stream) {
  if (!stream || typeof stream !== "object") return "Stream · separate reading · unavailable";
  const exp = Array.isArray(stream.expiries)
    ? `${stream.expiries.length} exp`
    : "expiry scope unknown";
  const units = typeof stream.units === "string" && stream.units ? stream.units : "units unknown";
  const formula = typeof stream.formula_version === "string" && stream.formula_version
    ? stream.formula_version
    : "version unknown";
  return `Stream · separate reading · ${exp} · ${units} · ${formula}`;
}

function comparableStrike(value) {
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const strike = Number(value);
  return Number.isFinite(strike) ? strike : null;
}

export function snapshotStreamNote(snapshotNodes, stream) {
  const snapRegime = snapshotNodes?.regime ?? null;
  const snapKing = snapshotNodes?.king?.strike ?? null;
  const streamRegime = stream?.regime ?? null;
  const streamKing = stream?.king?.strike ?? null;
  const regimeDiffers = snapRegime != null && streamRegime != null && snapRegime !== streamRegime;
  const snapKingN = comparableStrike(snapKing);
  const streamKingN = comparableStrike(streamKing);
  const kingDiffers = snapKingN != null && streamKingN != null && snapKingN !== streamKingN;
  if (!regimeDiffers && !kingDiffers) return null;
  return "Snapshot and stream are separate readings — different scope and clocks. Not one signal.";
}
