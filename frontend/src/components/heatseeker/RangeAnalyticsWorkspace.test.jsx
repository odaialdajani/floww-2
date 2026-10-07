import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import RangeAnalyticsWorkspace from './RangeAnalyticsWorkspace';
import useScreenContext from '../../agent/useScreenContext';
import AgentProvider from '../../agent/AgentProvider';
import SkylitDashboard from './SkylitDashboard';
jest.mock('axios');
import complete from '../../fixtures/integration/range-analytics.v1/complete.json';
import partial from '../../fixtures/integration/range-analytics.v1/partial.json';
const response = data => ({ok:true,json:async()=>data});
beforeAll(()=>{Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true});});
function Context(){const [context]=useScreenContext();return <output data-testid="range-context">{JSON.stringify(context)}</output>;}
beforeEach(()=>{global.fetch=jest.fn(async()=>response(complete));});

// Actual envelope fixtures with consumer transport wrappers; not producer/restart proof.
const storedRow=e=>({record_id:e.record_id,ticker:e.symbol,window:{min_dte:14,max_dte:60},asof_date:e.query.as_of_ny,received_at:e.clocks.received_at,recorded_at:'2026-10-05T14:00:00+00:00',status:e.status,digest:e.content_digest,integrity:'verified',synthetic:e.synthetic});
const index=()=>({version:'range-records.v1',status:'ok',filters:{ticker:'SPY',min_dte:14,max_dte:60,as_of:null,status:null},limit:50,offset:0,n_returned:2,rows:[storedRow(complete),storedRow(partial)]});
const replay=e=>({version:'range-records.v1',...storedRow(e),envelope:e});
const loadStored=async()=>{
 fireEvent.click(screen.getByRole('button',{name:'Range replay',exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await waitFor(()=>expect(screen.getByLabelText('Stored range record').options).toHaveLength(3));
};

test('owning stored range selection drives grid and shared context; Live clears without fetching current chains',async()=>{
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(partial):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:partial.record_id}});
 await screen.findByRole('grid',{name:'Raw OI GEX · strike by expiry'});
 expect(JSON.parse(screen.getByTestId('range-context').textContent)).toMatchObject({displayMode:'range-replay',snapshotId:partial.record_id});
 fireEvent.click(screen.getByRole('button',{name:/^590 · 2026-10-26/}));
 expect(JSON.parse(screen.getByTestId('range-context').textContent).selectedStrike).toBe(590);
 expect(screen.getByRole('button',{name:'Load analytical range'})).toBeDisabled();
 const calls=global.fetch.mock.calls.length;fireEvent.click(screen.getByRole('button',{name:'Live',exact:true}));
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();expect(global.fetch).toHaveBeenCalledTimes(calls);
 expect(JSON.parse(screen.getByTestId('range-context').textContent)).toMatchObject({displayMode:'range-live',snapshotId:null});
 expect(global.fetch.mock.calls.every(([url])=>String(url).includes('/solstice/price-paths/range-records'))).toBe(true);
});

test('a corrupt next frame clears the mounted grid and canonical record, never retains a mislabeled previous frame',async()=>{
 // v3 chronological order: complete loads first, so select IT and corrupt the
 // NEXT frame (partial) — the pre-v3 order had partial first and Next disabled.
 let corrupt=false;global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?corrupt?{version:'range-records.v1',status:'refused',reason:'DIGEST_MISMATCH'}:replay(complete):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);await loadStored();
 fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:complete.record_id}});await screen.findByRole('grid');
 corrupt=true;fireEvent.click(screen.getByRole('button',{name:'Next frame'}));await screen.findByText(/Stored range replay unavailable.*DIGEST_MISMATCH/);
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();expect(JSON.parse(screen.getByTestId('range-context').textContent).snapshotId).toBeNull();
});

test('query changes abort an in-flight stored frame and reject its late envelope',async()=>{
 let release;global.fetch.mockImplementation(async url=>String(url).includes('/range-records/')?await new Promise(resolve=>{release=resolve;}):response(index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);await loadStored();
 fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:partial.record_id}});
 const signal=global.fetch.mock.calls[1][1].signal;fireEvent.change(screen.getByLabelText('Minimum DTE'),{target:{value:'30'}});
 expect(signal.aborted).toBe(true);await act(async()=>release(response(replay(partial))));
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();expect(JSON.parse(screen.getByTestId('range-context').textContent).snapshotId).toBeNull();
});

