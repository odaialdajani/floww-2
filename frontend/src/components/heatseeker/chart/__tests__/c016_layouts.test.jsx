import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';
import { _clear, saveLocal } from '../persistence/layoutStore';

jest.setTimeout(15000);
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const mockReadings = [];
let mockFrameAdvance = 0;
jest.mock('../../PriceNodeHistory', () => {
  const React = require('react');
  const Actual = jest.requireActual('../../PriceNodeHistory').default;
  return { __esModule: true, default: function ObservedActualHistory(props) {
    const { onChartReading } = props;
    const onReading = React.useCallback(value => {
      if (value) mockReadings.push({ value, deliver: onChartReading });
      onChartReading?.(value);
    }, [onChartReading]);
    return <Actual {...props} onChartReading={props.onChartReading ? onReading : null} />;
  } };
});
const frames = [
  { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 100 },
  { time: '2026-10-06T14:30:00Z', open: 101, high: 103, low: 100, close: 102, volume: 200 },
];
const slots = () => [...document.querySelectorAll('.pane-slot')];
const symbols = () => slots().map(slot => slot.querySelector('.price-chart-symbol')?.textContent);
const settle = async () => { await act(async () => { await new Promise(resolve => setTimeout(resolve, 120)); }); };
beforeEach(() => {
  _clear(); localStorage.clear(); mockReadings.length = 0; mockFrameAdvance = 0;
  require('axios').get.mockReset();
  require('axios').get.mockImplementation(async url => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] || 'SPY';
    return { data: { ticker, query_key: ticker + ':scope', scopes: [ticker + ':scope'],
      frames: frames.map(frame => ({ ...frame, time: new Date(Date.parse(frame.time) + mockFrameAdvance * 1000).toISOString() })), candles_with_recorded_nodes: 2, node_status: 'available' } };
  });
});
afterEach(() => { cleanup(); _clear(); });

test('C016 ownership: genuine host ticker change retargets only the focused real pane', async () => {
  saveLocal('workspace-current', { layoutId: 'split', symbols: ['SPY', 'QQQ'], focusedIndex: 1 });
  const view = render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(2));
  await settle();
  expect(symbols()).toEqual(['SPY', 'QQQ']);
  expect(screen.getByTestId('focus-pane-1')).toHaveAttribute('aria-pressed', 'true');
  const before = require('axios').get.mock.calls.length;
  view.rerender(<ChartWorkspace ticker="IWM" open useNew />);
  await settle();
  const requests = require('axios').get.mock.calls.slice(before).map(call => String(call[0]));
  expect(symbols()).toEqual(['SPY', 'IWM']);
  expect(requests.some(url => url.includes('price-history/IWM'))).toBe(true);
  expect(requests.some(url => url.includes('price-history/SPY'))).toBe(false);
});

test('C016 ownership: retained actual reading callback cannot overwrite a replacement instance', async () => {
  const contexts = [];
  render(<ChartWorkspace ticker="SPY" open useNew onChartContext={value => contexts.push(value)} />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(1));
  fireEvent.click(screen.getByTestId('layout-split'));
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(2));
  fireEvent.click(screen.getByTestId('focus-pane-1'));
  await waitFor(() => expect(mockReadings.some(r => r.value.source === 'pane-1' && r.value.scope)).toBe(true));
  await settle();
  const old = [...mockReadings].reverse().find(r => r.value.source === 'pane-1' && r.value.scope);
  fireEvent.click(screen.getByTestId('layout-single'));
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(1));
  mockFrameAdvance = 3600;
  fireEvent.click(screen.getByTestId('layout-split'));
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(2));
  fireEvent.click(screen.getByTestId('focus-pane-1'));
  await settle();
  const current = [...mockReadings].reverse().find(r => r.value.source === 'pane-1' && r.value.scope);
  // Deliver the exact retained real callback payload, unmodified, after the
  // replacement mounted chart has reported its synthetic hour-later frames.
  const late = old.value;
  expect(current.value.cursor).toBe(old.value.cursor + 3600);
  await act(async () => { old.deliver(late); });
  const last = contexts[contexts.length - 1];
  expect(current.value.epoch).not.toBe(old.value.epoch);
  expect(last.descriptor.status).toBe('bound');
  expect(last.descriptor.cursor).toBe(current.value.cursor);
});

const NEW_LAYOUTS = [
  ['two-stack', 2], ['three-stack', 3], ['one-plus-two', 3], ['one-beside-two', 3],
  ['four-grid', 4], ['four-up', 4], ['four-stack', 4], ['five-stack', 5],
];
test.each(NEW_LAYOUTS)('C016 arrangement %s mounts %i actual charts behind More layouts', async (id, count) => {
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(1));
  expect(screen.getByTestId('layout-single')).toBeVisible();
  expect(screen.getByTestId('layout-split')).toBeVisible();
  expect(screen.getByTestId('layout-three')).toBeVisible();
  const choice = screen.getByTestId('layout-' + id);
  expect(choice).not.toBeVisible();
  fireEvent.click(screen.getByText('More layouts'));
  expect(choice).toBeVisible();
  fireEvent.click(choice);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(count));
  expect(screen.getByTestId('pane-layout')).toHaveAttribute('data-layout', id);
  expect(slots().filter(slot => slot.querySelector('.pane-focus-btn[aria-pressed="true"]'))).toHaveLength(1);
});

