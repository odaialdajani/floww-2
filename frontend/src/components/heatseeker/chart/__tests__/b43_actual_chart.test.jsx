import React from 'react';
import {render, screen, waitFor} from '@testing-library/react';
import axios from 'axios';
import PriceNodeHistory from '../../PriceNodeHistory';
import {geometryFor, viewportFor} from '../drawings/drawingReducer';
import {composeExportSvg, captureChartSvgs} from '../ChartExport';
import ChartWorkspace from '../ChartWorkspace';

jest.mock('axios', () => ({get: jest.fn(), post: jest.fn()}));
const frames = [
  {time:'2026-10-21T13:30:00Z',open:100,high:102,low:99,close:101,volume:100},
  {time:'2026-10-21T14:00:00Z',open:101,high:104,low:100,close:103,volume:150},
];
test('drawing anchors render inside the actual candle SVG, never on a second canvas', async () => {
  axios.get.mockResolvedValue({data:{ticker:'SPY',frames,scopes:[]}});
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getAllByTestId('price-candle')).toHaveLength(2));
  const layer=screen.getByTestId('drawing-layer');
  expect(layer.tagName.toLowerCase()).toBe('g');
  expect(layer.closest('svg')).toHaveAttribute('aria-label','SPY recorded price candles');
  expect(layer).toHaveAttribute('data-domain','renderer');
});
test('one-anchor horizontal and vertical tools span the actual plot', () => {
  const vp=viewportFor(frames,800,480), a={t:Date.parse(frames[0].time),p:101};
  expect(geometryFor('horizontal',[a],vp).points).toEqual([{x:0,y:expect.any(Number)},{x:800,y:expect.any(Number)}]);
  expect(geometryFor('vertical',[a],vp).points).toEqual([{x:expect.any(Number),y:0},{x:expect.any(Number),y:480}]);
});
test('composition export includes real candle and volume primitives and refuses empty capture', () => {
  const host=document.createElement('div');
  host.innerHTML='<div class="pane-slot"><div class="recorded-price-chart"><div class="recorded-chart-surface"><svg viewBox="0 0 800 480"><g data-testid="price-candle"><rect x="20" y="30" width="4" height="50"/></g></svg></div><svg class="recorded-volume-pane" viewBox="0 0 800 60"><rect data-testid="real-volume" x="20" y="10" width="4" height="40"/></svg></div></div>';
  const charts=captureChartSvgs(host);
  const svg=composeExportSvg({panes:[{symbol:'SPY',focused:true}],charts});
  const parsed=new DOMParser().parseFromString(svg,'image/svg+xml');
  expect(parsed.querySelector('parsererror')).toBeNull();
  expect(parsed.querySelector('[data-testid="price-candle"] rect').getAttribute('height')).toBe('50');
  expect(parsed.querySelector('[data-testid="real-volume"]')).toBeTruthy();
  expect(() => composeExportSvg({panes:[{symbol:'SPY'}],charts:[]})).toThrow(/no rendered charts/i);
  expect(() => composeExportSvg({panes:[{symbol:'SPY'},{symbol:'QQQ'}],charts:[charts[0],[]]})).toThrow(/pane.*unavailable/i);
});

test('fetch-time opening range is refused after scrubbing to an earlier cursor', async () => {
  const envelope={status:'available',ticker:'SPY',cursor:Date.parse(frames[1].time)/1000,
    instrument:{ticker:'SPY'},bounds:{low:99,high:104},coverage:{covered:2,expected_total:2,complete:true},
    approximation:'bar-resolution',certification:{basis:'recorded'}};
  axios.get.mockResolvedValue({data:{ticker:'SPY',frames,scopes:[],envelopes:{initial_balance:envelope}}});
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(()=>expect(screen.getByTestId('profile-ib')).toHaveTextContent('99–104'));
  const {fireEvent,act}=require('@testing-library/react');
  await act(async()=>fireEvent.change(screen.getByLabelText('Replay position'),{target:{value:'0'}}));
  await waitFor(()=>expect(screen.getByTestId('profile-ib')).not.toHaveTextContent('99–104'));
  expect(screen.getByTestId('profile-ib')).toHaveTextContent('cursor');
});

test('actual chart reports use millisecond windows but transport context in server seconds', async () => {
  axios.get.mockResolvedValue({data:{ticker:'SPY',frames,query_key:'owning-scope',scopes:[]}});
  const onContext=jest.fn(),onReplay=jest.fn();
  const first=render(<PriceNodeHistory ticker="SPY" open onReplayState={onReplay} />);
  await waitFor(()=>expect(onReplay.mock.calls.some(([r])=>r?.bar)).toBe(true));
  const report=onReplay.mock.calls.filter(([r])=>r?.bar).at(-1)[0];
  expect(report.bar.bucketEnd-report.bar.bucketStart).toBe(1800000);
  first.unmount();
  render(<ChartWorkspace ticker="SPY" open useNew onChartContext={onContext} />);
  await waitFor(()=>expect(onContext.mock.calls.some(([c])=>c?.descriptor?.status==='bound')).toBe(true));
  const descriptor=onContext.mock.calls.filter(([c])=>c?.descriptor?.status==='bound').at(-1)[0].descriptor;
  expect(descriptor.cursor).toBe(Date.parse(frames[1].time)/1000);
});

test('workspace replay starts the real candle transport, not only a banner', async () => {
  axios.get.mockResolvedValue({data:{ticker:'SPY',frames,query_key:'owning-scope',scopes:[]}});
  const {fireEvent,act}=require('@testing-library/react');
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(()=>expect(screen.getByLabelText('Replay position')).toHaveValue('1'));
  await act(async()=>fireEvent.click(screen.getByTestId('replay-touch')));
  expect(screen.getByLabelText('Replay position')).toHaveValue('0');
  expect(screen.getByLabelText('Replay position').closest('.price-history-replay').querySelector('button')).toHaveTextContent('Pause replay');
});

test.each([undefined,'wrong-scope'])('explicit available envelopes refuse missing or foreign scope (%s)', async scope => {
  axios.get.mockResolvedValue({data:{ticker:'SPY',frames,query_key:'owning-scope',scopes:[]}});
  const envelope={status:'available',instrument:{ticker:'SPY'},cursor:Date.parse(frames[1].time)/1000,
    ...(scope===undefined?{}:{scope}),bounds:{low:99,high:104},coverage:{covered:2,expected_total:2,complete:true}};
  render(<ChartWorkspace ticker="SPY" open useNew ibEnvelope={envelope} />);
  await waitFor(()=>expect(screen.getAllByTestId('price-candle')).toHaveLength(2));
  await waitFor(()=>expect(screen.getByTestId('profile-ib')).toHaveTextContent('scope'));
  expect(screen.getByTestId('profile-ib')).not.toHaveTextContent('99–104');
});

test('the real chart comes before folded flow/profile diagnostics in document order', async () => {
  axios.get.mockResolvedValue({data:{ticker:'SPY',frames,query_key:'owning-scope',scopes:[]}});
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await waitFor(()=>expect(screen.getByTestId('profile-ib')).toBeInTheDocument());
  const evidence=screen.getByTestId('workspace-evidence');
  expect(evidence).not.toHaveAttribute('open');
  expect(screen.getByTestId('recorded-price-chart').compareDocumentPosition(evidence)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
