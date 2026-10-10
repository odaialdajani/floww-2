import { createPanes, focusPane, shouldEcho, priceLinked, syncState, applyResult, LINK_DIMS } from '../chartReducer';
test('focus/sync/generation guards', () => {
  expect(LINK_DIMS).toHaveLength(5);
  const panes = createPanes(3, 'SPY');
  const next = focusPane(panes, 'pane-1', 'QQQ');
  expect(next[1].focused && next[1].symbol).toBe('QQQ');
  expect(next[0].focused).toBe(false);
  expect(shouldEcho({ origin: 'a' }, 'b')).toBe(true);
  expect(shouldEcho({ origin: 'a' }, 'a')).toBe(false);
  expect(priceLinked({ symbol: 'SPY' }, { symbol: 'QQQ' })).toBe(false);
  const synced = syncState(next[1], { interval: '5m', symbol: 'HACK' });
  expect(synced.interval).toBe('5m');
  expect(synced.symbol).toBe('QQQ');
  expect(applyResult(synced, { generation: -1, data: 1 })).toBe(synced);
  expect(applyResult(synced, { generation: synced.generation, removed: true })).toBe(null);
});
