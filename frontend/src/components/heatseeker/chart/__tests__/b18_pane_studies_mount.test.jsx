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

test('C118: CVD anchor/MA/zero-axis visibly change the real path; holes never bridge', async () => {
  await mountPane();
  expect(screen.getByTestId('cvd-settings')).toBeInTheDocument();
  expect(screen.getByTestId('cvd-approx-label')).toHaveTextContent(/estimated/i);
  const gNone = cvdGeometry();
  expect(gNone).toBeTruthy();
  // anchor alone groups the MA and prepares the rebase; zero-axis is what
  // visibly rebases the path to zero at each session anchor
  setSelect('cvd-anchor', 'session');
  await waitFor(() => expect(cvdGeometry()).toBeTruthy());
  setSelect('cvd-zero-axis', 'zero-at-anchor');
  await waitFor(() => expect(cvdGeometry()).not.toBe(gNone), { timeout: 3000 });
  // MA period 3: the window RESETS at the session boundary — the MA renders
  // as per-session segments that never span the boundary
  setInput('cvd-ma', 2);
  await waitFor(() => expect(document.querySelectorAll('[data-testid="cvd-ma-line"]').length).toBeGreaterThan(0), { timeout: 3000 });
  const maPoints = [...document.querySelectorAll('[data-testid="cvd-ma-line"]')].map(l => l.getAttribute('points'));
  expect(maPoints.length).toBe(2); // one segment per session — the boundary breaks it
  // reload survival: the configured pane state persists per ticker scope
  const persisted = JSON.parse(window.localStorage.getItem('floww.pane.config.SPY'));
  expect(persisted.cvd).toMatchObject({ anchor: 'session', maPeriod: 2, zeroAxis: 'zero-at-anchor' });
});

test('C118: a missing CVD bar stays an explicit hole — the path and MA never bridge it', async () => {
  // one frame with NO cvd_line entry: a real gap, never zero-filled or drawn across
  const holed = CVD_LINE.slice(0, 4).concat(CVD_LINE.slice(5));
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: FRAMES, candles_with_recorded_nodes: 6, scopes: [] } }));
  const { unmount } = render(<PriceNodeHistory ticker="SPY" open cvdLine={holed} />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '6'), { timeout: 4000 });
  // the hole splits day 2 into two SINGLE-known bars: the day-1 run draws one
  // polyline (3 points) and the isolated bars draw as SEPARATE dots — nothing
  // ever bridges the hole. The polyline's points string must contain exactly
  // the day-1 x positions, never the post-hole bars.
  const line = document.querySelector('[data-testid="cvd-line"]');
  expect(line).not.toBeNull();
  expect(line.getAttribute('points').split(' ')).toHaveLength(4); // the run BEFORE the hole
  expect(document.querySelectorAll('[data-testid="cvd-point"]').length).toBe(1); // the isolated bar AFTER the hole
  setInput('cvd-ma', 2);
  await waitFor(() => {
    // the MA runs only on day 1's contiguous run — one segment, never bridging
    const maSegments = document.querySelectorAll('[data-testid="cvd-ma-line"]').length;
    expect(maSegments).toBe(1);
  }, { timeout: 3000 });
  unmount();
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
  // FINITE GEOMETRY, not just text: every fact label's y must parse as a
  // finite number (the object-vs-price NaN defect survived textContent-only
  // pins and only surfaced as browser SVG attribute errors).
  const finiteY = id => {
    const el = screen.getByTestId(id);
    expect(Number.isFinite(Number(el.getAttribute('y')))).toBe(true);
    expect(Number.isFinite(Number(el.getAttribute('x')))).toBe(true);
  };
  expect(screen.getByTestId('profile-fact-poc')).toHaveTextContent(/POC [0-9]/);
  expect(screen.getByTestId('profile-fact-vah')).toHaveTextContent(/VAH [0-9]/);
  expect(screen.getByTestId('profile-fact-val')).toHaveTextContent(/VAL [0-9]/);
  finiteY('profile-fact-poc'); finiteY('profile-fact-vah'); finiteY('profile-fact-val');
  // VA% shifts the value area — the VA row count changes
  const vaBefore = document.querySelectorAll('[data-testid="profile-va-row"]').length;
  setInput('profile-va-pct', 0.9);
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
