/** @jest-environment jsdom */
// MARKET DESKTOP COMPOSITION (owner 13:40): the money display + the grid's
// additive Market display lease. RED-first.
// - marketFormat: human K/M/B at appropriate thresholds with signs/units —
//   the owner's actual on-screen values ($-918,926.0K, $9,469.8M) become
//   readable (-$918.9M, $9.5B) with EXACT source values still accessible.
// - the grid lease is ADDITIVE ONLY: default Stock rendering byte/behavior
//   equivalent; Market mode = the scoped class + the passed formatters.
import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { marketMoney, exactMoney } from '../../../triad/marketFormat';
import SkylitHeatmapGrid from '../../SkylitHeatmapGrid';

const EXPS = ['2026-10-02', '2026-10-09', '2026-10-16', '2026-10-23'];
const STRIKES = [765, 760];
const data = () => ({
  ticker: 'SPY', asof: '2026-10-26T15:00:00Z',
  grid: {
    expiries: EXPS, strikes: STRIKES,
    grid: { '2026-10-02': { '760': -918926012, '765': 9469800000 } },
  },
});

test('marketMoney: human K/M/B at appropriate thresholds with signs and units', () => {
  // the owner's ACTUAL on-screen values
  expect(marketMoney(-918926012)).toBe('-$918.9M');      // was "$-918,926.0K"
  expect(marketMoney(9469800000)).toBe('$9.5B');         // was "$9,469.8M"
  // thresholds: sub-K exact, K at 1e3, M at 1e6, B at 1e9
  expect(marketMoney(732)).toBe('$732');
  expect(marketMoney(1234)).toBe('$1.2K');
  expect(marketMoney(-45678)).toBe('-$45.7K');
  expect(marketMoney(250000)).toBe('$250.0K');
  expect(marketMoney(1000000)).toBe('$1.0M');
  expect(marketMoney(-2834500000)).toBe('-$2.8B');
  // never fabricated: null/undefined/NaN stay empty (the existing gap rule)
  expect(marketMoney(null)).toBe('');
  expect(marketMoney(undefined)).toBe('');
  expect(marketMoney(NaN)).toBe('');
});

test('exactMoney: the EXACT source value, full precision, signs, grouping', () => {
  expect(exactMoney(-918926012)).toBe('-$918,926,012');
  expect(exactMoney(9469800000)).toBe('$9,469,800,000');
  expect(exactMoney(1234.56)).toBe('$1,234.56');
  expect(exactMoney(null)).toBe('');
  expect(exactMoney(NaN)).toBe('');
});

test('the grid lease is ADDITIVE: default rendering stays fmtK-equivalent; Market mode uses the passed formatters + the scoped class', () => {
  // DEFAULT (the Stock path, unchanged): the existing fmtK cell + title
  const base = render(<SkylitHeatmapGrid data={data()} ticker="SPY" />);
  expect(base.getByTitle(/760 · 2026-10-02 · -\$918,926\.0K/)).toBeTruthy();
  expect(base.container.querySelector('.skh-market')).toBe(null); // no Market class on the default path
  base.unmount();
  // MARKET mode: the scoped class + the passed cell formatter, and the cell
  // TITLE carries the EXACT source value (precision never tooltip-only — the
  // inspector and provenance show it too)
  const mk = render(<SkylitHeatmapGrid data={data()} ticker="SPY"
    displayMode="market" formatValue={marketMoney} formatTitle={exactMoney} />);
  expect(mk.container.querySelector('.skh-market')).toBeTruthy();
  expect(mk.getByText('-\$918.9M')).toBeTruthy();         // the human scale IN the cell
  expect(mk.getByTitle(/760 · 2026-10-02 · -\$918,926,012/)).toBeTruthy(); // the exact value in the title
  // and the B-scale value
  expect(mk.getByText('\$9.5B')).toBeTruthy();
});
