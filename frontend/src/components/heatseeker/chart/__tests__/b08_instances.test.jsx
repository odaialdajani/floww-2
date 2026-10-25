// B08 ACTUAL STUDY INSTANCES — contract v2 alignment (C045-C051, C112-C116).
// The b08_registry_contract (C2-PRODUCER-CONTRACTS v2, 2026-10-25) is the
// source of truth: six kinds (sma/ema/bollinger/volume/vwap/exposure-vwap),
// per-declaration schemas with bounds, pane source-eligibility refusals,
// and the bollinger two-window band warmup. Existing VWAP/profile engines
// are reused; missing data stays missing — never zero, never fabricated.
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import { STUDIES, getStudy, createStudyInstance, validateStudySettings, studySpecs, paneEligibility } from '../indicators/registry';
import { bollinger, sessionVwapValues } from '../indicators/priceStudies';
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
const frames4 = () => [
  { time: '2026-10-06T14:00:00Z', close: 101, volume: 10 },
  { time: '2026-10-06T14:30:00Z', close: 103, volume: 20 },
  { time: '2026-10-06T15:00:00Z', close: 104, volume: 30 },
  { time: '2026-10-06T15:30:00Z', close: 105, volume: 40 },
];

test('registry: the six contract kinds, schemas with bounds, unique instance ids (C045)', () => {
  for (const kind of ['sma', 'ema', 'bollinger', 'volume', 'vwap', 'exposure-vwap']) {
    expect(getStudy(kind)).toBeTruthy();
  }
  const a = createStudyInstance('ema', { period: 9 }, 'p1');
  const b = createStudyInstance('ema', { period: 21 }, 'p1');
  expect(a.instanceId).not.toBe(b.instanceId);
  expect(a.kind).toBe('ema');
  expect(a.source).toBe('close');
  expect(a.visible).toBe(true);
  expect(typeof a.order).toBe('number');
  // MA periods: integer 1..500
  expect(validateStudySettings('sma', { period: 1 })).toBe(true);
  expect(validateStudySettings('sma', { period: 500 })).toBe(true);
  expect(validateStudySettings('sma', { period: 501 })).toBe(false);
  expect(validateStudySettings('sma', { period: 2.5 })).toBe(false);
  expect(validateStudySettings('sma', { period: '20' })).toBe(false);
  expect(validateStudySettings('sma', { period: 0 })).toBe(false);
  // bollinger: period 10..500, multiple 0.5..5
  expect(validateStudySettings('bollinger', { period: 10, multiple: 2 })).toBe(true);
  expect(validateStudySettings('bollinger', { period: 9, multiple: 2 })).toBe(false);
  expect(validateStudySettings('bollinger', { period: 501, multiple: 2 })).toBe(false);
  expect(validateStudySettings('bollinger', { period: 20, multiple: 0.5 })).toBe(true);
  expect(validateStudySettings('bollinger', { period: 20, multiple: 5 })).toBe(true);
  expect(validateStudySettings('bollinger', { period: 20, multiple: 0.4 })).toBe(false);
  expect(validateStudySettings('bollinger', { period: 20, multiple: 5.1 })).toBe(false);
  // vwap: source hlc3|close, std|percent basis, <=3 multipliers; volume: {}
  expect(validateStudySettings('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], bands: false })).toBe(true);
  expect(validateStudySettings('vwap', { source: 'open', bandBasis: 'std', multipliers: [], bands: false })).toBe(false);
  expect(validateStudySettings('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3, 4], bands: false })).toBe(false);
  expect(validateStudySettings('volume', {})).toBe(true);
  expect(validateStudySettings('madeup', {})).toBe(false);
});

test('pane source-eligibility: typed refusals per kind', () => {
  const withClose = frames4();
  const noVolume = frames4().map(f => ({ time: f.time, close: f.close }));
  const noClose = frames4().map(f => ({ time: f.time, volume: f.volume }));
  expect(paneEligibility('sma', withClose).ok).toBe(true);
  expect(paneEligibility('sma', noClose).ok).toBe(false);
  expect(paneEligibility('sma', noClose).reason).toBe('no finite close on this pane');
  expect(paneEligibility('vwap', withClose).ok).toBe(true);
  expect(paneEligibility('vwap', noVolume).ok).toBe(false);
  expect(paneEligibility('vwap', noVolume).reason).toBe('no finite volume on this pane');
  expect(paneEligibility('volume', noVolume).ok).toBe(false);
  expect(paneEligibility('exposure-vwap', withClose).ok).toBe(false);
  expect(paneEligibility('exposure-vwap', withClose).reason).toBe('no eligible board source on the price pane');
});

test('bollinger: centre from period-1, bands only after 2*period-1 samples, pinned population std (C048)', () => {
  // values 1..5, period 3, multiple 2. Centre (window mean) from i>=2.
  // Contract warmup: "no centre before period-1; no bands before 2*period-1
  // samples of variance" — bands once 2*period-1 samples exist (i >= 2*period-2).
  // Population sigma (ddof=0) over the same window the SMA uses.
  const out = bollinger([1, 2, 3, 4, 5], 3, 2);
  expect(out[0]).toBe(null);
  expect(out[1]).toBe(null);
  expect(out[2].mean).toBe(2);
  expect(out[2].upper).toBe(null);
  expect(out[2].lower).toBe(null);
  expect(out[3].mean).toBe(3);
  expect(out[3].upper).toBe(null);
  expect(out[4].mean).toBe(4);
  const sigma32 = Math.sqrt(2 / 3);
  expect(out[4].sigma).toBeCloseTo(sigma32, 12);
  expect(out[4].upper).toBeCloseTo(4 + 2 * sigma32, 12);
  expect(out[4].lower).toBeCloseTo(4 - 2 * sigma32, 12);
  // non-finite input refuses the whole series — no fabricated windows
  expect(bollinger([1, NaN, 3], 2, 2)).toEqual([null, null, null]);
  expect(bollinger([1, 2], 9, 2)).toEqual([null, null]);
});

test('studyStore: versioned round-trip with the contract instance shape, corrupt recover, quota cap', () => {
  window.localStorage.clear();
  const inst = [createStudyInstance('ema', { period: 9 }, 'SPY'), createStudyInstance('bollinger', { period: 20, multiple: 2 }, 'SPY')];
  saveStudyInstances('SPY', inst);
  const loaded = loadStudyInstances('SPY');
  expect(loaded).toHaveLength(2);
  expect(loaded[0].instanceId).toBe(inst[0].instanceId);
  expect(loaded[0].kind).toBe('ema');
  expect(loaded[0].settings.period).toBe(9);
  expect(loaded[1].kind).toBe('bollinger');
  expect(loaded[1].settings.multiple).toBe(2);
  window.localStorage.setItem('floww.chart.studies.SPY', '{not json');
  expect(loadStudyInstances('SPY')).toEqual([]);
  let threw = null;
  try { saveStudyInstances('SPY', Array.from({ length: STUDY_QUOTA + 1 }, () => createStudyInstance('sma', { period: 2 }, 'SPY'))); } catch (e) { threw = e.message; }
  expect(threw).toBe('study quota exceeded');
});

test('studySpecs: MA/bollinger series from real frames; vwap through the EXISTING engine; volume is a record instance', () => {
  const frames = frames4();
  const smaSpec = studySpecs(createStudyInstance('sma', { period: 2 }, 'SPY'), frames);
  expect(smaSpec).toHaveLength(1);
  expect(smaSpec[0].points.map(p => p.value)).toEqual([null, 102, 103.5, 104.5]);
  const emaSpec = studySpecs(createStudyInstance('ema', { period: 2 }, 'SPY'), frames);
  expect(emaSpec[0].points[3].value).not.toBe(smaSpec[0].points[3].value);
  const bbSpec = studySpecs(createStudyInstance('bollinger', { period: 10, multiple: 2 }, 'SPY'), Array.from({ length: 25 }, (_, i) => ({ time: `2026-10-06T1${Math.floor(i / 6)}:${String((i * 30) % 60).padStart(2, '0')}:00Z`, close: 100 + i, volume: 10 + i })));
  expect(bbSpec.map(s => s.band).sort()).toEqual(['lower', 'mean', 'upper']);
  // centre from index 9, bands only from index 18 (2*period-1 samples): the
  // band lines carry fewer points than the centre — the warmup is visible
  expect(bbSpec[0].points.filter(p => p.value !== null).length).toBe(16);
  expect(bbSpec[1].points.filter(p => p.value !== null).length).toBe(7);
  expect(bbSpec[2].points.filter(p => p.value !== null).length).toBe(7);
  // vwap rides the EXISTING session engine (hlc3 of the frames), aligned per frame
  const vwapSpec = studySpecs(createStudyInstance('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], bands: false }, 'SPY'), frames);
  expect(vwapSpec).toHaveLength(1);
  const oracle = sessionVwapValues(frames);
  expect(vwapSpec[0].points.map(p => p.value)).toEqual(oracle);
  // volume: a record instance (eligibility + persistence) — no price-axis line
  expect(studySpecs(createStudyInstance('volume', {}, 'SPY'), frames)).toEqual([]);
  // a frame with a missing close refuses the whole MA series (complete samples)
  const gappy = frames4(); gappy[2] = { time: '2026-10-06T15:00:00Z', volume: 30 };
  expect(studySpecs(createStudyInstance('sma', { period: 2 }, 'SPY'), gappy)[0].points.every(p => p.value === null)).toBe(true);
});

test('MOUNTED: two differently configured studies render independently and survive reload (C045)', async () => {
  arm();
  window.localStorage.clear();
  const { unmount } = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '4'));
  fireEvent.click(screen.getByTestId('studies-panel-summary'));
  fireEvent.change(screen.getByTestId('study-add-period'), { target: { value: '2' } });
  fireEvent.click(screen.getByTestId('study-add-sma'));
  fireEvent.change(screen.getByTestId('study-add-period'), { target: { value: '3' } });
  fireEvent.click(screen.getByTestId('study-add-ema'));
  await waitFor(() => expect(document.querySelectorAll('[data-testid^="study-line-"]')).toHaveLength(2));
  const polylines = [...document.querySelectorAll('[data-testid^="study-line-"]')];
  const points = polylines.map(p => p.getAttribute('points'));
  expect(points[0]).not.toBe(points[1]);
  const persisted = loadStudyInstances('SPY');
  expect(persisted.map(s => s.kind).sort()).toEqual(['ema', 'sma']);
  unmount();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(document.querySelectorAll('[data-testid^="study-line-"]')).toHaveLength(2));
  // invalid settings refused with a typed message; no instance is created
  fireEvent.click(screen.getByTestId('studies-panel-summary'));
  fireEvent.change(screen.getByTestId('study-add-period'), { target: { value: '0' } });
  fireEvent.click(screen.getByTestId('study-add-sma'));
  expect(screen.getByTestId('studies-refusal')).toBeInTheDocument();
  expect(document.querySelectorAll('[data-testid^="study-line-"]').length).toBe(2);
  // the exposure-vwap kind is DECLARED but this pane has no board source: typed refusal
  fireEvent.click(screen.getByTestId('study-add-exposure-vwap'));
  expect(screen.getByTestId('studies-refusal')).toHaveTextContent(/eligible board source/i);
  expect(document.querySelectorAll('[data-testid^="study-line-"]').length).toBe(2);
});

test('MOUNTED: bollinger bands render only after the two-window warmup (20 frames, period 10)', async () => {
  window.localStorage.clear();
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: Array.from({ length: 20 }, (_, i) => ({
    time: `2026-10-06T${String(9 + Math.floor(i * 30 / 60)).padStart(2, '0')}:${String((i * 30) % 60).padStart(2, '0')}:00Z`,
    open: 100 + i, high: 102 + i, low: 99 + i, close: 101 + i, volume: 10 + i, nodes: [] })), candles_with_recorded_nodes: 20, scopes: [] } }));
  const first = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '20'));
  saveStudyInstances('SPY', [createStudyInstance('bollinger', { period: 10, multiple: 2 }, 'SPY')]);
  first.unmount();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(document.querySelectorAll('[data-testid^="study-line-"]')).toHaveLength(3));
  const byBand = [...document.querySelectorAll('[data-testid^="study-line-"]')].map(e => e.getAttribute('data-band'));
  expect(byBand.sort()).toEqual(['lower', 'mean', 'upper']);
  // the centre line has MORE rendered points than the band lines (warmup gap)
  const pts = [...document.querySelectorAll('[data-testid^="study-line-"]')].map(e => (e.getAttribute('points') || '').split(' ').length);
  const meanPts = Math.max(...pts);
  expect(Math.min(...pts)).toBeLessThan(meanPts);
});
