// CHART-C050 focused pins — the ANCHOR STUDY ENGINE (NEW pure helper module).
// RED-first: anchorStudies.js does not exist yet. Contract:
// c050_vwap_anchor_contract v1.0 (C2-PRODUCER-CONTRACTS v2.4, H3 PASS as a
// contract): ONE engine — sessionVwap's cumulative math with a GENERALIZED
// grouping key periodKey(time, anchor); NY calendar identity; Monday-based
// ISO week; quarter months 1-3/4-6/7-9/10-12; same flush-at-boundary reset,
// same gap/hold rules, same bands; honest partial-coverage measurement.
import {
  periodKey, anchoredVwapValues, anchoredVwapBands, anchorCoverage,
} from '../indicators/anchorStudies';
import { sessionVwapValues } from '../indicators/priceStudies';

// NY time helpers for building synthetic bars at chosen NY instants.
const atNY = (dateStr, h, m) => new Date(new Date(`${dateStr}T12:00:00`).getTime()
  - (12 * 60 - (h * 60 + m)) * 60000).toISOString();
const bar = (time, close, volume, high = close, low = close) => ({ time, close, volume, high, low });

test('periodKey: each anchor derives its boundary key from the SAME NY calendar identity', () => {
  // 2026-10-25 is a Sunday; 2026-10-26 is a Monday (ISO week 44 of 2026).
  expect(periodKey(atNY('2026-10-26', 9, 30), 'session')).toBe('2026-10-26'); // NY calendar day (existing sessionDay key)
  expect(periodKey(atNY('2026-10-25', 20, 0), 'session')).toBe('2026-10-25');  // NY date, not UTC (UTC is already the 26th)
  expect(periodKey(atNY('2026-10-26', 9, 30), 'week')).toBe('2026-W44');      // Monday-based ISO week of the NY date
  expect(periodKey(atNY('2026-10-25', 20, 0), 'week')).toBe('2026-W43');      // Sunday belongs to the PRIOR week
  expect(periodKey(atNY('2026-10-26', 9, 30), 'month')).toBe('2026-10');
  expect(periodKey(atNY('2026-10-26', 9, 30), 'quarter')).toBe('2026-Q4');    // months 10-12
  expect(periodKey(atNY('2026-03-31', 15, 0), 'quarter')).toBe('2026-Q1');    // months 1-3
  expect(periodKey(atNY('2026-10-26', 9, 30), 'year')).toBe('2026');
  // a non-finite time never yields a key (existing gap semantics)
  expect(periodKey('not-a-date', 'session')).toBe(null);
  expect(periodKey(null, 'week')).toBe(null);
  // an out-of-enum anchor refuses — never a guessed grouping
  expect(periodKey(atNY('2026-10-26', 9, 30), 'decade')).toBe(null);
});

test('anchored VWAP resets at each period boundary — the cumulative never carries across', () => {
  // Two ISO weeks of bars (Mon 2026-10-19 and Mon 2026-10-26), same per-bar shape,
  // so the second week's first cumulative value must depend ONLY on that week's bars.
  const week1 = [bar(atNY('2026-10-19', 9, 30), 100, 10), bar(atNY('2026-10-19', 10, 0), 110, 10)];
  const week2 = [bar(atNY('2026-10-26', 9, 30), 200, 10), bar(atNY('2026-10-26', 10, 0), 210, 10)];
  const frames = [...week1, ...week2];
  const values = anchoredVwapValues(frames, { source: 'hlc3', anchor: 'week' });
  // week 1: (100*10 + 110*10) / 20 = 105; week 2 restarts: (200*10 + 210*10)/20 = 205
  expect(values[2]).toBeCloseTo(200, 6); // first bar of week 2 = its own price — NOT 152.5 (carry would give that)
  expect(values[3]).toBeCloseTo(205, 6);
  // month/quarter/year anchors reset at their boundaries too (same machinery)
  const monthFrames = [bar(atNY('2026-09-30', 15, 0), 100, 10), bar(atNY('2026-10-01', 9, 30), 300, 10)];
  const monthly = anchoredVwapValues(monthFrames, { source: 'hlc3', anchor: 'month' });
  expect(monthly[1]).toBeCloseTo(300, 6); // October restarts from its own bars
  const yearFrames = [bar(atNY('2025-12-31', 15, 0), 100, 10), bar(atNY('2026-01-02', 9, 30), 400, 10)];
  const yearly = anchoredVwapValues(yearFrames, { source: 'hlc3', anchor: 'year' });
  expect(yearly[1]).toBeCloseTo(400, 6);
});