test('stored selected cell asks the existing Lodestar route with its canonical record scope, never a native contract',async()=>{
 let asked;
 global.fetch.mockImplementation(async (url,options)=>{
  if(String(url).endsWith('/session'))return response({});
  if(String(url).endsWith('/ask')){asked=JSON.parse(options.body);return response({turn_id:'range-ui-turn'});}
  if(String(url).includes('/agent/turn/'))return response({turn_id:'range-ui-turn',status:'completed',ticker:'SPY',answer:{context:asked.screen,facts:[],plan_draft:{contract:null,executable:false}}});
  return response(String(url).includes('/range-records/')?replay(partial):index());
 });
 render(<AgentProvider><RangeAnalyticsWorkspace ticker="SPY"/></AgentProvider>);await loadStored();
 fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:partial.record_id}});await screen.findByRole('grid');
 fireEvent.click(screen.getByRole('button',{name:/^590 · 2026-10-26/}));
 fireEvent.click(screen.getByTestId('range-ask-lodestar-btn'));fireEvent.click(screen.getByRole('menuitem',{name:'Explain the recorded cells'}));
 await waitFor(()=>expect(asked).toBeTruthy());
 expect(asked).toMatchObject({horizon:'range:14:60',screen:{displayMode:'range-replay',snapshotId:partial.record_id,rangeDigest:partial.content_digest,selectedStrike:590,selectedExpiry:'2026-10-26',selectedContract:null}});
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(1);
 expect(global.fetch.mock.calls.some(([url])=>String(url).includes('/heatmap/') || String(url).includes('/public/'))).toBe(false);
 await act(async()=>{});
});

test('stored replay mode reports pause ownership until deliberate Live exit',async()=>{
 const onReplayModeChange=jest.fn();global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(partial):index()));
 require('axios').get.mockResolvedValue({data:{rows:[],decisions:[],snapshots:[]}});
 render(<SkylitDashboard ticker="SPY" analyticalRangeOpen onReplayChange={onReplayModeChange}/>);
 fireEvent.click(screen.getByRole('button',{name:'Range replay',exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await waitFor(()=>expect(screen.getByLabelText('Stored range record').options).toHaveLength(3));
 fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:partial.record_id}});await screen.findByRole('grid');
 expect(onReplayModeChange.mock.calls.at(-1)).toEqual([true]);
 fireEvent.click(screen.getByRole('button',{name:'Live',exact:true}));
 expect(onReplayModeChange.mock.calls.at(-1)).toEqual([false]);
});

