import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import RangeReplayControls from './RangeReplayControls';
import complete from '../../../../docs/solstice/r18/fixtures/complete_v1.json';
import partial from '../../../../docs/solstice/r18/fixtures/partial_skipped_v1.json';

// Consumer transport harness: real envelope shapes with constructed wrappers.
// Not a producer-published replay fixture, production capture or restart proof.
const clone = value => JSON.parse(JSON.stringify(value));
const row = e => ({record_id:e.record_id,ticker:e.symbol,window:{min_dte:14,max_dte:60},
 asof_date:e.query.as_of_ny,received_at:e.clocks.received_at,recorded_at:'2026-10-05T14:00:00+00:00',
 status:e.status,digest:e.content_digest,integrity:'verified',synthetic:e.synthetic});
const rows=[row(complete),row(partial)];
const wrapper = e => ({version:'range-records.v1',...row(e),envelope:clone(e),replay_note:'exact stored envelope restored'});
const page = (entries=rows,offset=0,limit=50) => ({version:'range-records.v1',status:'ok',
 filters:{ticker:'SPY',min_dte:14,max_dte:60,as_of:null,status:null},limit,offset,n_returned:entries.length,rows:entries});
const response = (body,status=200) => ({ok:status>=200&&status<300,status,json:async()=>body});
let onRecord,onLive;
beforeEach(()=>{
 onRecord=jest.fn(); onLive=jest.fn(); window.localStorage.clear();
 global.fetch=jest.fn(async url=>response(String(url).includes('/range-records/')
  ?wrapper(String(url).endsWith(partial.record_id)?partial:complete):page()));
});
afterEach(()=>{jest.useRealTimers();});
const mount = () => render(<RangeReplayControls ticker="SPY" minDte={14} maxDte={60} onRecord={onRecord} onLive={onLive}/>);
const load = async () => {fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await waitFor(()=>expect(screen.getByLabelText('Stored range record').options).toHaveLength(3));};
const select = id => fireEvent.change(screen.getByLabelText('Stored range record'),{target:{value:id}});
const settle = async () => {await act(async()=>{});};
const lastEnvelope = () => onRecord.mock.calls[onRecord.mock.calls.length-1]?.[0];