test('session anchor is EXACTLY the existing engine (byte-equivalence pin)', () => {
  const frames = [
    bar(atNY('2026-10-23', 9, 30), 100, 10), bar(atNY('2026-10-23', 10, 0), 111, 5),
    bar(atNY('2026-10-26', 9, 30), 120, 8), bar(atNY('2026-10-26', 10, 0), 99, 2),
  ];
  const viaAnchored = anchoredVwapValues(frames, { source: 'hlc3', anchor: 'session' });
  const viaExisting = sessionVwapValues(frames, { source: 'hlc3' });
  expect(viaAnchored).toEqual(viaExisting); // every value identical — no second engine, no drift
});

test('gap semantics preserved for every anchor: missing volume -> null gap; zero volume holds', () => {
  const frames = [
    bar(atNY('2026-10-19', 9, 30), 100, 10),
    bar(atNY('2026-10-19', 10, 0), 110),      // no volume -> gap
    bar(atNY('2026-10-19', 10, 30), 120, 0),  // zero volume -> HOLD the last value
    bar(atNY('2026-10-19', 11, 0), 130, 10),
  ];
  for (const anchor of ['session', 'week', 'month', 'quarter', 'year']) {
    const values = anchoredVwapValues(frames, { source: 'hlc3', anchor });
    expect(values[1]).toBe(null);                 // missing volume never fabricates
    expect(values[2]).toBeCloseTo(100, 6);        // hold, not a new average
    expect(values[3]).toBeCloseTo((100 * 10 + 130 * 10) / 20, 6);
  }
});

test('anchoredVwapBands carries EVERY multiplier pair per frame (the renderer contract)', () => {
  const frames = [bar(atNY('2026-10-19', 9, 30), 100, 10), bar(atNY('2026-10-19', 10, 0), 110, 10)];
  const bands = anchoredVwapBands(frames, { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], anchor: 'week' });
  const last = bands[bands.length - 1];
  expect(last).toHaveLength(3); // one {upper, lower} pair PER multiplier
  expect(last.map((b) => b.m)).toEqual([1, 2, 3]);
  for (const b of last) {
    expect(b.upper).toBeGreaterThan(b.lower);
    expect(Number.isFinite(b.upper) && Number.isFinite(b.lower)).toBe(true);
  }
});

test('anchorCoverage measures partial windows honestly — never a complete-history claim', () => {
  // A window that starts MID-week (Wednesday) cannot contain the week's first bars.
  const midWeek = [
    bar(atNY('2026-10-21', 9, 30), 100, 10),  // Wed 10-21, week W43 starts Mon 10-19
    bar(atNY('2026-10-21', 10, 0), 101, 10),
  ];
  const partial = anchorCoverage(midWeek, 'week');
  expect(partial.coverage).toBe('partial');
  expect(partial.periodStart).toMatch(/2026-10-19/);          // the derived NY Monday boundary
  expect(partial.firstBar).toBeTruthy();                      // the first loaded bar in the period
  // a window that starts AT the period's calendar boundary is full
  const fromMonday = [
    bar(atNY('2026-10-19', 9, 30), 100, 10),
    bar(atNY('2026-10-19', 10, 0), 101, 10),
  ];
  const full = anchorCoverage(fromMonday, 'week');
  expect(full.coverage).toBe('full');
  // session anchor: a window opening at the session's calendar day start is full
  const dayFull = anchorCoverage([bar(atNY('2026-10-26', 0, 0), 100, 10), bar(atNY('2026-10-26', 9, 30), 101, 10)], 'session');
  expect(dayFull.coverage).toBe('full');
  // empty window -> no coverage object facts (never fabricated)
  expect(anchorCoverage([], 'week').coverage).toBe('none');
});

test('anchorCoverage labels the loaded span honestly (groups measured, not invented)', () => {
  const frames = [
    bar(atNY('2026-10-19', 9, 30), 100, 10),
    bar(atNY('2026-10-20', 9, 30), 101, 10),
    bar(atNY('2026-10-26', 9, 30), 102, 10), // a second week begins
  ];
  const cov = anchorCoverage(frames, 'week');
  expect(cov.groups).toBe(2);                     // W43 and W44 actually present
  expect(cov.firstGroupKey).toBe('2026-W43');
  expect(cov.lastGroupKey).toBe('2026-W44');
  // fewer than 2 measured bars in the period: the value state says so honestly
  const single = [bar(atNY('2026-10-19', 9, 30), 100, 10)];
  expect(anchorCoverage(single, 'week').minBarsState).toBe('insufficient'); // <2 bars: null-with-reason semantics
});
