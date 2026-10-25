// B08 study-instance persistence: per-symbol, versioned, quota-capped,
// corrupt rows recover to empty — the drawing-store pattern applied to study
// instances. Local only — never a cross-device sync claim. No secrets: only
// registry-known kinds + validated numeric settings are stored. The stored
// rows carry the contract shape {instanceId, kind, settings, source,
// visible, order} plus additive provenance (paneKey/created) verbatim —
// booleans and numbers round-trip exactly, never coerced.
import { getStudy, validateStudySettings } from '../indicators/registry';

export const STUDY_QUOTA = 24;
export const STUDY_BYTES = 20000;
const SCHEMA_VERSION = 1;
const keyFor = (ticker) => `floww.chart.studies.${String(ticker || '').toUpperCase()}`;

function isPlainInstance(value) {
  if (!value || typeof value !== 'object') return false;
  if (typeof value.instanceId !== 'string' || !value.instanceId) return false;
  const declaration = getStudy(value.kind);
  if (!declaration) return false;
  const settings = value.settings && typeof value.settings === 'object' ? value.settings : null;
  if (!settings) return false;
  // persisted settings must still validate against the registry declaration
  return validateStudySettings(value.kind, settings);
}

export function loadStudyInstances(ticker) {
  try {
    const raw = window.localStorage.getItem(keyFor(ticker));
    if (!raw) return [];
    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object' || !Array.isArray(data.instances)) return [];
    if (data.schema_version !== SCHEMA_VERSION) return [];
    return data.instances.filter(isPlainInstance);
  } catch {
    return [];
  }
}

export function saveStudyInstances(ticker, instances) {
  const list = Array.isArray(instances) ? instances : [];
  if (list.length > STUDY_QUOTA) throw new Error('study quota exceeded');
  for (const inst of list) {
    if (!isPlainInstance(inst)) throw new Error('invalid study instance');
  }
  const text = JSON.stringify({ schema_version: SCHEMA_VERSION, instances: list });
  if (text.length > STUDY_BYTES) throw new Error('study quota exceeded');
  window.localStorage.setItem(keyFor(ticker), text);
}

export function clearStudyInstances(ticker) {
  window.localStorage.removeItem(keyFor(ticker));
}
