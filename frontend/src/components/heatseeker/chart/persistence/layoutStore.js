// B12 store: durable versioned local layouts (localStorage replaces the old
// module Map — layouts now survive actual reload/reopen). Debounced PER-ID
// autosave, count + byte caps, typed storage-quota handling, corrupt-payload
// recovery on read via migrate. Local only — never cross-device sync, and the
// serializer refuses secrets/positions before anything is written.
import { MAX_LAYOUTS, serialize, migrate } from './layoutSchema';

const PREFIX = 'floww.chart.layout.';
const timers = new Map();

function storedNames() {
  const out = [];
  for (let i = 0; i < localStorage.length; i += 1) {
    const key = localStorage.key(i);
    if (key && key.startsWith(PREFIX)) out.push(key.slice(PREFIX.length));
  }
  return out;
}

export function saveLocal(id, layout) {
  const names = storedNames();
  if (names.length >= MAX_LAYOUTS && !names.includes(id)) throw new Error('quota-count');
  const text = serialize(layout);
  try {
    localStorage.setItem(PREFIX + id, text);
  } catch (error) {
    // Browser storage quota exceeded (or storage disabled): honest typed
    // refusal — never silently drop the save.
    throw new Error('quota-storage');
  }
  return text;
}

export function loadLocal(id) {
  const raw = localStorage.getItem(PREFIX + id);
  if (raw === null) return null;
  // Corrupt or old-schema payloads recover to a valid layout instead of
  // poisoning the workspace; the caller receives clean serialized bytes.
  const { layout } = migrate(raw);
  return serialize(layout);
}

export function listLocal() {
  return storedNames();
}

export function removeLocal(id) {
  localStorage.removeItem(PREFIX + id);
}

export function scheduleAutosave(id, layout, ms = 300) {
  // Per-id debounce: saving layout B must never cancel layout A's pending
  // save (the old single global timer did exactly that).
  if (timers.has(id)) clearTimeout(timers.get(id));
  timers.set(id, setTimeout(() => { timers.delete(id); saveLocal(id, layout); }, ms));
}

export function cancelAutosave(id) {
  const timer = timers.get(id);
  if (timer) { clearTimeout(timer); timers.delete(id); }
}

export function _clear() {
  for (const name of storedNames()) localStorage.removeItem(PREFIX + name);
  for (const timer of timers.values()) clearTimeout(timer);
  timers.clear();
}
