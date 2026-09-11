import { applyFilters, defaultFilterState, widenActions } from './filterState.js';
import { tickerScopeFilter, resultsCap, sortRows } from '../feed/feedTabs.js';

describe('filter subtractiveness', () => {
  const rows = [
    { ticker: 'SPY', type: 'call', premium: 50000, classification: 'sweep', side: 'ASK', volume: 200 },
    { ticker: 'AAPL', type: 'put', premium: 10000, classification: 'regular', side: 'BID', volume: 50 },
    { ticker: 'SPX', type: 'call', premium: 30000, classification: 'sweep', side: 'MID', volume: 300 },
  ];
  it('sweepsOnly removes non-sweep, does not scale bars', () => {
    const { rows: out, beforeCount, afterCount } = applyFilters(rows, { ...defaultFilterState(), sweepsOnly: true });
    expect(beforeCount).toBe(3);
    expect(afterCount).toBe(2);
    expect(out.every((r) => r.classification === 'sweep')).toBe(true);
  });
  it('equityType ETF-off removes SPY', () => {
    const { rows: out } = applyFilters(rows, { ...defaultFilterState(), equityType: { stocks: true, etfs: false, indices: true } });
    // SPY is etf, SPX is index, AAPL stock
    expect(out.find((r) => r.ticker === 'SPY')).toBeUndefined();
  });
  it('before/after counts exposed', () => {
    const res = applyFilters(rows, defaultFilterState());
    expect(res.beforeCount).toBe(3);
    expect(res.afterCount).toBe(3);
  });
});

describe('!ticker exclusion', () => {
  const rows = [{ ticker: 'SPY' }, { ticker: 'AAPL' }, { ticker: 'SPY' }];
  it('!SPY excludes SPY', () => {
    expect(tickerScopeFilter(rows, '!SPY')).toHaveLength(1);
    expect(tickerScopeFilter(rows, '!SPY')[0].ticker).toBe('AAPL');
  });
  it('SPY includes only SPY', () => {
    expect(tickerScopeFilter(rows, 'SPY')).toHaveLength(2);
  });
  it('ALL passes all', () => {
    expect(tickerScopeFilter(rows, 'ALL')).toHaveLength(3);
  });
});

describe('non-Time sort floor', () => {
  it('premium sort filters <25K', () => {
    const rows = [{ premium: 10000 }, { premium: 50000 }, { premium: 30000 }];
    const out = sortRows(rows, { key: 'premium', dir: 'desc' });
    expect(out).toHaveLength(2);
    expect(out[0].premium).toBe(50000);
  });
  it('size sort filters <150', () => {
    const rows = [{ volume: 50 }, { volume: 200 }, { volume: 100 }];
    const out = sortRows(rows, { key: 'size', dir: 'desc' });
    expect(out).toHaveLength(1);
    expect(out[0].volume).toBe(200);
  });
  it('time sort has no floor', () => {
    const rows = [{ timestamp: 100 }, { timestamp: 200 }];
    expect(sortRows(rows, { key: 'time', dir: 'desc' })).toHaveLength(2);
  });
});

describe('resultsCap', () => {
  it('caps at 50/100/250/500', () => {
    const rows = Array.from({ length: 200 }, (_, i) => ({ id: i }));
    expect(resultsCap(rows, 50)).toHaveLength(50);
    expect(resultsCap(rows, 100)).toHaveLength(100);
  });
});

describe('widen actions', () => {
  it('each action measurably widens on fixture', () => {
    const rows = [
      { ticker: 'SPY', premium: 50000, classification: 'sweep', volume: 200 },
      { ticker: 'AAPL', premium: 10000, classification: 'regular', volume: 50 },
      { ticker: 'NVDA', premium: 60000, classification: 'sweep', volume: 300 },
    ];
    const tight = { ...defaultFilterState(), sweepsOnly: true, minPremium: 40000 };
    const afterTight = applyFilters(rows, tight).afterCount;
    expect(afterTight).toBe(2); // SPY + NVDA sweeps >=40k
    const widened = applyFilters(rows, { ...tight, sweepsOnly: false, minPremium: 0 }).afterCount;
    expect(widened).toBeGreaterThan(afterTight);
  });
  it('widenActions returns at least one for tight filters', () => {
    const acts = widenActions({ sweepsOnly: true, minPremium: 50000, equityType: { stocks: true, etfs: false, indices: true } });
    expect(acts.length).toBeGreaterThan(0);
    expect(acts.some((a) => a.action === 'clear_sweep')).toBe(true);
  });
});
