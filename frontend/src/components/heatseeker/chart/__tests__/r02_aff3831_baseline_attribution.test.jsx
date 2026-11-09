import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';
import { _clear, saveLocal } from '../persistence/layoutStore';

jest.setTimeout(15000);
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const mockReadings = [];
const mockFocusedProps = [];
let mockFrameAdvance = 0;
jest.mock('../../PriceNodeHistory', () => {
  const React = require('react');
  const Actual = jest.requireActual('../../PriceNodeHistory').default;
  return { __esModule: true, default: function ObservedActualHistory(props) {
    if (props.onChartReading) mockFocusedProps.push(props);
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
  _clear(); localStorage.clear(); mockReadings.length = 0; mockFocusedProps.length = 0; mockFrameAdvance = 0;
  require('axios').get.mockReset();
  require('axios').get.mockImplementation(async (url, config) => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] || 'SPY';
    const scope = config?.params?.query_key || ticker + ':scope';
    return { data: { ticker, query_key: scope, scopes: [scope],
      frames: frames.map(frame => ({ ...frame, time: new Date(Date.parse(frame.time) + mockFrameAdvance * 1000).toISOString() })), candles_with_recorded_nodes: 2, node_status: 'available' } };
  });
});
afterEach(() => { cleanup(); _clear(); });

test('observe host ticker rerender while the second unlike-symbol real pane owns focus', async () => {
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
  console.log('C016_HOST_TICKER=' + JSON.stringify({ host: 'IWM', focused: 1, actualPaneSymbols: symbols(), newRequests: requests }));
  expect(symbols()).toEqual(['SPY', 'IWM']);
  expect(requests.some(url => url.includes('price-history/IWM'))).toBe(true);
  expect(requests.some(url => url.includes('price-history/SPY'))).toBe(false);
});

test('observe old actual chart-reading delivery after remove and re-add of the same focused slot', async () => {
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
  console.log('C016_READD_READING=' + JSON.stringify({ old: old.value, replacement: current.value, deliveredOldCursor: late.cursor, acceptedContext: last }));
  expect(current.value.epoch).not.toBe(old.value.epoch);
  expect(last.descriptor.status).toBe('bound');
  expect(last.descriptor.cursor).toBe(current.value.cursor);
});

test('five saved unlike panes restore fifth focus, false visibility and focused host retarget only', async () => {
  const names = ['SPY', 'QQQ', 'IWM', 'DIA', 'TLT'];
  saveLocal('workspace-current', { layoutId: 'five-stack', symbols: names, focusedIndex: 4,
    settingsSync: false, paneStates: { 'pane-4': { interval: 5, session: 'all', settings: { volume: false } } } });
  const view = render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(5));
  expect(symbols()).toEqual(names);
  expect(screen.getByTestId('focus-pane-4')).toHaveAttribute('aria-pressed', 'true');
  expect(slots()[4].querySelector('[aria-label="Toggle volume pane"]')).not.toBeChecked();
  await waitFor(() => expect(JSON.parse(localStorage.getItem('floww.chart.layout.workspace-current')).focusedIndex).toBe(4));
  view.unmount();
  const reopened = render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(() => expect(screen.getAllByTestId('recorded-price-chart')).toHaveLength(5));
  expect(symbols()).toEqual(names);
  expect(screen.getByTestId('focus-pane-4')).toHaveAttribute('aria-pressed', 'true');
  expect(slots()[4].querySelector('[aria-label="Toggle volume pane"]')).not.toBeChecked();
  await settle(); const before = require('axios').get.mock.calls.length;
  reopened.rerender(<ChartWorkspace ticker="XLK" open useNew />);
  await waitFor(() => expect(symbols()).toEqual(['SPY', 'QQQ', 'IWM', 'DIA', 'XLK']));
  const requests = require('axios').get.mock.calls.slice(before).map(call => String(call[0]));
  expect(requests.some(url => url.includes('price-history/XLK'))).toBe(true);
  expect(requests.some(url => /price-history\/(SPY|QQQ|IWM|DIA)$/.test(url))).toBe(false);
  console.log('AFF_FIVE_RESTORE=' + JSON.stringify({ symbols: symbols(), focus: 4, volumeFalse: true, requests }));
});

