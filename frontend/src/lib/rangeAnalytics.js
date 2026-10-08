export const RANGE_METRICS = Object.freeze({
 raw_oi: {label:'Raw OI GEX',metric:'gex_net_v1',basis:'OI'},
 delta_weighted: {label:'Delta-weighted OI GEX',metric:'dadgex_net_v1',basis:'OI_DELTA_WEIGHTED'},
 volume: {label:'Cumulative volume gamma',metric:'volume_gamma_v1',basis:'VOLUME'},
 window: {label:'Window volume · delta-adjusted gamma',metric:'window_dadgex_v1',basis:'VOLUME_WINDOW'},
});
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const count = value => Number.isInteger(value) && value >= 0;
const text = value => typeof value === 'string' && value.trim().length > 0;
const timestamp = value => text(value) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const date = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
 && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
const keysEqual = (value,keys) => object(value) && Object.keys(value).length === keys.length && keys.every(key=>Object.hasOwn(value,key));

/** Shape/identity admission, not cryptographic replay integrity or execution permission. */
export function admitRangeEnvelope(data,{symbol,minDte,maxDte,asOf,recordId}={}) {
 const refuse = reason => ({reason,envelope:null});
 if(data?.version !== 'range-analytics.v1') return refuse('RANGE_VERSION_UNSUPPORTED');
 if(data.symbol !== symbol || data.query?.min_dte !== minDte || data.query?.max_dte !== maxDte
  || !date(data.query?.as_of_ny) || (asOf && data.query.as_of_ny !== asOf)
  || (recordId && data.record_id !== recordId)) return refuse('RANGE_IDENTITY_MISMATCH');
 if(!Array.isArray(data.refusals) || data.refusals.some(reason=>!text(reason))) return refuse('RANGE_SHAPE_UNAVAILABLE');
 if(data.status === 'refused') return refuse(data.refusals.join(' · ') || 'RANGE_REFUSED');
 if(!['ok','partial'].includes(data.status)) return refuse('RANGE_SHAPE_UNAVAILABLE');
 if(!/^[a-f0-9]{64}$/.test(data.content_digest || '') || data.record_id !== 'rga1-'+data.content_digest.slice(0,24)) return refuse('RANGE_IDENTITY_MISMATCH');
 const axes=data.axes,expiries=axes?.expiries,strikes=axes?.strike_keys;
 if(!Array.isArray(expiries) || !expiries.length || !Array.isArray(strikes) || !strikes.length
  || !count(axes.n_strikes) || axes.n_strikes !== strikes.length
  || strikes.some((key,i)=>!text(key) || !Number.isFinite(Number(key)) || Number(key)<=0 || (i>0 && Number(key)<=Number(strikes[i-1])))
  || expiries.some((row,i)=>!date(row?.expiry) || !count(row.dte) || row.dte<minDte || row.dte>maxDte
    || (Date.parse(row.expiry)-Date.parse(data.query.as_of_ny))/86400000 !== row.dte
    || (i>0 && row.dte<=expiries[i-1].dte))) return refuse('RANGE_AXES_UNAVAILABLE');
 const coverage=data.coverage;
 if(!object(coverage) || typeof coverage.complete !== 'boolean' || typeof coverage.listing_capped !== 'boolean'
  || typeof coverage.lower_edge_observed !== 'boolean' || typeof coverage.upper_edge_observed !== 'boolean'
  || coverage.requested_window?.min_dte !== minDte || coverage.requested_window?.max_dte !== maxDte
  || !['n_listed','n_admitted','n_returned_expiries','n_skipped_expiries','n_contracts'].every(key=>count(coverage[key]))
  || !Array.isArray(coverage.skipped) || coverage.n_skipped_expiries !== coverage.skipped.length
  || coverage.n_admitted !== expiries.length || coverage.n_returned_expiries>coverage.n_admitted
  || coverage.skipped.some(row=>!text(row?.expiry) || !text(row.reason))
  || (coverage.complete && (!coverage.lower_edge_observed || !coverage.upper_edge_observed || coverage.listing_capped
     || coverage.skipped.length>0 || coverage.n_returned_expiries !== coverage.n_admitted))) return refuse('RANGE_COVERAGE_UNAVAILABLE');
 const clocks=data.clocks;
 if(!object(clocks) || !timestamp(clocks.received_at) || (clocks.fetched_at !== null && !timestamp(clocks.fetched_at))
  || (clocks.chain_event_time !== null && !timestamp(clocks.chain_event_time))
  || (clocks.oi_effective_dates !== null && (!Array.isArray(clocks.oi_effective_dates) || clocks.oi_effective_dates.some(value=>!date(value))))
  || !object(clocks.spot) || (clocks.spot.price !== null && (typeof clocks.spot.price !== 'number' || !Number.isFinite(clocks.spot.price) || clocks.spot.price <= 0))
  || !object(data.provenance) || typeof data.provenance.stale !== 'boolean'
  || !text(data.provenance.data_source)) return refuse('RANGE_CLOCKS_UNAVAILABLE');
 const expiryKeys=expiries.map(row=>row.expiry);
 for(const [name,expected] of Object.entries(RANGE_METRICS)) {
  const section=data.grids?.[name],registry=data.metric_registry?.[name];
  if(!object(section) || !object(registry) || section.metric_id !== expected.metric || section.basis !== expected.basis
   || section.formula_version !== 'gex.v2' || !text(section.model) || !text(section.unit)
   || ['metric_id','basis','formula_version','model','unit'].some(key=>section[key] !== registry[key])) return refuse('RANGE_METRIC_UNSUPPORTED');
  if(!['ok','partial','unavailable'].includes(section.status) || !keysEqual(section.cells,expiryKeys)
   || section.n_cells !== expiryKeys.length*strikes.length || !count(section.n_available)
   || section.n_available>section.n_cells || expiryKeys.some(expiry=>!keysEqual(section.cells[expiry],strikes)
     || strikes.some(strike=>section.cells[expiry][strike] !== null
       && (typeof section.cells[expiry][strike] !== 'number' || !Number.isFinite(section.cells[expiry][strike]))))) return refuse('RANGE_GRID_UNAVAILABLE');
  const available=expiryKeys.reduce((sum,expiry)=>sum+strikes.filter(strike=>section.cells[expiry][strike] !== null).length,0);
  if(section.n_available !== available || (section.status === 'unavailable' && available !== 0)) return refuse('RANGE_GRID_UNAVAILABLE');
 }
 return {reason:null,envelope:data};
}

