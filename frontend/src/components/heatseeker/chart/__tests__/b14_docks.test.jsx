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
