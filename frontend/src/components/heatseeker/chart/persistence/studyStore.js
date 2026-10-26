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

// Set-wide identity invariant (C045): row validation alone cannot stop two
// VALID rows from sharing one instanceId (a legacy/corrupt persisted set, or
// a caller handing saveStudyInstances a duplicated list) — and duplicate ids
// become duplicate React keys that make the caller's update/remove by id hit
// EVERY matching row. Deterministic repair at BOTH store boundaries: the
// FIRST row in stored order keeps its id verbatim (legacy ids stay stable);
// each later duplicate is re-minted `${id}-dup2`, `-dup3`, … skipping any id
// the set already contains. Every other field rides through untouched — no
// study is dropped, coalesced or overwritten, and the repair is a pure
// function of stored content+order, so an unrepaired set heals identically
// on every load until the next save persists it.
function resolveDuplicateInstanceIds(list) {
  const taken = new Set(list.map(inst => inst.instanceId));
  const kept = new Set();
  return list.map(inst => {
    if (!kept.has(inst.instanceId)) { kept.add(inst.instanceId); return inst; }
    let suffix = 2;
    while (taken.has(`${inst.instanceId}-dup${suffix}`)) suffix += 1;
    const repaired = { ...inst, instanceId: `${inst.instanceId}-dup${suffix}` };
    taken.add(repaired.instanceId);
    return repaired;
  });
}

export function loadStudyInstances(ticker) {
  try {
    const raw = window.localStorage.getItem(keyFor(ticker));
    if (!raw) return [];
    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object' || !Array.isArray(data.instances)) return [];
    if (data.schema_version !== SCHEMA_VERSION) return [];
    return resolveDuplicateInstanceIds(data.instances.filter(isPlainInstance));
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
  const unique = resolveDuplicateInstanceIds(list);
  const text = JSON.stringify({ schema_version: SCHEMA_VERSION, instances: unique });
  if (text.length > STUDY_BYTES) throw new Error('study quota exceeded');
  window.localStorage.setItem(keyFor(ticker), text);
}

export function clearStudyInstances(ticker) {
  window.localStorage.removeItem(keyFor(ticker));
}
