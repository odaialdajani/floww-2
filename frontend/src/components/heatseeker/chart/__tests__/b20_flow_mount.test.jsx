import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';
import { bucketHash } from '../indicators/FlowPane';

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

// Real-shaped bucket trades: classified feed tags only, multi-leg groups.
// g1 is a same-side call group: two legs net into ONE economic unit (+40).
const TRADES = [
  { side: 'call', premium: 100 },
  { side: 'put', premium: 40 },
  { side: 'call', premium: 25, group_id: 'g1' },
  { side: 'call', premium: 15, group_id: 'g1' },
];

test('B20 MOUNTED: flow pane renders the focused bucket at the replay cursor', async () => {
  armPayload(FRAMES);
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    render(<ChartWorkspace ticker="SPY" open useNew flowTrades={TRADES} />);
    await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    // The pane sits beside the replay readout, bucketed at the head cursor.
    expect(screen.getByTestId('flow-pane')).toBeInTheDocument();
    // Economic grouping: the two-leg same-side group nets into ONE call
    // unit (+25 +15 = +40) beside the +100 single -> 140. (A mixed-direction
    // ticket would stay explicitly unknown — the pinned unit tests cover it.)
    expect(screen.getByTestId('flow-call-premium').textContent).toContain('140');
    expect(screen.getByTestId('flow-put-premium').textContent).toContain('-40');
    // Drilldown and totals share the SAME bar/window/filter identity, so the
    // drilldown can only ever equal the totals for this bucket.
    expect(screen.getByTestId('flow-drilldown-call').textContent).toBe(screen.getByTestId('flow-call-premium').textContent);
    expect(screen.getByTestId('flow-drilldown-put').textContent).toBe(screen.getByTestId('flow-put-premium').textContent);
    expect(screen.queryByTestId('flow-drilldown-scope-note')).not.toBeInTheDocument();
    // Scrub the cursor: the bucket identity follows the replay cursor's bar.
    const slider = screen.getByLabelText('Replay position');
    await act(async () => { fireEvent.change(slider, { target: { value: '0' } }); });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(screen.getByTestId('replay-readout').getAttribute('data-cursor')).toBe(String(Date.parse('2026-09-10T14:00:00+00:00')));
    // onBucketClick hands the drilldown opener the exact bucket hash.
    const opened = [];
    render(<span />); // no-op keep structure stable
    const workspace2 = render(<ChartWorkspace ticker="SPY" open useNew flowTrades={TRADES}
      onFlowBucket={({ hash }) => opened.push(hash)} />);
    await waitFor(() => expect(screen.getAllByTestId('flow-open-drilldown').length).toBeGreaterThan(0));
    await act(async () => { screen.getAllByTestId('flow-open-drilldown')[0].click(); });
    expect(opened).toHaveLength(1);
    expect(opened[0]).toBe(bucketHash(Date.parse('2026-09-10T14:01:00+00:00'), '1m', {}));
    workspace2.unmount();
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});

test('B20 MOUNTED: no published trades renders an explicit unknown bucket', async () => {
  armPayload(FRAMES);
  window.__FLOWW_CHART_WORKSPACE__ = true;
  try {
    render(<ChartWorkspace ticker="SPY" open useNew />);
    await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    // The live payload publishes aggregates, not per-bucket trades — the
    // pane says so explicitly instead of inventing trades from aggregates.
    expect(screen.getByTestId('flow-pane-unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('flow-pane')).not.toBeInTheDocument();
  } finally { window.__FLOWW_CHART_WORKSPACE__ = false; }
});
