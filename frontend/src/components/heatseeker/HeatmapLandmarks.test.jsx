import React from 'react';
import {render, screen} from '@testing-library/react';
import '@testing-library/jest-dom';
import HeatmapLandmarks, {readLandmarks} from './HeatmapLandmarks';
import SkylitHeatmapGrid from './SkylitHeatmapGrid';

const wall = (id, low, high = low) => ({wall_id:id,low,high,members:[low,high]});
const packet = () => ({ticker:'SPY',spot:100,exposure_basis:'OI',snapshotId:'record-1',asof:'2026-10-14T15:00:00Z',data_source:'fixture',
  grid:{expiries:['2026-10-16'],strikes:[90,95,99,100,101,105,110],grid:{'2026-10-16':{90:2,95:-3,99:1,100:2,101:3,105:4,110:5}}},
  strikes:[{strike:95,call_gex:10,put_gex:50},{strike:100,call_gex:20,put_gex:30},{strike:105,call_gex:70,put_gex:10},
    ...[90,99,101,110].map(strike=>({strike,call_gex:0,put_gex:0}))],
  metrics:{walls:[wall('far-high',110),wall('below',95),wall('inside',99,101),wall('above',105),wall('far-low',90)]}});

test('uses nearest structural zones in price order, not largest exposure or array order', () => {
  const read = readLandmarks(packet());
  expect(read.below.map(w=>w.low)).toEqual([95,90]);
  expect(read.above.map(w=>w.low)).toEqual([105,110]);
  expect(read.inside.low).toBe(99);
  expect(read.inside.high).toBe(101);
  expect(read.call.strike).toBe(105);
  expect(read.put.strike).toBe(95);
});

test('shows support/resistance watches and call/put concentrations without promising a direction', () => {
  render(<HeatmapLandmarks data={packet()} />);
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('Support watch');
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('95.00 → 90.00');
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('Resistance watch');
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('105.00 → 110.00');
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('Call wall');
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('Put wall');
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('not a forecast or entry signal');
});

test('does not call the most negative net strike a put wall without a measured put component', () => {
  const data = packet();
  data.strikes = [{strike:95,gex:-999999}, {strike:105,gex:888888}];
  expect(readLandmarks(data).call).toBeNull();
  expect(readLandmarks(data).put).toBeNull();
});

test.each([null,undefined,NaN,Infinity,true,'', '100'])('unknown or malformed map spot %p does not create support or resistance', spot => {
  const read = readLandmarks({...packet(),spot});
  expect(read.below).toEqual([]);
  expect(read.above).toEqual([]);
  expect(read.inside).toBeNull();
});

test.each([undefined, 'VOLUME_SCALP'])('unknown or volume basis %p never becomes a raw OI wall', exposure_basis => {
  const read = readLandmarks({...packet(),exposure_basis});
  expect(read.call).toBeNull();
  expect(read.put).toBeNull();
  expect(read.above).toEqual([]);
});

test('source-reported missing OI keeps the concentration ranking explicitly partial', () => {
  const data = packet();
  data.metrics.raw_missing_oi = 1;
  expect(readLandmarks(data).call.partial).toBe(true);
  expect(readLandmarks(data).put.partial).toBe(true);
});

test('one missing side stays unknown; same-side zone is never substituted', () => {
  const read = readLandmarks({...packet(),metrics:{walls:[wall('above',105)]}});
  expect(read.below).toEqual([]);
  expect(read.above).toHaveLength(1);
});

test('missing side values disclose partial ranking, real zero is not missing, invalid duplicates refuse', () => {
  const data = packet();
  data.strikes[0].call_gex = null;
  expect(readLandmarks(data).call.partial).toBe(true);
  data.strikes[0].call_gex = 0;
  expect(readLandmarks(data).call.partial).toBe(false);
  data.strikes.push({...data.strikes[0]});
  expect(readLandmarks(data).call).toBeNull();
});

test('recorded packet uses its own spot and levels, never another live quote or current data', () => {
  render(<HeatmapLandmarks data={{...packet(),replay:true,spot:92}} />);
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('Recorded map · $92.00');
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('Market time unknown');
  expect(screen.getByLabelText('Raw OI landmarks')).toHaveTextContent('Snapshot 2026-10-14T15:00:00Z');
});

test('paired panes can share one landmark summary while retaining their own row labels', () => {
  const {container} = render(<SkylitHeatmapGrid data={packet()} ticker="SPY" spot={100} showLandmarks={false} />);
  expect(screen.queryByLabelText('Raw OI landmarks')).toBeNull();
  expect(container.querySelector('[data-strike="105"] .heatmap-row-landmark')).toHaveTextContent('Call');
});

test('real grid marks call/put and nearest level rows without changing cell values or requests', () => {
  const {container} = render(<SkylitHeatmapGrid data={packet()} ticker="SPY" spot={100} />);
  expect(screen.getByLabelText('Raw OI landmarks')).toBeVisible();
  expect(container.querySelector('[data-strike="105"] .heatmap-row-landmark')).toHaveTextContent('Call');
  expect(container.querySelector('[data-strike="95"] .heatmap-row-landmark')).toHaveTextContent('Put');
  expect(screen.getByRole('gridcell',{name:/105 by 2026-10-16, value/})).toHaveTextContent('$0.0K');
});
