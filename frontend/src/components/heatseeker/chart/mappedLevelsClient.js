// B09 mapped-levels client (b09_mapped_levels_contract v2): the caller half
// of the cross-INSTRUMENT source->target price mapping. The backend route is
// the ONE ratio authority (direction, provenance, eligibility); this module
// only requests, strictly parses and refuses — it NEVER computes a ratio and
// NEVER substitutes naked-levels claims for mapped levels.
//
// Route (contract): GET /api/heatseeker/mapped-levels/{target_ticker}?source={source_ticker}&cursor={epoch-seconds}&scope={scenario-scope-id}

// CHART-C040 validated families. Futures (ES/NQ) and GLD/SLV/DIA/IWM pairs
// stay OFF the selectable list until the validated mapping exists — absent
// one the pair stays refused, never a guessed ratio.
const FAMILY_SOURCES = {
  SPY: ['SPXW', 'SPX'],
  QQQ: ['NDXP', 'NDX'],
};

export function eligibleMappedPairsFor(target) {
  const list = FAMILY_SOURCES[String(target || '').toUpperCase()];
  return Array.isArray(list) ? list.slice() : [];
}

export function MAPPED_SOURCE_OPTIONS() {
  const families = { SPXW: 'SPX family', SPX: 'SPX family', NDXP: 'NDX family', NDX: 'NDX family' };
  const all = Object.values(FAMILY_SOURCES).flat();
  return all.map(source => ({ value: source, family: families[source] || '' }));
}

const REFUSALS = [
  'unsupported-pair',
  'source-not-eligible',
  'ratio-unavailable-at-cursor',
  'no-shared-session',
  'cursor-not-in-regular-session',
  'spxw-board-combination-unavailable',
];

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

// Strict parse of the route body. Available bodies must carry a finite ratio
// with provenance whose known_at is AT-OR-BEFORE the cursor (no-lookahead is
// enforced client-side too), levels with finite mapped_price, and BOTH shape
// kinds in the legend. Anything malformed or contradictory -> unavailable /
// the typed refusal — partial data never renders.
export function parseMappedLevelsResponse(body, cursor) {
  if (!body || typeof body !== 'object') return { status: 'unavailable', reason: 'no mapped-levels body', shapes: [], legend: null, ratio: null };
  if (body.status === 'refused') {
    if (!REFUSALS.includes(body.reason)) return { status: 'unavailable', reason: 'unknown refusal vocabulary', shapes: [], legend: null, ratio: null };
    return { status: 'refused', reason: body.reason, shapes: [], legend: null, ratio: null };
  }
  if (body.status === 'unavailable') {
    return { status: 'unavailable', reason: typeof body.reason === 'string' ? body.reason : 'unavailable', shapes: [], legend: null, ratio: null };
  }
  if (typeof body.status === 'string' && body.status !== 'available') {
    return { status: 'unavailable', reason: 'unknown status vocabulary', shapes: [], legend: null, ratio: null };
  }
  // Available shape per the contract: the body carries target/source/ratio/
  // levels/legend directly (a status field is optional on this path).
  if (!Array.isArray(body.levels) || !body.ratio || typeof body.ratio !== 'object') {
    return { status: 'unavailable', reason: 'malformed mapped-levels body', shapes: [], legend: null, ratio: null };
  }
  const ratioValue = finiteNumber(body.ratio?.value);
  const knownAt = finiteNumber(body.ratio?.provenance?.known_at);
  const cursorNum = finiteNumber(cursor);
  if (ratioValue === null || knownAt === null || cursorNum === null || knownAt > cursorNum) {
    return { status: 'refused', reason: 'ratio-unavailable-at-cursor', shapes: [], legend: null, ratio: null };
  }
  const legend = body.legend && typeof body.legend === 'object' && typeof body.legend.diamond === 'string' && typeof body.legend.triangle === 'string'
    ? { diamond: body.legend.diamond, triangle: body.legend.triangle } : null;
  const levels = Array.isArray(body.levels) ? body.levels : [];
  const shapes = [];
  for (const level of levels) {
    const price = finiteNumber(level?.mapped_price);
    const kind = level?.kind === 'diamond' || level?.kind === 'triangle' ? level.kind : null;
    if (price === null || kind === null || typeof level?.label !== 'string') {
      return { status: 'unavailable', reason: 'malformed level entry', shapes: [], legend, ratio: null };
    }
    shapes.push({ price, kind, label: level.label, sourcePrice: finiteNumber(level.source_price) });
  }
  if (!legend) return { status: 'unavailable', reason: 'legend missing from response', shapes: [], legend: null, ratio: null };
  return {
    status: 'available',
    shapes,
    legend,
    ratio: { value: ratioValue, knownAt, provenance: body.ratio.provenance },
    cursor: finiteNumber(body.cursor),
    session: typeof body.session === 'string' ? body.session : null,
  };
}
