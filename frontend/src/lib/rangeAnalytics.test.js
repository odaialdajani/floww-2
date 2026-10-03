import complete from '../fixtures/integration/range-analytics.v1/complete.json';
import partial from '../fixtures/integration/range-analytics.v1/partial.json';
import refused from '../fixtures/integration/range-analytics.v1/refused.json';
import {admitRangeEnvelope, rangeSelectionContext} from './rangeAnalytics';
const clone = value => JSON.parse(JSON.stringify(value));
const query = {symbol:'SPY',minDte:14,maxDte:60};

test('actual complete and partial producer axes, cells, clocks and nulls survive admission',()=>{
 for(const fixture of [complete,partial]){
  const result=admitRangeEnvelope(fixture,query);
  expect(result.reason).toBeNull();expect(result.envelope).toBe(fixture);
  expect(result.envelope.grids.window.cells['2026-10-26']['590']).toBeNull();
 }
 expect(partial.coverage.complete).toBe(false);
});
test('producer refusals and unavailable metrics never become zero grids',()=>{
 expect(admitRangeEnvelope(refused,{...query,minDte:60,maxDte:14}).reason).toBe('REVERSED_WINDOW');
 const selection=rangeSelectionContext(complete,'window',{strike:'590',expiry:'2026-10-26'},'live');
 expect(selection.selectedStrike).toBeNull();expect(selection.selectedContract).toBeNull();
});
test.each([
 ['foreign symbol',d=>{d.symbol='QQQ';},'RANGE_IDENTITY_MISMATCH'],
 ['foreign window',d=>{d.query.max_dte=90;},'RANGE_IDENTITY_MISMATCH'],
 ['foreign record',d=>{d.record_id='rga1-'+'0'.repeat(24);},'RANGE_IDENTITY_MISMATCH'],
 ['unsupported version',d=>{d.version='range-analytics.v2';},'RANGE_VERSION_UNSUPPORTED'],
 ['wrong DTE',d=>{d.axes.expiries[0].dte=20;},'RANGE_AXES_UNAVAILABLE'],
 ['duplicate strike',d=>{d.axes.strike_keys[1]='590';},'RANGE_AXES_UNAVAILABLE'],
 ['missing cell',d=>{delete d.grids.raw_oi.cells['2026-10-26']['590'];},'RANGE_GRID_UNAVAILABLE'],
 ['string cell',d=>{d.grids.raw_oi.cells['2026-10-26']['590']='12';},'RANGE_GRID_UNAVAILABLE'],
 ['foreign basis',d=>{d.grids.volume.basis='OI';},'RANGE_METRIC_UNSUPPORTED'],
 ['foreign formula',d=>{d.grids.delta_weighted.formula_version='preview';},'RANGE_METRIC_UNSUPPORTED'],
 ['false completeness',d=>{d.coverage.upper_edge_observed=false;},'RANGE_COVERAGE_UNAVAILABLE'],
 ['missing clock',d=>{delete d.clocks.received_at;},'RANGE_CLOCKS_UNAVAILABLE'],
 ['false cell population',d=>{d.grids.raw_oi.n_available=0;},'RANGE_GRID_UNAVAILABLE'],
 ['unavailable numeric grid',d=>{d.grids.raw_oi.status='unavailable';},'RANGE_GRID_UNAVAILABLE'],
 ['string spot',d=>{d.clocks.spot.price='600';},'RANGE_CLOCKS_UNAVAILABLE'],
])('refuses %s without coerced evidence',(_name,change,reason)=>{
 const data=clone(complete);change(data);expect(admitRangeEnvelope(data,query).reason).toBe(reason);
});
test('requesting a dated owner refuses another date while replay does not use today',()=>{
 expect(admitRangeEnvelope(complete,{...query,asOf:'2026-10-02'}).reason).toBe('RANGE_IDENTITY_MISMATCH');
 const context=rangeSelectionContext(complete,'delta_weighted',{strike:'590',expiry:'2026-10-26'},'replay');
 expect(context).toMatchObject({page:'heatseeker',ticker:'SPY',rangeRecordId:complete.record_id,
  rangeDigest:complete.content_digest,selectedStrike:590,selectedExpiry:'2026-10-26',
  rangeMetric:'delta_weighted',displayMode:'range-replay',selectedContract:null});
 expect(context.mapQuery).toEqual(complete.query);expect(context.rangeBasis).toBe('OI_DELTA_WEIGHTED');
 expect(context.observedAt).toBeNull();expect(context.mapVersion).toBe(complete.clocks.received_at);
});
