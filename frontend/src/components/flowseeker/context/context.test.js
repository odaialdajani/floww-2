import { earningsProximity } from './earningsProximity.js';
import { sectorForTicker, equityType } from './sectorMap.js';
import { strategyBadge } from './strategyBadge.js';

describe('W2 context columns', () => {
  it('earnings missing => dash, not zero', () => {
    const r = earningsProximity('AAPL', null);
    expect(r.daysTo).toBeNull();
    expect(r.label).toBe('—');
    expect(r.state).toBe('missing');
  });
  it('earnings computed', () => {
    const now = Date.parse('2026-09-03T00:00:00Z');
    const r = earningsProximity('NVDA', '2026-09-10', now);
    expect(r.daysTo).toBe(7);
    expect(r.state).toBe('has_date');
  });
  it('sector missing => Unknown', () => {
    expect(sectorForTicker('ZZTOP')).toBe('Unknown');
    expect(sectorForTicker(null)).toBe('Unknown');
  });
  it('equityType: SPY etf, SPX index, AAPL stock', () => {
    expect(equityType('SPY')).toBe('etf');
    expect(equityType('SPX')).toBe('index');
    expect(equityType('AAPL')).toBe('stock');
  });
  it('strategyBadge: under->ticker, exp->expiration, no infer legs', () => {
    expect(strategyBadge({ legs: [{ type: 'call' }, { type: 'put' }] })).toBe('MULTI_LEG');
    expect(strategyBadge({ type: 'call' })).toBe('CALL');
    expect(strategyBadge({ legs: [] })).toBeNull();
    expect(strategyBadge({ under: 'AAPL', exp: '2026-09-18' })).toBeNull(); // no type field => no badge, not inferred
  });
});
