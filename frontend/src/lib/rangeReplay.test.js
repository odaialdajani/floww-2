import {admitRangeIndex, admitRangeRecord} from './rangeReplay';
import complete from '../../../docs/solstice/r18/fixtures/complete_v1.json';
import partial from '../../../docs/solstice/r18/fixtures/partial_skipped_v1.json';
import metadataOnly from '../../../docs/solstice/r18/fixtures/record_replay_v1.json';
import transport from '../fixtures/integration/range-analytics.v1/replay-transport.json';

// Consumer transport tests built around real producer envelopes, NOT a
// published full replay fixture, cryptographic admission or restart proof.
const clone = value => JSON.parse(JSON.stringify(value));
const query = {symbol:'SPY', minDte:14, maxDte:60, asOf:'2026-10-05'};
const recordedAt = '2026-10-05T14:00:00+00:00';
const row = envelope => ({record_id:envelope.record_id, ticker:envelope.symbol,
 window:{min_dte:envelope.query.min_dte,max_dte:envelope.query.max_dte},
 asof_date:envelope.query.as_of_ny, received_at:envelope.clocks.received_at,
 recorded_at:recordedAt, status:envelope.status, digest:envelope.content_digest,
 integrity:'verified', synthetic:envelope.synthetic});
const record = envelope => ({version:'range-records.v1', ...row(envelope), envelope:clone(envelope),
 replay_note:'exact stored envelope restored; canonical content digest recomputed and verified; no recomputation'});
const index = (rows = [row(complete), row(partial)]) => ({version:'range-records.v1',status:'ok',
 filters:{ticker:'SPY',min_dte:14,max_dte:60,as_of:'2026-10-05',status:null},
 limit:50,offset:0,n_returned:rows.length,rows});

test('actual offline stored-route responses admit exact complete/partial envelopes without transforming metadata',()=>{
 expect(admitRangeIndex(transport.index,{...query,asOf:undefined}).reason).toBeNull();
 for(const body of Object.values(transport.records)){
  const result=admitRangeRecord(body,{...query,recordId:body.record_id});
  expect(result.reason).toBeNull();expect(result.envelope).toBe(body.envelope);
  expect(result.qualification).toBe('pending');
 }
 expect(admitRangeIndex(transport.empty,{...query,asOf:undefined}).rows).toEqual([]);
 expect(admitRangeRecord(transport.corrupt,{...query,recordId:transport.corrupt.record_id}).reason).toBe('CORRUPT_PAYLOAD');
});

test('index admits partial rows and sorts received clock then record ID without changing input', () => {
 const body=index(), before=clone(body);
 const result=admitRangeIndex(body,query);
 expect(result.reason).toBeNull();
 // v3 with distinct received_at: complete (13:59:30) precedes partial (13:59:35),
 // so chronological order is received_at ASC; the record_id tiebreak only applies
 // on equal clocks.
 expect(result.rows.map(r=>r.record_id))
  .toEqual([complete.record_id, partial.record_id]);
 expect(result.rows[0].received_at<=result.rows[1].received_at).toBe(true);
 expect(body).toEqual(before);
 expect(result).toMatchObject({researchOnly:true,qualification:'pending',page:{limit:50,offset:0,nReturned:2,mayHaveMore:false}});
});
test('timeline compares timestamp instants, not lexicographic offsets', () => {
 const a=row(complete), b=row(partial);
 a.received_at='2026-10-05T10:10:00-04:00'; b.received_at='2026-10-05T14:00:00+00:00';
 expect(admitRangeIndex(index([a,b]),query).rows.map(r=>r.record_id)).toEqual([b.record_id,a.record_id]);
});
test('honest empty success is distinct from HTTP-200 refusal and missing rows', () => {
 expect(admitRangeIndex(index([]),query)).toMatchObject({reason:null,rows:[]});
 for(const reason of ['recorder_unavailable','STORE_READ_FAILED']) {
  expect(admitRangeIndex({version:'range-records.v1',status:'refused',reason,rows:[],n_returned:0},query))
   .toMatchObject({reason,rows:null});
 }
 expect(admitRangeIndex({...index(),rows:undefined},query).reason).toBeTruthy();
});
test('full pages disclose only possible additional history, not complete coverage', () => {
 const body=index(); body.limit=2;
 expect(admitRangeIndex(body,query).page.mayHaveMore).toBe(true);
});
test('optional owning date permits distinct stored dates but never a foreign window', () => {
 const body=index(); body.filters.as_of=null; body.rows[1].asof_date='2026-10-06';
 expect(admitRangeIndex(body,{...query,asOf:undefined}).reason).toBeNull();
 expect(admitRangeIndex(body,query).reason).toBeTruthy();
});

