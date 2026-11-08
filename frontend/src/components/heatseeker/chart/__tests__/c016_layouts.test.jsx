import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    const onReading = React.useCallback(value => {
      if (value) mockReadings.push({ value, deliver: props.onChartReading });
      props.onChartReading?.(value);
    }, [props.onChartReading]);
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

