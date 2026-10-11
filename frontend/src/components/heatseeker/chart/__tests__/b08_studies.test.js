// B08 RED->GREEN: deterministic warmup/EMA, session VWAP, exposure gaps/envelopes.
import { sma, ema, sessionVwap, exposureVwap } from '../indicators/priceStudies';
import { getStudy } from '../indicators/registry';

test('SMA/EMA deterministic warmup', () => {
  expect(sma([1, 2, 3, 4], 2)).toEqual([null, 1.5, 2.5, 3.5]);
  expect(ema([1, 2, 3, 4], 2)[3]).toBeCloseTo(3.52, 2);
  expect(sma([1, NaN, 3], 2)).toEqual([null, null, null]);
});

test('session VWAP zero volume unavailable, forming provisional', () => {
  const bars = [
    { high: 10, low: 8, close: 9, volume: 100 },
    { high: 10, low: 9, close: 9.5, volume: 0 },
    { high: 11, low: 9, close: 10, volume: null },
  ];
  const out = sessionVwap(bars, { source: 'hlc3' });
  expect(out[0].vwap).toBeCloseTo(9, 5);
  expect(out[1].reason).toBe('ok');
  expect(out[2].reason).toBe('unavailable');
});

test('exposure-VWAP gaps never carry, opening needs 8 and freezes', () => {
  const boards = [{ eligible: true, centre: 100, upper: 101, lower: 99 }, null, { eligible: true, centre: 102, upper: 103, lower: 101 }];
  const out = exposureVwap(boards, { envelope: 'off' });
  expect(out[1].gap).toBe(true);
  expect(out[2].centre).toBe(102);
  const opening = Array.from({ length: 15 }, (_, i) => ({ eligible: true, centre: 100 + i }));
  const env = exposureVwap(opening, { envelope: 'opening', openingMinutes: 15 });
  expect(env[7].envelope).toBe(null);
  expect(env[14].frozen).toBe(false);
  const after = exposureVwap([...opening, { eligible: true, centre: 200 }], { envelope: 'opening', openingMinutes: 15 });
  expect(after[15].frozen).toBe(true);
  expect(after[15].envelope.high).toBe(114);
});

test('multi-session VWAP resets each New York day (golden oracle)', () => {
  const { sessionVwapValues } = require('../indicators/priceStudies');
  const d1a = { time: '2026-10-06T13:30:00+00:00', high: 10, low: 8, close: 9, volume: 100 };
  const d1b = { time: '2026-10-06T13:31:00+00:00', high: 10, low: 9, close: 9.5, volume: 100 };
  const d2a = { time: '2026-10-07T13:30:00+00:00', high: 20, low: 18, close: 19, volume: 50 };
  const out = sessionVwapValues([d1a, d1b, d2a]);
  // Day 1: 9.0 then (900+950)/200 = 9.25. Day 2 resets: 19.0.
  expect(out[0]).toBeCloseTo(9.0, 8);
  expect(out[1]).toBeCloseTo(9.25, 8);
  expect(out[2]).toBeCloseTo(19.0, 8);
  // Missing volume breaks (null), zero volume with history holds value.
  const out2 = sessionVwapValues([d1a, { ...d1b, volume: null }, { ...d1b, volume: 0 }]);
  expect(out2[1]).toBe(null);
  expect(out2[2]).toBeCloseTo(9.0, 8);
});
test('VWAP bands: volume-weighted sigma + percent, hand-computed', () => {
  const { sessionVwap } = require('../indicators/priceStudies');
  const bars = [
    { high: 10, low: 8, close: 9, volume: 100 },
    { high: 10, low: 9, close: 9.5, volume: 100 },
  ];
  // VWAP 9.25, var = (100*0.0625 + 100*0.0625)/200 = 0.0625, sigma 0.25.
  const std = sessionVwap(bars, { bandBasis: 'std', multipliers: [1, 2] });
  expect(std[1].bands[0].upper).toBeCloseTo(9.5, 8);
  expect(std[1].bands[0].lower).toBeCloseTo(9.0, 8);
  expect(std[1].bands[1].upper).toBeCloseTo(9.75, 8);
  const pct = sessionVwap(bars, { bandBasis: 'percent', multipliers: [1] });
  expect(pct[1].bands[0].upper).toBeCloseTo(9.25 * 1.01, 8);
  expect(pct[1].bands[0].lower).toBeCloseTo(9.25 * 0.99, 8);
  // No volume yet: bands null, never fabricated.
  expect(sessionVwap([{ high: 1, low: 1, close: 1, volume: null }])[0].bands).toBe(null);
});
test('exposure envelopes: opening needs 8 minutes and freezes, session only widens', () => {
  const { openingEnvelope, sessionEnvelope } = require('../indicators/priceStudies');
  const day = '2026-10-06';
  const pts = [];
  for (let m = 0; m < 20; m += 1) {
    const hh = 13, mm = 30 + m;
    pts.push({ time: `${day}T${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}:00+00:00`, centre: 100 + (m % 5) });
  }
  // 09:30 ET = 13:30Z (October, EDT). 15-min window, plenty of minutes.
  const frozen = openingEnvelope(pts, { anchorDate: day, windowMinutes: 15 });
  expect(frozen.status).toBe('frozen');
  expect(frozen.high).toBe(104);
  expect(frozen.low).toBe(100);
  // Too few measured minutes: pending, never a misleading envelope.
  const thin = openingEnvelope(pts.slice(0, 5), { anchorDate: day, windowMinutes: 15 });
  expect(thin.status).toBe('pending');
  expect(thin.high).toBe(null);
  // Eight minutes but window still open: still pending, not frozen early.
  const forming = openingEnvelope(pts.slice(0, 8), { anchorDate: day, windowMinutes: 15 });
  expect(forming.status).toBe('pending');
  // January uses EST (09:30 -> 14:30Z), not a hardcoded -04:00.
  const jan = [];
  for (let m = 0; m < 16; m += 1) {
    jan.push({ time: `2026-01-05T14:${String(30 + m).padStart(2, '0')}:00+00:00`, centre: 200 + m });
  }
  const janEnv = openingEnvelope(jan, { anchorDate: '2026-01-05', windowMinutes: 15 });
  expect(janEnv.status).toBe('frozen');
  expect(janEnv.low).toBe(200);
  // Session envelope only widens through eligible points.
  const sess = sessionEnvelope([{ centre: 100 }, { centre: null }, { centre: 105 }, { centre: 102 }]);
  expect(sess).toEqual({ high: 105, low: 100 });
  expect(sessionEnvelope([{ centre: null }])).toEqual({ high: null, low: null });
});
test('registry declares approximation + replay', () => {
  expect(getStudy('vwap').approximation).toBe('bar-vwap');
  expect(getStudy('exposureVwap').source).toBe('board');
  expect(getStudy('nope')).toBe(null);
});
