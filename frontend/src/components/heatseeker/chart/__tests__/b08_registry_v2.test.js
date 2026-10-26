// B08/C046/C050/C116 focused pins — the registry v2.2 deltas.
// RED-first: the band-pair defect (first-upper/last-lower only), the missing
// anchor input, the missing EMA9 factory preset and the dead volume record
// are all CURRENT behavior this suite turns RED against.
import {
  STUDIES, getStudy, validateStudySettings, createStudyInstance,
  paneEligibility, studySpecs, STUDY_PRESETS, PANE_CONTROLS,
} from '../indicators/registry';

const C = (t, c, v = 10) => ({ time: t, close: c, volume: v, high: c + 1, low: c - 1, open: c });
const FRAMES = [
  C('2026-10-19T13:30:00.000Z', 100), C('2026-10-19T14:30:00.000Z', 102), C('2026-10-19T15:30:00.000Z', 101),
  C('2026-10-26T13:30:00.000Z', 130), C('2026-10-26T14:30:00.000Z', 128), C('2026-10-26T15:30:00.000Z', 131),
];

test('C116/C129-class fix: EVERY selected VWAP band pair is emitted — not first-upper/last-lower only', () => {
  const inst = createStudyInstance('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], bands: true, anchor: 'session' });
  const specs = studySpecs(inst, FRAMES);
  const uppers = specs.filter((s) => s.band === 'upper');
  const lowers = specs.filter((s) => s.band === 'lower');
  expect(uppers).toHaveLength(3); // one upper PER multiplier
  expect(lowers).toHaveLength(3);  // one lower PER multiplier
  // each pair carries its multiplier and every pair differs (1σ < 2σ < 3σ distance)
  expect(uppers.map((s) => s.multiplier).sort((a, b) => a - b)).toEqual([1, 2, 3]);
  expect(lowers.map((s) => s.multiplier).sort((a, b) => a - b)).toEqual([1, 2, 3]);
  const byM = (m) => uppers.find((s) => s.multiplier === m).points[2].value; // bar 3 of week 1: variance > 0, bands separate
  expect(byM(1)).toBeLessThan(byM(2));
  expect(byM(2)).toBeLessThan(byM(3));
  // ids are unique per pair
  expect(new Set(specs.map((s) => s.id)).size).toBe(specs.length);
});

test('C050: the vwap kind gains the anchor input with bounds — out-of-enum refused, default session byte-compatible', () => {
  expect(STUDIES.vwap.inputs).toEqual(expect.arrayContaining(['source', 'bands', 'anchor']));
  expect(STUDIES.vwap.version).toBe('vwap.v2');
  // default session: settings WITHOUT an anchor stay valid (persisted vwap.v1 rows load)
  expect(validateStudySettings('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1], bands: false })).toBe(true);
  // every contract anchor is valid
  for (const anchor of ['session', 'week', 'month', 'quarter', 'year']) {
    expect(validateStudySettings('vwap', { source: 'close', bandBasis: 'std', multipliers: [1], bands: false, anchor })).toBe(true);
  }
  // out-of-enum anchor refuses BEFORE any instance exists
  expect(validateStudySettings('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1], bands: false, anchor: 'decade' })).toBe(false);
  // a vwap.v1-shaped instance (no anchor) still renders — session by default
  const legacy = { ...createStudyInstance('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1], bands: false }), settings: { source: 'hlc3', bandBasis: 'std', multipliers: [1], bands: false } };
  expect(studySpecs(legacy, FRAMES).length).toBeGreaterThan(0);
});

test('C050: a week-anchored instance resets at the week boundary and the label names the anchor', () => {
  const inst = createStudyInstance('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1], bands: false, anchor: 'week' });
  const specs = studySpecs(inst, FRAMES);
  const line = specs[0];
  expect(line.label).toMatch(/week/);
  const values = line.points.map((p) => p.value);
  const lastOfWeek1 = values[2];   // Fri bar, week 1
  const firstOfWeek2 = values[3];  // Mon bar, week 2 — restarts from its own bars
  const week1Only = [FRAMES[0], FRAMES[1], FRAMES[2]];
  const sessionLike = studySpecs({ ...inst, settings: { ...inst.settings } }, week1Only)[0].points.map((p) => p.value);
  expect(firstOfWeek2).not.toBeCloseTo(lastOfWeek1, 6);           // NOT carried across the boundary
  expect(firstOfWeek2).toBeCloseTo(FRAMES[3].close, 6);           // week 2 first value = that bar's own HLC3
  expect(sessionLike[2]).toBeCloseTo((100 * 10 + 102 * 10 + 101 * 10) / 30, 6); // sanity: HLC3 ≈ close here
});

test('C046: EMA9 factory preset — named defaults, valid settings, instantiable', () => {
  expect(STUDY_PRESETS['EMA 9']).toEqual({ kind: 'ema', settings: { period: 9 } });
  expect(STUDY_PRESETS['SMA 20']).toEqual({ kind: 'sma', settings: { period: 20 } });
  expect(STUDY_PRESETS['Bollinger 20 · 2σ']).toEqual({ kind: 'bollinger', settings: { period: 20, multiple: 2 } });
  expect(STUDY_PRESETS['VWAP · session']).toEqual({ kind: 'vwap', settings: { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], bands: false, anchor: 'session' } });
  for (const key of Object.keys(STUDY_PRESETS)) {
    const p = STUDY_PRESETS[key];
    expect(validateStudySettings(p.kind, p.settings)).toBe(true);
    expect(() => createStudyInstance(p.kind, p.settings)).not.toThrow();
  }
});

test('Volume is a REAL pane control, not a dead record — explicit contract for H1', () => {
  // the pane-control mapping exists and is the honest semantic: the measured
  // volume pane already renders; the instance toggles THE REAL PANE, and no
  // price-axis line is ever drawn from volume.
  expect(PANE_CONTROLS.volume).toBe('volume-pane');
  expect(STUDIES.volume.paneControl).toBe('volume-pane');
  const inst = createStudyInstance('volume', {});
  expect(studySpecs(inst, FRAMES)).toEqual([]);          // never a price-axis line
  // eligibility still demands real volume on the pane
  expect(paneEligibility('volume', FRAMES).ok).toBe(true);
  expect(paneEligibility('volume', [{ close: 1 }]).ok).toBe(false);
});

test('exposure-vwap stays declared-but-unavailable with its typed reason (no fake Add)', () => {
  expect(paneEligibility('exposure-vwap', FRAMES)).toEqual({ ok: false, reason: 'no eligible board source on the price pane' });
  expect(validateStudySettings('exposure-vwap', {})).toBe(false);
});
