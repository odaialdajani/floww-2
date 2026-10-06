import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import axios from 'axios';
import SkylitControlBar from './SkylitControlBar';
import WallInspector from './WallInspector';
import TrinityView from '../TrinityView';

jest.mock('../../config/api', () => ({ API: '/api', BACKEND_URL: '', BACKEND_BASE: '' }));
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));

const wall = { wall_id: 'w', low: 100, high: 101, members: [100], gross: 100000, net: 100000 };
const section = (n) => ({ strikes: [100], expiries: ['2030-11-15'], grid: { '2030-11-15': { 100: n } } });
const row = (label) => screen.getByText(label).closest('tr');

test('Expand remains visible without a callback, but does not advertise a working action', () => {
  render(<SkylitControlBar />);
  expect(screen.getByTestId('skylit-expand-toolbar-btn')).toBeDisabled();
});

test('an explicit hideExpand controls visibility independently of callback availability', () => {
  render(<SkylitControlBar onExpand={jest.fn()} hideExpand />);
  expect(screen.queryByTestId('skylit-expand-toolbar-btn')).not.toBeInTheDocument();
});

test('GEX menu exposes distinct unweighted and delta-weighted session volume bases', () => {
  const onMetricChange = jest.fn();
  render(<SkylitControlBar onMetricChange={onMetricChange} />);
  const menu = screen.getByTestId('skylit-basis-select');
  expect(screen.getByRole('option', { name: 'Volume × |Δ|' })).toHaveValue('session_delta_volume');
  expect(screen.getByRole('option', { name: 'Session volume Γ (no Δ)' })).toHaveValue('activity');
  fireEvent.change(menu, { target: { value: 'session_delta_volume' } });
  expect(onMetricChange).toHaveBeenCalledWith('session_delta_volume');
});

test('wall comparison uses its volume delta value, not the unweighted or scope amount', () => {
  render(<WallInspector wall={wall} metrics={{ session_delta_volume_net_v1: 999999,
    wall_metrics: { w: { volume_net: 10000, volume_gross: 10000, volume_usable: 1,
      session_delta_volume_net: 5000, session_delta_volume_gross: 5000,
      session_delta_volume_usable: 1, session_delta_volume_missing: 0, session_delta_volume_invalid: 0 } } }} />);
  expect(row('Session vol × |Δ|').textContent).toContain('$5.0K / $5.0K');
  expect(row('Session vol × |Δ|').textContent).not.toContain('999');
});

test('window refusal reads canonical key and preserves the actual reason', () => {
  render(<WallInspector wall={wall} metrics={{ window_dadgex_reason: 'VOLUME_REBASE' }} />);
  expect(row('Recent window').textContent).toContain('volume rebase');
});

test('older legacy window reason remains readable', () => {
  render(<WallInspector wall={wall} metrics={{ window_daddex_reason: 'PROVIDER_MISMATCH' }} />);
  expect(row('Recent window').textContent).toContain('PROVIDER_MISMATCH');
});

test('Triad volume × delta picks the actual fourth surface and leaves raw unchanged', async () => {
  window.sessionStorage.clear();
  axios.get.mockImplementation(async url => ({ data: String(url).includes('/heatmap/') ? {
    ticker: 'SPY', spot: 102, snapshotId: 'r12-synthetic', grid: section(100000),
    metrics: { walls: [wall], grids: { delta: section(50000), activity: section(10000),
      session_delta_volume: section(5000) } }, quality: { state: 'usable' },
  } : {} }));
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId('triad-pane-adjusted')).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText('Adjusted context'), { target: { value: 'session_delta_volume' } });
  expect(screen.getByTestId('triad-pane-adjusted').textContent).toContain('$5.0K');
  expect(screen.getByTestId('triad-pane-adjusted').textContent).not.toContain('$10.0K');
  expect(screen.getByTestId('triad-pane-raw').textContent).toContain('$100.0K');
});
