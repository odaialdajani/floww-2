import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import RecordedPriceChart from '../../RecordedPriceChart';
import { checkedCandles } from '../../recordedPriceChartData';

jest.mock('axios', () => ({ get: jest.fn() }));

// Volume-carrying frames — the shape price-history must serve once the
// backend passes provider `v` through build_history.
const volFrames = [
  { time: '2026-10-06T13:30:00+00:00', open: 100, high: 102, low: 99, close: 101, volume: 12000, duration_seconds: 60, nodes: [] },
  { time: '2026-10-06T13:31:00+00:00', open: 101, high: 103, low: 100, close: 102, volume: 34000, duration_seconds: 60, nodes: [] },
];

beforeEach(() => {
  jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 480, width: 800, height: 480, toJSON: () => ({}) });
});
afterEach(() => jest.restoreAllMocks());

test('a per-candle volume pane renders when frames carry volume', () => {
  render(<RecordedPriceChart ticker="SPY" frames={volFrames} />);
  const pane = screen.getByTestId('volume-pane');
  const bars = pane.querySelectorAll('[data-testid="volume-bar"]');
  expect(bars).toHaveLength(2);
  // Bar heights must be proportional to real volume, not flat/fabricated.
  const h0 = Number(bars[0].getAttribute('height'));
  const h1 = Number(bars[1].getAttribute('height'));
  expect(h1).toBeGreaterThan(h0);
  expect(h0).toBeGreaterThan(0);
});

test('frames without volume render no volume pane and say so', () => {
  const bare = volFrames.map(({ volume, ...rest }) => rest);
  render(<RecordedPriceChart ticker="SPY" frames={bare} />);
  expect(screen.queryByTestId('volume-pane')).not.toBeInTheDocument();
  expect(screen.getByText(/volume unavailable/i)).toBeInTheDocument();
});

test('an orb whose strike is outside the visible price range is not drawn at a fake edge price', () => {
  // Candle prices ~100; orb strike 4000 is inside the auto range (levels feed
  // priceRange), so first zoom the price scale in — then the orb is out of
  // range and must NOT be clamped to the plot edge (a fake price).
  const frames = [
    { ...volFrames[0], nodes: [{ id: 'far', metric: 'gex', level: 4000, signed_value: -900, known_at: '2026-10-06T13:30:00+00:00', age_seconds: 1 }] },
    volFrames[1],
  ];
  const { container } = render(<RecordedPriceChart ticker="SPY" frames={frames} />);
  const region = screen.getByRole('region', { name: 'SPY candle chart' });
  fireEvent.wheel(region, { deltaY: -120, shiftKey: true, clientX: 400, clientY: 240 });
  const orbs = screen.queryAllByTestId('chart-orb');
  const clamped = orbs.filter(o => {
    const cy = Number(o.getAttribute('cy'));
    return cy === 16 || cy === 442; // top/bottom plot edge
  });
  expect(clamped).toHaveLength(0);
  // The dropped orb leaves an explicit out-of-range marker, not silence.
  expect(screen.getAllByTestId('orb-out-of-range').length).toBeGreaterThanOrEqual(1);
});

test('an exposure-vwAP point outside the price range never joins the visible segment', () => {
  const frames = [
    { ...volFrames[0], nodes: [] },
    { ...volFrames[1], nodes: [] },
    { time: '2026-10-06T13:32:00+00:00', open: 102, high: 104, low: 101, close: 103, volume: 8000, duration_seconds: 60, nodes: [] },
  ];
  // In-range, absurd, in-range: the absurd middle point must be dropped —
  // clamping it to the edge would draw a fake price into the polyline and
  // split the segment into two false "gaps".
  render(<RecordedPriceChart ticker="SPY" frames={frames}
    exposureLine={[
      { time: frames[0].time, centre: 100.5 },
      { time: frames[1].time, centre: 99999 },
      { time: frames[2].time, centre: 101.5 },
    ]} />);
  const segs = screen.queryAllByTestId('exposure-vwap-line');
  // Exactly ONE continuous segment joining point 0 to point 2.
  expect(segs).toHaveLength(1);
  segs.forEach(seg => {
    const pts = seg.getAttribute('points').split(' ');
    expect(pts).toHaveLength(2);
    pts.forEach(p => {
      const y = Number(p.split(',')[1]);
      expect(y).toBeGreaterThan(16);
      expect(y).toBeLessThan(442);
    });
  });
});

test('checkedCandles preserves volume through validation', () => {
  const out = checkedCandles(volFrames);
  expect(out).toHaveLength(2);
  expect(out[0].volume).toBe(12000);
  expect(out[1].volume).toBe(34000);
});
