// B08 ACTUAL STUDY INSTANCES (C045-C048): independently configured SMA/EMA
// (+ eligible Bollinger) through the ONE registry and the actual renderer.
// Missing data stays a gap/refusal — never fabricated; the existing VWAP/
// profile/volume semantics are untouched (their pins live in b08_studies).
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import { STUDIES, getStudy, createStudyInstance, validateStudySettings, studySpecs } from '../indicators/registry';
import { bollinger } from '../indicators/priceStudies';
import { saveStudyInstances, loadStudyInstances, STUDY_QUOTA } from '../persistence/studyStore';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const arm = () => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: [
    { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 10, nodes: [] },
    { time: '2026-10-06T14:30:00Z', open: 101, high: 104, low: 100, close: 103, volume: 20, nodes: [] },
    { time: '2026-10-06T15:00:00Z', open: 103, high: 105, low: 101, close: 104, volume: 30, nodes: [] },
    { time: '2026-10-06T15:30:00Z', open: 104, high: 106, low: 102, close: 105, volume: 40, nodes: [] },
  ], candles_with_recorded_nodes: 4, scopes: [] } }));
};
const frames4 = () => JSON.parse(JSON.stringify({
  f: [
    { time: '2026-10-06T14:00:00Z', close: 101 },
    { time: '2026-10-06T14:30:00Z', close: 103 },
    { time: '2026-10-06T15:00:00Z', close: 104 },
    { time: '2026-10-06T15:30:00Z', close: 105 },
  ],
})).f;

test('registry: bb declared; instances get unique ids and validated settings (C045/C048)', () => {
  expect(STUDIES.bb.inputs).toEqual(['period', 'multiple']);
  expect(getStudy('sma').inputs).toEqual(['period']);
  const a = createStudyInstance('sma', { period: 20 }, 'p1');
  const b = createStudyInstance('sma', { period: 50 }, 'p1');
  expect(a.id).not.toBe(b.id);
  expect(a.id.startsWith('sma-')).toBe(true);
  expect(a.settings.period).toBe(20);
  // validated settings: integers >=1 for MA periods; bb period >=2, multiple finite >0
  expect(validateStudySettings('sma', { period: 20 })).toBe(true);
  expect(validateStudySettings('sma', { period: 0 })).toBe(false);
  expect(validateStudySettings('sma', { period: 2.5 })).toBe(false);
  expect(validateStudySettings('sma', { period: '20' })).toBe(false);
  expect(validateStudySettings('ema', { period: 9 })).toBe(true);
  expect(validateStudySettings('bb', { period: 20, multiple: 2 })).toBe(true);
  expect(validateStudySettings('bb', { period: 1, multiple: 2 })).toBe(false);
  expect(validateStudySettings('bb', { period: 20, multiple: 0 })).toBe(false);
  expect(validateStudySettings('bb', { period: 20, multiple: -1 })).toBe(false);
  expect(validateStudySettings('madeup', {})).toBe(false);
});

test('bollinger: pinned population-std convention, full-window warmup, NaN refusal (C048/C047)', () => {
  // values 1,2,3 with period 3: mean 2, population sigma sqrt(2/3)
  const out = bollinger([1, 2, 3, 4], 3, 2);
  expect(out[0]).toBe(null);
  expect(out[1]).toBe(null);
  const sigma32 = Math.sqrt(2 / 3);
  expect(out[2].mean).toBe(2);
  expect(out[2].sigma).toBeCloseTo(sigma32, 12);
  expect(out[2].upper).toBeCloseTo(2 + 2 * sigma32, 12);
  expect(out[2].lower).toBeCloseTo(2 - 2 * sigma32, 12);
  expect(out[3].mean).toBe(3);
  expect(out[3].sigma).toBeCloseTo(sigma32, 12);
  expect(out[3].upper).toBeCloseTo(3 + 2 * sigma32, 12);
  expect(out[3].lower).toBeCloseTo(3 - 2 * sigma32, 12);
  // any non-finite value refuses the whole series — no fabricated windows
  expect(bollinger([1, NaN, 3], 2, 2)).toEqual([null, null, null]);
  expect(bollinger([1, 2], 0, 2)).toEqual([null, null]);
});

test('studyStore: versioned round-trip, corrupt recover, quota cap', () => {
  window.localStorage.clear();
  const inst = [createStudyInstance('ema', { period: 9 }, 'SPY'), createStudyInstance('bb', { period: 20, multiple: 2 }, 'SPY')];
  saveStudyInstances('SPY', inst);
  const loaded = loadStudyInstances('SPY');
  expect(loaded).toHaveLength(2);
  expect(loaded[0].study).toBe('ema');
  expect(loaded[0].settings.period).toBe(9);
  expect(loaded[1].settings.multiple).toBe(2);
  // corrupt payload recovers to empty
  window.localStorage.setItem('floww.chart.studies.SPY', '{not json');
  expect(loadStudyInstances('SPY')).toEqual([]);
  // quota refusal is typed, never a silent drop
  let threw = null;
  try { saveStudyInstances('SPY', Array.from({ length: STUDY_QUOTA + 1 }, () => createStudyInstance('sma', { period: 2 }, 'SPY'))); } catch (e) { threw = e.message; }
  expect(threw).toBe('study quota exceeded');
});

