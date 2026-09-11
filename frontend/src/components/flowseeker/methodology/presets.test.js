import { STARTER_PRESETS } from './presets.js';

describe('starter presets', () => {
  it('two presets', () => expect(STARTER_PRESETS).toHaveLength(2));
  it('Broad $100K Stocks', () => {
    const p = STARTER_PRESETS.find((x) => x.id === 'broad100k');
    expect(p.title).toMatch(/Broad/);
    expect(p.filters.minPremium).toBe(100000);
    expect(p.filters.equityType.stocks).toBe(true);
    expect(p.filters.equityType.etfs).toBe(false);
  });
  it('High-Conviction Sweeps', () => {
    const p = STARTER_PRESETS.find((x) => x.id === 'sweeps250k');
    expect(p.filters.sweepsOnly).toBe(true);
    expect(p.filters.absScore).toBe(true);
  });
});
