// P3 drawing persistence: localStorage per symbol, like saved views.
// Quota-capped, corrupt rows recover to empty, secrets/positions refused.
// Local only — never a cross-device sync claim.
import { isSupportedTool } from './toolRegistry';
export const DRAWING_QUOTA = 100;
export const DRAWING_BYTES = 100000;
const keyFor = (ticker) => `floww.drawings.${String(ticker || '').toUpperCase()}`;
export function loadDrawings(ticker) {
  try {
    const raw = window.localStorage.getItem(keyFor(ticker));
    if (!raw) return [];
    const data = JSON.parse(raw);
    if (!Array.isArray(data)) return [];
    return data.filter((d) => d && typeof d.id === 'string' && isSupportedTool(d.tool));
  } catch { return []; }
}
export function saveDrawings(ticker, drawings) {
  const list = Array.isArray(drawings) ? drawings : [];
  if (list.length > DRAWING_QUOTA) throw new Error('drawing quota exceeded');
  for (const d of list) {
    if (!d || typeof d.id !== 'string' || !isSupportedTool(d.tool)) {
      throw new Error('unsupported drawing');
    }
    if (d.apiKey || d.positions || d.brokerAccount) throw new Error('secrets refused');
  }
  const text = JSON.stringify(list);
  if (text.length > DRAWING_BYTES) throw new Error('drawing quota exceeded');
  window.localStorage.setItem(keyFor(ticker), text);
}
export function clearDrawings(ticker) {
  window.localStorage.removeItem(keyFor(ticker));
}
