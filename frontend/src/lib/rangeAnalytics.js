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
  || !Array.isArray(clocks.oi_effective_dates) || clocks.oi_effective_dates.some(value=>!date(value))
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

export function rangeSelectionContext(envelope,metric,selection,mode='live') {
 const section=envelope?.grids?.[metric];
 const available=section && section.status !== 'unavailable' && typeof section.cells?.[selection?.expiry]?.[selection?.strike] === 'number';
 return {contextVersion:2,page:'heatseeker',sourceWorkspace:'heatseeker',ticker:envelope?.symbol || null,
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
