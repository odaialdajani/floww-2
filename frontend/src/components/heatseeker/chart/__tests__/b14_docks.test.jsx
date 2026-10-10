import React from 'react';
import { render, screen } from '@testing-library/react';
import ChartDocks, { sidecarFor, MAX_SUBSCRIPTIONS, capSubscriptions } from '../ChartDocks';
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
