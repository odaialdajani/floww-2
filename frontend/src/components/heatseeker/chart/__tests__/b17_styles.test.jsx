import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import { createDrawing, reduceDrawings, geometryFor } from '../drawings/drawingReducer';
import { loadDrawings, saveDrawings } from '../drawings/drawingPersistence';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const arm = () => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: [
    { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, nodes: [] },
    { time: '2026-10-06T14:30:00Z', open: 101, high: 104, low: 100, close: 103, nodes: [] },
    { time: '2026-10-06T15:00:00Z', open: 103, high: 105, low: 101, close: 104, nodes: [] },
  ], candles_with_recorded_nodes: 3, scopes: [] } }));
};

// B17 style model (proposal option A, owner-granted): per-drawing optional
// {color?, width?, dash?}; absent = incumbent defaults (old drawings
// behavior-identical); locked drawings refuse style changes.
test('the reducer styles a drawing additively, bumps revision, refuses locked', () => {
  const d = createDrawing('trend', [{ t: 0, p: 100 }, { t: 1000, p: 101 }]);
  const styled = reduceDrawings([d], { type: 'style', id: d.id, style: { color: '#5ec986', width: 3 } });
  expect(styled[0].style).toEqual({ color: '#5ec986', width: 3 });
  expect(styled[0].revision).toBe(d.revision + 1);
  // merge keeps unspecified keys
  const again = reduceDrawings(styled, { type: 'style', id: d.id, style: { dash: true } });
  expect(again[0].style).toEqual({ color: '#5ec986', width: 3, dash: true });
  // locked drawings refuse
  const locked = reduceDrawings(styled, { type: 'lock', id: d.id });
  const refused = reduceDrawings(locked, { type: 'style', id: d.id, style: { color: '#fff' } });
  expect(refused[0].style).toEqual({ color: '#5ec986', width: 3 });
  // unknown id: unchanged
  const untouched = reduceDrawings([d], { type: 'style', id: 'nope', style: { color: '#fff' } });
  expect(untouched[0].style).toBeUndefined();
});

test('a styled drawing persists through the quota-capped store and loads back', () => {
  window.localStorage.clear();
  const d = createDrawing('trend', [{ t: 0, p: 100 }, { t: 1000, p: 101 }]);
  saveDrawings('SPY', [reduceDrawings([d], { type: 'style', id: d.id, style: { color: '#e3c16a', dash: true } })[0]]);
  const loaded = loadDrawings('SPY');
  expect(loaded[0].style).toEqual({ color: '#e3c16a', dash: true });
});

test('the rail styles the SELECTED drawing and the chart renders it; unstyled stays default', async () => {
  arm();
  window.localStorage.clear();
  const d = createDrawing('trend', [{ t: Date.parse('2026-10-06T14:00:00Z'), p: 100 }, { t: Date.parse('2026-10-06T15:00:00Z'), p: 104 }]);
  saveDrawings('SPY', [d]);
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '3'));
  let shape = document.querySelector('[data-testid="drawing-shape"]');
  expect(shape.getAttribute('stroke')).toBe('#7fa6c0'); // incumbent unselected default
  // select the drawing, then style it through the rail controls
  fireEvent.click(screen.getByTestId('rail-select-' + d.id));
  expect(document.querySelector('[data-testid="drawing-shape"]').getAttribute('data-selected')).toBe('true');
  const color = screen.getByTestId('rail-style-color');
  fireEvent.change(color, { target: { value: '#5ec986' } });
  await waitFor(() => expect(document.querySelector('[data-testid="drawing-shape"]').getAttribute('stroke')).toBe('#5ec986'));
  fireEvent.click(screen.getByTestId('rail-style-dash'));
  await waitFor(() => expect(document.querySelector('[data-testid="drawing-shape"]').getAttribute('stroke-dasharray')).toBe('6 3'));
  // width rides the style model too
  fireEvent.change(screen.getByTestId('rail-style-width'), { target: { value: '3' } });
  await waitFor(() => expect(document.querySelector('[data-testid="drawing-shape"]').getAttribute('stroke-width')).toBe('3'));
  // persisted with the style
  const persisted = JSON.parse(window.localStorage.getItem('floww.drawings.SPY'));
  expect(persisted[0].style).toEqual({ color: '#5ec986', dash: true, width: 3 });
  // selection still draws gold only when unstyled
  expect(screen.getByTestId('rail-style-color')).toBeInTheDocument();
});
