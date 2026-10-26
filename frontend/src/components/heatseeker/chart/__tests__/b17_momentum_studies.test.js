// SLICE 2 (owner 13:40): RSI 14 / MACD 12-26-9 / ATR 14 — configurable pure
// math + catalog support in the chart/indicators family. RED-first.
// Conventional named methods (Wilder 1978): RSI/ATR use Wilder smoothing;
// MACD = EMA(fast) - EMA(slow) with an EMA(signal) — all through the EXISTING
// ema primitive (the ONE engine rule; this module never re-implements EMA).
// Gap/warmup contract: complete-sample semantics like the rest of the family
// (any non-finite input refuses the series — never a fabricated window);
// warmup slots carry null, never a guessed value.
import { rsi, macd, atr } from '../indicators/momentumStudies';
import { ema } from '../indicators/priceStudies';
import { STUDIES, STUDY_PRESETS, validateStudySettings, studySpecs } from '../indicators/registry';

const CLOSES = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64];
// MACD(26/9) needs more history than RSI(14): a deterministic 40-bar wave.
const MACD_CLOSES = Array.from({ length: 40 }, (_, i) => 44 + Math.sin(i / 4) * 2 + i * 0.05);

test('RSI 14: Wilder-smoothed, textbook recurrence, warmup nulls, flat = 100', () => {
  const out = rsi(CLOSES, 14);
  expect(out).toHaveLength(CLOSES.length);
  // warmup: no value before index period (the first average spans the 14
  // CHANGES at indices 1..14, so the first RSI lands at index 14)
  for (let i = 0; i < 14; i += 1) expect(out[i]).toBeNull();
  expect(out[14]).not.toBeNull();
  // INDEPENDENT derivation (the textbook recurrence, written test-side)
  let g = 0, l = 0;
  for (let i = 1; i <= 14; i += 1) { const d = CLOSES[i] - CLOSES[i - 1]; if (d > 0) g += d; else l -= d; }
  let ag = g / 14, al = l / 14;
  const expect1 = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
  expect(out[14]).toBeCloseTo(expect1, 6);
  // Wilder smoothing: EVERY bar after the first average steps once (15 and 16)
  const step = (d) => { ag = (ag * 13 + Math.max(d, 0)) / 14; al = (al * 13 + Math.max(-d, 0)) / 14; };
  step(CLOSES[15] - CLOSES[14]);
  expect(out[15]).toBeCloseTo(al === 0 ? 100 : 100 - 100 / (1 + ag / al), 6);
  step(CLOSES[16] - CLOSES[15]);
  expect(out[16]).toBeCloseTo(al === 0 ? 100 : 100 - 100 / (1 + ag / al), 6);
  // flat closes: zero average loss -> RSI 100 after warmup (never NaN)
  const flat = rsi(new Array(20).fill(10), 14);
  expect(flat[14]).toBe(100);
  expect(flat[19]).toBe(100);
  // non-finite input: complete-sample refusal (never a fabricated window)
  expect(rsi([...CLOSES.slice(0, 5), NaN, ...CLOSES.slice(6)], 14).every((v) => v === null)).toBe(true);
  // bounds: period < 2 refused
  expect(rsi(CLOSES, 1).every((v) => v === null)).toBe(true);
});

