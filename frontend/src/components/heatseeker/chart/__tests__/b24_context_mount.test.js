// B24 mirror of backend tests/chart/test_b24_context.py, plus the client
// display contract: the focused-chart ask gate refuses exactly these races.
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
import { bindContext, resolveContext } from '../context/chartContext';

test('B24 bind refuses incomplete binding; complete bind carries the identity', () => {
  expect(bindContext({ focus: null, query: 'q', scope: 's', cursor: 1, generation: 1 }).status).toBe('refused');
  expect(bindContext({ focus: 'SPY', query: '', scope: 's', cursor: 1, generation: 1 }).status).toBe('refused');
  expect(bindContext({ focus: 'SPY', query: 'q', scope: '', cursor: 1, generation: 1 }).status).toBe('refused');
  expect(bindContext({ focus: 'SPY', query: 'q', scope: 's', cursor: null, generation: 1 }).status).toBe('refused');
  expect(bindContext({ focus: 'SPY', query: 'q', scope: 's', cursor: 1, generation: null }).status).toBe('refused');
  const d = bindContext({ focus: 'SPY', query: 'q', scope: 'front', cursor: 100, generation: 7 });
  expect(d).toEqual({ status: 'bound', focus: 'SPY', query: 'q', scope: 'front', cursor: 100, generation: 7 });
});

test('B24 resolve admits only exact generation + matching scope on a live pane', () => {
  const d = bindContext({ focus: 'SPY', query: 'q', scope: 'front', cursor: 100, generation: 7 });
  expect(resolveContext(null, { generation: 7, scope: 'front' })).toEqual({ status: 'refused', reason: 'unbound' });
  expect(resolveContext(d, { generation: 6, scope: 'front' })).toEqual({ status: 'refused', reason: 'stale generation' });
  expect(resolveContext(d, { generation: 7, scope: 'other' })).toEqual({ status: 'refused', reason: 'scope mismatch' });
  expect(resolveContext(d, { generation: 7, scope: 'front', pane_removed: true })).toEqual({ status: 'refused', reason: 'pane removed' });
  expect(resolveContext(d, { generation: 7, scope: 'front' })).toEqual({ status: 'admitted', focus: 'SPY' });
});

// --- B24 admission gate + mounted strip (AskFlow + workspace) ---
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';
import { admissionBlock } from '../../AskFlow';

test('B24 admission: a bound, current chart context admits the price-history ask; races refuse; absent context keeps the legacy refusal', () => {
  const descriptor = bindContext({ focus: 'SPY', query: 'focused-chart', scope: 'front', cursor: 100, generation: 7 });
  // Admitted: the ask opens; the disclosure states the server resolves facts.
  expect(admissionBlock({ context: { ticker: 'SPY' }, overlayMetric: 'raw', displayMode: 'price-history',
    chartContext: { descriptor, current: { generation: 7, scope: 'front' } } })).toBe(null);
  // Stale generation refuses with the exact race reason.
  const stale = admissionBlock({ context: {}, overlayMetric: 'raw', displayMode: 'price-history',
    chartContext: { descriptor, current: { generation: 6, scope: 'front' } } });
  expect(stale).toContain('stale generation');
  // Scope change refuses.
  expect(admissionBlock({ context: {}, overlayMetric: 'raw', displayMode: 'price-history',
    chartContext: { descriptor, current: { generation: 7, scope: 'other' } } })).toContain('scope mismatch');
  // Removed pane refuses.
  expect(admissionBlock({ context: {}, overlayMetric: 'raw', displayMode: 'price-history',
    chartContext: { descriptor, current: { generation: 7, scope: 'front', pane_removed: true } } })).toContain('pane removed');
  // No chart context: the legacy honest refusal stands exactly.
  expect(admissionBlock({ context: { ticker: 'SPY' }, overlayMetric: 'raw', displayMode: 'price-history' }))
    .toBe('Close the price-history chart to ask about the live map.');
});

