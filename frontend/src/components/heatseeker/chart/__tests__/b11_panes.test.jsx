import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { createPanes, focusPane, shouldEcho, priceLinked, syncState, applyResult, LINK_DIMS, LAYOUT_PRESETS, invalidateAll, resizePanes, resolveSync, panesReducer } from '../chartReducer';

// Bare factory + per-test re-arm (durable pattern for this CRA setup).
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));

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

test('B11 layout presets: three-pane and single are real, named presets', () => {
  expect(LAYOUT_PRESETS.map(p => p.id)).toEqual(['single', 'split', 'three']);
  expect(LAYOUT_PRESETS.find(p => p.id === 'three').panes).toBe(3);
  expect(LAYOUT_PRESETS.find(p => p.id === 'split').panes).toBe(2);
  expect(LAYOUT_PRESETS.find(p => p.id === 'single').panes).toBe(1);
});

test('B11 atomic invalidation: a layout change rejects results computed for the previous composition', () => {
  const before = createPanes(2, 'SPY');
  const staleGeneration = before[1].generation;
  const after = panesReducer(before, { type: 'layout', layout: 'three' });
  expect(after).toHaveLength(3);
  // Every pane's generation advanced together — old-generation evidence is dead.
  after.forEach(p => expect(p.generation).toBeGreaterThan(staleGeneration));
  const applied = panesReducer(after, { type: 'result', id: 'pane-1', result: { generation: staleGeneration, data: 'stale' } });
  expect(applied.find(p => p.id === 'pane-1').data).toBeUndefined();
  // The new generation applies.
  const gen = applied.find(p => p.id === 'pane-1').generation;
  const applied2 = panesReducer(applied, { type: 'result', id: 'pane-1', result: { generation: gen, data: 'live' } });
  expect(applied2.find(p => p.id === 'pane-1').data).toBe('live');
  // Shrinking back to single removes the extra panes; their results are gone.
  const single = panesReducer(applied2, { type: 'layout', layout: 'single' });
  expect(single).toHaveLength(1);
  expect(single[0].focused).toBe(true);
});

test('B11 sync resolution: allowlist applies, unlike symbols never share price, origin never echoes', () => {
  const panes = createPanes(2, 'SPY');
  const unlike = focusPane(panes, 'pane-1', 'QQQ');
  const origin = unlike[0];
  // Same symbol: interval/session patch applies, price applies too.
  const target2 = { ...unlike[1], symbol: 'SPY' };
  const synced = resolveSync(origin, target2, { interval: '15m', session: 'overnight', price: { low: 99, high: 101 } }, ['interval', 'session', 'price']);
  expect(synced.interval).toBe('15m');
  expect(synced.session).toBe('overnight');
  expect(synced.price).toEqual({ low: 99, high: 101 });
  expect(synced.generation).toBe(target2.generation + 1);
  // Unlike symbol: price is dropped, presentation dims still apply.
  const unlikeSynced = resolveSync(origin, unlike[1], { interval: '15m', price: { low: 99, high: 101 } }, ['interval', 'session', 'price']);
  expect(unlikeSynced.interval).toBe('15m');
  expect(unlikeSynced.price).toBeUndefined();
  // Origin never receives its own transaction back.
  const echoed = resolveSync(origin, origin, { interval: '15m' });
  expect(echoed).toBe(origin);
  // Symbol identity is never rewritten by sync (per-instrument ownership).
  expect(unlikeSynced.symbol).toBe('QQQ');
});

test('B11 mounted: the pane manager renders real panes, real layouts and real focus', async () => {
  // Per-test axios re-arm (durable pattern): payload matches any requested ticker.
  const axios = require('axios');
  axios.get.mockImplementation(async url => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] ?? 'SPY';
    return { data: { ticker, query_key: '', frames: [{ time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101 }], candles_with_recorded_nodes: 1, node_status: 'available' } };
  });
  const W = require('../ChartWorkspace').default;
  render(<W ticker="SPY" open useNew />);
  // Single pane by default: one real chart.
  expect(screen.getAllByTestId('price-node-history')).toHaveLength(1);
  expect(screen.getByTestId('pane-count').textContent).toContain('1 pane');
  // Three-pane preset: three REAL chart panes mount, focused pane keeps controls.
  await act(async () => { screen.getByTestId('layout-three').click(); });
  expect(screen.getAllByTestId('price-node-history')).toHaveLength(3);
  expect(screen.getByTestId('pane-layout')).toHaveAttribute('data-layout', 'three');
  // Each real pane keeps its own controls — three charts, three Reload buttons.
  expect(screen.getAllByRole('button', { name: 'Reload history' })).toHaveLength(3);
  expect(screen.getByTestId('pane-count').textContent).toContain('3 panes');
  // Focus moves between real panes.
  await act(async () => { screen.getByTestId('focus-pane-1').click(); });
  expect(screen.getByTestId('focus-pane-1')).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByTestId('focus-pane-0')).toHaveAttribute('aria-pressed', 'false');
  // Back to single: one real pane remains.
  await act(async () => { screen.getByTestId('layout-single').click(); });
  expect(screen.getAllByTestId('price-node-history')).toHaveLength(1);
  // Phone stacking is a real CSS rule, not a claim (direct fs path —
  // require.resolve on CSS yields CRA's mock stub in the jest environment).
  const fs = require('fs');
  const path = require('path');
  const css = fs.readFileSync(path.join(__dirname, '..', 'ChartWorkspace.css'), 'utf8');
  expect(css).toMatch(/@media \(max-width: 620px\)/);
  expect(css).toMatch(/pane-count-2, \.pane-layout\.pane-count-3 \{ grid-template-columns: minmax\(0, 1fr\); \}/);
});
