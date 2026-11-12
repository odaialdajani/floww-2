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