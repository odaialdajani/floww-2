/** @jest-environment jsdom */
import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import AskLodestar, {admissionBlock,STARTERS} from './AskLodestar';
import AgentProvider from '../../agent/AgentProvider';
import {publishScreenContext} from '../../agent/useScreenContext';
import {rangeSelectionContext} from '../../lib/rangeAnalytics';
import rangeComplete from '../../fixtures/integration/range-analytics.v1/complete.json';
import rangePartial from '../../fixtures/integration/range-analytics.v1/partial.json';
beforeAll(()=>{Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true});});
beforeEach(()=>{global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).endsWith('/session')?{}
 :String(url).endsWith('/ask')?{turn_id:'range-menu-turn'}:{turn_id:'range-menu-turn',status:'completed',ticker:'SPY',text:'Stored research only',contract:null,executable:false}}));});

test("live raw context is admitted", () => {
  expect(admissionBlock({ context: { ticker: "SPY" }, overlayMetric: "raw", displayMode: "live" })).toBeNull();
});

test("replay stays unavailable with an explicit reason", () => {
  expect(admissionBlock({ context: { ticker: "SPY" }, overlayMetric: "raw", displayMode: "replay" }))
    .toMatch(/recorded-snapshot resolution|return to Live/);
});

test("price-history stays unavailable with an explicit reason", () => {
  expect(admissionBlock({ context: { ticker: "SPY" }, overlayMetric: "raw", displayMode: "price-history" }))
    .toMatch(/price-history/);
});

test("adjusted overlays stay unavailable with an explicit reason", () => {
  for (const basis of ["delta", "session_delta_volume", "activity"]) {
    const reason = admissionBlock({ context: { ticker: "SPY" }, overlayMetric: basis, displayMode: "live" });
    expect(reason).toMatch(/Raw OI|adjusted/i);
  }
});

const complete = { contextVersion: 2, page: "heatseeker", ticker: "SPY", snapshotId: "snap1",
  mapQuery: { expiries: 4 }, mapVersion: "2026-10-01T14:00:00Z", provider: "fixture", formula: "gex.v2",
  metric: "gex", overlayMetric: "delta", displayMode: "live", activePane: "delta" };

test("verified adjusted selector is admitted, with server-owned numerical resolution", () => {
  expect(admissionBlock({ context: complete, overlayMetric: "delta", displayMode: "live" })).toBeNull();
});

test("replay admission requires a complete recorded identity and rejects changed selection", () => {
  const replay = { ...complete, displayMode: "replay" };
  expect(admissionBlock({ context: replay, overlayMetric: "delta", displayMode: "replay" })).toBeNull();
  expect(admissionBlock({ context: { ...replay, mapQuery: null }, overlayMetric: "delta", displayMode: "replay" })).toMatch(/recorded/i);
  expect(admissionBlock({ context: replay, overlayMetric: "raw", displayMode: "replay" })).toMatch(/selection|basis/i);
});

test("unsupported window and exact-contract contexts remain explicitly unavailable", () => {
  expect(admissionBlock({ context: { ...complete, overlayMetric: "window" }, overlayMetric: "window", displayMode: "live" })).toMatch(/unavailable|unsupported/i);
  expect(admissionBlock({ context: { ...complete, selectedContract: { osi: "X" } }, overlayMetric: "delta", displayMode: "live" })).toMatch(/contract/i);
});

test("window admission requires the owning recorded baseline and declared interval", () => {
  const window = { ...complete, overlayMetric: "window", windowBaselineId: "prior", windowInterval: { start: "2026-10-01T13:59:00Z", end: "2026-10-01T14:00:00Z" } };
  expect(admissionBlock({ context: window, overlayMetric: "window", displayMode: "live" })).toBeNull();
  expect(admissionBlock({ context: { ...window, windowBaselineId: null }, overlayMetric: "window", displayMode: "live" })).toMatch(/unavailable|baseline/i);
  expect(admissionBlock({ context: { ...window, windowInterval: null }, overlayMetric: "window", displayMode: "live" })).toMatch(/unavailable|interval/i);
  expect(admissionBlock({ context: { ...window, windowBaselineId: "snap1" }, overlayMetric: "window", displayMode: "live" })).toMatch(/unavailable|baseline/i);
});

test.each(["vex", "charm"])("%s replay requires a recorded metric-envelope selector", (metric) => {
 const context={...complete,metric,overlayMetric:"raw",displayMode:"replay",recordedMetricVersion:"metric-record.v1"};
 expect(admissionBlock({context,overlayMetric:"raw",displayMode:"replay"})).toBeNull();
 expect(admissionBlock({context:{...context,recordedMetricVersion:null},overlayMetric:"raw",displayMode:"replay"})).toMatch(/unavailable|recorded/i);
});

test("missing published selection stays unavailable", () => {
  expect(admissionBlock({ context: {}, overlayMetric: "raw", displayMode: "live" }))
    .toMatch(/No published selection/);
});

const storedRangeContext = (fixture=rangeComplete,metric='raw_oi') => rangeSelectionContext(
 fixture,metric,{strike:'590',expiry:'2026-10-26'},'replay');