test('MACD 12/26/9: line = EMA12-EMA26 through the ONE ema primitive; signal + histogram', () => {
  const out = macd(MACD_CLOSES, { fast: 12, slow: 26, signal: 9 });
  const e12 = ema(MACD_CLOSES, 12), e26 = ema(MACD_CLOSES, 26);
  expect(out).toHaveLength(MACD_CLOSES.length);
  // warmup: no line before slow-1; every line slot equals the EMA difference
  for (let i = 0; i < 25; i += 1) { expect(out[i].line).toBeNull(); expect(out[i].signal).toBeNull(); expect(out[i].histogram).toBeNull(); }
  for (let i = 25; i < MACD_CLOSES.length; i += 1) {
    expect(out[i].line).not.toBeNull();
    expect(out[i].line).toBeCloseTo(e12[i] - e26[i], 10);
  }
  // the signal is the EMA(9) over the line's available span (warmup nulls)
  const lineSpan = out.map((r) => r.line);
  const firstIdx = lineSpan.findIndex((v) => v !== null);
  const sig = ema(lineSpan.slice(firstIdx), 9);
  for (let i = 0; i < sig.length; i += 1) {
    expect(out[firstIdx + i].signal).toBe(sig[i] === null ? null : sig[i]);
  }
  // histogram = line - signal (null where either is null)
  out.forEach((r) => {
    if (r.line != null && r.signal != null) expect(r.histogram).toBeCloseTo(r.line - r.signal, 10);
    else expect(r.histogram).toBeNull();
  });
  // invalid windows refused: fast >= slow
  expect(macd(MACD_CLOSES, { fast: 26, slow: 12, signal: 9 }).every((r) => r.line === null)).toBe(true);
  // non-finite input: complete-sample refusal
  expect(macd([...MACD_CLOSES.slice(0, 3), null, ...MACD_CLOSES.slice(4)], { fast: 12, slow: 26, signal: 9 }).every((r) => r.line === null)).toBe(true);
});

const BARS = [
  { high: 10.2, low: 9.8, close: 10.0 }, { high: 10.6, low: 10.0, close: 10.5 },
  { high: 10.4, low: 9.9, close: 10.1 }, { high: 10.9, low: 10.2, close: 10.8 },
  { high: 11.0, low: 10.3, close: 10.9 }, { high: 10.7, low: 10.1, close: 10.4 },
  { high: 10.9, low: 10.3, close: 10.6 }, { high: 11.2, low: 10.5, close: 11.0 },
  { high: 11.4, low: 10.8, close: 11.3 }, { high: 11.1, low: 10.4, close: 10.7 },
  { high: 11.3, low: 10.6, close: 11.1 }, { high: 11.5, low: 10.9, close: 11.2 },
  { high: 11.2, low: 10.5, close: 10.8 }, { high: 11.4, low: 10.7, close: 11.1 },
  { high: 11.6, low: 11.0, close: 11.4 },
];

test('ATR 14: true range with prevClose, Wilder smoothing, first-bar rule', () => {
  const out = atr(BARS, 14);
  expect(out).toHaveLength(BARS.length);
  for (let i = 0; i < 13; i += 1) expect(out[i]).toBeNull();
  // INDEPENDENT derivation test-side: TR list, first ATR = mean(TR[0..13]), Wilder after
  const tr = BARS.map((b, i) => (i === 0
    ? b.high - b.low
    : Math.max(b.high - b.low, Math.abs(b.high - BARS[i - 1].close), Math.abs(b.low - BARS[i - 1].close))));
  let a = tr.slice(0, 14).reduce((s, v) => s + v, 0) / 14;
  expect(out[13]).toBeCloseTo(a, 10);
  a = (a * 13 + tr[14]) / 14;
  expect(out[14]).toBeCloseTo(a, 10);
  // a bar with non-finite high/low/close refuses the whole series
  const bad = [...BARS.slice(0, 5), { high: NaN, low: 9.9, close: 10 }, ...BARS.slice(6)];
  expect(atr(bad, 14).every((v) => v === null)).toBe(true);
  // empty input: nothing fabricated
  expect(atr([], 14)).toEqual([]);
});

