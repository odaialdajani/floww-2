// localStorage-first tracker store — bookmark, P/L, statuses. Mongo promotion out of scope.
const KEY = 'fsb-tracker-v1';

export function loadTracker() {
  try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; }
}
export function saveTracker(items) {
  try { localStorage.setItem(KEY, JSON.stringify(items)); } catch { /* private mode */ }
}
export function addBookmark(row) {
  const items = loadTracker();
  const id = `${row.ticker ?? row.under}|${row.type}|${row.strike}|${row.exp ?? row.expiration}|${Date.now()}`;
  const entry = {
    id, ticker: row.ticker ?? row.under, type: row.type, strike: row.strike,
    exp: row.exp ?? row.expiration, entryPremium: row.premium ?? null,
    entryPrice: row.last ?? row.mid ?? null, addedAt: Date.now(),
  };
  const next = [entry, ...items].slice(0, 100);
  saveTracker(next);
  return next;
}
export function removeBookmark(id) {
  const next = loadTracker().filter((x) => x.id !== id);
  saveTracker(next);
  return next;
}

// P/L mark priority: mid -> last -> stale
export function markFor(contract, quote) {
  if (!quote) return null;
  if (quote.mid != null && Number.isFinite(Number(quote.mid))) return Number(quote.mid);
  if (quote.last != null && Number.isFinite(Number(quote.last))) return Number(quote.last);
  return null; // stale
}

export function trackerPL(entry, quote) {
  const mark = markFor(entry, quote);
  if (mark == null || entry.entryPrice == null) return { pl: null, mark, state: 'stale' };
  const entryPx = Number(entry.entryPrice);
  const qty = 1; // single contract display; real qty would come from row
  const isCall = String(entry.type).toLowerCase().startsWith('c');
  // Long premium P/L proxy: (mark - entry) * 100
  const pl = (mark - entryPx) * 100 * qty;
  return { pl, mark, state: 'live' };
}

// Close detection proxy via OI drift/volume — labeled as proxy
export function trackerStatus(entry, oiInfo) {
  if (!oiInfo) return 'UNKNOWN';
  const { oi, prevOI, volume } = oiInfo;
  if (oi == null || prevOI == null) return 'UNKNOWN';
  if (oi === 0 && (volume || 0) > 0) return 'EXITED';
  if (prevOI > 0 && oi < prevOI * 0.5) return 'PARTIAL';
  if (prevOI > 0 && oi >= prevOI * 0.9) return 'STILL IN';
  if (oi > 0 && oi < prevOI) return 'PENDING';
  // expiry check
  if (entry.exp) {
    const expMs = Date.parse(entry.exp);
    if (Number.isFinite(expMs) && Date.now() > expMs) return 'EXPIRED';
  }
  return 'UNKNOWN';
}
