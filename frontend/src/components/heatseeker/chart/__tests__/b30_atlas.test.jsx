import React from 'react';
import { render, screen } from '@testing-library/react';
import AtlasChart, { atlasSummary } from '../AtlasChart';
const frames = [
  { time: '2026-10-06T13:30:00+00:00', open: 100, high: 101, low: 99, close: 100.5 },
  { time: '2026-10-06T13:31:00+00:00', open: 100.5, high: 102, low: 100, close: 101.5 },
];
test('disabled flag preserves incumbent path', () => {
  render(<AtlasChart ticker="SPY" frames={frames} enabled={false} />);
  expect(document.querySelector('[data-testid="recorded-price-chart"]')).toBeInTheDocument();
  expect(screen.queryByTestId('atlas-chart')).not.toBeInTheDocument();
});
test('enabled overlay shows king + vwap + flow + attribution', () => {
  const nodes = [{ strike: 100, signed_value: -100, status: 'ok' }, { strike: 105, signed_value: 50, status: 'ok' }];
  const bars = [{ high: 10, low: 8, close: 9, volume: 100 }, { high: 10, low: 9, close: 9.5, volume: 100 }];
  const summary = atlasSummary({ nodes, bars, flow: { call_premium: 5, put_premium: -2 }, darkLevels: [{ price: 1 }] });
  expect(summary.king.strike).toBe(100);
  expect(summary.vwap).toBeCloseTo(9.25, 1);
  render(<AtlasChart ticker="SPY" frames={frames} nodes={nodes} bars={bars} flow={{ call_premium: 5, put_premium: -2 }} darkLevels={[{ price: 1 }]} enabled />);
  expect(screen.getByTestId('atlas-chart')).toBeInTheDocument();
  expect(screen.getByTestId('atlas-orbs')).toHaveTextContent('King 100');
  expect(screen.getByTestId('atlas-vwap')).toHaveTextContent('VWAP');
  expect(screen.getByTestId('atlas-flow')).toHaveTextContent('puts -2');
  expect(screen.getByTestId('atlas-attribution')).toHaveTextContent('TradingView');
});