test('studySpecs bridge: SMA/EMA series from real frames, gaps on missing, bb three-band', () => {
  const frames = frames4();
  const smaSpec = studySpecs(createStudyInstance('sma', { period: 2 }, 'SPY'), frames);
  expect(smaSpec).toHaveLength(1);
  expect(smaSpec[0].points.map(p => p.value)).toEqual([null, 102, 103.5, 104.5]);
  expect(smaSpec[0].points.map(p => p.time)[0]).toBe('2026-10-06T14:00:00Z');
  const emaSpec = studySpecs(createStudyInstance('ema', { period: 2 }, 'SPY'), frames);
  expect(emaSpec[0].points[0].value).toBe(null);
  expect(emaSpec[0].points[3].value).not.toBe(smaSpec[0].points[3].value); // independent math
  const bbSpec = studySpecs(createStudyInstance('bb', { period: 3, multiple: 2 }, 'SPY'), frames);
  expect(bbSpec).toHaveLength(3);
  const kinds = bbSpec.map(s => s.band).sort();
  expect(kinds).toEqual(['lower', 'mean', 'upper']);
  // a frame with a missing close refuses the whole series (no window fabrication)
  const gappy = frames4(); gappy[2] = { time: '2026-10-06T15:00:00Z' };
  expect(studySpecs(createStudyInstance('sma', { period: 2 }, 'SPY'), gappy)[0].points.every(p => p.value === null)).toBe(true);
});

test('MOUNTED: two differently configured studies render independently and survive reload (C045)', async () => {
  arm();
  window.localStorage.clear();
  const { unmount } = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '4'));
  // add SMA(2) and EMA(3) through the real Studies panel
  fireEvent.click(screen.getByTestId('studies-panel-summary'));
  fireEvent.change(screen.getByTestId('study-add-period'), { target: { value: '2' } });
  fireEvent.click(screen.getByTestId('study-add-sma'));
  fireEvent.change(screen.getByTestId('study-add-period'), { target: { value: '3' } });
  fireEvent.click(screen.getByTestId('study-add-ema'));
  await waitFor(() => expect(document.querySelectorAll('[data-testid^="study-line-"]')).toHaveLength(2));
  const ids = [...document.querySelectorAll('[data-testid^="study-line-"]')].map(e => e.getAttribute('data-testid')).sort();
  expect(ids[0]).not.toBe(ids[1]);
  // the two polylines carry DIFFERENT point sets (independent configurations)
  const polylines = [...document.querySelectorAll('[data-testid^="study-line-"]')];
  const points = polylines.map(p => p.getAttribute('points'));
  expect(points[0]).not.toBe(points[1]);
  // persisted
  const persisted = loadStudyInstances('SPY');
  expect(persisted.map(s => s.study).sort()).toEqual(['ema', 'sma']);
  expect(persisted.map(s => s.settings.period).sort()).toEqual([2, 3]);
  unmount();
  // RELOAD: a fresh mount reads the same store and renders both instances again
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(document.querySelectorAll('[data-testid^="study-line-"]')).toHaveLength(2));
  // invalid settings are refused by validation — no instance is created
  fireEvent.click(screen.getByTestId('studies-panel-summary'));
  fireEvent.change(screen.getByTestId('study-add-period'), { target: { value: '0' } });
  fireEvent.click(screen.getByTestId('study-add-sma'));
  expect(screen.getByTestId('studies-refusal')).toBeInTheDocument();
  expect(document.querySelectorAll('[data-testid^="study-line-"]').length).toBe(2);
});

test('MOUNTED: Bollinger instance renders mean/upper/lower through the actual renderer', async () => {
  arm();
  window.localStorage.clear();
  saveStudyInstances('SPY', [createStudyInstance('bb', { period: 3, multiple: 2 }, 'SPY')]);
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(document.querySelectorAll('[data-testid^="study-line-"]')).toHaveLength(3));
  const bands = [...document.querySelectorAll('[data-testid^="study-line-"]')].map(e => e.getAttribute('data-band'));
  expect(bands.sort()).toEqual(['lower', 'mean', 'upper']);
  // warmup: 4 frames, period 3 -> the first two points are absent from every polyline
  const segs = [...document.querySelectorAll('[data-testid^="study-line-"]')];
  segs.forEach(s => expect(s.getAttribute('points').startsWith('0,')).toBe(false));
});
