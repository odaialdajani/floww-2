// B12 versioned local layouts: false/zero roundtrip, quota/size caps, no secrets.
export const SCHEMA_VERSION = 1;
export const MAX_LAYOUTS = 50;
export const MAX_BYTES = 200000;
export function createLayout(overrides = {}) {
  return { schema_version: SCHEMA_VERSION, showGrid: false, opacity: 0, drawings: [], ...overrides };
}
export function serialize(layout) {
  if (layout?.apiKey || layout?.positions || layout?.brokerAccount) throw new Error('secrets-refused');
  const text = JSON.stringify({ ...layout, schema_version: SCHEMA_VERSION });
  if (text.length > MAX_BYTES) throw new Error('quota-bytes');
  return text;
}
export function migrate(raw) {
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (!data || typeof data !== 'object') return { recovered: true, layout: createLayout() };
    return { recovered: false, layout: { ...createLayout(), ...data, schema_version: SCHEMA_VERSION } };
  } catch {
    return { recovered: true, layout: createLayout() };
  }
}
export function sanitizeImport(obj) {
  if (!obj || typeof obj !== 'object') throw new Error('bad-import');
  for (const k of Object.keys(obj)) {
    if (k === '__proto__' || k === 'constructor' || k === 'prototype') throw new Error('proto-refused');
  }
  if (typeof obj.script === 'string') throw new Error('scripts-refused');
  return obj;
}
