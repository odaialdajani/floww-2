import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';
import { createLayout } from '../persistence/layoutSchema';
import { _clear, saveLocal } from '../persistence/layoutStore';
import { applyPaneSettings } from '../chartReducer';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));

beforeEach(() => {
  localStorage.clear();
  _clear();
  const axios = require('axios');
  axios.get.mockReset();
  axios.get.mockImplementation(async url => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] ?? 'SPY';
    const price = ticker === 'QQQ' ? 400 : 100;
    return { data: { ticker, query_key: '', frames: [
      { time: '2026-10-06T14:00:00Z', open: price, high: price + 2, low: price - 1, close: price + 1, volume: 100 },
      { time: '2026-10-06T14:30:00Z', open: price + 1, high: price + 3, low: price, close: price + 2, volume: 200 },
    ], candles_with_recorded_nodes: 2, node_status: 'available' } };
  });
});

afterEach(() => { cleanup(); _clear(); });

async function mountSplit(overrides = {}) {
  saveLocal('workspace-current', createLayout({ layoutId: 'split', symbols: ['SPY', 'QQQ'], focusedIndex: 0, ...overrides }));
  const view = render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('volume-pane')).toHaveLength(2));
  return view;
}

const panes = () => [...document.querySelectorAll('.pane-slot')];
const volume = pane => within(pane).getByLabelText('Toggle volume pane');
const changeVolume = async pane => {
  await act(async () => {
    if (!volume(pane).closest('details').open) fireEvent.click(within(pane).getByRole('button', { name: 'Chart tools' }));
    fireEvent.click(volume(pane));
  });
};

test('Settings sync defaults off and leaves the other actual chart visible', async () => {
  await mountSplit();
  expect(screen.getByRole('button', { name: 'Settings sync' })).toHaveAttribute('aria-pressed', 'false');
  const [spy, qqq] = panes();
  await changeVolume(spy);
  expect(volume(spy)).not.toBeChecked();
  expect(within(spy).queryByTestId('volume-pane')).not.toBeInTheDocument();
  expect(volume(qqq)).toBeChecked();
  expect(within(qqq).getByTestId('volume-pane')).toBeInTheDocument();
});

test('Settings sync copies false visibility, uses each chart data, then switches back to focused-only', async () => {
  await mountSplit();
  const [spy, qqq] = panes();
  await changeVolume(spy);
  const reads = require('axios').get.mock.calls.length;
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Settings sync' })); });
  expect(volume(qqq)).not.toBeChecked();
  expect(screen.queryAllByTestId('volume-pane')).toHaveLength(0);
  await changeVolume(spy);
  expect(screen.getAllByTestId('volume-pane')).toHaveLength(2);
  expect(within(spy).getByRole('region', { name: 'SPY candle chart' })).toBeInTheDocument();
  expect(within(qqq).getByRole('region', { name: 'QQQ candle chart' })).toBeInTheDocument();
  expect(within(spy).getByTestId('recorded-price-chart')).toHaveAttribute('data-price-low', expect.any(String));
  expect(within(spy).getByTestId('recorded-price-chart').getAttribute('data-price-low'))
    .not.toBe(within(qqq).getByTestId('recorded-price-chart').getAttribute('data-price-low'));
  expect(within(spy).getByLabelText('Candle interval')).toHaveValue('30');
  expect(within(qqq).getByLabelText('Session coverage')).toHaveValue('regular');
  expect(require('axios').get.mock.calls).toHaveLength(reads);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Settings sync' })); });
  await act(async () => { fireEvent.click(screen.getByTestId('focus-pane-1')); });
  await changeVolume(qqq);
  expect(within(spy).getByTestId('volume-pane')).toBeInTheDocument();
  expect(within(qqq).queryByTestId('volume-pane')).not.toBeInTheDocument();
});