test.each(['raw_oi','delta_weighted','volume'])('range %s admission is checked before legacy overlay guards',metric=>{
 const context=storedRangeContext(rangePartial,metric);
 expect(admissionBlock({context,overlayMetric:metric,displayMode:'range-replay'})).toBeNull();
 expect(admissionBlock({context,overlayMetric:'raw',displayMode:'range-replay'})).toMatch(/RANGE_RESEARCH_UNAVAILABLE/);
 expect(admissionBlock({context,overlayMetric:metric,displayMode:'live'})).toMatch(/RANGE_RESEARCH_UNAVAILABLE/);
});
test('range recorded-cell starters remain explicit and use the same agent transport and canonical horizon',async()=>{
 const context=storedRangeContext();publishScreenContext(context);
 const starters=['What does this recorded cell show?','Which recorded inputs are unknown?'];
 render(<AgentProvider><AskLodestar overlayMetric="raw_oi" displayMode="range-replay" starters={starters}
  subject="recorded SPY cell" testId="range-ask"/></AgentProvider>);
 expect(global.fetch).not.toHaveBeenCalled();
 expect(screen.getByTestId('range-ask-range-disclosure')).toHaveTextContent(/research only.*pending/i);
 expect(screen.getByTestId('range-ask-range-disclosure')).toHaveTextContent(/native draft/i);
 fireEvent.click(screen.getByTestId('range-ask-btn'));expect(global.fetch).not.toHaveBeenCalled();
 expect(screen.getAllByRole('menuitem').map(node=>node.textContent)).toEqual(starters);
 fireEvent.click(screen.getByTestId('range-ask-q-0'));
 await waitFor(()=>expect(global.fetch.mock.calls.some(([url])=>String(url).endsWith('/ask'))).toBe(true));
 const payload=JSON.parse(global.fetch.mock.calls.find(([url])=>String(url).endsWith('/ask'))[1].body);
 expect(payload.question).toBe('What does this recorded cell show? (recorded SPY cell)');
 expect(payload.horizon).toBe('range:14:60');expect(payload.screen).toEqual(context);
 expect(payload.screen.selectedContract).toBeNull();expect(payload.screen.selectedWall).toBeNull();
 const calls=global.fetch.mock.calls.length;
 act(()=>publishScreenContext({...context,selectedStrike:null,selectedExpiry:null}));
 expect(global.fetch).toHaveBeenCalledTimes(calls);
});
test.each([
 ['live',c=>{c.displayMode='range-live';}],
 ['mismatched identity',c=>{c.snapshotId=rangePartial.record_id;}],
 ['unavailable section',c=>{c.rangeStatus='unavailable';}],
 ['window',c=>{c.rangeMetric='window';c.overlayMetric='window';c.rangeBasis='VOLUME_WINDOW';c.rangeStatus='unavailable';}],
 ['invented wall',c=>{c.selectedWall={id:'wall'};}],
 ['invented contract',c=>{c.selectedContract={osi:'fake'};}],
 ['missing selection',c=>{c.selectedStrike=null;c.selectedExpiry=null;}],
])('range menu blocks %s before any session, fallback or model request',async(_,change)=>{
 const context=storedRangeContext();change(context);publishScreenContext(context);
 render(<AgentProvider><AskLodestar overlayMetric={context.overlayMetric} displayMode={context.displayMode}/></AgentProvider>);
 fireEvent.click(screen.getByTestId('ask-lodestar-btn'));fireEvent.click(screen.getByTestId('ask-lodestar-q-0'));
 expect(screen.getByTestId('ask-lodestar-note')).toHaveTextContent('RANGE_RESEARCH_UNAVAILABLE');
 expect(global.fetch).not.toHaveBeenCalled();
});
test('malformed range mode refuses before fetch without crashing under legacy props',()=>{
 const context=storedRangeContext();context.displayMode={invalid:true};publishScreenContext(context);
 render(<AgentProvider><AskLodestar/></AgentProvider>);
 fireEvent.click(screen.getByTestId('ask-lodestar-btn'));fireEvent.click(screen.getByTestId('ask-lodestar-q-0'));
 expect(screen.getByTestId('ask-lodestar-note')).toHaveTextContent('RANGE_RESEARCH_UNAVAILABLE');
 expect(global.fetch).not.toHaveBeenCalled();
});
test('resolved exact-contract legacy selectors still require and preserve their authoritative drawer identity',()=>{
 const context={...complete,selectedStrike:600,selectedExpiry:'2026-10-09',mapStrikes:[590,600],mapExpiries:['2026-10-09'],
  contractResolution:'resolved',selectedContract:{osi:'SPY261009C00600000',strike:600,expiry:'2026-10-09',type:'call'}};
 expect(admissionBlock({context,overlayMetric:'delta',displayMode:'live'})).toBeNull();
 expect(admissionBlock({context:{...context,contractResolution:'unresolved'},overlayMetric:'delta',displayMode:'live'})).toMatch(/contract/i);
});
test('default wall starters and their test IDs are preserved for legacy screens',()=>{
 publishScreenContext({ticker:'SPY',page:'heatseeker',overlayMetric:'raw',displayMode:'live'});
 render(<AgentProvider><AskLodestar/></AgentProvider>);
 fireEvent.click(screen.getByTestId('ask-lodestar-btn'));
 STARTERS.forEach((question,index)=>expect(screen.getByTestId(`ask-lodestar-q-${index}`)).toHaveTextContent(question));
 expect(screen.queryByTestId('ask-lodestar-range-disclosure')).not.toBeInTheDocument();
 expect(global.fetch).not.toHaveBeenCalled();
});