test.each([['four-grid', 3], ['five-stack', 4]])('C016 %s reopens with its last pane focused and own saved state', async (layoutId, focusedIndex) => {
  const names = ['SPY', 'QQQ', 'IWM', 'DIA', 'TLT'].slice(0, focusedIndex + 1);
  const id = 'pane-' + focusedIndex;
  saveLocal('workspace-current', { layoutId, symbols: names, focusedIndex, settingsSync: false,
    paneStates: { [id]: { interval: 5, session: 'all', settings: { volume: false } } } });
  const view = render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(names.length));
  expect(symbols()).toEqual(names);
  expect(screen.getByTestId('focus-' + id)).toHaveAttribute('aria-pressed', 'true');
  const focused = slots()[focusedIndex];
  expect(focused.querySelector('[aria-label="Candle interval"]')).toHaveValue('5');
  expect(focused.querySelector('[aria-label="Session coverage"]')).toHaveValue('all');
  await waitFor(() => expect(JSON.parse(localStorage.getItem('floww.chart.layout.workspace-current')).focusedIndex).toBe(focusedIndex));
  view.unmount();
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(names.length));
  expect(symbols()).toEqual(names);
  expect(screen.getByTestId('focus-' + id)).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'Settings sync' })).toHaveAttribute('aria-pressed', 'false');
});

test('C016 five mixed panes keep settings local off and link only visibility without refetch', async () => {
  saveLocal('workspace-current', { layoutId: 'five-stack', symbols: ['SPY', 'QQQ', 'IWM', 'DIA', 'TLT'], focusedIndex: 4 });
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(5));
  const volume = pane => within(pane).getByLabelText('Toggle volume pane');
  const first = slots()[0];
  await act(async () => {
    fireEvent.click(within(first).getByRole('button', { name: 'Chart tools' }));
    fireEvent.click(volume(first));
  });
  expect(volume(first)).not.toBeChecked();
  slots().slice(1).forEach(pane => expect(volume(pane)).toBeChecked());
  // The recorded-scope fixture also schedules one existing attribute read per
  // chart after150ms. Finish initial mount before counting visibility traffic.
  await waitFor(() => expect(require('axios').get.mock.calls.filter(call => String(call[0]).includes('/solstice/attribute/'))).toHaveLength(5));
  const reads = require('axios').get.mock.calls.length;
  fireEvent.click(screen.getByRole('button', { name: 'Settings sync' }));
  await waitFor(() => slots().forEach(pane => expect(volume(pane)).toBeChecked()));
  // Enabling copies the live focused fifth pane's true setting, not pane0's false.
  expect(symbols()).toEqual(['SPY', 'QQQ', 'IWM', 'DIA', 'TLT']);
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 180)); });
  expect(require('axios').get.mock.calls).toHaveLength(reads);
});

test('C016 five-pane export/import and saved cycling retain focus and revoke previous callbacks', async () => {
  const layout = { layoutId: 'five-stack', symbols: ['SPY', 'QQQ', 'IWM', 'DIA', 'TLT'], focusedIndex: 4 };
  saveLocal('workspace-current', layout); saveLocal('five', layout);
  const contexts = [];
  render(<ChartWorkspace ticker="SPY" open useNew onChartContext={value => contexts.push(value)} />);
  await waitFor(() => expect(mockReadings.some(reading => reading.value.source === 'pane-4' && reading.value.scope)).toBe(true));
  const old = [...mockReadings].reverse().find(reading => reading.value.source === 'pane-4' && reading.value.scope);
  const writeText = jest.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  fireEvent.click(screen.getByTestId('layouts-panel').querySelector('summary'));
  await act(async () => { fireEvent.click(screen.getByTestId('layout-export')); });
  const exported = JSON.parse(writeText.mock.calls[0][0]);
  expect(exported.layoutId).toBe('five-stack'); expect(exported.focusedIndex).toBe(4);
  expect(exported.symbols).toEqual(layout.symbols);
  fireEvent.click(screen.getByTestId('layout-single'));
  await act(async () => { fireEvent.change(screen.getByTestId('layout-import'), { target: { files: [new File([JSON.stringify(exported)], 'five.json', { type: 'application/json' })] } }); });
  await waitFor(() => expect(screen.getByTestId('focus-pane-4')).toHaveAttribute('aria-pressed', 'true'));
  await waitFor(() => expect(contexts[contexts.length - 1]?.descriptor.status).toBe('bound'));
  const count = contexts.length;
  await act(async () => { old.deliver(old.value); });
  expect(contexts).toHaveLength(count);
  fireEvent.click(screen.getByTestId('layout-single'));
  await act(async () => { fireEvent.click(screen.getByTestId('layout-cycle')); });
  await waitFor(() => expect(screen.getByTestId('focus-pane-4')).toHaveAttribute('aria-pressed', 'true'));
  expect(symbols()).toEqual(layout.symbols);
});

test('C016 default-off incumbent follows the host and closed five-pane workspace starts no reads', async () => {
  const view = render(<ChartWorkspace ticker="SPY" open />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(1));
  expect(screen.queryByTestId('pane-layout')).not.toBeInTheDocument();
  view.rerender(<ChartWorkspace ticker="QQQ" open />);
  await waitFor(() => expect(screen.getByRole('region', { name: 'QQQ candle chart' })).toBeInTheDocument());
  view.unmount();
  saveLocal('workspace-current', { layoutId: 'five-stack', symbols: ['SPY', 'QQQ', 'IWM', 'DIA', 'TLT'], focusedIndex: 4 });
  require('axios').get.mockClear();
  render(<ChartWorkspace ticker="SPY" open={false} useNew />);
  await waitFor(() => expect(screen.getByTestId('pane-layout')).toHaveAttribute('data-panes', '5'));
  await settle();
  expect(require('axios').get.mock.calls).toHaveLength(0);
});