/** UI completeness guard only, not server permission or hash validation.
 * The backend resolves the stored envelope and its actual selected-cell facts. */
export function rangeResearchBlock(context) {
 if(!object(context)) return null;
 const rangeContext = (typeof context.displayMode === 'string' && context.displayMode.startsWith('range-'))
  || ['rangeVersion','rangeRecordId','rangeDigest','rangeMetric','rangeBasis','rangeStatus'].some(key=>context[key] != null)
  || (typeof context.snapshotId === 'string' && context.snapshotId.startsWith('rga1-'));
 if(!rangeContext) return null;
 const block = reason => `RANGE_RESEARCH_UNAVAILABLE: ${reason}`;
 if(context.displayMode !== 'range-replay') return block('only stored range-replay research is available; live reads are not persisted evidence');
 if(context.contextVersion !== 2 || context.page !== 'heatseeker' || context.activePane !== 'gex'
  || context.metric !== 'gex' || context.rangeVersion !== 'range-analytics.v1'
  || !text(context.ticker) || context.ticker !== context.ticker.trim()
  || !text(context.provider) || context.provider.length > 128 || context.provider !== context.provider.trim()
  || !timestamp(context.mapVersion) || !date(context.mapVersion.slice(0,10))
  || (context.sourceWorkspace != null && context.sourceWorkspace !== 'heatseeker')) return block('RANGE_CONTEXT_INVALID');
 if(typeof context.rangeDigest !== 'string' || !/^[a-f0-9]{64}$/.test(context.rangeDigest)
  || typeof context.rangeRecordId !== 'string' || !/^rga1-[a-f0-9]{24}$/.test(context.rangeRecordId)
  || context.rangeRecordId !== 'rga1-'+context.rangeDigest.slice(0,24)
  || context.snapshotId !== context.rangeRecordId) return block('RANGE_IDENTITY_MISMATCH');
 const metric=context.rangeMetric;
 if(metric === 'window') return block('RANGE_WINDOW_UNAVAILABLE');
 if(!['raw_oi','delta_weighted','volume'].includes(metric) || context.overlayMetric !== metric
  || context.rangeBasis !== RANGE_METRICS[metric].basis || context.formula !== 'gex.v2') return block('RANGE_METRIC_MISMATCH');
 if(!['ok','partial'].includes(context.rangeStatus)) return block('RANGE_CELL_UNAVAILABLE');
 const query=context.mapQuery;
 if(!keysEqual(query,['min_dte','max_dte','as_of_ny']) || !count(query.min_dte) || !count(query.max_dte)
  || query.min_dte > query.max_dte || query.max_dte > 365 || !date(query.as_of_ny)) return block('RANGE_QUERY_INVALID');
 const bounds=context.expiryRange;
 if(bounds != null && !(Array.isArray(bounds) && bounds.length === 2
  && ((bounds[0] === null && bounds[1] === null) || (bounds[0] === query.min_dte && bounds[1] === query.max_dte)))) return block('RANGE_SCOPE_MISMATCH');
 const strikes=context.mapStrikes,expiries=context.mapExpiries;
 if(!Array.isArray(strikes) || !strikes.length || strikes.length > 512
  || strikes.some((strike,i)=>typeof strike !== 'number' || !Number.isFinite(strike) || strike <= 0 || (i > 0 && strike <= strikes[i-1]))
  || !Array.isArray(expiries) || !expiries.length || expiries.length > 24
  || expiries.some((expiry,i)=>!date(expiry) || (i > 0 && expiry <= expiries[i-1])
   || (Date.parse(expiry)-Date.parse(query.as_of_ny))/86400000 < query.min_dte
   || (Date.parse(expiry)-Date.parse(query.as_of_ny))/86400000 > query.max_dte)) return block('RANGE_AXES_INVALID');
 if(context.selectedWall !== null || context.selectedContract !== null
  || context.contractResolution !== 'RANGE_CONTRACT_UNAVAILABLE') return block('RANGE_CONTRACT_UNAVAILABLE');
 if(typeof context.selectedStrike !== 'number' || !Number.isFinite(context.selectedStrike)
  || !strikes.includes(context.selectedStrike) || !expiries.includes(context.selectedExpiry)) return block('RANGE_SELECTION_MISMATCH');
 return null;
}

