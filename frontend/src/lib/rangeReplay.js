import {admitRangeEnvelope} from './rangeAnalytics';

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const count = value => Number.isSafeInteger(value) && value >= 0;
const text = value => typeof value === 'string' && value.trim().length > 0;
const date = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
 && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
const timestamp = value => typeof value === 'string'
 && /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
 && date(value.slice(0,10)) && Number.isFinite(Date.parse(value));
const status = value => value === 'ok' || value === 'partial';
const research = {researchOnly:true, qualification:'pending'};
const refusal = (body,fallback) => text(body?.reason) ? body.reason : text(body?.error) ? body.error : fallback;
const owningQuery = ({symbol,minDte,maxDte,asOf}) => text(symbol) && symbol === symbol.trim()
 && count(minDte) && count(maxDte) && minDte <= maxDte && maxDte <= 365
 && (asOf == null || asOf === '' || date(asOf));
const identity = row => object(row) && /^[a-f0-9]{64}$/.test(row.digest || '')
 && row.record_id === 'rga1-'+row.digest.slice(0,24);
const header = (row,{symbol,minDte,maxDte,asOf}) => identity(row)
 && row.ticker === symbol && object(row.window)
 && row.window.min_dte === minDte && row.window.max_dte === maxDte
 && date(row.asof_date) && (!asOf || row.asof_date === asOf)
 && status(row.status) && timestamp(row.received_at) && timestamp(row.recorded_at)
 && row.integrity === 'verified';
const chronological = (a,b) => Date.parse(a.received_at)-Date.parse(b.received_at)
 || (a.record_id < b.record_id ? -1 : a.record_id > b.record_id ? 1 : 0);

/** Stored-page shape/identity admission only. Producer-reported integrity is
 * necessary here, but is NOT a cryptographic or production qualification. */
export function admitRangeIndex(body,{symbol,minDte,maxDte,asOf}={}) {
 const refuse = reason => ({...research,reason,rows:null,page:null});
 const query={symbol,minDte,maxDte,asOf};
 if(!owningQuery(query)) return refuse('RANGE_QUERY_INVALID');
 if(body?.version !== 'range-records.v1') return refuse('RANGE_RECORDS_VERSION_UNSUPPORTED');
 if(body.status !== 'ok' || body.error || body.reason) return refuse(refusal(body,'RANGE_INDEX_REFUSED'));
 const filters=body.filters;
 if(!object(filters) || filters.ticker !== symbol || filters.min_dte !== minDte || filters.max_dte !== maxDte
  || filters.as_of !== (asOf || null) || (filters.status !== null && !status(filters.status))) return refuse('RANGE_INDEX_FILTER_MISMATCH');
 if(!count(body.limit) || body.limit < 1 || body.limit > 200 || !count(body.offset)
  || !count(body.n_returned) || !Array.isArray(body.rows) || body.n_returned !== body.rows.length
  || body.n_returned > body.limit) return refuse('RANGE_INDEX_PAGE_INVALID');
 const ids=new Set();
 for(const row of body.rows) {
  if(!header(row,query) || (row.synthetic !== null && typeof row.synthetic !== 'boolean')
   || (filters.status !== null && row.status !== filters.status)) return refuse('RANGE_INDEX_ROW_INVALID');
  if(ids.has(row.record_id)) return refuse('RANGE_DUPLICATE_IDENTITY');
  ids.add(row.record_id);
 }
 return {...research,reason:null,rows:[...body.rows].sort(chronological),
  page:{limit:body.limit,offset:body.offset,nReturned:body.n_returned,mayHaveMore:body.n_returned === body.limit}};
}

