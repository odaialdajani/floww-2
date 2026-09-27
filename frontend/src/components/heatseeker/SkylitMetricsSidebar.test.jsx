/** @jest-environment jsdom */
import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import SkylitMetricsSidebar from './SkylitMetricsSidebar';

const BASE = {
  ticker: 'SPY',
  exposure_basis: 'OI',
  strikes: [{ strike: 500, gex: 1000000 }],
  nodes: { king: { strike: 500, gex: 1000000 }, floors: [], ceilings: [] },
  metrics: {
    grids: {
      delta: {
        grid: { '2030-01-15': { 500: 250000 } },
        exposure_basis: 'OI_DELTA_WEIGHTED',
      },
    },
  },
};

test('R6-1: sidebar follows the active metric', () => {
  const { unmount } = render(<SkylitMetricsSidebar data={BASE} spot={500} metric="raw" />);
  expect(screen.getByText('Key Levels · GEX · OI')).toBeInTheDocument();
  unmount();
  render(<SkylitMetricsSidebar data={BASE} spot={500} metric="delta" />);
  expect(screen.getByText('Key Levels · GEX · delta · OI_DELTA_WEIGHTED')).toBeInTheDocument();
  // Net 250K renders signed; raw 1M must not leak into the delta summary.
  expect(screen.getByText('+250.0K')).toBeInTheDocument();
});

test('R6-1: missing metric surface renders unavailable, never raw totals', () => {
  render(<SkylitMetricsSidebar data={{ ...BASE, metrics: { grids: {} } }} spot={500} metric="delta" />);
  expect(screen.getByTestId('skylit-sidebar-unavailable')).toBeInTheDocument();
  expect(screen.queryByText('+1.0M')).toBeNull();
});

test('R8: vex view labels structural anchors honestly, never VEX values', () => {
  const data = {
    exposure_basis: 'OI',
    net_gex_total: 1000,
    strikes: [{ strike: 500, gex: 1000 }],
    nodes: { total_gex: 1000, king: { strike: 500 }, floors: [], ceilings: [] },
    grid: { expiries: ['2030-01-15'], strikes: [500], grid: {},
      vex_grid: { '2030-01-15': { 500: 25 } } },
  };
  render(<SkylitMetricsSidebar data={data} spot={500} viewMode="vex" metric="raw" />);
  expect(screen.getByText('Key Levels · GEX structural · OI')).toBeInTheDocument();
});

test("missing readings do not claim a neutral gamma regime", () => {
  const view = render(<SkylitMetricsSidebar />);
  expect(screen.getByText("Gamma reading unavailable")).toBeInTheDocument();
  expect(screen.queryByText("Neutral γ")).not.toBeInTheDocument();
  view.rerender(<SkylitMetricsSidebar regime="neutral" />);
  expect(screen.getByText("Neutral γ")).toBeInTheDocument();
});
