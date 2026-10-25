// B10 FUTURE WHITESPACE + TYPED SCENARIO ZONES (b10_projection_contract v2 —
// H3 PASS). C044: the future axis extends in EXACT interval multiples; the
// whitespace is EMPTY CANVAS (no probabilities, no pseudo-candles, no
// forecast values); the zone comes from sessionZones at its own known-at and
// NEVER extends high/low into the future; the source age is ALWAYS visible.
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import { projectWhitespace } from '../scenarioProjection';
import { sessionZones } from '../indicators/ProfilePrimitives';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const arm = () => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: [
    { time: '2026-10-06T13:30:00Z', open: 100, high: 102, low: 99, close: 101, volume: 10, nodes: [] },
    { time: '2026-10-06T14:00:00Z', open: 101, high: 104, low: 100, close: 103, volume: 20, nodes: [] },
    { time: '2026-10-06T14:30:00Z', open: 103, high: 105, low: 101, close: 104, volume: 30, nodes: [] },
  ], candles_with_recorded_nodes: 3, scopes: [] } }));
};
const GRID = [1, 5, 15, 30, 60];
// 2026-10-06 is a Tuesday; 13:30Z = 9:30 ET (session open).
const lastKnownMs = Date.parse('2026-10-06T14:30:00Z');
const cursorAtLast = lastKnownMs;

test('contract vector: empty frames -> zone-source-unavailable propagates verbatim', () => {
  const out = projectWhitespace([], { intervalMinutes: 30, horizonMinutes: 120, supportedGrid: GRID, cursorMs: cursorAtLast });
  expect(out.status).toBe('refused');
  expect(out.reason).toBe('zone-source-unavailable');
  expect(out.segments).toEqual([]);
  expect(out.sourceAgeSeconds).toBe(null);
  expect(out.zone && out.zone.reason).toBe('no eligible bars known at the cursor');
});

test('contract vector: segments align to interval multiples from lastKnownTime; none past the horizon', () => {
  const out = projectWhitespace([
    { time: '2026-10-06T13:30:00Z', open: 100, high: 102, low: 99, close: 101 },
    { time: '2026-10-06T14:00:00Z', open: 101, high: 104, low: 100, close: 103 },
    { time: '2026-10-06T14:30:00Z', open: 103, high: 105, low: 101, close: 104 },
  ], { intervalMinutes: 30, horizonMinutes: 120, supportedGrid: GRID, cursorMs: cursorAtLast });
  expect(out.status).toBe('ok');
  expect(out.segments).toHaveLength(3);
  out.segments.forEach((seg, i) => {
    expect(seg.startMs).toBe(lastKnownMs + (i + 1) * 30 * 60000);
    expect(seg.endMs).toBe(lastKnownMs + (i + 2) * 30 * 60000);
  });
  expect(out.segments[2].endMs).toBe(lastKnownMs + 120 * 60000);
  expect(out.segments.every(s => s.kind === 'future-whitespace')).toBe(true);
});

test('contract vector: sourceAgeSeconds = cursor - lastKnownTime on every ok response', () => {
  const frames = [{ time: '2026-10-06T14:00:00Z', high: 104, low: 100, open: 101, close: 103 }, { time: '2026-10-06T14:30:00Z', high: 105, low: 101, open: 103, close: 104 }];
  const out = projectWhitespace(frames, { intervalMinutes: 15, horizonMinutes: 60, supportedGrid: GRID, cursorMs: lastKnownMs + 45000 });
  expect(out.status).toBe('ok');
  expect(out.sourceAgeSeconds).toBe(45);
  const zeroAge = projectWhitespace(frames, { intervalMinutes: 15, horizonMinutes: 60, supportedGrid: GRID, cursorMs: lastKnownMs });
  expect(zeroAge.sourceAgeSeconds).toBe(0);
});

test('contract vector: unsorted bars -> zone unchanged through the projection (b23 order-independence)', () => {
  const bars = [
    { time: '2026-10-06T14:30:00Z', open: 103, high: 105, low: 101, close: 104 },
    { time: '2026-10-06T13:30:00Z', open: 100, high: 102, low: 99, close: 101 },
    { time: '2026-10-06T14:00:00Z', open: 101, high: 104, low: 100, close: 103 },
  ];
  const out = projectWhitespace(bars, { intervalMinutes: 30, horizonMinutes: 120, supportedGrid: GRID, cursorMs: cursorAtLast });
  expect(out.status).toBe('ok');
  expect(out.zone.high).toBe(105);
  expect(out.zone.low).toBe(99);
  expect(out.zone.bars).toBe(3);
  expect(out.zone.firstKnownTime).toBe(Date.parse('2026-10-06T13:30:00Z'));
  expect(out.zone.lastKnownTime).toBe(lastKnownMs);
});

test('contract vector: open/close absent -> zone open/close null, never zero', () => {
  const out = projectWhitespace([{ time: '2026-10-06T14:30:00Z', high: 105, low: 101 }], { intervalMinutes: 30, horizonMinutes: 60, supportedGrid: GRID, cursorMs: cursorAtLast });
  expect(out.status).toBe('ok');
  expect(out.zone.open).toBe(null);
  expect(out.zone.close).toBe(null);
});

test('typed refusals: no-eligible-interval and cursor-ineligible', () => {
  const frames = [{ time: '2026-10-06T14:30:00Z', open: 103, high: 105, low: 101, close: 104 }];
  const badInterval = projectWhitespace(frames, { intervalMinutes: 7, horizonMinutes: 60, supportedGrid: GRID, cursorMs: cursorAtLast });
  expect(badInterval.status).toBe('refused');
  expect(badInterval.reason).toBe('no-eligible-interval');
  // 2026-10-03 is a Saturday — bars known BEFORE it (Friday Oct 2) so the zone
  // resolves, and the cursor is outside every regular session -> cursor-ineligible
  const weekend = projectWhitespace([{ time: '2026-10-02T15:00:00Z', open: 103, high: 105, low: 101, close: 104 }], { intervalMinutes: 30, horizonMinutes: 60, supportedGrid: GRID, cursorMs: Date.parse('2026-10-03T15:00:00Z') });
  expect(weekend.status).toBe('refused');
  expect(weekend.reason).toBe('cursor-ineligible');
});

test('MOUNTED: the future-whitespace strip renders the typed zone label, source age and empty slots', async () => {
  arm();
  window.localStorage.clear();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '3'));
  const strip = screen.getByTestId('future-whitespace-strip');
  expect(strip).toBeInTheDocument();
  expect(screen.getAllByTestId('future-whitespace-slot').length).toBeGreaterThan(0);
  expect(screen.getByTestId('scenario-zone-label')).toHaveTextContent(/Session zone 105\/99/);
  expect(screen.getByTestId('scenario-source-age')).toHaveTextContent(/age \d+s/);
  // the zone note rides the strip verbatim
  expect(strip.textContent).toContain('only bars knowable at the cursor');
  // an interval off the pane's grid is refused visibly — the strip disappears
  const select = screen.getByLabelText('Candle interval');
  // 1 min IS on the grid: still ok (just fewer minutes of horizon)
  fireEvent.change(select, { target: { value: '1' } });
  await waitFor(() => expect(screen.getByTestId('future-whitespace-strip')).toBeInTheDocument());
});
