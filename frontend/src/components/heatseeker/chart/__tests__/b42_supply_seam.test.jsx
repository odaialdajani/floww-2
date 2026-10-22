/** @jest-environment jsdom */
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';

// OpenCode (R21-03/04 supply seam, written after the fleet's lanes went
// silent under the user's finish instruction): pins the REAL fetch ->
// onEnvelopes pane-report -> render-site binding that c0493033 landed.
// The envelopes in these fixtures are the committed admission shapes —
// statuses/refusals ride through verbatim, never re-derived locally.
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const armPayload = (extra) => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({
    data: {
      ticker: 'SPY',
      frames: [
        { time: '2026-09-10T14:00:00+00:00', open: 100, high: 102, low: 99, close: 101, nodes: [] },
        { time: '2026-09-10T14:01:00+00:00', open: 101, high: 103, low: 100, close: 102, nodes: [] },
      ],
      candles_with_recorded_nodes: 0, scopes: [], ...extra,
    },
  }));
};

const mount = async (props = {}) => {
  render(<ChartWorkspace ticker="SPY" open useNew {...props} />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  await act(async () => { await new Promise(r => setTimeout(r, 200)); });
};

test('payload envelopes bind the committed consumers over the local algebra', async () => {
  armPayload({
    envelopes: {
      initial_balance: { status: 'not_requested', reason: 'no live-session bars for the receipt\'s own day; the supplier does not fabricate availability for older days' },
      naked: { status: 'not_requested', reason: 'no naked-level candidates at this supplier; claims render only when explicit candidates and coverage exist' },
      flow: { status: 'refused', reason: 'capability-not-declared: classified_sizes' },
    },
  });
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    await mount();
    // The supplier's honest statuses render verbatim — the midday-truncated
    // read never becomes a fabricated opening balance, and the desktop's
    // missing classified-size capability names its refusal instead of a
    // total invented from nothing.
    expect(screen.getByTestId('profile-ib').textContent).toContain('Initial balance not_requested — no live-session bars');
    expect(screen.getByTestId('profiles-panel').getAttribute('data-ib-status')).toBe('not_requested');
    expect(screen.getByTestId('flow-pane-refused')).toBeInTheDocument();
    expect(screen.getByTestId('flow-pane-refused').getAttribute('data-reason')).toBe('capability-not-declared: classified_sizes');
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});

test('an explicit caller envelope still wins over the recorded one', async () => {
  armPayload({
    envelopes: {
      initial_balance: { status: 'not_requested', reason: 'recorded says not requested' },
    },
  });
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    await mount({
      ibEnvelope: {
        status: 'available', bounds: { low: 99, high: 103 },
        coverage: { covered: 2, expected_total: 2, complete: true },
        approximation: 'bar-resolution',
        certification: { basis: 'explicit-caller-envelope', certified_by_hash: false },
      },
    });
    const text = screen.getByTestId('profile-ib').textContent;
    expect(text).toContain('Initial balance 99–103');
    expect(text).toContain('2 of 2 opening bars');
    expect(text).toContain('explicit-caller-envelope');
    expect(text).not.toContain('not_requested');
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});

test('a payload without envelopes keeps the legacy local path byte-stable', async () => {
  armPayload({});
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    await mount();
    expect(screen.getByTestId('profiles-panel').getAttribute('data-ib-status')).toBe('ok');
    // Local bar-resolution approximation label, exactly as committed.
    expect(screen.getByTestId('profile-ib').textContent).toContain('99–103 over 2 bars · bar-resolution');
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});
