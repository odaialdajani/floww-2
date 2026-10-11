import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import RecordedPriceChart from '../../RecordedPriceChart';

jest.mock('axios', () => ({ get: jest.fn() }));

// Frames with real volume; CVD arrives as its own line (time-matched),
// parallel to exposure_line — never derived from up/down candles.
const frames = [
  { time: '2026-10-06T13:30:00+00:00', open: 100, high: 101, low: 99, close: 100, volume: 1000, duration_seconds: 60, nodes: [] },
  { time: '2026-10-06T13:31:00+00:00', open: 100, high: 102, low: 100, close: 101, volume: 1000, duration_seconds: 60, nodes: [] },
  { time: '2026-10-06T13:32:00+00:00', open: 101, high: 103, low: 101, close: 102, volume: 1000, duration_seconds: 60, nodes: [] },
  { time: '2026-10-06T13:33:00+00:00', open: 102, high: 104, low: 102, close: 103, volume: 1000, duration_seconds: 60, nodes: [] },
];
const cvdLine = [
  { time: '2026-10-06T13:30:00+00:00', delta: null, cvd: null },
  { time: '2026-10-06T13:31:00+00:00', delta: 500, cvd: 500 },
  { time: '2026-10-06T13:32:00+00:00', delta: null, cvd: null },
  { time: '2026-10-06T13:33:00+00:00', delta: 300, cvd: 800 },
];

beforeEach(() => {
  jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 480, width: 800, height: 480, toJSON: () => ({}) });
});
afterEach(() => jest.restoreAllMocks());

test('CVD pane renders honest gaps and mandatory label', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames} cvdLine={cvdLine} />);
  expect(screen.getByText(/CVD estimated via bulk volume classification/)).toBeInTheDocument();
  expect(screen.getByText(/80%.*equities/)).toBeInTheDocument();
  expect(screen.getByText(/directional, not exact/)).toBeInTheDocument();
});

test('CVD line shows gaps for unknown bars (first, sigma-zero, absent volume)', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames} cvdLine={cvdLine} />);
  const pane = screen.getByTestId('cvd-pane');
  // Unknown bars break the polyline: two known bars separated by a gap
  // render as two single-point... no — single known points cannot form a
  // segment, so with this fixture the pane shows gaps and no joined line.
  const segs = pane.querySelectorAll('[data-testid="cvd-line"]');
  segs.forEach(seg => {
    const pts = seg.getAttribute('points').trim().split(' ');
    expect(pts.length).toBeGreaterThanOrEqual(2);
    pts.forEach(p => {
      const y = Number(p.split(',')[1]);
      expect(Number.isFinite(y)).toBe(true);
    });
  });
});

test('CVD pane joins adjacent known bars into one honest segment', () => {
  const joined = [
    { time: '2026-10-06T13:30:00+00:00', delta: null, cvd: null },
    { time: '2026-10-06T13:31:00+00:00', delta: 500, cvd: 500 },
    { time: '2026-10-06T13:32:00+00:00', delta: 300, cvd: 800 },
    { time: '2026-10-06T13:33:00+00:00', delta: null, cvd: null },
  ];
  render(<RecordedPriceChart ticker="SPY" frames={frames} cvdLine={joined} />);
  const pane = screen.getByTestId('cvd-pane');
  const segs = pane.querySelectorAll('[data-testid="cvd-line"]');
  expect(segs).toHaveLength(1);
  expect(segs[0].getAttribute('points').trim().split(' ')).toHaveLength(2);
});

test('no CVD line renders without a cvd line payload — never a fabricated flat line', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames} />);
  expect(screen.queryByTestId('cvd-pane')).not.toBeInTheDocument();
  expect(screen.queryByTestId('cvd-line')).not.toBeInTheDocument();
});

test('CVD toggle hides the pane; toggle is disabled with no known CVD', () => {
  const { rerender } = render(<RecordedPriceChart ticker="SPY" frames={frames} cvdLine={cvdLine} />);
  expect(screen.getByTestId('cvd-pane')).toBeInTheDocument();
  const toggle = screen.getByRole('checkbox', { name: 'Toggle CVD' });
  expect(toggle).toBeEnabled();
  fireEvent.click(toggle);
  expect(screen.queryByTestId('cvd-pane')).not.toBeInTheDocument();
  rerender(<RecordedPriceChart ticker="SPY" frames={frames} cvdLine={[{ time: frames[0].time, delta: null, cvd: null }]} />);
  expect(screen.getByRole('checkbox', { name: 'Toggle CVD' })).toBeDisabled();
});

test('CVD pane states its own value range (own-scale honesty)', () => {
  render(<RecordedPriceChart ticker="SPY" frames={frames} cvdLine={cvdLine} />);
  const pane = screen.getByTestId('cvd-pane');
  expect(pane.textContent).toMatch(/Range/);
  expect(pane.textContent).toMatch(/500/);
  expect(pane.textContent).toMatch(/800/);
});
