import React from 'react';
import { render, screen } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';
test('incumbent fallback preserves PriceNodeHistory path', () => {
  render(<ChartWorkspace ticker="SPY" open useNew={false} />);
  expect(document.querySelector('[data-testid="recorded-price-chart"], [data-testid="price-history"]') || screen.getByText(/SPY/i)).toBeTruthy();
});
test('new workspace keeps retry + notice', () => {
  const fn = jest.fn();
  render(<ChartWorkspace ticker="SPY" open useNew notice="partial bars" onRetry={fn} />);
  expect(screen.getByTestId('chart-workspace')).toBeInTheDocument();
  expect(screen.getByTestId('workspace-notice')).toHaveTextContent('partial bars');
  screen.getByText('Retry').click();
  expect(fn).toHaveBeenCalled();
});
test('atlas toggle flips to overlay without losing incumbent default', async () => {
  const { act } = require('@testing-library/react');
  render(<ChartWorkspace ticker="SPY" open useNew />);
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'false');
  await act(async () => { screen.getByTestId('atlas-toggle').click(); });
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByTestId('atlas-chart')).toBeInTheDocument();
});
