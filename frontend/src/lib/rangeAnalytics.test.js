import complete from '../fixtures/integration/range-analytics.v1/complete.json';
import partial from '../fixtures/integration/range-analytics.v1/partial.json';
import refused from '../fixtures/integration/range-analytics.v1/refused.json';
import {admitRangeEnvelope, rangeSelectionContext, rangeResearchBlock} from './rangeAnalytics';
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
  rangeMetric:'delta_weighted',displayMode:'range-replay',selectedContract:null,activePane:'gex'});
 expect(context.mapQuery).toEqual(complete.query);expect(context.rangeBasis).toBe('OI_DELTA_WEIGHTED');
 expect(context.observedAt).toBeNull();expect(context.mapVersion).toBe(complete.clocks.received_at);
});

// UI selector completeness only: real producer fixtures do not confer
// cryptographic/production qualification or server research permission.
const researchContext = (fixture=complete,metric='raw_oi') => rangeSelectionContext(
 fixture,metric,{strike:'590',expiry:'2026-10-26'},'replay');
test.each(['raw_oi','delta_weighted','volume'])('stored %s selectors admit research without modifying source evidence',metric=>{
 for(const fixture of [complete,partial]) {
  const before=clone(fixture),context=researchContext(fixture,metric),beforeContext=clone(context);
  expect(rangeResearchBlock(context)).toBeNull();
  expect(context.activePane).toBe('gex');
  expect(context).toEqual(beforeContext);expect(fixture).toEqual(before);
  expect(context.selectedContract).toBeNull();expect(context.selectedWall).toBeNull();
 }
});
test('unbound metric admission claims never affect selector completeness',()=>{
 const fixture=clone(complete);fixture.metrics={admitted:['window'],qualification:'production'};
 expect(rangeResearchBlock(researchContext(fixture))).toBeNull();
 expect(rangeResearchBlock(researchContext(fixture,'window'))).toMatch(/RANGE_WINDOW_UNAVAILABLE/);
});
test.each([
 ['live',c=>{c.displayMode='range-live';},'RANGE_RESEARCH_UNAVAILABLE'],
 ['unsupported range mode',c=>{c.displayMode='range-other';},'RANGE_RESEARCH_UNAVAILABLE'],
 ['missing range mode',c=>{c.displayMode='live';},'RANGE_RESEARCH_UNAVAILABLE'],
 ['v1 context',c=>{c.contextVersion=1;},'RANGE_CONTEXT_INVALID'],
 ['foreign owner',c=>{c.page='trinity';},'RANGE_CONTEXT_INVALID'],
 ['missing pane',c=>{delete c.activePane;},'RANGE_CONTEXT_INVALID'],
 ['wrong pane',c=>{c.activePane='delta';},'RANGE_CONTEXT_INVALID'],
 ['wrong metric family',c=>{c.metric='vex';},'RANGE_CONTEXT_INVALID'],
 ['missing ticker',c=>{c.ticker=null;},'RANGE_CONTEXT_INVALID'],
 ['wrong version',c=>{c.rangeVersion='range-analytics.v2';},'RANGE_CONTEXT_INVALID'],
 ['missing ID',c=>{c.rangeRecordId=null;},'RANGE_IDENTITY_MISMATCH'],
 ['digest prefix mismatch',c=>{c.rangeDigest='0'.repeat(64);},'RANGE_IDENTITY_MISMATCH'],
 ['short digest',c=>{c.rangeDigest='54f0';},'RANGE_IDENTITY_MISMATCH'],
 ['snapshot mismatch',c=>{c.snapshotId=partial.record_id;},'RANGE_IDENTITY_MISMATCH'],
 ['missing provider',c=>{c.provider=null;},'RANGE_CONTEXT_INVALID'],
 ['wrong formula',c=>{c.formula='gex.v1';},'RANGE_METRIC_MISMATCH'],
 ['basis mismatch',c=>{c.rangeBasis='VOLUME';},'RANGE_METRIC_MISMATCH'],
 ['overlay mismatch',c=>{c.overlayMetric='raw';},'RANGE_METRIC_MISMATCH'],
 ['unregistered metric',c=>{c.rangeMetric='invented';c.overlayMetric='invented';},'RANGE_METRIC_MISMATCH'],
 ['unavailable section',c=>{c.rangeStatus='unavailable';},'RANGE_CELL_UNAVAILABLE'],
 ['unknown section',c=>{c.rangeStatus=null;},'RANGE_CELL_UNAVAILABLE'],
 ['missing query',c=>{c.mapQuery=null;},'RANGE_QUERY_INVALID'],
 ['string DTE',c=>{c.mapQuery={...c.mapQuery,min_dte:'14'};},'RANGE_QUERY_INVALID'],
 ['reversed query',c=>{c.mapQuery={...c.mapQuery,min_dte:61};},'RANGE_QUERY_INVALID'],
 ['invalid date',c=>{c.mapQuery={...c.mapQuery,as_of_ny:'2026-02-30'};},'RANGE_QUERY_INVALID'],
 ['query extras',c=>{c.mapQuery={...c.mapQuery,dte:'all'};},'RANGE_QUERY_INVALID'],
 ['wrong bound scope',c=>{c.expiryRange=[0,30];},'RANGE_SCOPE_MISMATCH'],
 ['missing clock',c=>{c.mapVersion=null;},'RANGE_CONTEXT_INVALID'],
 ['naive clock',c=>{c.mapVersion='2026-10-05T13:59:30';},'RANGE_CONTEXT_INVALID'],
 ['missing strikes',c=>{c.mapStrikes=[];},'RANGE_AXES_INVALID'],
 ['string strike axis',c=>{c.mapStrikes=['590',600];},'RANGE_AXES_INVALID'],
 ['duplicate strike',c=>{c.mapStrikes=[590,590];},'RANGE_AXES_INVALID'],
 ['unsorted strike',c=>{c.mapStrikes=[600,590];},'RANGE_AXES_INVALID'],
 ['duplicate expiry',c=>{c.mapExpiries=['2026-10-26','2026-10-26'];},'RANGE_AXES_INVALID'],
 ['foreign expiry',c=>{c.mapExpiries=['2027-01-01'];c.selectedExpiry='2027-01-01';},'RANGE_AXES_INVALID'],
 ['missing expiry',c=>{c.mapExpiries=[];},'RANGE_AXES_INVALID'],
 ['no cell',c=>{c.selectedStrike=null;c.selectedExpiry=null;},'RANGE_SELECTION_MISMATCH'],
 ['string selected strike',c=>{c.selectedStrike='590';},'RANGE_SELECTION_MISMATCH'],
 ['foreign cell',c=>{c.selectedStrike=591;},'RANGE_SELECTION_MISMATCH'],
 ['foreign selected expiry',c=>{c.selectedExpiry='2026-11-10';},'RANGE_SELECTION_MISMATCH'],
 ['wall invention',c=>{c.selectedWall={id:'wall',lower:590,upper:600};},'RANGE_CONTRACT_UNAVAILABLE'],
 ['contract invention',c=>{c.selectedContract={osi:'SPY-fake'};},'RANGE_CONTRACT_UNAVAILABLE'],
 ['resolved contract claim',c=>{c.contractResolution='resolved';},'RANGE_CONTRACT_UNAVAILABLE'],
])('range research blocks %s without trusting client facts',(_,change,reason)=>{
 const context=researchContext();change(context);
 expect(rangeResearchBlock(context)).toContain(reason);
});
test('available-cell selection cannot be synthesized from null, nonfinite or unavailable section values',()=>{
 const skipped=rangeSelectionContext(partial,'raw_oi',{strike:'590',expiry:'2026-12-04'},'replay');
 expect(rangeResearchBlock(skipped)).toMatch(/RANGE_SELECTION_MISMATCH/);
 const fixture=clone(complete);fixture.grids.raw_oi.cells['2026-10-26']['590']=Infinity;
 const context=researchContext(fixture);
 expect(context.selectedStrike).toBeNull();expect(context.selectedExpiry).toBeNull();
 expect(rangeResearchBlock(context)).toMatch(/RANGE_SELECTION_MISMATCH/);
});
test('legacy contexts are unchanged, while orphaned range identity cannot fall through to live research',()=>{
 for(const context of [null,{}, {page:'heatseeker',ticker:'SPY',displayMode:'live',overlayMetric:'delta'},
  {page:'flowseeker-pro',ticker:'NVDA',displayMode:'replay'}]) expect(rangeResearchBlock(context)).toBeNull();
 expect(rangeResearchBlock({page:'heatseeker',ticker:'SPY',displayMode:'live',snapshotId:complete.record_id})).toMatch(/RANGE_RESEARCH_UNAVAILABLE/);
});