export function rangeSelectionContext(envelope,metric,selection,mode='live') {
 const section=envelope?.grids?.[metric];
 const cell=section?.cells?.[selection?.expiry]?.[selection?.strike];
 const available=section && ['ok','partial'].includes(section.status) && typeof cell === 'number' && Number.isFinite(cell)
  && envelope?.axes?.strike_keys?.includes(String(selection?.strike))
  && envelope?.axes?.expiries?.some(row=>row.expiry === selection?.expiry);
 return {contextVersion:2,page:'heatseeker',sourceWorkspace:'heatseeker',activePane:'gex',ticker:envelope?.symbol || null,
  displayMode:mode==='replay'?'range-replay':'range-live',metric:'gex',overlayMetric:metric,
  rangeRecordId:envelope?.record_id || null,rangeDigest:envelope?.content_digest || null,rangeMetric:metric,
  rangeBasis:section?.basis || null,rangeStatus:section?.status || null,rangeVersion:envelope?.version || null,
  snapshotId:envelope?.record_id || null,mapQuery:envelope?.query || null,mapVersion:envelope?.clocks?.received_at || null,
  provider:envelope?.provenance?.data_source || null,formula:section?.formula_version || null,
  observedAt:envelope?.clocks?.chain_event_time || null,mapStrikes:envelope?.axes?.strike_keys?.map(Number) || [],
  mapExpiries:envelope?.axes?.expiries?.map(row=>row.expiry) || [],
  selectedStrike:available?Number(selection.strike):null,selectedExpiry:available?selection.expiry:null,
  selectedWall:null,selectedContract:null,contractResolution:'RANGE_CONTRACT_UNAVAILABLE',
  confirmationEvidence:[],dte:envelope?`${envelope.query.min_dte}–${envelope.query.max_dte}`:null};
}
