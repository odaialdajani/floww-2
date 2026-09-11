import { defaultTabConfig, migrateTabConfig, serializeTabConfig, deserializeTabConfig, MAX_TABS_LIVE_FEED, MAX_TABS_SCANNER, TAB_SCHEMA_VERSION } from './tabConfig.js';

describe('tabConfig', () => {
  it('default has schemaVersion and all fields', () => {
    const c = defaultTabConfig();
    expect(c.schemaVersion).toBe(TAB_SCHEMA_VERSION);
    expect(c.id).toBeDefined();
    expect(c.highlighting.sizeGtOI).toBe(true);
    expect(c.tickerScope).toBe('ALL');
    expect(c.resultsCap).toBe(100);
  });
  it('migrate fills missing fields', () => {
    const m = migrateTabConfig({ title: 'Old' });
    expect(m.schemaVersion).toBe(TAB_SCHEMA_VERSION);
    expect(m.id).toBeDefined();
    expect(m.tickerScope).toBe('ALL');
    expect(m.highlighting).toBeDefined();
  });
  it('migrate handles null/old version', () => {
    expect(migrateTabConfig(null).schemaVersion).toBe(TAB_SCHEMA_VERSION);
    expect(migrateTabConfig({ schemaVersion: 0, title: 'v0' }).schemaVersion).toBe(TAB_SCHEMA_VERSION);
  });
  it('serialize/deserialize round-trip', () => {
    const c = defaultTabConfig({ title: 'My Tab' });
    const s = serializeTabConfig(c);
    const d = deserializeTabConfig(s);
    expect(d.title).toBe('My Tab');
    expect(d.schemaVersion).toBe(TAB_SCHEMA_VERSION);
  });
  it('deserialize handles bad JSON', () => {
    const d = deserializeTabConfig('not json');
    expect(d.schemaVersion).toBe(TAB_SCHEMA_VERSION);
  });
  it('max tabs constants', () => {
    expect(MAX_TABS_LIVE_FEED).toBe(10);
    expect(MAX_TABS_SCANNER).toBe(5);
  });
});
