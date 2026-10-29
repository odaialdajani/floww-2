import React from 'react';
import { render, screen } from '@testing-library/react';
import ChartDocks, { sidecarFor, MAX_SUBSCRIPTIONS, capSubscriptions } from '../ChartDocks';
import { chartScopeFor } from '../scopeEcho';
test('sidecar policy: focus, stale, tombstone, cap', () => {
  expect(sidecarFor(null, {}).status).toBe('unavailable');
  expect(sidecarFor('SPY', {}).status).toBe('missing');
  expect(sidecarFor('SPY', { SPY: { tombstone: true } }).status).toBe('removed');
  expect(sidecarFor('SPY', { SPY: { stale: true, data: 1 } }).status).toBe('stale');
  expect(sidecarFor('SPY', { SPY: { data: 1 } }).status).toBe('ok');
  expect(MAX_SUBSCRIPTIONS).toBe(10);
  expect(capSubscriptions(Array.from({ length: 25 }, (_, i) => 'S' + i))).toHaveLength(10);
  render(<ChartDocks focusedSymbol="SPY" maps={{ SPY: { data: 1 } }} />);
  expect(screen.getByTestId('chart-docks')).toHaveAttribute('data-status', 'ok');
});
test('chart scope comes only from a live server echo', () => {
  expect(chartScopeFor({ scope_echo: 'SPY:4:day:None:False' }, false)).toBe('SPY:4:day:None:False');
  expect(chartScopeFor({ scope_echo: 'SPY:4:day:None:False' }, true)).toBe(null);
  expect(chartScopeFor({}, false)).toBe(null);
  expect(chartScopeFor({ scope_echo: 42 }, false)).toBe(null);
  expect(chartScopeFor(null, false)).toBe(null);
});

// --- B14 dock frame: badges, tombstone suppression, lazy sidecar, census ---
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
import { fireEvent } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';

test('B14 dock: stale badged, tombstone suppressed, sidecar lazy, census capped', async () => {
  // Stale scope is badged visibly, and stale entries still dock content.
  const stale = render(<ChartDocks focusedSymbol="SPY" maps={{ SPY: { stale: true, data: 1 } }} renderSidecar={() => <b>x</b>} />);
  expect(screen.getByTestId('chart-docks')).toHaveAttribute('data-status', 'stale');
  expect(screen.getByTestId('dock-badge').textContent).toContain('stale map');
  expect(screen.getByTestId('dock-sidecar')).toBeInTheDocument();
  stale.unmount();
  // Tombstone: deleted symbols stay removed — no sidecar content is offered.
  const removed = render(<ChartDocks focusedSymbol="SPY" maps={{ SPY: { tombstone: true, data: 1 } }} renderSidecar={() => <b>x</b>} />);
  expect(screen.getByTestId('chart-docks')).toHaveAttribute('data-status', 'removed');
  expect(screen.getByTestId('dock-badge').textContent).toContain('stays removed');
  expect(screen.queryByTestId('dock-sidecar')).not.toBeInTheDocument();
  removed.unmount();
  // Missing entry: honest badge, no invented sidecar.
  const missing = render(<ChartDocks focusedSymbol="QQQ" maps={{ SPY: { data: 1 } }} renderSidecar={() => <b>x</b>} />);
  expect(screen.getByTestId('chart-docks')).toHaveAttribute('data-status', 'missing');
  expect(screen.queryByTestId('dock-sidecar')).not.toBeInTheDocument();
  missing.unmount();
  // Subscription census: 25 requested symbols cap at 10; 3 stay 3.
  const many = render(<ChartDocks focusedSymbol="SPY" maps={{ SPY: { data: 1 } }} subscriptionSymbols={Array.from({ length: 25 }, (_, i) => 'S' + i)} />);
  expect(screen.getByTestId('dock-subs').textContent).toBe('10 of 10 subscriptions');
  many.unmount();
  const few = render(<ChartDocks focusedSymbol="SPY" maps={{ SPY: { data: 1 } }} subscriptionSymbols={['SPY', 'QQQ', 'HOOD']} />);
  expect(screen.getByTestId('dock-subs').textContent).toBe('3 of 10 subscriptions');
  few.unmount();
  // The sidecar content renders ONLY when the disclosure opens — the dock
  // adds no always-on load and never mounts a hidden duplicate dashboard.
  const sidecarSpy = jest.fn(() => <b>sidecar-content</b>);
  const lazy = render(<ChartDocks focusedSymbol="SPY" maps={{ SPY: { data: 1 } }} renderSidecar={sidecarSpy} />);
  expect(sidecarSpy).not.toHaveBeenCalled();
  // jsdom queues the details toggle event, so settle it inside an async act.
  const { act } = require('@testing-library/react');
  await act(async () => { fireEvent.click(lazy.getByTestId('dock-sidecar').querySelector('summary')); });
  expect(sidecarSpy).toHaveBeenCalledTimes(1);
  expect(lazy.getByText('sidecar-content')).toBeInTheDocument();
  lazy.unmount();
});

test('B14 MOUNTED: the dock follows the focused pane with explicit policy', async () => {
  jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
  const axios = require('axios');
  axios.get.mockImplementation(async url => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] ?? 'SPY';
    return { data: { ticker, query_key: '', frames: [{ time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101 }], candles_with_recorded_nodes: 1, node_status: 'available' } };
  });
  const { act } = require('@testing-library/react');
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    const sidecarSpy = jest.fn(() => <b>market-view</b>);
    render(<ChartWorkspace ticker="SPY" open useNew docksMaps={{ SPY: { data: 1 } }} docksSidecar={sidecarSpy} />);
    // Focused pane symbol drives the dock: ok entry, census of one pane.
    expect(screen.getByTestId('chart-docks')).toHaveAttribute('data-status', 'ok');
    expect(screen.getByTestId('chart-docks')).toHaveAttribute('data-symbol', 'SPY');
    expect(screen.getByTestId('dock-subs').textContent).toBe('1 of 10 subscriptions');
    expect(screen.queryByTestId('dock-badge')).not.toBeInTheDocument();
    // Three panes -> census grows with the capped pane symbols.
    await act(async () => { screen.getByTestId('layout-three').click(); });
    expect(screen.getByTestId('dock-subs').textContent).toBe('3 of 10 subscriptions');
    // The sidecar opens the consumer's component for the focused symbol.
    fireEvent.click(screen.getByTestId('dock-sidecar').querySelector('summary'));
    expect(sidecarSpy).toHaveBeenCalledWith(expect.objectContaining({ status: 'ok' }), 'SPY');
    expect(screen.getByText('market-view')).toBeInTheDocument();
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});
