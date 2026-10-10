import { nextGeneration, currentGeneration, dedupeKey, isStale, badgeFor, registerQuery, shouldApply, backfillReplace } from '../useChartData';
test('abort stale generations + dedupe', () => {
  const g1 = nextGeneration(); registerQuery('SPY|5m|rth|front', g1);
  const g2 = nextGeneration();
  expect(isStale(g1, currentGeneration())).toBe(true);
  expect(shouldApply('SPY|5m|rth|front', g1)).toBe(false);
  registerQuery('SPY|5m|rth|front', g2);
  expect(shouldApply('SPY|5m|rth|front', g2)).toBe(true);
  expect(dedupeKey({ symbol: 'SPY', interval: '5m', session: 'rth', scope: 'front' })).toBe('SPY|5m|rth|front');
});
test('badges + backfill replace', () => {
  expect(badgeFor({ outage: true })).toBe('outage');
  expect(badgeFor({ budget: true })).toBe('budget-exhausted');
  expect(badgeFor({ stale: true })).toBe('stale');
  expect(badgeFor({ cached: true })).toBe('cached');
  expect(badgeFor({})).toBe('live');
  const cur = [1];
  expect(backfillReplace(cur, { generation: currentGeneration(), data: [2] })).toEqual([2]);
  expect(backfillReplace(cur, { generation: -1, data: [9] })).toEqual([1]);
});
