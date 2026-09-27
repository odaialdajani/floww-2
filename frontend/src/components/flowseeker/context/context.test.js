// Trimmed 2026-09-27: earningsProximity.js and strategyBadge.js were removed as
// dead code (zero product imports; only this test referenced them). sectorMap.js
// is still live via filters/filterState.js, so its coverage stays.
import { sectorForTicker, equityType } from './sectorMap.js';

describe('W2 context columns', () => {
  it('sector missing => Unknown', () => {
    expect(sectorForTicker('ZZTOP')).toBe('Unknown');
    expect(sectorForTicker(null)).toBe('Unknown');
  });
  it('equityType: SPY etf, SPX index, AAPL stock', () => {
    expect(equityType('SPY')).toBe('etf');
    expect(equityType('SPX')).toBe('index');
    expect(equityType('AAPL')).toBe('stock');
  });
});