test('index is explicit and reads only stored routes with credentials and stored key',async()=>{
 window.localStorage.setItem('floww_app_key','offline-key');mount();expect(global.fetch).not.toHaveBeenCalled();
 await load();
 const [url,options]=global.fetch.mock.calls[0];
 const parsed=new URL(url);
 expect(parsed.pathname).toBe('/api/solstice/price-paths/range-records');
 expect(Object.fromEntries(parsed.searchParams)).toEqual({ticker:'SPY',min_dte:'14',max_dte:'60',limit:'50',offset:'0'});
 expect(options).toMatchObject({method:'GET',credentials:'include',headers:{'X-API-Key':'offline-key'}});
 expect(screen.getByText(/Research only.*qualification pending/i)).toBeInTheDocument();
 expect(screen.getByText(/Full integrity.*HOLD/i)).toBeInTheDocument();
 expect(screen.getByText(/gaps.*unknown/i)).toBeInTheDocument();
 expect(screen.getByText(/frames.*not continuous market time/i)).toBeInTheDocument();
 expect(lastEnvelope()).toBeNull();
});
test('partial selection clears parent synchronously then supplies actual stored cells',async()=>{
 mount();await load();
 const transport=wrapper(partial);global.fetch.mockResolvedValueOnce(response(transport));
 select(partial.record_id);
 expect(lastEnvelope()).toBeNull();
 await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(partial.record_id));
 expect(lastEnvelope().grids.raw_oi.cells['2026-12-04']['590']).toBeNull();
 expect(lastEnvelope()).toBe(transport.envelope);
 expect(lastEnvelope()).toEqual(partial);
 expect(lastEnvelope().metrics).toBe(transport.envelope.metrics);
 expect(lastEnvelope().metrics).toEqual(partial.metrics);
 expect(global.fetch.mock.calls[1][0]).toContain('/range-records/'+partial.record_id);
});
test('altered metrics pass through verbatim without a UI qualification or integrity upgrade',async()=>{
 mount();await load();const transport=wrapper(complete);
 transport.envelope.metrics={admitted:['window'],qualification:'production',integrity:'cryptographically-verified'};
 global.fetch.mockResolvedValueOnce(response(transport));select(complete.record_id);
 await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(complete.record_id));
 expect(lastEnvelope()).toBe(transport.envelope);
 expect(lastEnvelope().metrics).toBe(transport.envelope.metrics);
 expect(screen.getByText(/Research only.*qualification pending/i)).toBeInTheDocument();
 expect(screen.getByText(/Full integrity.*HOLD/i)).toBeInTheDocument();
});
test('previous, next, scrub and record select share owning stored retrieval',async()=>{
 // v3: records load in CHRONOLOGICAL order (received_at ASC, record_id ASC),
 // so the index list is [complete, partial] — derive the direction from the
 // fixtures instead of baking the pre-v3 ID order.
 // v3: chronological — received_at ASC, record_id ASC tiebreak; the fixtures now
 // carry DISTINCT received_at so this follows the true producer order.
 const [first,second]=[complete,partial].sort(
  (a,b)=>(Date.parse(a.clocks.received_at)-Date.parse(b.clocks.received_at))
         || (a.record_id<b.record_id?-1:1));
 mount();await load();
 fireEvent.click(screen.getByRole('button',{name:'Next frame'}));
 await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(first.record_id));
 fireEvent.click(screen.getByRole('button',{name:'Next frame'}));expect(lastEnvelope()).toBeNull();
 await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(second.record_id));
 fireEvent.click(screen.getByRole('button',{name:'Previous frame'}));
 await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(first.record_id));
 fireEvent.change(screen.getByLabelText('Replay frame'),{target:{value:'1'}});
 await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(second.record_id));
 expect(global.fetch.mock.calls.every(([url])=>String(url).includes('/solstice/price-paths/range-records'))).toBe(true);
});
test.each(['recorder_unavailable','STORE_READ_FAILED'])('HTTP-200 %s refusal never becomes empty history',async reason=>{
 global.fetch.mockResolvedValue(response({version:'range-records.v1',status:'refused',reason,rows:[],n_returned:0}));
 mount();fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await screen.findByText(new RegExp(reason));expect(lastEnvelope()).toBeNull();
 expect(screen.queryByText(/No stored records match/)).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Play frames'})).toBeDisabled();
});
test('empty admitted index is disclosed without auto-reading a live map',async()=>{
 global.fetch.mockResolvedValue(response(page([])));mount();
 fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await screen.findByText(/No stored records match/);expect(global.fetch).toHaveBeenCalledTimes(1);
});
test.each([
 ['foreign digest', body=>{body.digest=partial.content_digest;}],
 ['changed index clock', body=>{body.received_at='2026-10-05T14:01:00+00:00';body.envelope.clocks.received_at=body.received_at;}],
 ['string population', body=>{body.envelope.grids.raw_oi.population.usable='12';}],
 ['corrupt envelope', body=>{delete body.envelope.axes;}],
])('%s frame refuses and clears the previous owning record',async(_,mutate)=>{
 mount();await load();select(partial.record_id);await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(partial.record_id));
 const bad=wrapper(complete);mutate(bad);global.fetch.mockResolvedValueOnce(response(bad));select(complete.record_id);
 await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent(/unavailable/i));
 expect(lastEnvelope()).toBeNull();expect(screen.getByRole('button',{name:'Play frames'})).toBeEnabled();
});
test('playback waits for each stored response, applies speed, pauses and stops at final frame',async()=>{
 jest.useFakeTimers();mount();await load();
 fireEvent.change(screen.getByLabelText('Replay speed'),{target:{value:'2'}});
 fireEvent.click(screen.getByRole('button',{name:'Play frames'}));await settle();
 expect(lastEnvelope()?.record_id).toBe(complete.record_id);
 await act(async()=>jest.advanceTimersByTime(999));expect(global.fetch).toHaveBeenCalledTimes(2);
 fireEvent.click(screen.getByRole('button',{name:'Pause frames'}));
 await act(async()=>jest.advanceTimersByTime(3000));expect(global.fetch).toHaveBeenCalledTimes(2);
 fireEvent.click(screen.getByRole('button',{name:'Play frames'}));
 await act(async()=>jest.advanceTimersByTime(1000));await settle();
 expect(lastEnvelope()?.record_id).toBe(partial.record_id);
 expect(screen.getByRole('button',{name:'Play frames'})).toBeInTheDocument();
 await act(async()=>jest.advanceTimersByTime(10000));expect(global.fetch).toHaveBeenCalledTimes(3);
});
test('corrupt playback frame stops the timer and clears record, without live fallback',async()=>{
 jest.useFakeTimers();mount();await load();
 fireEvent.click(screen.getByRole('button',{name:'Play frames'}));await settle();
 global.fetch.mockResolvedValueOnce(response({version:'range-records.v1',status:'refused',reason:'DIGEST_MISMATCH'},422));
 await act(async()=>jest.advanceTimersByTime(2000));await settle();
 expect(lastEnvelope()).toBeNull();expect(screen.getByRole('status')).toHaveTextContent('DIGEST_MISMATCH');
 await act(async()=>jest.advanceTimersByTime(10000));expect(global.fetch).toHaveBeenCalledTimes(3);
});
test('overlapping selections abort the old read and reject its delayed response',async()=>{
 mount();await load();let release;
 global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));select(complete.record_id);
 const signal=global.fetch.mock.calls[1][1].signal;select(partial.record_id);
 await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(partial.record_id));expect(signal.aborted).toBe(true);
 await act(async()=>release(response(wrapper(complete))));expect(lastEnvelope()?.record_id).toBe(partial.record_id);
});
test.each(['ticker','window','date','Live','key','unmount'])('%s invalidates pending frame and prevents stale reinstatement',async kind=>{
 const ui=mount();await load();let release;
 global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));select(complete.record_id);
 const signal=global.fetch.mock.calls[1][1].signal;
 if(kind==='ticker') ui.rerender(<RangeReplayControls ticker="QQQ" minDte={14} maxDte={60} onRecord={onRecord}/>);
 if(kind==='window') ui.rerender(<RangeReplayControls ticker="SPY" minDte={21} maxDte={60} onRecord={onRecord}/>);
 if(kind==='date') fireEvent.change(screen.getByLabelText('Stored owning NY date'),{target:{value:'2026-10-06'}});
 if(kind==='Live') fireEvent.click(screen.getByRole('button',{name:'Live'}));
 if(kind==='key') {window.localStorage.setItem('floww_app_key','replacement');fireEvent(window,new Event('storage'));}
 if(kind==='unmount') ui.unmount();
 expect(signal.aborted).toBe(true);expect(lastEnvelope()).toBeNull();
 const count=onRecord.mock.calls.length;await act(async()=>release(response(wrapper(complete))));
 expect(onRecord).toHaveBeenCalledTimes(count);expect(global.fetch).toHaveBeenCalledTimes(2);
 if(kind==='Live') expect(onLive).toHaveBeenCalledTimes(1);
});
test('same-tab key change without storage event cannot admit an old reply',async()=>{
 mount();await load();let release;global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));select(complete.record_id);
 window.localStorage.setItem('floww_app_key','replacement');await act(async()=>release(response(wrapper(complete))));
 expect(lastEnvelope()).toBeNull();expect(screen.getByRole('status')).toHaveTextContent('RANGE_KEY_CHANGED');
});
test('timeout stops play even if fake transport ignores abort; its late reply stays invalid',async()=>{
 jest.useFakeTimers();mount();await load();let release;
 global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));
 fireEvent.click(screen.getByRole('button',{name:'Play frames'}));
 const signal=global.fetch.mock.calls[1][1].signal;
 await act(async()=>jest.advanceTimersByTime(15000));expect(signal.aborted).toBe(true);
 expect(lastEnvelope()).toBeNull();expect(screen.getByRole('status')).toHaveTextContent('RANGE_READ_TIMEOUT');
 await act(async()=>release(response(wrapper(partial))));expect(lastEnvelope()).toBeNull();
 expect(screen.getByRole('button',{name:'Play frames'})).toBeInTheDocument();
});
test('invalid integer props refuse before requesting stored data',async()=>{
 render(<RangeReplayControls ticker="SPY" minDte="14" maxDte={60} onRecord={onRecord}/>);
 fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 expect(screen.getByRole('status')).toHaveTextContent('RANGE_QUERY_INVALID');expect(global.fetch).not.toHaveBeenCalled();
});
test('optional date is sent exactly and date change clears history without automatic fetch',async()=>{
 mount();await load();fireEvent.change(screen.getByLabelText('Stored owning NY date'),{target:{value:'2026-10-05'}});
 expect(lastEnvelope()).toBeNull();expect(global.fetch).toHaveBeenCalledTimes(1);
 global.fetch.mockResolvedValueOnce(response({...page(),filters:{...page().filters,as_of:'2026-10-05'}}));
 await load();expect(new URL(global.fetch.mock.calls[1][0]).searchParams.get('as_of')).toBe('2026-10-05');
});
test('pagination is explicit, chronological and capped at 200 frames with unknown coverage',async()=>{
 // Distinct transport identities with matching digest prefixes; no frame
 // envelopes are manufactured or asserted as cryptographically valid here.
 const makeValidPage = offset => page(Array.from({length:50},(_,i)=>{
  const digest=(200-offset-i).toString(16).padStart(24,'0')+'0'.repeat(40);
  return {...row(complete),digest,record_id:'rga1-'+digest.slice(0,24)};
 }),offset);
 global.fetch.mockImplementation(async url=>response(makeValidPage(Number(new URL(url).searchParams.get('offset')))));
 mount();fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await waitFor(()=>expect(screen.getByLabelText('Stored range record').options).toHaveLength(51));
 for(const size of [101,151,201]) {fireEvent.click(screen.getByRole('button',{name:'Load older records'}));
  await waitFor(()=>expect(screen.getByLabelText('Stored range record').options).toHaveLength(size));}
 expect(screen.getByRole('button',{name:'Load older records'})).toBeDisabled();
 expect(screen.getByText(/200.*cap.*coverage.*unknown/i)).toBeInTheDocument();
 expect(global.fetch.mock.calls.map(([url])=>new URL(url).searchParams.get('offset'))).toEqual(['0','50','100','150']);
});
test('pause invalidates a pending playback frame rather than admitting it after pause',async()=>{
 mount();await load();let release;
 global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));
 fireEvent.click(screen.getByRole('button',{name:'Play frames'}));
 const signal=global.fetch.mock.calls[1][1].signal;
 fireEvent.click(screen.getByRole('button',{name:'Pause frames'}));
 expect(signal.aborted).toBe(true);expect(lastEnvelope()).toBeNull();
 await act(async()=>release(response(wrapper(partial))));expect(lastEnvelope()).toBeNull();
});
test('slow frames never overlap requests or advance merely because wall time elapsed',async()=>{
 jest.useFakeTimers();mount();await load();let release;
 global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));
 fireEvent.click(screen.getByRole('button',{name:'Play frames'}));
 await act(async()=>jest.advanceTimersByTime(6000));expect(global.fetch).toHaveBeenCalledTimes(2);
 await act(async()=>release(response(wrapper(complete))));
 await act(async()=>jest.advanceTimersByTime(1999));expect(global.fetch).toHaveBeenCalledTimes(2);
 await act(async()=>jest.advanceTimersByTime(1));expect(global.fetch).toHaveBeenCalledTimes(3);
});
test('in-flight index is invalidated by date change and does not supply old history',async()=>{
 let release;global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));mount();
 fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 const signal=global.fetch.mock.calls[0][1].signal;
 fireEvent.change(screen.getByLabelText('Stored owning NY date'),{target:{value:'2026-10-05'}});
 expect(signal.aborted).toBe(true);
 await act(async()=>release(response(page())));expect(screen.getByLabelText('Stored range record')).toBeDisabled();
 expect(lastEnvelope()).toBeNull();expect(global.fetch).toHaveBeenCalledTimes(1);
});
test('index timeout invalidates a delayed index even when fetch ignores abort',async()=>{
 jest.useFakeTimers();let release;global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));mount();
 fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await act(async()=>jest.advanceTimersByTime(15000));
 expect(screen.getByRole('status')).toHaveTextContent('RANGE_READ_TIMEOUT');
 await act(async()=>release(response(page())));expect(screen.getByLabelText('Stored range record')).toBeDisabled();
});
test('key change stops playback before another request, even without a storage event',async()=>{
 jest.useFakeTimers();mount();await load();fireEvent.click(screen.getByRole('button',{name:'Play frames'}));await settle();
 window.localStorage.setItem('floww_app_key','changed');
 await act(async()=>jest.advanceTimersByTime(2000));expect(global.fetch).toHaveBeenCalledTimes(2);
 expect(lastEnvelope()).toBeNull();expect(screen.getByRole('status')).toHaveTextContent('RANGE_KEY_CHANGED');
});
test.each(['offset','limit'])('index rejects transport pagination %s contradictions',async field=>{
 const body=page();body[field]=field==='offset'?50:200;global.fetch.mockResolvedValueOnce(response(body));mount();
 fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await screen.findByText(/RANGE_INDEX_PAGE_MISMATCH/);expect(screen.getByRole('button',{name:'Play frames'})).toBeDisabled();
});
test('non-2xx response cannot admit a healthy-looking frame and malformed JSON clears parent',async()=>{
 mount();await load();global.fetch.mockResolvedValueOnce(response(wrapper(complete),503));select(complete.record_id);
 await screen.findByText(/RANGE_HTTP_503/);expect(lastEnvelope()).toBeNull();
 global.fetch.mockResolvedValueOnce({ok:true,status:200,json:async()=>{throw new Error('bad JSON');}});select(complete.record_id);
 await screen.findByText(/RANGE_READ_FAILED/);expect(lastEnvelope()).toBeNull();
});
test('Live is deliberate, remains usable without a callback and never refreshes providers',async()=>{
 render(<RangeReplayControls ticker="SPY" minDte={14} maxDte={60} onRecord={onRecord}/>);
 await load();select(complete.record_id);await waitFor(()=>expect(lastEnvelope()?.record_id).toBe(complete.record_id));
 fireEvent.click(screen.getByRole('button',{name:'Live'}));expect(lastEnvelope()).toBeNull();
 expect(global.fetch).toHaveBeenCalledTimes(2);
});
test('a duplicate across pages refuses the combined timeline rather than replaying twice',async()=>{
 const full=page(Array.from({length:50},(_,i)=>{
  const digest=i.toString(16).padStart(24,'0')+'0'.repeat(40);return {...row(complete),digest,record_id:'rga1-'+digest.slice(0,24)};
 }));
 global.fetch.mockResolvedValueOnce(response(full));mount();fireEvent.click(screen.getByRole('button',{name:'Load stored range records'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Load older records'})).toBeEnabled());
 global.fetch.mockResolvedValueOnce(response(page([full.rows[0]],50)));fireEvent.click(screen.getByRole('button',{name:'Load older records'}));
 await screen.findByText(/RANGE_DUPLICATE_IDENTITY/);expect(lastEnvelope()).toBeNull();
 expect(screen.getByRole('button',{name:'Play frames'})).toBeDisabled();
});
