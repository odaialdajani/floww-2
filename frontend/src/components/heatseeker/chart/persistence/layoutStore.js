// B12 store: debounced autosave, quota caps. Local only, never cross-device sync.
import { MAX_LAYOUTS, serialize } from './layoutSchema';
const mem = new Map();
let timer = null;
export function saveLocal(id, layout) {
  if (mem.size >= MAX_LAYOUTS && !mem.has(id)) throw new Error('quota-count');
  mem.set(id, serialize(layout));
}
export function loadLocal(id) { return mem.get(id) || null; }
export function scheduleAutosave(id, layout, ms = 300) {
  clearTimeout(timer);
  timer = setTimeout(() => saveLocal(id, layout), ms);
}
export function _clear() { mem.clear(); }
