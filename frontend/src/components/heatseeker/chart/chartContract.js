// B01 canonical chart contract (frontend mirror, preserves RecordedPriceChart SVG).
// Strict ingress: rejects bool/null/blank/array/object/NaN/Infinity.
// Numeric strings only via explicit grammar. Prices >0, volume >=0.
// Legacy PriceNodeHistory/Trinity consumers unchanged; inferred end never
// proves recorded availability. Recorded-only, no gap fillers.
const NUMERIC_RE = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;

function strictNumber(value) {
  if (typeof value === 'boolean') return null;
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === 'string') {
    const text = value.trim();
    if (!text || !NUMERIC_RE.test(text)) return null;
    const n = Number(text);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function parsePrice(value) {
  const n = strictNumber(value);
  return n !== null && n > 0 ? n : null;
}

export function parseVolume(value) {
  if (value === null || value === undefined) return null;
  const n = strictNumber(value);
  return n !== null && n >= 0 ? n : null;
}

export function legacyCloseForTrinity(frame) {
  if (!frame || typeof frame !== 'object') return null;
  const c = frame.close;
  if (typeof c === 'boolean') return null;
  return typeof c === 'number' && Number.isFinite(c) ? c : null;
}

export function vwapCaption(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return `VWAP ${value.toFixed(2)}`;
  return 'unavailable VWAP';
}

export function barIsComplete(endTime, cursor) {
  const e = Number(endTime), c = Number(cursor);
  return Number.isFinite(e) && Number.isFinite(c) && e <= c;
}

export function revisionIsRecorded(availability, endTime, cursor) {
  return availability === 'recorded' && barIsComplete(endTime, cursor);
}
