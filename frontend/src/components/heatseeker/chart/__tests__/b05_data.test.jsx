import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { nextGeneration, currentGeneration, dedupeKey, isStale, badgeFor, registerQuery, shouldApply, backfillReplace, createChartSession, useChartData } from '../useChartData';
test('abort stale generations + dedupe (legacy module session, unchanged contract)', () => {
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

test('B05 per-pane sessions isolate generations — pane B can never invalidate pane A', () => {
  const paneA = createChartSession();
  const paneB = createChartSession();
  const ga = paneA.nextGeneration();
  paneA.registerQuery('SPY|5m|rth|front', ga);
  paneB.nextGeneration(); // pane B refreshes its own pane
  expect(paneA.shouldApply('SPY|5m|rth|front', ga)).toBe(true); // pane A unaffected
  expect(paneB.shouldApply('SPY|5m|rth|front', paneB.currentGeneration())).toBe(false); // B never registered that key
});

function Harness({ symbol, fetcher }) {
  const chart = useChartData({ symbol, interval: '5m', session: 'rth', scope: 'front', fetcher });
  return <div data-testid="pane" data-status={chart.status} data-badge={chart.badge}>{JSON.stringify(chart.data)}<button type="button" onClick={() => chart.refresh()}>refresh</button></div>;
}

test('B05 mounted: a stale symbol generation is aborted and never lands; the new one does', async () => {
  const deferred = [];
  const fetcher = jest.fn(({ symbol }) => new Promise(resolve => { deferred.push({ symbol, resolve }); }));
  const view = render(<Harness symbol="SPY" fetcher={fetcher} />);
  expect(fetcher).toHaveBeenCalledTimes(1);
  // Symbol switches before the first response arrives.
  await act(async () => { view.rerender(<Harness symbol="QQQ" fetcher={fetcher} />); });
  expect(fetcher).toHaveBeenCalledTimes(2);
  // The stale SPY response resolves late — it must never land.
  await act(async () => { deferred[0].resolve({ data: [{ close: 'STALE-SPY' }] }); });
  expect(screen.getByTestId('pane').textContent).not.toContain('STALE-SPY');
  // The active QQQ generation lands.
  await act(async () => { deferred[1].resolve({ data: [{ close: 'QQQ-LIVE' }] }); });
  await waitFor(() => expect(screen.getByTestId('pane')).toHaveAttribute('data-status', 'ready'));
  expect(screen.getByTestId('pane').textContent).toContain('QQQ-LIVE');
});

test('B05 mounted: same-key requests dedupe to one in-flight query', async () => {
  const deferred = [];
  const fetcher = jest.fn(() => new Promise(resolve => { deferred.push({ resolve }); }));
  render(<Harness symbol="SPY" fetcher={fetcher} />);
  expect(fetcher).toHaveBeenCalledTimes(1);
  // A second request for the SAME pane key while the first is still in
  // flight shares that query — no duplicate fetch.
  await act(async () => { screen.getByRole('button', { name: 'refresh' }).click(); });
  await act(async () => { screen.getByRole('button', { name: 'refresh' }).click(); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { deferred[0].resolve({ data: [{ close: 1 }] }); });
  await waitFor(() => expect(screen.getByTestId('pane')).toHaveAttribute('data-status', 'ready'));
});

test('B05 mounted: explicit stale/cache/budget/outage badges surface from fetcher outcomes', async () => {
  const cases = [
    [{ cached: true, data: [] }, 'cached'],
    [{ stale: true, data: [] }, 'stale'],
    [{ budgetExhausted: true, data: [] }, 'budget-exhausted'],
    [{ outage: true, data: [] }, 'outage'],
  ];
  for (const [outcome, expected] of cases) {
    const fetcher = jest.fn(() => new Promise(resolve => resolve(outcome)));
    const view = render(<Harness symbol="SPY" fetcher={fetcher} />);
    await waitFor(() => expect(screen.getByTestId('pane')).toHaveAttribute('data-badge', expected));
    view.unmount();
  }
});

test('B05 mounted: a rejected fetch with an outage flag surfaces error + outage, never fake data', async () => {
  const fetcher = jest.fn(() => Promise.reject(Object.assign(new Error('provider unreachable'), { outage: true })));
  render(<Harness symbol="SPY" fetcher={fetcher} />);
  await waitFor(() => expect(screen.getByTestId('pane')).toHaveAttribute('data-status', 'error'));
  expect(screen.getByTestId('pane')).toHaveAttribute('data-badge', 'outage');
  expect(screen.getByTestId('pane').textContent).toMatch(/^null/); // no invented data before the refresh control
});
