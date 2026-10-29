// B17 preset PERSISTENCE — the local device half. localStorage per SCOPE
// (ticker), mirroring drawingPersistence.js: quota-capped, corrupt rows
// recover to empty, secrets/positions refused, local only — never a
// cross-device or account sync claim (cloudSyncStatus says so honestly).
// The local half is NOT gated on any account/auth state: there is no auth
// parameter in this module at all.
import { isSupportedTool } from './toolRegistry';
import { PRESET_CAP } from './presetSchema';

export const PRESET_STORAGE_VERSION = 1;
export const PRESET_BYTES = 50000;
const keyFor = (scope) => `floww.drawing.presets.${String(scope || '').toUpperCase()}`;

function readEnvelope(scope) {
  try {
    const raw = window.localStorage.getItem(keyFor(scope));
    if (!raw) return null;
    const data = JSON.parse(raw);
    return data && typeof data === 'object' ? data : null;
  } catch {
    return null;
  }
}

// Forward compat: versioned envelope. Unknown NEWER versions load as empty
// (honest unknown, never a guessed preset) and savePresets REFUSES to
// overwrite them — an older build must never destroy future data. Unknown
// fields INSIDE the current version are preserved untouched.
export function loadPresets(scope) {
  const env = readEnvelope(scope);
  if (!env || typeof env.v !== 'number' || !Array.isArray(env.presets)) return [];
  if (env.v > PRESET_STORAGE_VERSION) return []; // future envelope — not ours to interpret
  return env.presets.filter((p) => p && typeof p.id === 'string' && typeof p.name === 'string' && isSupportedTool(p.tool));
}

export function savePresets(scope, list) {
  const clean = Array.isArray(list) ? list : [];
  const existing = readEnvelope(scope);
  if (existing && typeof existing.v === 'number' && existing.v > PRESET_STORAGE_VERSION) {
    throw new Error('newer preset storage version (' + existing.v + ') — refusing to overwrite future data');
  }
  if (clean.length > PRESET_CAP) {
    throw new Error('preset cap reached (' + PRESET_CAP + ')');
  }
  for (const p of clean) {
    if (!p || typeof p.id !== 'string' || typeof p.name !== 'string' || !isSupportedTool(p.tool)) {
      throw new Error('invalid preset row');
    }
    if (p.apiKey || p.positions || p.brokerAccount) throw new Error('secrets refused');
  }
  const text = JSON.stringify({ v: PRESET_STORAGE_VERSION, presets: clean });
  if (text.length > PRESET_BYTES) throw new Error('preset quota exceeded');
  window.localStorage.setItem(keyFor(scope), text);
}

export function clearPresets(scope) {
  window.localStorage.removeItem(keyFor(scope));
}

// C091 account sync stays honest-external: the local device half makes NO
// cloud/account claim. available:false is the truth for this module; any
// future cloud half is a separate owner-approved surface, not implied here.
export function cloudSyncStatus() {
  return {
    available: false,
    claim: 'Local device only — presets are stored on this device per chart scope; no cloud or account sync is claimed or performed.',
  };
}

// CHART-C131 "local-only explicitly labelled": the short UI label every
// mounted preset section shows. Single-sourced here so the module's honesty
// and the visible label can never drift apart.
export const LOCAL_ONLY_LABEL = 'Local to this device — no cloud or account sync claimed.';
