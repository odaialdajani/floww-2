// B09 MAPPED-LEVELS CALLER (b09_mapped_levels_contract v2): cross-INSTRUMENT
// source->target price mapping (SPX levels ON the SPY pane) — never
// naked_levels_claim substitution. The backend route is the ONE authority for
// ratio direction/provenance; this caller only renders what the route admits.
// Offline contract pins now (H3's allowance); the live route is not built —
// the honest unavailable state renders until it lands.
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PriceNodeHistory from '../../PriceNodeHistory';
import { MAPPED_SOURCE_OPTIONS, parseMappedLevelsResponse, eligibleMappedPairsFor } from '../mappedLevelsClient';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const arm = () => {
  const axios = require('axios');
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: [
    { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 10, nodes: [] },
    { time: '2026-10-06T14:30:00Z', open: 101, high: 104, low: 100, close: 103, volume: 20, nodes: [] },
    { time: '2026-10-06T15:00:00Z', open: 103, high: 105, low: 101, close: 104, volume: 30, nodes: [] },
  ], candles_with_recorded_nodes: 3, scopes: [] } }));
};

const availableBody = {
  target: 'SPY', source: 'SPX',
  ratio: { value: 10.02, provenance: { source_bars_used: 2, target_bars_used: 2, window: { start: 1728121200, end: 1728124800 }, known_at: 1728124800 } },
  levels: [
    { source_price: 6000, mapped_price: 103.5, kind: 'diamond', label: '6000 call wall' },
    { source_price: 5800, mapped_price: 100.5, kind: 'triangle', label: '5800 put wall' },
  ],
  legend: { diamond: 'Source call wall', triangle: 'Source put wall' },
  cursor: 1728124800, session: '2026-10-06',
};

test('the supported-pairs table: families only; futures need the validated mapping; others unsupported', () => {
  expect(eligibleMappedPairsFor('SPY')).toEqual(['SPXW', 'SPX']);
  expect(eligibleMappedPairsFor('QQQ')).toEqual(['NDXP', 'NDX']);
  // futures are IN the family table but stay refused until the validated
  // mapping exists — not offered as selectable sources
  expect(eligibleMappedPairsFor('SPY')).not.toContain('ES');
  expect(eligibleMappedPairsFor('QQQ')).not.toContain('NQ');
  // GLD/SLV/DIA/IWM map only to related futures with a validated mapping: none offered
  expect(eligibleMappedPairsFor('GLD')).toEqual([]);
  // an unrelated target has no pairs
  expect(eligibleMappedPairsFor('AAPL')).toEqual([]);
  const options = MAPPED_SOURCE_OPTIONS();
  expect(options).toContainEqual(expect.objectContaining({ value: 'SPXW', family: 'SPX family' }));
});

test('parseMappedLevelsResponse: available body -> shapes + provenance; no-lookahead enforced client-side', () => {
  const parsed = parseMappedLevelsResponse(availableBody, 1728124800);
  expect(parsed.status).toBe('available');
  expect(parsed.shapes).toHaveLength(2);
  expect(parsed.shapes[0]).toMatchObject({ price: 103.5, kind: 'diamond', label: '6000 call wall' });
  expect(parsed.shapes[1]).toMatchObject({ price: 100.5, kind: 'triangle', label: '5800 put wall' });
  expect(parsed.legend).toEqual({ diamond: 'Source call wall', triangle: 'Source put wall' });
  expect(parsed.ratio.value).toBe(10.02);
  expect(parsed.ratio.knownAt).toBe(1728124800);
  // a ratio whose known_at is AFTER the cursor is never used (no-lookahead)
  const lookahead = parseMappedLevelsResponse({ ...availableBody, ratio: { ...availableBody.ratio, provenance: { ...availableBody.ratio.provenance, known_at: 9999999999 } } }, 1728124800);
  expect(lookahead.status).toBe('refused');
  expect(lookahead.reason).toBe('ratio-unavailable-at-cursor');
  // malformed bodies never render partial shapes
  expect(parseMappedLevelsResponse({ status: 'available' }, 1).status).toBe('unavailable');
  expect(parseMappedLevelsResponse(null, 1).status).toBe('unavailable');
});

