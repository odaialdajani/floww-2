// B20 MOUNTED MOMENTUM — H2's frozen producer (81cdfb91) consumed through H1's
// REAL renderer: separate honest scales (RSI fixed 0..100, MACD zero-anchored
// with line/signal strokes + histogram bars, ATR own price scale), warmup
// nulls break lines, a refused series renders the honest note and NOTHING.
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
// 40 clean bars: warmup windows are visible and the first values land late
const FRAMES = Array.from({ length: 40 }, (_, i) => ({
  time: new Date(Date.UTC(2026, 9, 20 + Math.floor(i / 13), 14 + (i % 13) * 0.5, (i % 2) * 30)).toISOString(),
  open: 100 + i * 0.2, high: 101 + i * 0.2, low: 99 + i * 0.2, close: 100.5 + i * 0.2, volume: 10 + i, nodes: [],
}));
const REFUSED = FRAMES.map((f, i) => (i === 10 ? { ...f, close: NaN } : f));
beforeEach(() => {
  const axios = require('axios');
  window.localStorage.clear();
});
const mountPane = async (frames = FRAMES) => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames, candles_with_recorded_nodes: frames.length, scopes: [] } }));
  const r = render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => {
    const n = Number(screen.getByTestId('recorded-price-chart').getAttribute('data-candles'));
    expect(n).toBeGreaterThan(0);
  }, { timeout: 5000 });
  return r;
};

test('RSI/MACD/ATR render in their OWN panes with honest scales and warmup breaks', async () => {
  await mountPane();
  fireEvent.click(screen.getByTestId('catalog-add-rsi'));
  fireEvent.click(screen.getByTestId('catalog-add-macd'));
  fireEvent.click(screen.getByTestId('catalog-add-atr'));
  await waitFor(() => expect(screen.getByTestId('momentum-pane-rsi')).toBeInTheDocument());
  // RSI: its own pane, the fixed 0..100 scale noted, a real broken line
  expect(screen.getByTestId('momentum-label-rsi')).toHaveTextContent(/0–100 fixed scale/);
  const rsiLine = document.querySelector('[data-testid="rsi-line"]');
  expect(rsiLine).not.toBeNull();
  // warmup: RSI's first value lands at index period (14) — the line is broken
  const rsiPts = rsiLine.getAttribute('points').split(' ').length;
  expect(rsiPts).toBeLessThan(40); // the warmup nulls are NOT drawn or bridged
  // MACD: line + signal strokes and the histogram bars around zero
  expect(document.querySelectorAll('[data-testid="macd-line"]').length).toBeGreaterThan(0);
  expect(document.querySelectorAll('[data-testid="macd-histogram"]').length).toBeGreaterThan(0);
  expect(screen.getByTestId('momentum-label-macd')).toHaveTextContent(/zero-anchored/);
  // ATR: its own pane + own price scale
  expect(document.querySelector('[data-testid="atr-line"]')).not.toBeNull();
  expect(screen.getByTestId('momentum-label-atr')).toHaveTextContent(/own price scale/);
  // the price chart itself stays clean of momentum specs (no pane bleed)
  expect([...document.querySelectorAll('[data-testid^="study-line-"]')].length).toBe(0);
});

test('settings edits change the real plots; remove removes the pane', async () => {
  await mountPane();
  fireEvent.click(screen.getByTestId('catalog-add-rsi'));
  await waitFor(() => expect(screen.getByTestId('momentum-pane-rsi')).toBeInTheDocument());
  const geo = () => document.querySelector('[data-testid="rsi-line"]').getAttribute('points');
  const g14 = geo();
  // the per-instance editor: period 14 -> 7 (shorter warmup, different geometry)
  const editor = document.querySelector('[data-testid^="instance-period-"]');
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  act(() => { setter.call(editor, '7'); editor.dispatchEvent(new Event('input', { bubbles: true })); });
  await waitFor(() => expect(geo()).not.toBe(g14), { timeout: 3000 });
  expect(screen.getByTestId('momentum-label-rsi')).toHaveTextContent(/RSI 7/);
  // remove: the instance row's remove button kills the pane
  const rm = document.querySelector('[data-testid^="instance-remove-"]');
  fireEvent.click(rm);
  await waitFor(() => expect(document.querySelector('[data-testid="momentum-pane-rsi"]')).toBeNull());
});

test('a refused series renders the honest note and NOTHING — never zero-filled', async () => {
  // The producer's refusal shape: an all-null points array (C047 — a
  // non-finite close refuses the WHOLE series). The renderer must show the
  // honest note and draw NOTHING: no zero-fill, no bridged line.
  const RecordedPriceChart = (await import('../../RecordedPriceChart')).default;
  const spec = { instanceId: 'x', study: 'rsi', id: 'x', band: null, label: 'RSI 14', pane: 'rsi',
    points: FRAMES.map(f => ({ time: f.time, value: null })) };
  render(<RecordedPriceChart ticker="SPY" frames={FRAMES} studyLines={[spec]} showAtlas={false} />);
  await waitFor(() => expect(screen.getByTestId('momentum-pane-rsi')).toBeInTheDocument());
  expect(screen.getByText(/series refused/i)).toBeInTheDocument();
  expect(document.querySelector('[data-testid="rsi-line"]')).toBeNull();
});