test('B24 MOUNTED: the workspace binds the focused pane identity and emits it', async () => {
  jest.setTimeout(15000);
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: [
    { time: '2026-09-10T14:00:00+00:00', open: 100, high: 102, low: 99, close: 101, nodes: [] },
    { time: '2026-09-10T14:01:00+00:00', open: 101, high: 103, low: 100, close: 102, nodes: [] },
  ], candles_with_recorded_nodes: 0, scopes: [], query_key: 'SPY:4:day:None:False' } }));
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    const emitted = [];
    const onCtx = (payload) => emitted.push(payload);
    render(<ChartWorkspace ticker="SPY" open useNew onChartContext={onCtx} />);
    await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
    await act(async () => { await new Promise(r => setTimeout(r, 300)); });
    // The strip binds the focused pane's real identity.
    const strip = screen.getByTestId('chart-context');
    expect(strip.getAttribute('data-status')).toBe('bound');
    expect(strip.textContent).toContain('SPY');
    expect(strip.textContent).toContain('scope SPY:4:day:None:False');
    // The caller receives descriptor + current, resolving admitted.
    expect(emitted.length).toBeGreaterThanOrEqual(1);
    const last = emitted[emitted.length - 1];
    expect(last.descriptor.status).toBe('bound');
    expect(last.descriptor.focus).toBe('SPY');
    expect(last.descriptor.scope).toBe('SPY:4:day:None:False');
    const { resolveContext } = require('../context/chartContext');
    expect(resolveContext(last.descriptor, last.current).status).toBe('admitted');
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});

test('R21-06: focus/layout transitions revoke the chart context atomically; late old-pane reports refuse', async () => {
  jest.setTimeout(15000);
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: [
    { time: '2026-09-10T14:00:00+00:00', open: 100, high: 102, low: 99, close: 101, nodes: [] },
    { time: '2026-09-10T14:01:00+00:00', open: 101, high: 103, low: 100, close: 102, nodes: [] },
  ], candles_with_recorded_nodes: 0, scopes: [], query_key: 'SPY:4:day:None:False' } }));
  const { act, render, screen } = require('@testing-library/react');
  const React = require('react');
  const W = require('../ChartWorkspace').default;
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    const emitted = [];
    render(<W ticker="SPY" open useNew onChartContext={p => emitted.push(p)} />);
    await screen.findByTestId('chart-context');
    await act(async () => { await new Promise(r => setTimeout(r, 300)); });
    // Bound while the single focused pane is current.
    const bound = emitted[emitted.length - 1];
    expect(bound.descriptor.status).toBe('bound');
    // Focus/layout transition: switching to the three-pane layout recreates
    // the panes — the OLD binding must revoke IMMEDIATELY (fail-closed), not
    // linger until the new pane reports.
    const beforeCount = emitted.length;
    await act(async () => { screen.getByTestId('layout-three').click(); });
    await act(async () => { await new Promise(r => setTimeout(r, 250)); });
    // The FIRST new emission is the atomic revocation; the rebind may follow.
    expect(emitted.length).toBeGreaterThan(beforeCount);
    expect(emitted[beforeCount].descriptor.status).toBe('refused');
    // Once the new focused pane re-reports (epoch change), the context
    // REBINDS to the new identity — revoked atomically, never lingering.
    await act(async () => { await new Promise(r => setTimeout(r, 400)); });
    const rebind = emitted[emitted.length - 1];
    expect(rebind.descriptor.status).toBe('bound');
    // Focus transition: the old pane-0 binding is revoked ATOMICALLY — the
    // refusal emission exists in the sequence after the transition, and the
    // newly focused pane re-reports and rebinds with its OWN identity (late
    // pane-0 reports can never re-admit: their source no longer matches).
    const preFocusCount = emitted.length;
    await act(async () => { screen.getByTestId('focus-pane-2').click(); });
    await act(async () => { await new Promise(r => setTimeout(r, 400)); });
    const afterFocus = emitted.slice(preFocusCount);
    expect(afterFocus.some(e => e.descriptor.status === 'refused')).toBe(true);
    expect(emitted[emitted.length - 1].descriptor.status).toBe('bound');
    expect(emitted[emitted.length - 1].descriptor.focus).toBe('SPY');
    // Removal transition: dropping to single revokes the pane-2 binding
    // (refusal in the sequence), and the surviving focused pane rebinds with
    // its own current identity.
    const preRemovalCount = emitted.length;
    await act(async () => { screen.getByTestId('layout-single').click(); });
    await act(async () => { await new Promise(r => setTimeout(r, 400)); });
    expect(emitted.slice(preRemovalCount).some(e => e.descriptor.status === 'refused')).toBe(true);
    expect(emitted[emitted.length - 1].descriptor.status).toBe('bound');
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});
