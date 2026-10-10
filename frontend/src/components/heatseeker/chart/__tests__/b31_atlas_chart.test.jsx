import React from 'react';
import { render, screen } from '@testing-library/react';
import RecordedPriceChart from '../../RecordedPriceChart';
const frames = [
  { time: '2026-10-06T13:30:00+00:00', open: 100, high: 102, low: 99, close: 101, duration_seconds: 60, nodes_known_at: '2026-10-06T13:30:00+00:00', node_age_seconds: 5, nodes: [{ id: 'a', metric: 'gex', level: 100, signed_value: -100, known_at: '2026-10-06T13:30:00+00:00', age_seconds: 1 }, { id: 'b', metric: 'gex', level: 101, signed_value: 50, known_at: '2026-10-06T13:30:00+00:00', age_seconds: 1 }] },
  { time: '2026-10-06T13:31:00+00:00', open: 101, high: 103, low: 100, close: 102, duration_seconds: 60, nodes: [] },
];
beforeEach(() => { jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 480, width: 800, height: 480, toJSON: () => ({}) }); });
afterEach(() => jest.restoreAllMocks());
test('Atlas orbs render per-bar with king marked, candles untouched', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames} />);
  expect(screen.getAllByTestId('price-candle')).toHaveLength(2);
  const orbs = screen.getAllByTestId('chart-orb');
  expect(orbs.length).toBeGreaterThanOrEqual(2);
  expect(orbs.map((o) => o.textContent).join(' ')).toContain('King Node');
});
test('Atlas overlay off hides orbs only', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames} showAtlas={false} />);
  expect(screen.getAllByTestId('price-candle')).toHaveLength(2);
  expect(screen.queryByTestId('chart-orb')).not.toBeInTheDocument();
});
test('exposure line gaps on missing minutes, dark levels and flow render', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames}
    exposureLine={[{ time: frames[0].time, centre: 100.5 }, { time: frames[1].time, centre: null }]}
    darkLevels={[{ price: 101, venue: 'D' }, { price: 99999 }]}
    flowBars={[{ call: 100, put: 40 }, { call: 10, put: 90 }]} />);
  expect(screen.queryAllByTestId('exposure-vwap-line')).toHaveLength(0);
  expect(screen.getAllByTestId('dark-pool-level')).toHaveLength(1);
  expect(screen.getByTestId('flow-pane')).toBeInTheDocument();
});
test('full exposure line draws one segment', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames}
    exposureLine={[{ time: frames[0].time, centre: 100.5 }, { time: frames[1].time, centre: 101.5 }]} />);
  expect(screen.getAllByTestId('exposure-vwap-line')).toHaveLength(1);
});
