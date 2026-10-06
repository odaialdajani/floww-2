import React, {useCallback, useEffect, useRef, useState} from 'react';
import {API} from '../../config/api';
import {storedAppKeyHeaders} from '../../utils/appKey';
import {admitRangeIndex, admitRangeRecord} from '../../lib/rangeReplay';

const PAGE_SIZE = 50;
const FRAME_CAP = 200;
const TIMEOUT_MS = 15000;
const storedKey = () => storedAppKeyHeaders()?.['X-API-Key'] || '';
const chronological = (a,b) => Date.parse(a.received_at)-Date.parse(b.received_at)
 || (a.record_id < b.record_id ? -1 : a.record_id > b.record_id ? 1 : 0);

/** Research-only playback of stored rga1 frames. Index pages and frames are
 * explicitly requested; Live exits without fetching a current chain. */
export default function RangeReplayControls({ticker,minDte,maxDte,onRecord,onLive}) {
 const [asOf,setAsOf] = useState('');
 const [rows,setRows] = useState([]);
 const [page,setPage] = useState(null);
 const [cursor,setCursor] = useState(-1);
 const [playing,setPlaying] = useState(false);
 const [speed,setSpeed] = useState(1);
 const [loading,setLoading] = useState(false);
 const [error,setError] = useState(null);
 const callbacks = useRef({onRecord,onLive});
 callbacks.current = {onRecord,onLive};
 const scope = JSON.stringify([ticker,minDte,maxDte,asOf]);
 const scopeRef = useRef(scope);
 scopeRef.current = scope;
 const mounted = useRef(false);
 const epoch = useRef(0);
 const active = useRef(null);
 const playTimer = useRef(null);
 const historyKey = useRef(null);
 const knownKey = useRef(storedKey());
 const query = {symbol:ticker,minDte,maxDte,asOf:asOf || undefined};

 const invalidate = useCallback(() => {
  epoch.current++;
  active.current?.controller.abort();
  clearTimeout(active.current?.timer);
  active.current = null;
  clearTimeout(playTimer.current);
 },[]);
 const clear = useCallback((reason=null,clearHistory=true) => {
  invalidate();
  setPlaying(false);setLoading(false);setCursor(-1);setError(reason);
  if(clearHistory) {setRows([]);setPage(null);historyKey.current=null;}
  callbacks.current.onRecord(null);
 },[invalidate]);

 useEffect(() => {
  mounted.current=true;
  return () => {
   mounted.current=false;invalidate();callbacks.current.onRecord(null);
  };
 },[invalidate]);
 useEffect(() => {clear();},[scope,clear]);
 useEffect(() => {
  const keyChanged = event => {
   if(event.key != null && event.key !== 'floww_app_key') return;
   const key=storedKey();
   if(key !== knownKey.current) {knownKey.current=key;clear('RANGE_KEY_CHANGED');}
  };
  window.addEventListener('storage',keyChanged);
  return () => window.removeEventListener('storage',keyChanged);
 },[clear]);

 // Timeout invalidates the epoch itself: even a transport that ignores abort
 // cannot restore a timed-out frame or leave playback permanently loading.
 const read = async (path,admit,accept,{isIndex=false,continuePlaying=false}={}) => {
  invalidate();
  const generation=epoch.current, owningScope=scopeRef.current, key=storedKey();
  knownKey.current=key;
  const controller=new AbortController();
  const current = () => {
   if(!mounted.current || epoch.current !== generation || scopeRef.current !== owningScope) return false;
   if(storedKey() !== key) {knownKey.current=storedKey();clear('RANGE_KEY_CHANGED');return false;}
   return true;
  };
  callbacks.current.onRecord(null);
  setCursor(-1);setError(null);setLoading(true);setPlaying(continuePlaying);
  const timer=setTimeout(() => {if(current()) clear('RANGE_READ_TIMEOUT',isIndex);},TIMEOUT_MS);
  active.current={controller,timer};
  try {
   const response=await fetch(`${API}/solstice/price-paths/range-records${path}`,{
    method:'GET',headers:storedAppKeyHeaders() || {},credentials:'include',signal:controller.signal,
   });
   if(!current()) return;
   const body=await response.json();
   if(!current()) return;
   const result=admit(body);
   if(result.reason || !response.ok) {
    clear(result.reason || `RANGE_HTTP_${response.status}`,isIndex);return;
   }
   accept(result,body);
  } catch {
   if(current()) clear('RANGE_READ_FAILED',isIndex);
  } finally {
   if(mounted.current && epoch.current === generation) {
    clearTimeout(timer);active.current=null;setLoading(false);
   }
  }
 };

 const loadIndex = (older=false) => {
  const previous=older ? rows : [];
  const offset=older ? page.offset+page.nReturned : 0;
  if(older && historyKey.current !== storedKey()) {clear('RANGE_KEY_CHANGED');return;}
  const limit=Math.min(PAGE_SIZE,FRAME_CAP-previous.length);
  if(limit < 1) return;
  clear(null,!older);
  const params=new URLSearchParams({ticker,min_dte:String(minDte),max_dte:String(maxDte),limit:String(limit),offset:String(offset)});
  if(asOf) params.set('as_of',asOf);
  // Validate before a request, including strict integer props and date input.
  const probe=admitRangeIndex({version:'range-records.v1',status:'ok',
   filters:{ticker,min_dte:minDte,max_dte:maxDte,as_of:asOf || null,status:null},
   limit,offset,n_returned:0,rows:[]},query);
  if(probe.reason) {clear(probe.reason);return;}
  read(`?${params}`,body => admitRangeIndex(body,query),(result) => {
   if(result.page.offset !== offset || result.page.limit !== limit) {clear('RANGE_INDEX_PAGE_MISMATCH');return;}
   const combined=[...previous,...result.rows];
   if(new Set(combined.map(row=>row.record_id)).size !== combined.length) {clear('RANGE_DUPLICATE_IDENTITY');return;}
   setRows(combined.sort(chronological));setPage(result.page);historyKey.current=storedKey();
  },{isIndex:true});
 };

 const openFrame = (position,continuePlaying=false) => {
  const row=rows[position];
  if(!row) return;
  if(historyKey.current !== storedKey()) {clear('RANGE_KEY_CHANGED');return;}
  read(`/${encodeURIComponent(row.record_id)}`,body => admitRangeRecord(body,{
   ...query,asOf:row.asof_date,recordId:row.record_id,
  }),(result,body) => {
   if(body.digest !== row.digest || body.status !== row.status || body.received_at !== row.received_at
    || body.recorded_at !== row.recorded_at || body.asof_date !== row.asof_date
    || (row.synthetic !== null && result.envelope.synthetic !== row.synthetic)) {
    clear('RANGE_INDEX_RECORD_MISMATCH',false);return;
   }
   setCursor(position);callbacks.current.onRecord(result.envelope);
  },{continuePlaying});
 };

 const pause = () => {
  setPlaying(false);clearTimeout(playTimer.current);
  if(active.current) clear(null,false);
 };
 const togglePlay = () => {
  if(playing) {pause();return;}
  if(historyKey.current !== storedKey()) {clear('RANGE_KEY_CHANGED');return;}
  if(cursor < 0 || cursor === rows.length-1) openFrame(0,true);
  else setPlaying(true);
 };
 useEffect(() => {
  if(!playing || loading || cursor < 0) return undefined;
  if(cursor >= rows.length-1) {setPlaying(false);return undefined;}
  playTimer.current=setTimeout(() => openFrame(cursor+1,true),2000/speed);
  return () => clearTimeout(playTimer.current);
  // A callback change must not restart a frame timer; read uses callback refs.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[playing,loading,cursor,speed,rows,scope]);

 const selected=rows[cursor];
 const capped=rows.length >= FRAME_CAP;
 return <section className="range-replay-controls" aria-label="Stored range replay">
  <p>Research only · qualification pending. Full integrity and production admission HOLD; “verified” is producer-reported, not consumer cryptographic certification.</p>
  <div className="range-replay-toolbar">
   <label>Stored owning NY date<input aria-label="Stored owning NY date" type="date" value={asOf}
    onChange={event => {clear();setAsOf(event.target.value);}}/></label>
   <button type="button" onClick={() => loadIndex()} disabled={loading}>Load stored range records</button>
   <button type="button" onClick={() => loadIndex(true)} disabled={loading || !page?.mayHaveMore || capped}>Load older records</button>
   <label>Stored range record<select aria-label="Stored range record" value={selected?.record_id || ''} disabled={!rows.length}
    onChange={event => {const position=rows.findIndex(row=>row.record_id === event.target.value);if(position < 0) clear(null,false);else openFrame(position);}}>
    <option value="">Select a stored frame</option>
    {rows.map(row => <option key={row.record_id} value={row.record_id}>
     {row.received_at} · {row.record_id} · {row.status}{row.synthetic === true ? ' · synthetic' : ' · qualification pending'}
    </option>)}
   </select></label>
   <button type="button" onClick={() => openFrame(cursor-1)} disabled={loading || cursor <= 0}>Previous frame</button>
   <button type="button" onClick={togglePlay} disabled={!rows.length || (loading && !playing)}>{playing ? 'Pause frames' : 'Play frames'}</button>
   <button type="button" onClick={() => openFrame(cursor+1)} disabled={loading || !rows.length || cursor >= rows.length-1}>Next frame</button>
   <label>Replay speed<select aria-label="Replay speed" value={speed} onChange={event => setSpeed(Number(event.target.value))}>
    <option value={0.5}>0.5× · 4 seconds/frame</option><option value={1}>1× · 2 seconds/frame</option>
    <option value={2}>2× · 1 second/frame</option><option value={4}>4× · 0.5 seconds/frame</option>
   </select></label>
   <label>Replay frame<input aria-label="Replay frame" type="range" min="0" max={Math.max(0,rows.length-1)} step="1"
    value={Math.max(0,cursor)} disabled={!rows.length} onChange={event => openFrame(Number(event.target.value))}/></label>
   <button type="button" onClick={() => {clear();callbacks.current.onLive?.();}}>Live</button>
  </div>
  <p role="status">{error ? `Stored range replay unavailable · ${error}` : loading ? 'Reading stored range evidence; previous owning record cleared.'
   : page && !rows.length ? 'No stored records match these filters; coverage is unknown.'
   : selected ? `Stored frame ${cursor+1}/${rows.length} · ${selected.status} · ${selected.record_id}` : 'Select or play explicitly loaded stored frames.'}</p>
  <p>{rows.length} loaded frames · {FRAME_CAP}-frame cap · history coverage and capture gaps are unknown.
   {capped ? ' Pagination cap reached; older records may exist.' : page?.mayHaveMore ? ' More older records may exist; load the next page explicitly.'
    : page ? ' This page is exhausted; that does not establish complete capture.' : ' No index loaded.'}</p>
  <p>Cadence advances explicit stored frames, not continuous market time. No interpolation, live Greeks, current-chain substitution or automatic provider refresh on Live exit.</p>
 </section>;
}