test('the registry gains the three momentum kinds: declarations, bounds, presets, and bridge specs', () => {
  // declarations carry the exact conventional contract
  expect(STUDIES.rsi).toMatchObject({ version: 'rsi.v1', source: 'ohlc', unit: 'percent', replay: true });
  expect(STUDIES.macd).toMatchObject({ version: 'macd.v1', source: 'ohlc', unit: 'price', replay: true });
  expect(STUDIES.atr).toMatchObject({ version: 'atr.v1', source: 'ohlc', unit: 'price', replay: true });
  // named presets at the conventional defaults
  expect(STUDY_PRESETS['RSI 14']).toEqual({ kind: 'rsi', settings: { period: 14 } });
  expect(STUDY_PRESETS['MACD 12·26·9']).toEqual({ kind: 'macd', settings: { fast: 12, slow: 26, signal: 9 } });
  expect(STUDY_PRESETS['ATR 14']).toEqual({ kind: 'atr', settings: { period: 14 } });
  // validation bounds
  expect(validateStudySettings('rsi', { period: 14 })).toBe(true);
  expect(validateStudySettings('rsi', { period: 1 })).toBe(false);
  expect(validateStudySettings('macd', { fast: 12, slow: 26, signal: 9 })).toBe(true);
  expect(validateStudySettings('macd', { fast: 26, slow: 12, signal: 9 })).toBe(false); // fast must be < slow
  expect(validateStudySettings('macd', { fast: 12, slow: 26, signal: 0 })).toBe(false);
  expect(validateStudySettings('atr', { period: 14 })).toBe(true);
  expect(validateStudySettings('atr', { period: 0 })).toBe(false);
  // the bridge: MACD = THREE specs (line/signal/histogram) in its OWN pane;
  // RSI/ATR = one line each in their own panes; warmup points stay null
  const frames = CLOSES.map((c, i) => ({ time: `2026-10-26T13:${String(30 + i).padStart(2, '0')}:00Z`, close: c, open: c, high: c + 0.2, low: c - 0.2, volume: 100 }));
  const rsiSpecs = studySpecs({ instanceId: 'rsi-1', kind: 'rsi', settings: { period: 14 } }, frames);
  expect(rsiSpecs).toHaveLength(1);
  expect(rsiSpecs[0].label).toBe('RSI 14');
  expect(rsiSpecs[0].pane).toBe('rsi');
  expect(rsiSpecs[0].points[13].value).toBeNull();
  expect(rsiSpecs[0].points[14].value).not.toBeNull();
  const macdSpecs = studySpecs({ instanceId: 'macd-1', kind: 'macd', settings: { fast: 12, slow: 26, signal: 9 } }, frames);
  expect(macdSpecs).toHaveLength(3);
  expect(macdSpecs.map((s) => s.pane)).toEqual(['macd', 'macd', 'macd']);
  const atrSpecs = studySpecs({ instanceId: 'atr-1', kind: 'atr', settings: { period: 14 } }, frames);
  expect(atrSpecs).toHaveLength(1);
  expect(atrSpecs[0].pane).toBe('atr');
  // invalid settings produce NO specs (the existing refusal contract)
  expect(studySpecs({ instanceId: 'x', kind: 'rsi', settings: { period: 0 } }, frames)).toEqual([]);
});

// The panel surfaces the momentum kinds: catalog rows, editors, labels.
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import IndicatorsPanel from '../indicators/IndicatorsPanel';

test('the panel creates/edits RSI and MACD with the conventional controls', () => {
  const created = [];
  const updates = [];
  render(<IndicatorsPanel
    instances={[{ instanceId: 'rsi-a', kind: 'rsi', settings: { period: 14 }, visible: true, order: 0 }]}
    frames={CLOSES.map((c, i) => ({ time: `2026-10-26T13:${String(30 + i).padStart(2, '0')}:00Z`, close: c, open: c, high: c + 0.2, low: c - 0.2, volume: 100 }))} paneState={{}} availability={{}}
    onCreate={(kind, settings) => created.push({ kind, settings })}
    onUpdateSettings={(inst, patch) => updates.push({ inst, patch })} />);
  // the catalog rows exist for all three momentum kinds
  expect(screen.getByTestId('catalog-add-rsi')).toBeInTheDocument();
  expect(screen.getByTestId('catalog-add-macd')).toBeInTheDocument();
  expect(screen.getByTestId('catalog-add-atr')).toBeInTheDocument();
  // clicking RSI creates the conventional default
  fireEvent.click(screen.getByTestId('catalog-add-rsi'));
  expect(created).toEqual([{ kind: 'rsi', settings: STUDY_PRESETS['RSI 14'].settings }]);
  // the existing instance shows its label + editor (the catalog chip shares
  // the text, so assert the instance's OWN editor is present)
  expect(screen.getByTestId('instance-period-rsi-a')).toBeInTheDocument();
  fireEvent.change(screen.getByTestId('instance-period-rsi-a'), { target: { value: '21' } });
  expect(updates).toEqual([{ inst: 'rsi-a', patch: { period: 21 } }]); // the panel passes the instance id
});
