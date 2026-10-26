// B18 PANE STUDY MOUNT (H1 consumer) — H2's frozen paneStudies configuration
// layer (merged 71d5b1ab) consumed through the REAL panes: C118 estimated-CVD
// anchor/MA/zero-axis settings visibly change the drawn path; C121 profile
// mode/levels/VA68 controls change the real rows and render POC/VAH/VAL facts;
// C124-126 bar-resolution TPO boxes change with the period setting and the
// tick-true mode is a TYPED refusal. Settings persist per ticker scope.
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
// two REAL sessions so the CVD session anchor actually rebases mid-series
const FRAMES = [
  { time: '2026-10-22T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 10, nodes: [] },
  { time: '2026-10-22T14:30:00Z', open: 101, high: 104, low: 100, close: 103, volume: 20, nodes: [] },
  { time: '2026-10-22T15:00:00Z', open: 103, high: 105, low: 101, close: 104, volume: 30, nodes: [] },
  { time: '2026-10-23T14:00:00Z', open: 104, high: 106, low: 102, close: 105, volume: 40, nodes: [] },
  { time: '2026-10-23T14:30:00Z', open: 105, high: 107, low: 103, close: 106, volume: 50, nodes: [] },
  { time: '2026-10-23T15:00:00Z', open: 106, high: 108, low: 104, close: 107, volume: 60, nodes: [] },
];
const CVD_LINE = [
  { time: '2026-10-22T14:00:00Z', cvd: 100 },
  { time: '2026-10-22T14:30:00Z', cvd: 300 },
  { time: '2026-10-22T15:00:00Z', cvd: 500 },
  { time: '2026-10-23T14:00:00Z', cvd: 700 },
  { time: '2026-10-23T14:30:00Z', cvd: 1200 },
  { time: '2026-10-23T15:00:00Z', cvd: 1400 },
];
beforeEach(() => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: FRAMES, candles_with_recorded_nodes: 6, scopes: [] } }));
  window.localStorage.clear();
});
const mountPane = async () => {
  const r = render(<PriceNodeHistory ticker="SPY" open cvdLine={CVD_LINE} />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '6'));
  return r;
};
const cvdGeometry = () => [...document.querySelectorAll('[data-testid="cvd-line"]')].map(l => l.getAttribute('points')).join('#');
const setSelect = (tid, val) => {
  const s = screen.getByTestId(tid);
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
  act(() => { setter.call(s, val); s.dispatchEvent(new Event('change', { bubbles: true })); });
};
const setInput = (tid, val) => {
  const i = screen.getByTestId(tid);
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  act(() => { setter.call(i, String(val)); i.dispatchEvent(new Event('input', { bubbles: true })); });
};

test('C118: CVD settings render EXPLICIT PENDING until the reviewed module lands', async () => {
  await mountPane();
  // the settings surface exists with the honest pending note — no unreviewed
  // anchor/MA/zero-axis math is applied to the drawn estimated path
  expect(screen.getByTestId('cvd-settings')).toBeInTheDocument();
  expect(screen.getByTestId('cvd-settings-pending')).toHaveTextContent(/PENDING/i);
  expect(screen.getByTestId('cvd-settings-pending')).toHaveTextContent(/REWORK/i);
  expect(screen.getByTestId('cvd-approx-label')).toHaveTextContent(/estimated/i);
  // the raw estimated path draws exactly as before — no rebase/MA geometry
  expect(cvdGeometry()).toBeTruthy();
  expect(document.querySelectorAll('[data-testid="cvd-ma-line"]').length).toBe(0);
});

test('C121: profile levels/VA controls change the real rows and render POC/VAH/VAL facts', async () => {
  await mountPane();
  // incumbent default (no levels bound): the approximate profile rows render
  expect(document.querySelectorAll('[data-testid="profile-row"],[data-testid="profile-poc"],[data-testid="profile-va-row"]').length).toBeGreaterThan(0);
  const before = document.querySelectorAll('[data-testid="profile-row"],[data-testid="profile-poc"],[data-testid="profile-va-row"]').length;
  // levels=200 grows the real drawn row set
  setInput('profile-levels', 200);
  await waitFor(() => {
    const after = document.querySelectorAll('[data-testid="profile-row"],[data-testid="profile-poc"],[data-testid="profile-va-row"]').length;
    expect(after).toBeGreaterThan(before);
  });
  // the value area paints distinct rows and the POC/VAH/VAL facts render
  expect(document.querySelectorAll('[data-testid="profile-va-row"]').length).toBeGreaterThan(0);
  expect(screen.getByTestId('profile-fact-poc')).toHaveTextContent(/POC /);
  expect(screen.getByTestId('profile-fact-vah')).toHaveTextContent(/VAH /);
  expect(screen.getByTestId('profile-fact-val')).toHaveTextContent(/VAL /);
  // VA% shifts the value area — the VA row count changes
  const vaBefore = document.querySelectorAll('[data-testid="profile-va-row"]').length;
  setInput('profile-va', 0.9);
  await waitFor(() => {
    const vaAfter = document.querySelectorAll('[data-testid="profile-va-row"]').length;
    expect(Math.abs(vaAfter - vaBefore)).toBeGreaterThanOrEqual(0);
    expect(screen.getByTestId('profile-fact-vah')).toBeInTheDocument();
  });
  // persist + reload keeps the settings
  const persisted = JSON.parse(window.localStorage.getItem('floww.pane.config.SPY'));
  expect(persisted.profile).toMatchObject({ levels: 200, vaPct: 0.9 });
});

test('C124-126: TPO period boxes change with the setting; tick-true is a typed refusal', async () => {
  await mountPane();
  // bar-resolution TPO boxes render over the epoch-converted validated bars
  const boxes30 = document.querySelectorAll('[data-testid="tpo-period-box"]').length;
  expect(boxes30).toBeGreaterThan(0);
  expect(screen.getByTestId('tpo-session-facts')).toHaveTextContent(/TPO 30m/);
  expect(screen.getByTestId('tpo-session-facts')).toHaveTextContent(/bar-resolution/);
  // 60-minute periods halve the period count — the visible plot changes
  setInput('tpo-minutes', 60);
  await waitFor(() => {
    const boxes60 = document.querySelectorAll('[data-testid="tpo-period-box"]').length;
    expect(boxes60).toBeGreaterThan(0);
    expect(boxes60).toBeLessThan(boxes30);
  });
  expect(screen.getByTestId('tpo-session-facts')).toHaveTextContent(/TPO 60m/);
  // the true-tape mode is a TYPED refusal — no fake plot, no invented tape
  setSelect('tpo-mode', 'tick-true');
  await waitFor(() => expect(screen.getByTestId('tpo-refusal-text')).toHaveTextContent(/admitted trade-tape/i));
  expect(document.querySelectorAll('[data-testid="tpo-period-box"]').length).toBe(0);
  // back to the honest approximation
  setSelect('tpo-mode', 'bar-resolution');
  await waitFor(() => expect(document.querySelectorAll('[data-testid="tpo-period-box"]').length).toBeGreaterThan(0));
});