test.each([
 ['version', b=>{b.version='coverage-read.v1';}],
 ['refused without reason', b=>{b.status='refused';}],
 ['filter symbol', b=>{b.filters.ticker='QQQ';}],
 ['filter window string', b=>{b.filters.min_dte='14';}],
 ['filter date', b=>{b.filters.as_of='2026-10-06';}],
 ['missing filters', b=>{delete b.filters;}],
 ['wrong filter status', b=>{b.filters.status='refused';}],
 ['status contradiction', b=>{b.filters.status='ok';}],
 ['string count', b=>{b.n_returned='2';}],
 ['count contradiction', b=>{b.n_returned=1;}],
 ['string limit', b=>{b.limit='50';}],
 ['limit over cap', b=>{b.limit=201;}],
 ['page over limit', b=>{b.limit=1;}],
 ['fractional offset', b=>{b.offset=0.5;}],
 ['negative offset', b=>{b.offset=-1;}],
 ['duplicate identity', b=>{b.rows[1]=clone(b.rows[0]);}],
 ['foreign ticker', b=>{b.rows[0].ticker='QQQ';}],
 ['foreign window', b=>{b.rows[0].window.max_dte=30;}],
 ['string row window', b=>{b.rows[0].window.min_dte='14';}],
 ['foreign date', b=>{b.rows[0].asof_date='2026-10-06';}],
 ['invalid date', b=>{b.rows[0].asof_date='2026-02-30';}],
 ['naive received clock', b=>{b.rows[0].received_at='2026-10-05T14:00:00';}],
 ['missing recorded clock', b=>{delete b.rows[0].recorded_at;}],
 ['corrupt row', b=>{b.rows[0].integrity='corrupt';}],
 ['refused row', b=>{b.rows[0].integrity='refused:DIGEST_MISMATCH';}],
 ['refused status', b=>{b.rows[0].status='refused';}],
 ['digest/ID contradiction', b=>{b.rows[0].digest='0'.repeat(64);}],
 ['legacy identity', b=>{b.rows[0].record_id='snapshot-1';}],
 ['synthetic string', b=>{b.rows[0].synthetic='false';}],
])('index refuses %s rather than supplying safe history', (_,mutate) => {
 const body=index(); mutate(body);
 expect(admitRangeIndex(body,query)).toMatchObject({rows:null,reason:expect.any(String)});
});