test('the six typed refusal vectors parse to visible typed states (C040-C043, C115)', () => {
  const refused = (reason) => ({ status: 'refused', reason, levels: [] });
  for (const reason of ['unsupported-pair', 'source-not-eligible', 'ratio-unavailable-at-cursor', 'no-shared-session', 'cursor-not-in-regular-session', 'spxw-board-combination-unavailable']) {
    const parsed = parseMappedLevelsResponse(refused(reason), 1728124800);
    expect(parsed.status).toBe('refused');
    expect(parsed.reason).toBe(reason);
    expect(parsed.shapes).toEqual([]);
  }
  const unavailable = parseMappedLevelsResponse({ status: 'unavailable', reason: 'no-shared-session' }, 1728124800);
  expect(unavailable.status).toBe('unavailable');
  expect(unavailable.reason).toBe('no-shared-session');
});

test('MOUNTED: SPX levels render as diamonds/triangles with a legend on the SPY pane', async () => {
  arm();
  const axios = require('axios');
  const calls = [];
  const baseGet = axios.get.getMockImplementation();
  axios.get.mockImplementation(async (url, config) => {
    calls.push({ url: String(url), params: config?.params });
    if (String(url).includes('/mapped-levels/')) {
      return { data: availableBody };
    }
    return baseGet(url, config);
  });
  window.localStorage.clear();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '3'));
  fireEvent.click(screen.getByTestId('mapped-levels-summary'));
  fireEvent.change(screen.getByTestId('mapped-levels-source'), { target: { value: 'SPX' } });
  await waitFor(() => expect(document.querySelectorAll('[data-testid="mapped-level-shape"]').length).toBe(2));
  const kinds = [...document.querySelectorAll('[data-testid="mapped-level-shape"]')].map(e => e.getAttribute('data-kind')).sort();
  expect(kinds).toEqual(['diamond', 'triangle']);
  expect(screen.getByTestId('mapped-levels-legend')).toHaveTextContent(/Source call wall/);
  expect(screen.getByTestId('mapped-levels-ratio')).toHaveTextContent(/10\.02/);
  expect(calls.some(c => c.url.includes('/api/heatseeker/mapped-levels/SPY') && c.params?.source === 'SPX')).toBe(true);
});

test('MOUNTED: route absent renders the honest unavailable state; a refused body renders the typed reason', async () => {
  arm();
  const axios = require('axios');
  const baseGet = axios.get.getMockImplementation();
  axios.get.mockImplementation(async (url, config) => {
    if (String(url).includes('/mapped-levels/')) {
      throw new Error('Request failed with status code 404');
    }
    return baseGet(url, config);
  });
  window.localStorage.clear();
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-candles', '3'));
  fireEvent.click(screen.getByTestId('mapped-levels-summary'));
  fireEvent.change(screen.getByTestId('mapped-levels-source'), { target: { value: 'SPXW' } });
  await waitFor(() => expect(screen.getByTestId('mapped-levels-status')).toHaveTextContent(/unavailable/i));
  expect(document.querySelectorAll('[data-testid="mapped-level-shape"]').length).toBe(0);
  // refused body -> the typed reason renders
  axios.get.mockImplementation(async (url, config) => {
    if (String(url).includes('/mapped-levels/')) {
      return { data: { status: 'refused', reason: 'cursor-not-in-regular-session', levels: [] } };
    }
    return baseGet(url, config);
  });
  fireEvent.change(screen.getByTestId('mapped-levels-source'), { target: { value: 'SPX' } });
  await waitFor(() => expect(screen.getByTestId('mapped-levels-status')).toHaveTextContent(/cursor-not-in-regular-session/));
  expect(document.querySelectorAll('[data-testid="mapped-level-shape"]').length).toBe(0);
});