test('blank window is invalid instead of silently becoming zero DTE',async()=>{
 render(<RangeAnalyticsWorkspace ticker="SPY"/>);
 fireEvent.change(screen.getByLabelText('Minimum DTE'),{target:{value:''}});
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));
 await screen.findByText(/WINDOW_OUT_OF_RANGE/);
 expect(global.fetch).not.toHaveBeenCalled();
});
test('on-demand owning axes and metrics preserve nulls, clocks and research-only admission',async()=>{
 render(<RangeAnalyticsWorkspace ticker="SPY"/>);expect(global.fetch).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));
 await screen.findByRole('grid',{name:'Raw OI GEX · strike by expiry'});
 expect(String(global.fetch.mock.calls[0][0])).toContain('/heatmap/SPY/range-analytics?min_dte=14&max_dte=60&persist=false');
 expect(screen.getByText(/Chain event time unknown/)).toBeInTheDocument();
 expect(screen.getByText(/Research only/)).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Range metric'),{target:{value:'window'}});
 expect(screen.getByRole('status')).toHaveTextContent('HISTORY_NOT_YET_RECORDED');
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();
});
test('partial skipped expiry and stale provenance stay explicit, without replacement arithmetic',async()=>{
 global.fetch.mockResolvedValue(response(partial));render(<RangeAnalyticsWorkspace ticker="SPY"/>);
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));
 await screen.findByRole('grid');expect(screen.getByText(/Partial expiry coverage/)).toBeInTheDocument();
 expect(screen.getByText(`${partial.coverage.skipped[0].expiry} · reason ${partial.coverage.skipped[0].reason}`)).toBeInTheDocument();
});
test('symbol changes abort older range replies and cannot restore the previous selection',async()=>{
 let release;global.fetch.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
 const ui=render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));const signal=global.fetch.mock.calls[0][1].signal;
 ui.rerender(<><RangeAnalyticsWorkspace ticker="QQQ"/><Context/></>);expect(signal.aborted).toBe(true);
 await act(async()=>release(response(complete)));
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();expect(screen.getByTestId('range-context')).not.toHaveTextContent(complete.record_id);
});
test('basis and query changes invalidate the canonical selection without invoking a model',async()=>{
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));await screen.findByRole('grid');
 fireEvent.click(screen.getByRole('button',{name:/^590 · 2026-10-26/}));
 await waitFor(()=>expect(JSON.parse(screen.getByTestId('range-context').textContent).selectedStrike).toBe(590));
 fireEvent.change(screen.getByLabelText('Range metric'),{target:{value:'delta_weighted'}});
 expect(JSON.parse(screen.getByTestId('range-context').textContent).selectedStrike).toBeNull();
 fireEvent.change(screen.getByLabelText('Minimum DTE'),{target:{value:'30'}});
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();
 expect(JSON.parse(screen.getByTestId('range-context').textContent).snapshotId).toBeNull();
 expect(global.fetch).toHaveBeenCalledTimes(1);
});
test('price approach selector drives scenario text without any network call',async()=>{
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(partial):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:partial.record_id}});
 await screen.findByRole('grid');
 fireEvent.click(screen.getByRole('button',{name:/^590 · 2026-10-26/}));
 expect(screen.getByText(/No reaction measured yet/)).toBeInTheDocument();
 const calls=global.fetch.mock.calls.length;
 const raw=partial.grids.raw_oi.cells['2026-10-26']['590'];
 fireEvent.change(screen.getByLabelText('Price approach'),{target:{value:'above'}});
 if(typeof raw==='number'&&raw!==0){
  expect(screen.getByText(raw>0?/review bounce/:/review flush/)).toBeInTheDocument();
 }else{
  expect(screen.getByText(/direction unknown/)).toBeInTheDocument();
 }
 fireEvent.change(screen.getByLabelText('Price approach'),{target:{value:'below'}});
 if(typeof raw==='number'&&raw!==0){
  expect(screen.getByText(raw>0?/review rejection/:/review squeeze/)).toBeInTheDocument();
 }
 expect(global.fetch.mock.calls.length).toBe(calls);
});
test('handoff trace attaches wall context and declares the owner unselected',async()=>{
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(complete):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:complete.record_id}});
 await screen.findByRole('grid');
 expect(screen.getByText(/No cell selected — nothing attached/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/^590 · 2026-10-26/}));
 expect(screen.getByText(/Wall context attached · SPY · 590 USD · 2026-10-26/)).toBeInTheDocument();
 expect(screen.getByText(new RegExp(`Record ${complete.record_id}.*received`))).toBeInTheDocument();
 expect(screen.getByText(/Execution owner: unselected/)).toBeInTheDocument();
});
test('copy lodestar context writes the frozen record scope and nothing else',async()=>{
 const written=[];
 Object.defineProperty(navigator,'clipboard',{value:{writeText:jest.fn(async text=>{written.push(text);})},configurable:true});
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(complete):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 expect(screen.queryByRole('button',{name:'Copy Lodestar context'})).not.toBeInTheDocument();
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:complete.record_id}});
 await screen.findByRole('grid');
 expect(screen.getByRole('button',{name:'Copy Lodestar context'})).toBeEnabled();
 fireEvent.click(screen.getByRole('button',{name:/^590 · 2026-10-26/}));
 fireEvent.click(screen.getByRole('button',{name:'Copy Lodestar context'}));
 await screen.findByText('Context copied.');
 expect(written).toHaveLength(1);
 const payload=JSON.parse(written[0]);
 expect(payload).toMatchObject({kind:'range-lodestar-context',symbol:'SPY',record_id:complete.record_id,content_digest:complete.content_digest,metric:'raw_oi',replay:true});
 expect(payload.selection).toEqual({strike:'590',expiry:'2026-10-26'});
 expect(payload.note).toMatch(/not an execution permission/);
});
test('copy failure surfaces a status instead of throwing',async()=>{
 Object.defineProperty(navigator,'clipboard',{value:{writeText:jest.fn(async()=>{throw new Error('denied');})},configurable:true});
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(complete):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:complete.record_id}});
 await screen.findByRole('grid');
 fireEvent.click(screen.getByRole('button',{name:'Copy Lodestar context'}));
 await screen.findByText('Copy failed: clipboard unavailable.');
});
test('review trade opens a read-only summary and never touches order surfaces',async()=>{
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(complete):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 expect(screen.queryByRole('button',{name:'Review trade'})).not.toBeInTheDocument();
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:complete.record_id}});
 await screen.findByRole('grid');
 const calls=global.fetch.mock.calls.length;
 fireEvent.click(screen.getByRole('button',{name:'Review trade'}));
 expect(screen.getByText(/No cell selected\. Record/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/^590 · 2026-10-26/}));
 expect(screen.getByText(/Reviewing 590 USD · 2026-10-26/)).toBeInTheDocument();
 expect(screen.getByText(/Contract: RANGE_CONTRACT_UNAVAILABLE/)).toBeInTheDocument();
 expect(screen.getByText(/cannot place, approve, or route any order/)).toBeInTheDocument();
 expect(global.fetch.mock.calls.length).toBe(calls);
 expect(global.fetch.mock.calls.every(([url])=>String(url).includes('/solstice/price-paths/range-records'))).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Close trade review'}));
 expect(screen.queryByRole('region',{name:'Trade review'})).not.toBeInTheDocument();
});
test('compare toggle renders both bases side by side and exits cleanly without fetching',async()=>{
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(complete):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:complete.record_id}});
 await screen.findByRole('grid',{name:'Raw OI GEX · strike by expiry'});
 const calls=global.fetch.mock.calls.length;
 fireEvent.click(screen.getByRole('button',{name:'Compare Raw vs Adjusted'}));
 expect(screen.getByRole('grid',{name:/compare raw/})).toBeInTheDocument();
 expect(screen.getByRole('grid',{name:/compare adjusted/})).toBeInTheDocument();
 expect(global.fetch.mock.calls.length).toBe(calls);
 fireEvent.click(screen.getByRole('button',{name:'Exit compare'}));
 expect(screen.queryByRole('grid',{name:/compare/})).not.toBeInTheDocument();
 expect(screen.getByRole('grid',{name:'Raw OI GEX · strike by expiry'})).toBeInTheDocument();
});
test('right-pane selection syncs both panes and shows the derived delta honestly',async()=>{
 const {fmtK}=require('./SkylitHeatmapGrid');
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(complete):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:complete.record_id}});
 await screen.findByRole('grid',{name:'Raw OI GEX · strike by expiry'});
 fireEvent.click(screen.getByRole('button',{name:'Compare Raw vs Adjusted'}));
 const right=screen.getAllByRole('button',{name:/^590 · 2026-10-26/})[1];
 fireEvent.click(right);
 expect(JSON.parse(screen.getByTestId('range-context').textContent).selectedStrike).toBe(590);
 const raw=complete.grids.raw_oi.cells['2026-10-26']['590'],adj=complete.grids.delta_weighted.cells['2026-10-26']['590'],d=adj-raw;
 expect(screen.getByText(`Raw ${fmtK(raw)} · Adjusted ${fmtK(adj)} · display-derived delta ${d<0?'-':''}${fmtK(Math.abs(d))} (not a metric).`)).toBeInTheDocument();
});
test('metric select hides during compare and returns with its value preserved',async()=>{
 global.fetch.mockImplementation(async url=>response(String(url).includes('/range-records/')?replay(complete):index()));
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 await loadStored();fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:complete.record_id}});
 await screen.findByRole('grid');
 fireEvent.click(screen.getByRole('button',{name:'Compare Raw vs Adjusted'}));
 expect(screen.queryByLabelText('Range metric')).not.toBeInTheDocument();
 expect(screen.getByText(/Comparing Raw OI GEX \(left\) vs Delta-weighted/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Exit compare'}));
 expect(screen.getByLabelText('Range metric')).toHaveValue('raw_oi');
});
