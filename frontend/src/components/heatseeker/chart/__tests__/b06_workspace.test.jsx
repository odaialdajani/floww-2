import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { openStockPanel } from '../../../../testUtils/openStockPanel';

// Hermetic data: the real lifecycle reads a controlled payload. The factory
// stays bare and each test re-arms the implementation — the pattern the
// dashboard suite uses, immune to inter-test mock resets.
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
import axios from 'axios';

const armedPayload = () => ({ data: { ticker: 'SPY', query_key: '', frames: [{ time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101 }], candles_with_recorded_nodes: 1, node_status: 'available' } });
beforeEach(() => { axios.get.mockImplementation(() => Promise.resolve(armedPayload())); });

const workspace = () => require('../ChartWorkspace').default;

// The incumbent's real controls prove passthrough behaviorally — a stronger
// contract than a prop spy: if the workspace dropped toolbarActions, scope,
// contract or history props, these controls would disappear.
const expectIncumbentControls = () => {
  expect(screen.getByTestId('price-node-history')).toBeInTheDocument();
  openStockPanel('data');
  expect(screen.getByRole('button', { name: 'Reload history' })).toBeInTheDocument();
  expect(screen.getByLabelText('Option contract')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Chart tools', exact: true })).toBeInTheDocument();
};

test('incumbent fallback preserves the exact PriceNodeHistory path', () => {
  const W = workspace();
  const off = render(<W ticker="SPY" open useNew={false} />);
  expect(document.querySelector('[data-testid="chart-workspace"]')).toBeNull(); // no workspace chrome
  expectIncumbentControls();
  off.unmount();
});

test('new workspace keeps retry + notice', () => {
  const W = workspace();
  const fn = jest.fn();
  render(<W ticker="SPY" open useNew notice="partial bars" onRetry={fn} />);
  expect(screen.getByTestId('chart-workspace')).toBeInTheDocument();
  expect(screen.getByTestId('workspace-notice')).toHaveTextContent('partial bars');
  screen.getByText('Retry').click();
  expect(fn).toHaveBeenCalled();
});

test('atlas toggle composes the overlay beside the incumbent — never replaces it', async () => {
  const W = workspace();
  render(<W ticker="SPY" open useNew />);
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'false');
  await act(async () => { screen.getByTestId('atlas-toggle').click(); });
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByTestId('atlas-chart')).toBeInTheDocument();
  // Composed, never swapped: the incumbent stays mounted beside the overlay.
  expect(screen.getByTestId('price-node-history')).toBeInTheDocument();
});

test('B06: flag is a controlled open — off by default, on only when explicitly set', () => {
  const { isChartWorkspaceEnabled } = require('../ChartWorkspace');
  expect(isChartWorkspaceEnabled()).toBe(false);
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try { expect(isChartWorkspaceEnabled()).toBe(true); }
  finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
  expect(isChartWorkspaceEnabled()).toBe(false);
});

test('B06: the workspace branch keeps every incumbent control — nothing is lost', () => {
  const W = workspace();
  const on = render(<W ticker="SPY" open useNew notice="partial bars" onRetry={jest.fn()} />);
  expect(screen.getByTestId('chart-pane')).toBeInTheDocument();
  expectIncumbentControls();
  on.unmount();
});

test('B06: the pane surfaces the data-quality contract — source time, coverage, capability, retry', async () => {
  const W = workspace();
  render(<W ticker="SPY" open useNew />);
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 60)); });
  const strip = document.querySelector('[data-testid="workspace-quality"]');
  expect(strip).not.toBeNull();
  expect(strip.getAttribute('data-status')).toBe('ready');
  expect(strip.textContent).toContain('2026-10-06T14:00:00Z');
  expect(strip.textContent).toContain('1 of 1 candles carry saved nodes');
  expect(strip.textContent).toContain('Saved node history available');
  expect(strip.textContent).toContain('manual retry available');
});