test('saved layout restores the explicit off preference and false pane visibility', async () => {
  const view = await mountSplit();
  await changeVolume(panes()[0]);
  await waitFor(() => {
    const saved = JSON.parse(localStorage.getItem('floww.chart.layout.workspace-current'));
    expect(saved.settingsSync).toBe(false);
    expect(saved.paneStates['pane-0'].settings.volume).toBe(false);
  });
  view.unmount();
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(2));
  expect(screen.getByRole('button', { name: 'Settings sync' })).toHaveAttribute('aria-pressed', 'false');
  expect(volume(panes()[0])).not.toBeChecked();
  expect(volume(panes()[1])).toBeChecked();
});

test('Indicators hide/show functional updates use the latest pane visibility while linked', async () => {
  await mountSplit();
  const [spy, qqq] = panes();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Settings sync' })); });
  await act(async () => { fireEvent.click(within(spy).getByTestId('stock-dock-open-indicators')); });
  const toggle = within(spy).getByTestId('pane-toggle-volume-pane');
  await act(async () => { fireEvent.click(toggle); });
  expect(toggle).toHaveAttribute('aria-pressed', 'false');
  expect(within(spy).queryByTestId('volume-pane')).not.toBeInTheDocument();
  expect(within(qqq).queryByTestId('volume-pane')).not.toBeInTheDocument();
  await act(async () => { fireEvent.click(toggle); });
  expect(screen.getAllByTestId('volume-pane')).toHaveLength(2);
  // Two queued functional updates must compose from current owned state.
  await act(async () => { fireEvent.click(toggle); fireEvent.click(toggle); });
  expect(toggle).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getAllByTestId('volume-pane')).toHaveLength(2);
});

test('layout export/import retains visibility without exporting unrelated per-pane values', async () => {
  await mountSplit({ paneStates: { 'pane-0': { price: { low: 88, high: 99 }, privateReading: 123 } } });
  await changeVolume(panes()[0]);
  const writeText = jest.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  await act(async () => { fireEvent.click(screen.getByTestId('layout-export')); });
  const exported = JSON.parse(writeText.mock.calls[0][0]);
  expect(exported.settingsSync).toBe(false);
  expect(exported.paneStates['pane-0'].settings.volume).toBe(false);
  expect(exported.paneStates['pane-0']).not.toHaveProperty('price');
  expect(exported.paneStates['pane-0']).not.toHaveProperty('privateReading');
  exported.settingsSync = true;
  const file = new File([JSON.stringify(exported)], 'settings.json', { type: 'application/json' });
  await act(async () => { fireEvent.change(screen.getByTestId('layout-import'), { target: { files: [file] } }); });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Settings sync' })).toHaveAttribute('aria-pressed', 'true'));
  expect(volume(panes()[0])).not.toBeChecked();
  expect(volume(panes()[1])).toBeChecked();
});

test('late focus/layout/removed-pane settings and non-visibility payloads are refused', () => {
  const live = [
    { id: 'pane-0', symbol: 'SPY', generation: 2, focused: true },
    { id: 'pane-1', symbol: 'QQQ', generation: 1, focused: false },
  ];
  const states = { 'pane-0': { interval: 30 }, 'pane-1': { session: 'regular' } };
  const binding = { ...live[0], epoch: 4 };
  for (const invalid of [
    { ...binding, epoch: 3 }, { ...binding, focused: false },
    { ...binding, generation: 1 }, { ...binding, id: 'removed' },
    { ...binding, symbol: 'IWM' },
  ]) expect(applyPaneSettings(live, states, invalid, 4, { volume: false }, true)).toBe(states);
  for (const invalid of [{ volume: 0 }, { volume: false, symbol: 'IWM' }, { cvd: null }, { price: 99 }, []]) {
    expect(applyPaneSettings(live, states, binding, 4, invalid, true)).toBe(states);
  }
  const next = applyPaneSettings(live, states, binding, 4, { volume: false }, true);
  expect(next['pane-0'].settings.volume).toBe(false);
  expect(next['pane-1'].settings.volume).toBe(false);
  expect(next['pane-0'].interval).toBe(30);
  expect(next['pane-1'].session).toBe('regular');
  expect(next['pane-1']).not.toHaveProperty('interval');
  expect(live[1].symbol).toBe('QQQ');
});
