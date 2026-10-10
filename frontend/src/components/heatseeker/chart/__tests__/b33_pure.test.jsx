import React from 'react';
import { fireEvent, render, screen, act } from '@testing-library/react';
import RecordedPriceChart from '../../RecordedPriceChart';
import { zoomTime, zoomPrice } from '../../recordedPriceChartData';

jest.mock('axios', () => ({ get: jest.fn() }));
const frames = Array.from({length: 40}, (_, i) => ({ time: new Date(Date.UTC(2026,9,6,13,30+i)).toISOString(), open: 100+i*0.1, high: 101+i*0.1, low: 99+i*0.1, close: 100.5+i*0.1, duration_seconds: 60, nodes: [] }));
const BOX = { x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 480, width: 800, height: 480, toJSON: () => ({}) };

// Reproduce the EXISTING b33 test scenario but at the pure-function level:
// what does the CURRENT center-anchored zoomTime/zoomPrice do vs grab-anchored?
test('pure-function proof: center anchor vs grab anchor produce different windows', () => {
  // Zoomed-in view so the window has room to move.
  const view = { start: 4, count: 28 }, total = 40;
  const factor = Math.exp(50 / 240); // 50px left drag on time axis (zoom out)
  const center = zoomTime(view, factor, 0.5, total);
  const grab = zoomTime(view, factor, 0.3, total);
  console.log('center:', JSON.stringify(center), 'grab@0.3:', JSON.stringify(grab));
  expect(center).not.toEqual(grab); // anchors genuinely differ
  const point = view.start + 0.3 * (view.count - 1);
  const expectStart = Math.max(0, Math.min(total - grab.count, point - 0.3 * Math.max(0, grab.count - 1)));
  expect(Math.abs(grab.start - expectStart)).toBeLessThanOrEqual(1);
});

test('pure-function proof: zoomPrice grab anchor keeps the grabbed price at its fraction', () => {
  const range = { low: 98.528, high: 105.372 };
  const factor = Math.exp(50 / 180); // 50px down drag on price axis
  const center = zoomPrice(range, factor, 0.5);
  const grab = zoomPrice(range, factor, 0.75);
  const priceAt75Center = center.low + (center.high - center.low) * 0.75;
  const priceAt75Grab = grab.low + (grab.high - grab.low) * 0.75;
  console.log('center: price@0.75 =', priceAt75Center.toFixed(3), '(grabbed 103.376)');
  console.log('grab:   price@0.75 =', priceAt75Grab.toFixed(3), '(grabbed 103.376)');
  const grabbed = range.low + (range.high - range.low) * 0.75;
  expect(Math.abs(priceAt75Grab - grabbed)).toBeLessThan(0.01);
  expect(Math.abs(priceAt75Center - grabbed)).toBeGreaterThan(0.05);
});
