import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';

// Bare factory + per-test re-arm (durable pattern for this CRA setup).
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const armPayload = (frames) => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames, candles_with_recorded_nodes: 0, scopes: [] } }));
};

const FRAMES = [
  { time: '2026-09-10T14:00:00+00:00', open: 100, high: 102, low: 99, close: 101, nodes: [] },
  { time: '2026-09-10T14:01:00+00:00', open: 101, high: 103, low: 100, close: 102, nodes: [] },
];

test('B23 MOUNTED: profiles panel reads real bars honestly at the replay cursor', async () => {
  armPayload(FRAMES);
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    render(<ChartWorkspace ticker="SPY" open useNew />);
    await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    const panel = screen.getByTestId('profiles-panel');
    // Initial balance comes from the REAL visible bars — a labeled
    // bar-resolution approximation over the opening periods.
    expect(panel.getAttribute('data-ib-status')).toBe('ok');
    expect(screen.getByTestId('profile-ib').textContent).toContain('99');
    expect(screen.getByTestId('profile-ib').textContent).toContain('103');
    expect(screen.getByTestId('profile-ib').textContent).toContain('bar-resolution');
    // No classified trades published -> POC/value-area honestly unavailable.
    expect(panel.getAttribute('data-va-status')).toBe('unavailable');
    expect(screen.getByTestId('profile-va').textContent).toContain('no classified trade prices');
    // CVD without classified buy/sell sizes: the explicit refusal, never a
    // candle-direction proxy.
    expect(panel.getAttribute('data-cvd-status')).toBe('unavailable');
    expect(screen.getByTestId('profile-cvd').textContent).toContain('candle direction is not classified trade flow');
    // No dark-pool prints published -> no levels; aggregates never shown.
    expect(panel.getAttribute('data-dark-count')).toBe('0');
    expect(screen.getByTestId('profile-dark').textContent).toContain('no dark-pool prints published');
    // Scrub: the opening-period read follows the cursor (1 bar visible).
    const slider = screen.getByLabelText('Replay position');
    await act(async () => { fireEvent.change(slider, { target: { value: '0' } }); });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(screen.getByTestId('profiles-panel').getAttribute('data-ib-periods')).toBe('1');
    expect(screen.getByTestId('profile-ib').textContent).toContain('99');
    expect(screen.getByTestId('profile-ib').textContent).toContain('102');
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});

test('B23 MOUNTED: published trades/prints/classified bars light the exact paths', async () => {
  armPayload(FRAMES);
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    render(<ChartWorkspace ticker="SPY" open useNew
      profileTrades={[
        { price: 100.1, size: 10 },
        { price: 100.2, size: 30 },
        { price: 100.9, size: 5 },
      ]}
      darkPoolPrints={[
        { print_id: 'p1', price: 99.5, size: 40000, event_time: 1, venue: 'DARK', notional: 3980000 },
        { print_id: 'p2', price: 101.0, size: 10000, event_time: 2, venue: 'DARK', aggregate: true },
      ]}
      classifiedBars={[
        { time: '14:00', buy: 30, sell: 10 },
        { time: '14:01', buy: 5, sell: 25, session_reset: true },
      ]} />);
    await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    // Exact tick bins -> POC + 70% value area over REAL trade prices.
    expect(screen.getByTestId('profiles-panel').getAttribute('data-va-status')).toBe('ok');
    expect(screen.getByTestId('profile-va').textContent).toContain('70%');
    expect(screen.getByTestId('profile-poc').textContent).toContain('100');
    // Dark pool: only the EXACT print counts — the aggregate is refused.
    expect(screen.getByTestId('profiles-panel').getAttribute('data-dark-count')).toBe('1');
    expect(screen.getByTestId('profile-dark').textContent).toContain('direction unknown');
    expect(screen.getByTestId('profile-dark').textContent).toContain('venue DARK');
    // Classified sizes -> session CVD rows with session re-zeroing.
    expect(screen.getByTestId('profiles-panel').getAttribute('data-cvd-status')).toBe('ok');
    expect(screen.getByTestId('profile-cvd').textContent).toContain('+20');
    expect(screen.getByTestId('profile-cvd').textContent).toContain('-20');
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});

// R21-04 caller binding: when the server admission envelopes are provided,
// the profiles panel shows the SERVER-admitted truth — refusal codes,
// unavailable reasons, coverage honesty — instead of the local algebra.
test('R21-04 MOUNTED: ib/naked admission envelopes bind over the local algebra', async () => {
  armPayload(FRAMES);
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    render(<ChartWorkspace
      ticker="SPY" open useNew
      ibEnvelope={{
        status: 'refused', reason: 'opening-history-truncated',
      }}
      nakedEnvelope={{
        status: 'unavailable', reason: 'unknown-range-cannot-certify-untouched',
      }} />);
    await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    const panel = screen.getByTestId('profiles-panel');
    expect(panel.getAttribute('data-ib-status')).toBe('refused');
    expect(screen.getByTestId('profile-ib').textContent).toContain('opening-history-truncated');
    expect(screen.getByTestId('profile-naked').textContent).toContain('unknown-range-cannot-certify-untouched');
  } finally { delete window.__FLOWW_CHART_WORKSPACE__; }
});

test('R21-04 MOUNTED: available ib envelope shows server bounds and coverage', async () => {
  armPayload(FRAMES);
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    render(<ChartWorkspace
      ticker="SPY" open useNew
      ibEnvelope={{
        status: 'available',
        bounds: { low: 98, high: 103 },
        coverage: { covered: 4, expected_total: 4, complete: true, opening_minutes: 60 },
        approximation: 'bar-resolution',
        certification: { basis: 'recorded opening-window coverage knowable at the cursor', certified_by_hash: false },
      }} />);
    await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    const panel = screen.getByTestId('profiles-panel');
    expect(panel.getAttribute('data-ib-status')).toBe('available');
    expect(screen.getByTestId('profile-ib').textContent).toContain('98');
    expect(screen.getByTestId('profile-ib').textContent).toContain('103');
    expect(screen.getByTestId('profile-ib').textContent).toContain('4 of 4');
    expect(screen.getByTestId('profile-ib').textContent).toContain('recorded opening-window');
  } finally { delete window.__FLOWW_CHART_WORKSPACE__; }
});
