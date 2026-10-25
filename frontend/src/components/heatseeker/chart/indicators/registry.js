// B08 study registry: every study declares inputs/version/source/unit/
// approximation/replay/instance. Bar-VWAP is labelled approximation; tape-exact
// needs classified sizes. No proxy volume without source.
// B08 ACTUAL INSTANCES (b08_registry_contract v2, 2026-10-25): the registry
// owns the multi-instance model — the six contract kinds (sma, ema, bollinger,
// volume, vwap, exposure-vwap), per-declaration settings schemas WITH BOUNDS,
// pane source-eligibility with typed refusals, and a bridge that computes
// renderer specs from REAL frames using the priceStudies primitives — the
// ONE indicator engine. The registry NEVER re-implements math.
import { sma, ema, bollinger, sessionVwapValues, sessionVwapBands } from './priceStudies';

// Legacy fixed-import declarations stay byte-compatible for existing callers.
export const STUDIES = {
  sma: { inputs: ['period'], version: 'ma.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  ema: { inputs: ['period'], version: 'ma.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  bollinger: { inputs: ['period', 'multiple'], version: 'bb.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  volume: { inputs: [], version: 'volume.v1', source: 'bars', unit: 'volume', approximation: 'none', replay: true },
  vwap: { inputs: ['source', 'bands'], version: 'vwap.v1', source: 'bars', unit: 'price', approximation: 'bar-vwap', replay: true },
  'exposure-vwap': { inputs: ['scope', 'nodes', 'band', 'envelope'], version: 'gexvwap.v1', source: 'board', unit: 'price', approximation: 'board-weighted', replay: 'cursor-eligible-only' },
};
// Legacy declaration name kept as an ALIAS for the pre-contract import path
// (RecordedPriceChart/AtlasChart lookups); the contract kind is
// 'exposure-vwap' and only that vocabulary is CREATABLE as an instance.
STUDIES.exposureVwap = STUDIES['exposure-vwap'];

export function getStudy(name) {
  return STUDIES[name] || null;
}

function intBetween(value, min, max) {
  return typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;
}

// Settings schemas per kind (contract v2): MA periods integer 1..500;
// bollinger period 10..500 + multiple 0.5..5; vwap source/bandBasis/multipliers
// with at most 3 band pairs (bands off by default, C116); volume {}.
export function validateStudySettings(name, settings) {
  if (!getStudy(name) || !settings || typeof settings !== 'object') return false;
  if (name === 'sma' || name === 'ema') return intBetween(settings.period, 1, 500);
  if (name === 'bollinger') {
    return intBetween(settings.period, 10, 500)
      && typeof settings.multiple === 'number' && Number.isFinite(settings.multiple)
      && settings.multiple >= 0.5 && settings.multiple <= 5;
  }
  if (name === 'volume') return Object.keys(settings).length === 0;
  if (name === 'vwap') {
    const sources = ['hlc3', 'close'];
    const bases = ['std', 'percent'];
    if (!sources.includes(settings.source) || !bases.includes(settings.bandBasis)) return false;
    if (!Array.isArray(settings.multipliers) || settings.multipliers.length < 1 || settings.multipliers.length > 3) return false;
    if (!settings.multipliers.every(m => typeof m === 'number' && Number.isFinite(m) && m >= 0.5 && m <= 5)) return false;
    if (typeof settings.bands !== 'boolean') return false;
    return true;
  }
  if (name === 'exposure-vwap') return false; // not creatable on the price pane (no board source)
  return false;
}

// Unique instance ids (C045): <kind>-<seq> from a module-monotonic counter —
// two instances never share an id; the id is PERSISTED so a reloaded pane
// renders the SAME instance, not a regenerated one. Full contract shape:
// { instanceId, kind, settings, source, visible, order } (paneKey/created are
// additive provenance fields the store preserves verbatim).
export function createStudyInstance(kind, settings, paneKey = '') {
  if (!validateStudySettings(kind, settings)) throw new Error('invalid study settings');
  createStudyInstance._seq = (createStudyInstance._seq || 0) + 1;
  const source = kind === 'vwap' ? (settings.source || 'hlc3') : 'close';
  return {
    instanceId: `${kind}-${createStudyInstance._seq}`,
    kind,
    settings: { ...settings },
    source,
    visible: true,
    order: createStudyInstance._seq,
    paneKey: String(paneKey || ''),
    created: Date.now(),
  };
}

function closeOf(frame) {
  const c = frame?.close;
  return typeof c === 'number' && Number.isFinite(c) ? c : NaN;
}

// Pane source-eligibility (contract v2): an instance is creatable only on a
// pane whose frames satisfy the kind. Typed refusal reasons — never zeros.
export function paneEligibility(kind, frames) {
  const list = Array.isArray(frames) ? frames : [];
  if (!getStudy(kind)) return { ok: false, reason: 'unsupported study kind' };
  if (kind === 'sma' || kind === 'ema' || kind === 'bollinger') {
    const hasClose = list.some(f => typeof f?.close === 'number' && Number.isFinite(f.close));
    return hasClose ? { ok: true, reason: null } : { ok: false, reason: 'no finite close on this pane' };
  }
  if (kind === 'vwap' || kind === 'volume') {
    const hasVolume = list.some(f => typeof f?.volume === 'number' && Number.isFinite(f.volume));
    return hasVolume ? { ok: true, reason: null } : { ok: false, reason: 'no finite volume on this pane' };
  }
  if (kind === 'exposure-vwap') {
    // C051/C112-C114: needs per-minute ELIGIBLE boards; the price pane has
    // no board source — declared but never creatable here, with the typed reason.
    return { ok: false, reason: 'no eligible board source on the price pane' };
  }
  return { ok: false, reason: 'unsupported study kind' };
}

// Renderer specs for the actual chart: gap-segmented {time, value} points per
// line, computed from the pane's OWN frames via the existing primitives.
// A non-finite close refuses the whole MA series (complete-sample semantics,
// C047) — the renderer then draws nothing for that instance: no fabricated
// windows, no zero substitution. Volume is a RECORD instance (eligibility +
// persistence only — measured volume already renders in the chart's
// volume-gated layers with C049 gap honesty; no volume line on the price axis).
export function studySpecs(instance, frames) {
  if (!instance || !validateStudySettings(instance.kind, instance.settings)) return [];
  const list = Array.isArray(frames) ? frames : [];
  const closes = list.map(closeOf);
  const times = list.map(f => (typeof f?.time === 'string' ? f.time : null));
  const pointsOf = values => values.map((v, i) => ({ time: times[i], value: v }));
  const base = { instanceId: instance.instanceId, study: instance.kind };
  if (instance.kind === 'sma') {
    return [{ ...base, id: instance.instanceId, band: null, label: `SMA ${instance.settings.period}`, points: pointsOf(sma(closes, instance.settings.period)) }];
  }
  if (instance.kind === 'ema') {
    return [{ ...base, id: instance.instanceId, band: null, label: `EMA ${instance.settings.period}`, points: pointsOf(ema(closes, instance.settings.period)) }];
  }
  if (instance.kind === 'bollinger') {
    const bands = bollinger(closes, instance.settings.period, instance.settings.multiple);
    const label = `BB ${instance.settings.period} · ${instance.settings.multiple}σ`;
    return [
      { ...base, id: `${instance.instanceId}-mean`, band: 'mean', label, points: pointsOf(bands.map(b => (b ? b.mean : null))) },
      { ...base, id: `${instance.instanceId}-upper`, band: 'upper', label, points: pointsOf(bands.map(b => (b && b.upper !== null ? b.upper : null))) },
      { ...base, id: `${instance.instanceId}-lower`, band: 'lower', label, points: pointsOf(bands.map(b => (b && b.lower !== null ? b.lower : null))) },
    ];
  }
  if (instance.kind === 'vwap') {
    // The EXISTING session engine: HLC3/Close source, NY-session reset,
    // zero-weight unavailable, bands off by default (C116).
    const values = sessionVwapValues(list, { source: instance.settings.source, bandBasis: instance.settings.bandBasis, multipliers: instance.settings.multipliers });
    const specs = [{ ...base, id: `${instance.instanceId}-vwap`, band: null, label: `VWAP ${instance.settings.source}`, points: pointsOf(values) }];
    if (instance.settings.bands) {
      const bands = sessionVwapBands(list, { source: instance.settings.source, bandBasis: instance.settings.bandBasis, multipliers: instance.settings.multipliers });
      specs.push({ ...base, id: `${instance.instanceId}-upper`, band: 'upper', label: 'VWAP band', points: bands.map((b, i) => ({ time: times[i], value: b ? (b[0]?.upper ?? null) : null })) });
      specs.push({ ...base, id: `${instance.instanceId}-lower`, band: 'lower', label: 'VWAP band', points: bands.map((b, i) => ({ time: times[i], value: b ? (b[b.length - 1]?.lower ?? null) : null })) });
    }
    return specs;
  }
  if (instance.kind === 'volume') return [];
  return [];
}
