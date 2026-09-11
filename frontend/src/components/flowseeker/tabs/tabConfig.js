// Pure JS — no React, no backend. ESM.
export const TAB_SCHEMA_VERSION = 1;
export const MAX_TABS_LIVE_FEED = 10;
export const MAX_TABS_SCANNER = 5;

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export function defaultTabConfig(overrides = {}) {
  return {
    schemaVersion: TAB_SCHEMA_VERSION,
    id: overrides.id ?? uid(),
    title: overrides.title ?? 'New Tab',
    filters: overrides.filters ?? {},
    columns: overrides.columns ?? [],
    highlighting: { sizeGtOI: true, volGtOI: true, ...(overrides.highlighting || {}) },
    tickerScope: overrides.tickerScope ?? 'ALL',
    resultsCap: overrides.resultsCap ?? 100,
    sort: overrides.sort ?? { key: 'time', dir: 'desc' },
    ...overrides,
    // ensure nested defaults win if overrides omitted them
    schemaVersion: overrides.schemaVersion ?? TAB_SCHEMA_VERSION,
    id: overrides.id ?? uid(),
    highlighting: { sizeGtOI: true, volGtOI: true, ...(overrides.highlighting || {}) },
    sort: overrides.sort ?? { key: 'time', dir: 'desc' },
  };
}

export function migrateTabConfig(raw) {
  if (!raw || typeof raw !== 'object') return defaultTabConfig();
  const base = defaultTabConfig();
  const cfg = { ...base, ...raw };
  cfg.schemaVersion = TAB_SCHEMA_VERSION;
  if (!cfg.id) cfg.id = uid();
  if (!cfg.title) cfg.title = 'New Tab';
  if (!cfg.filters || typeof cfg.filters !== 'object') cfg.filters = {};
  if (!Array.isArray(cfg.columns)) cfg.columns = [];
  cfg.highlighting = { sizeGtOI: true, volGtOI: true, ...(raw.highlighting || {}) };
  if (!cfg.tickerScope) cfg.tickerScope = 'ALL';
  if (typeof cfg.resultsCap !== 'number') cfg.resultsCap = 100;
  if (!cfg.sort || typeof cfg.sort !== 'object') cfg.sort = { key: 'time', dir: 'desc' };
  if (!cfg.sort.key) cfg.sort.key = 'time';
  if (!cfg.sort.dir) cfg.sort.dir = 'desc';
  return cfg;
}

export function serializeTabConfig(cfg) {
  return JSON.stringify(cfg);
}

export function deserializeTabConfig(str) {
  try {
    const raw = JSON.parse(str);
    return migrateTabConfig(raw);
  } catch {
    return defaultTabConfig();
  }
}