test('retained callbacks refuse after focus away/back, closed state and complete unmount', async () => {
  const contexts = []; const onContext = value => contexts.push(value);
  const view = render(<ChartWorkspace ticker="SPY" open useNew onChartContext={onContext} />);
  await waitFor(() => expect(mockReadings.some(r => r.value.scope)).toBe(true));
  const old = mockReadings[mockReadings.length - 1];
  const props = mockFocusedProps[mockFocusedProps.length - 1];
  fireEvent.click(screen.getByTestId('layout-split'));
  fireEvent.click(screen.getByTestId('focus-pane-1'));
  fireEvent.click(screen.getByTestId('focus-pane-0'));
  await settle(); const count = contexts.length;
  await act(async () => {
    old.deliver(old.value);
    props.onQuality({ status: 'stale', sourceTime: 'STALE_OLD_OWNER', coverage: 'STALE_OLD_OWNER' });
    props.onEnvelopes({ owner: { scope: 'STALE_SCOPE' } });
    props.onReplayState({ source: 'pane-0', scope: 'STALE_SCOPE', cursor: 0, visible: [] });
    props.onReplayController({ toggle: () => { throw new Error('dead controller used'); } });
  });
  expect(contexts).toHaveLength(count);
  expect(screen.queryByText(/STALE_OLD_OWNER/)).not.toBeInTheDocument();
  const closing = [...mockReadings].reverse().find(r => r.value.source === "pane-0" && r.value.scope);
  const closingProps = mockFocusedProps[mockFocusedProps.length - 1];
  view.rerender(<ChartWorkspace ticker="SPY" open={false} useNew onChartContext={onContext} />);
  await settle(); const closed = contexts.length;
  await act(async () => { old.deliver(old.value); });
  expect(contexts).toHaveLength(closed);
  mockFrameAdvance = 3600;
  view.rerender(<ChartWorkspace ticker="SPY" open useNew onChartContext={onContext} />);
  await waitFor(() => expect(contexts[contexts.length - 1]?.descriptor.cursor).toBe(closing.value.cursor + 3600));
  const current = contexts[contexts.length - 1];
  await act(async () => {
    closing.deliver(closing.value);
    closingProps.onQuality({ status: 'stale', sourceTime: 'OLD_BEFORE_CLOSE', coverage: 'OLD_BEFORE_CLOSE' });
  });
  const after = contexts[contexts.length - 1];
  const staleQualityVisible = !!screen.queryByText(/Latest reading OLD_BEFORE_CLOSE/);
  console.log('AFF_OPEN_REOPEN=' + JSON.stringify({ old: closing.value, current, after, staleQualityVisible }));
  view.unmount(); const dead = contexts.length;
  await act(async () => { closing.deliver(closing.value); });
  expect(contexts).toHaveLength(dead);
  expect(after.descriptor.cursor).toBe(current.descriptor.cursor);
  expect(staleQualityVisible).toBe(false);
});

test('retained same-pane old-scope reading cannot replace the newer actual scope', async () => {
  const contexts = []; const onContext = value => contexts.push(value);
  const view = render(<ChartWorkspace ticker="SPY" forcedScope="SPY:old" open useNew onChartContext={onContext} />);
  await waitFor(() => expect(contexts[contexts.length - 1]?.descriptor.scope).toBe('SPY:old'));
  const old = [...mockReadings].reverse().find(r => r.value.scope === 'SPY:old');
  view.rerender(<ChartWorkspace ticker="SPY" forcedScope="SPY:new" open useNew onChartContext={onContext} />);
  await waitFor(() => expect(contexts[contexts.length - 1]?.descriptor.scope).toBe('SPY:new'));
  const current = contexts[contexts.length - 1];
  await act(async () => { old.deliver(old.value); });
  const after = contexts[contexts.length - 1];
  console.log('AFF_RETAINED_SCOPE=' + JSON.stringify({ old: old.value, current, after }));
  expect(after.descriptor.scope).toBe('SPY:new');
});

test('host ticker and mismatched explicit envelopes remain visibly refused', async () => {
  const envelope = { status: 'available', instrument: { ticker: 'QQQ' }, scope: 'SPY:scope', cursor: 1791297000, bounds: { low: 99, high: 103 }, coverage: { complete: true, covered: 2, expected_total: 2 }, approximation: 'bar-resolution', certification: { basis: 'synthetic' } };
  const view = render(<ChartWorkspace ticker="SPY" open useNew ibEnvelope={envelope} />);
  await waitFor(() => expect(screen.getByTestId('profile-ib')).toHaveTextContent('envelope instrument does not match focused chart'));
  view.rerender(<ChartWorkspace ticker="SPY" open useNew ibEnvelope={{ ...envelope, instrument: { ticker: 'SPY' }, scope: 'OTHER:scope' }} />);
  await waitFor(() => expect(screen.getByTestId('profile-ib')).toHaveTextContent('envelope scope does not match focused chart'));
  view.rerender(<ChartWorkspace ticker="IWM" open useNew ibEnvelope={{ ...envelope, instrument: { ticker: 'SPY' } }} />);
  await waitFor(() => expect(screen.getByTestId('profile-ib')).toHaveTextContent('envelope instrument does not match focused chart'));
});