function populationsHaveNumericCounts(envelope) {
 for(const section of Object.values(envelope.grids)) {
  if(!object(section) || !count(section.usable) || !count(section.cell_gaps) || section.cell_gaps !== section.n_cells-section.n_available
   || section.metric_admitted !== (section.status === 'ok') || !object(section.population)
   || !count(section.population.input_contracts) || !count(section.population.usable)
   || section.population.usable > section.population.input_contracts || section.usable !== section.population.usable) return false;
  for(const [key,value] of Object.entries(section.population)) {
   // The producer's BS-population annotation is prose, not an exclusion count.
   if(key !== 'zero_oi_or_excluded_by_kernel' && !count(value)) return false;
  }
  for(const key of ['missing_delta','invalid_delta','invalid_mult','quarantined','invalid_type','missing_volume']) {
   if(Object.hasOwn(section,key) && !count(section[key])) return false;
  }
  for(const key of ['cell_missing_delta','cell_invalid_delta']) {
   if(!Object.hasOwn(section,key)) continue;
   if(!object(section[key]) || Object.values(section[key]).some(row => !object(row) || Object.values(row).some(value=>!count(value)))) return false;
  }
 }
 return true;
}

function metadataHasNumericCounts(envelope) {
 const nullableCount = value => value == null || count(value);
 for(const key of ['bid_timestamps_present','ask_timestamps_present']) {
  const value=envelope.clocks[key];
  if(!count(value) || value > envelope.coverage.n_contracts) return false;
 }
 for(const key of ['n_expired_dropped','attempt_cap']) {
  if(!nullableCount(envelope.coverage[key])) return false;
 }
 const budget=envelope.coverage.budget;
 if(budget != null && (!object(budget) || !nullableCount(budget.pre_debit))) return false;
 const grounding=envelope.grounding;
 if(grounding != null) {
  if(!object(grounding) || !object(grounding.contract_population)) return false;
  for(const [expiry,population] of Object.entries(grounding.contract_population)) {
   if(!date(expiry) || !object(population) || !['n_contracts','n_call','n_put'].every(key=>count(population[key]))
    || population.n_call+population.n_put > population.n_contracts) return false;
  }
 }
 return true;
}

/** Restore actual stored cells using existing range shape admission and strict
 * transport/header cross-checks. Never recomputes Greeks or the content hash. */
export function admitRangeRecord(body,{symbol,minDte,maxDte,asOf,recordId}={}) {
 const refuse = reason => ({...research,reason,envelope:null});
 const query={symbol,minDte,maxDte,asOf};
 if(!owningQuery(query) || !/^rga1-[a-f0-9]{24}$/.test(recordId || '')) return refuse('RANGE_QUERY_INVALID');
 if(body?.version !== 'range-records.v1') return refuse('RANGE_RECORDS_VERSION_UNSUPPORTED');
 if(!status(body.status) || body.error || body.reason) return refuse(refusal(body,'RANGE_RECORD_REFUSED'));
 if(!header(body,query) || body.record_id !== recordId) return refuse('RANGE_RECORD_HEADER_INVALID');
 const envelope=body.envelope;
 if(!object(envelope) || envelope.content_schema !== 'rga-content.v3') return refuse('RANGE_CONTENT_SCHEMA_UNSUPPORTED');
 const admitted=admitRangeEnvelope(envelope,{...query,recordId});
 if(admitted.reason) return refuse(admitted.reason);
 if(body.record_id !== envelope.record_id || body.digest !== envelope.content_digest || body.ticker !== envelope.symbol
  || body.window.min_dte !== envelope.query.min_dte || body.window.max_dte !== envelope.query.max_dte
  || body.asof_date !== envelope.query.as_of_ny || body.status !== envelope.status
  || body.received_at !== envelope.clocks.received_at || typeof envelope.synthetic !== 'boolean'
  || (Object.hasOwn(body,'synthetic') && body.synthetic !== envelope.synthetic)) return refuse('RANGE_RECORD_HEADER_MISMATCH');
 if(!populationsHaveNumericCounts(envelope)) return refuse('RANGE_POPULATION_SHAPE_UNAVAILABLE');
 if(!metadataHasNumericCounts(envelope)) return refuse('RANGE_METADATA_COUNTS_UNAVAILABLE');
 // Preserve stored evidence verbatim. The unbound `metrics` summary must
 // not confer admission: callers render recorded grids/axes/clocks only.
 return {...research,reason:null,envelope};
}
