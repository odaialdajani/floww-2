// B08 study registry: every study declares inputs/version/source/unit/
// approximation/replay/instance. Bar-VWAP is labelled approximation; tape-exact
// needs classified sizes. No proxy volume without source.
// B08 ACTUAL INSTANCES (C045-C048): the registry also owns the multi-instance
// model — unique instance IDs, settings schemas validated per declaration,
// and a bridge that computes renderer specs from REAL frames using the
// priceStudies primitives (the ONE indicator engine — no second engine).
import { sma, ema, bollinger } from './priceStudies';

export const STUDIES = {
  sma: { inputs: ['period'], version: 'ma.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  ema: { inputs: ['period'], version: 'ma.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  bb: { inputs: ['period', 'multiple'], version: 'bb.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  vwap: { inputs: ['source', 'bands'], version: 'vwap.v1', source: 'bars', unit: 'price', approximation: 'bar-vwap', replay: true },
  exposureVwap: { inputs: ['scope', 'nodes', 'band', 'envelope'], version: 'gexvwap.v1', source: 'board', unit: 'price', approximation: 'board-weighted', replay: 'cursor-eligible-only' },
};

export function getStudy(name) {
  return STUDIES[name] || null;
}

function intAtLeast(value, min) {
  return typeof value === 'number' && Number.isInteger(value) && value >= min;
}

// Settings schemas (C045): validated against the declaration before any
// instance exists — invalid settings are refused, never coerced into a study.
export function validateStudySettings(name, settings) {
  if (!getStudy(name) || !settings || typeof settings !== 'object') return false;
  if (name === 'sma' || name === 'ema') {
    return intAtLeast(settings.period, 1);
  }
  if (name === 'bb') {
    return intAtLeast(settings.period, 2)
      && typeof settings.multiple === 'number' && Number.isFinite(settings.multiple) && settings.multiple > 0;
  }
  return false;
}

// Unique instance IDs (C045): <study>-<seq> from a module-monotonic counter —
// two instances of the same study never share an id, and the id is persisted
// so a reloaded pane renders the SAME instance, not a regenerated one.
export function createStudyInstance(name, settings, paneKey = '') {
  if (!validateStudySettings(name, settings)) throw new Error('invalid study settings');
  createStudyInstance._seq = (createStudyInstance._seq || 0) + 1;
  return { id: `${name}-${createStudyInstance._seq}`, study: name, settings: { ...settings }, paneKey: String(paneKey || ''), created: Date.now() };
}

function closeOf(frame) {
  const c = frame?.close;
  return typeof c === 'number' && Number.isFinite(c) ? c : NaN;
}

// Renderer specs for the actual chart: gap-segmented {time, value} points per
// line, computed from the pane's OWN frames via the existing primitives.
// A non-finite close refuses the whole series (complete-sample semantics,
// C047) — the renderer then draws nothing for that instance: no fabricated
// windows, no zero substitution.
export function studySpecs(instance, frames) {
  if (!instance || !validateStudySettings(instance.study, instance.settings)) return [];
  const list = Array.isArray(frames) ? frames : [];
  const closes = list.map(closeOf);
  const times = list.map(f => (typeof f?.time === 'string' ? f.time : null));
  const pointsOf = values => values.map((v, i) => ({ time: times[i], value: v }));
  const base = { instanceId: instance.id, study: instance.study };
  if (instance.study === 'sma') {
    return [{ ...base, id: instance.id, band: null, label: `SMA ${instance.settings.period}`, points: pointsOf(sma(closes, instance.settings.period)) }];
  }
  if (instance.study === 'ema') {
    return [{ ...base, id: instance.id, band: null, label: `EMA ${instance.settings.period}`, points: pointsOf(ema(closes, instance.settings.period)) }];
  }
  if (instance.study === 'bb') {
    const bands = bollinger(closes, instance.settings.period, instance.settings.multiple);
    const label = `BB ${instance.settings.period} · ${instance.settings.multiple}σ`;
    const mean = bands.map(b => (b ? b.mean : null));
    const upper = bands.map(b => (b ? b.upper : null));
    const lower = bands.map(b => (b ? b.lower : null));
    return [
      { ...base, id: `${instance.id}-mean`, band: 'mean', label, points: pointsOf(mean) },
      { ...base, id: `${instance.id}-upper`, band: 'upper', label, points: pointsOf(upper) },
      { ...base, id: `${instance.id}-lower`, band: 'lower', label, points: pointsOf(lower) },
    ];
  }
  return [];
}