test.each([complete,partial])('retrieval admits stored $status envelope as research with qualification pending', envelope => {
 const body=record(envelope), before=clone(body);
 const result=admitRangeRecord(body,{...query,recordId:envelope.record_id});
 expect(result.reason).toBeNull();
 expect(result.envelope).toBe(body.envelope);
 expect(result.envelope).toEqual(envelope);
 expect(body).toEqual(before);
 expect(result.envelope.axes).toEqual(envelope.axes);
 expect(result.envelope.grids).toEqual(envelope.grids);
 expect(result.envelope.status).toBe(envelope.status);
 expect(result).toMatchObject({researchOnly:true,qualification:'pending'});
 expect(result.envelope.metrics).toBe(body.envelope.metrics);
 expect(result.envelope.metrics).toEqual(envelope.metrics);
});
test('actual retrieval has no outer synthetic field; classification comes from the envelope', () => {
 const body=record(partial);delete body.synthetic;
 expect(admitRangeRecord(body,{...query,recordId:partial.record_id})).toMatchObject({reason:null,envelope:{synthetic:true,status:'partial'}});
});
test('altered unbound metrics are retained verbatim without upgrading research qualification', () => {
 const body=record(complete);
 body.envelope.metrics={admitted:['window'],qualification:'production',researchOnly:false,integrity:'cryptographically-verified'};
 const before=clone(body);
 const result=admitRangeRecord(body,{...query,recordId:complete.record_id});
 expect(result).toMatchObject({reason:null,researchOnly:true,qualification:'pending'});
 expect(result.envelope).toBe(body.envelope);
 expect(result.envelope).toEqual(before.envelope);
 expect(result.envelope.metrics).toBe(body.envelope.metrics);
 expect(body).toEqual(before);
});
test('record_replay wrapper carries the full bound envelope under v3 (C11 deliverable)', () => {
 // The old metadata-only wrapper shape WAS the C11 consumer-review defect:
 // v3 wrappers carry the full digest-bound envelope, so a replay wrapper
 // admits exactly like a stored record. It is never a bare metadata stub.
 const result=admitRangeRecord(metadataOnly,{...query,recordId:metadataOnly.record_id});
 expect(result.reason).toBeNull();
 expect(result.envelope).toBe(metadataOnly.envelope);
 expect(result.envelope.content_schema).toBe('rga-content.v3');
});
test.each([
 ['missing envelope', b=>{delete b.envelope;}],
 ['unsupported wrapper version', b=>{b.version='range-analytics.v1';}],
 ['legacy content schema', b=>{b.envelope.content_schema='rga-content.v1';}],
 ['wrapper ID', b=>{b.record_id=partial.record_id;}],
 ['wrapper digest', b=>{b.digest=partial.content_digest;}],
 ['wrapper ticker', b=>{b.ticker='QQQ';}],
 ['wrapper window', b=>{b.window.max_dte=30;}],
 ['string wrapper window', b=>{b.window.min_dte='14';}],
 ['wrapper owning date', b=>{b.asof_date='2026-10-06';}],
 ['wrapper status', b=>{b.status='partial';}],
 ['wrapper received clock', b=>{b.received_at='2026-10-05T14:01:00+00:00';}],
 ['missing recorded clock', b=>{delete b.recorded_at;}],
 ['integrity refusal', b=>{b.integrity='refused:DIGEST_MISMATCH';}],
 ['error on success', b=>{b.error='CORRUPT_PAYLOAD';}],
 ['string coverage count', b=>{b.envelope.coverage.n_contracts='12';}],
 ['string cell count', b=>{b.envelope.grids.raw_oi.n_cells='6';}],
 ['string population count', b=>{b.envelope.grids.raw_oi.population.usable='12';}],
 ['string bid clock count', b=>{b.envelope.clocks.bid_timestamps_present='12';}],
 ['string expiry drop count', b=>{b.envelope.coverage.n_expired_dropped='1';}],
 ['string budget count', b=>{b.envelope.coverage.budget.pre_debit='5';}],
 ['string captured contract count', b=>{b.envelope.grounding.contract_population['2026-10-26'].n_contracts='4';}],
 ['string usable count', b=>{b.envelope.grids.raw_oi.usable='12';}],
 ['contradictory usable counts', b=>{b.envelope.grids.raw_oi.usable=11;}],
 ['null extra grid', b=>{b.envelope.grids.foreign=null;}],
 ['population admission contradiction', b=>{b.envelope.grids.raw_oi.metric_admitted=false;}],
 ['corrupt cell', b=>{b.envelope.grids.raw_oi.cells['2026-10-26']['590']='123';}],
])('retrieval refuses %s and yields no envelope', (_,mutate) => {
 const body=record(complete); mutate(body);
 expect(admitRangeRecord(body,{...query,recordId:complete.record_id})).toMatchObject({envelope:null,reason:expect.any(String)});
});
test('explicit owning query and record identity are mandatory and cannot be coerced', () => {
 for(const change of [{recordId:undefined},{symbol:'QQQ'},{minDte:'14'},{minDte:60,maxDte:14},{asOf:'not-a-day'}]) {
  expect(admitRangeRecord(record(complete),{...query,recordId:complete.record_id,...change}).reason).toBeTruthy();
 }
});
test.each(['NO_RECORD','DIGEST_MISMATCH','STORE_READ_FAILED'])('typed retrieval refusal %s stays explicit', reason => {
 expect(admitRangeRecord({version:'range-records.v1',status:'refused',reason,record_id:complete.record_id},
  {...query,recordId:complete.record_id})).toMatchObject({reason,envelope:null});
});
