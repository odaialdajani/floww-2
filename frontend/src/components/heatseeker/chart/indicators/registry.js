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
import { anchoredVwapValues, anchoredVwapBands } from './anchorStudies';

// Legacy fixed-import declarations stay byte-compatible for existing callers.
export const STUDIES = {
  sma: { inputs: ['period'], version: 'ma.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  ema: { inputs: ['period'], version: 'ma.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  bollinger: { inputs: ['period', 'multiple'], version: 'bb.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  volume: { inputs: [], version: 'volume.v1', source: 'bars', unit: 'volume', approximation: 'none', replay: true, paneControl: 'volume-pane' },
  // C050 (c050_vwap_anchor_contract v1.0): the anchor input is added to the
  // vwap kind; version moves to vwap.v2. Persisted vwap.v1 rows (settings
  // without an anchor) stay loadable — 'session' is the default and is
  // byte-compatible with the existing engine behavior.
  vwap: { inputs: ['source', 'bands', 'anchor'], version: 'vwap.v2', source: 'bars', unit: 'price', approximation: 'bar-vwap', replay: true },
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
// C050: the vwap anchor enum ['session','week','month','quarter','year'],
// default 'session' (byte-compatible with every persisted vwap.v1 row — an
// absent anchor validates as session); out-of-enum anchors are refused
// BEFORE any instance exists.
const VWAP_ANCHORS = ['session', 'week', 'month', 'quarter', 'year'];
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
    const anchor = settings.anchor === undefined ? 'session' : settings.anchor;
    if (!VWAP_ANCHORS.includes(anchor)) return false;
    return true;
  }
  if (name === 'exposure-vwap') return false; // not creatable on the price pane (no board source)
  return false;
}

// C046: named factory presets — the discoverable defaults the panel offers
// as one-click rows (EMA 9 is the row's explicit demand). Every preset is
// valid per the schema above.
export const STUDY_PRESETS = {
  'EMA 9': { kind: 'ema', settings: { period: 9 } },
  'SMA 20': { kind: 'sma', settings: { period: 20 } },
  'Bollinger 20 · 2σ': { kind: 'bollinger', settings: { period: 20, multiple: 2 } },
  'VWAP · session': { kind: 'vwap', settings: { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], bands: false, anchor: 'session' } },
};

// Volume is a REAL pane control, not a dead record: the measured volume pane
// already renders in the chart's volume-gated layers with C049 gap honesty —
// a volume INSTANCE means the pane is ON. H1 binds this mapping to the real
// pane's visibility; studySpecs(volume) stays [] (never a price-axis line).
export const PANE_CONTROLS = { volume: 'volume-pane' };

// Unique instance ids (C045): `<kind>-<seq>` alone identified an instance
// only within ONE module lifetime — a reload restarts the counter at 1 while
// persisted instances keep their ids, so a fresh module re-minted an id a
// restored row already owned (and the caller's update/remove by id then hit
// BOTH rows). The mint therefore carries a per-module-lifetime token: unique
// within a module by seq, unique across module lifetimes by token, and never
// equal to a legacy short id because every fresh mint carries the suffix.
// The id is PERSISTED so a reloaded pane renders the SAME instance, not a
// regenerated one. Full contract shape:
// { instanceId, kind, settings, source, visible, order } (paneKey/created are
// additive provenance fields the store preserves verbatim).
const MODULE_MINT_TOKEN = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8).padEnd(6, '0')}`;

export function createStudyInstance(kind, settings, paneKey = '') {
  if (!validateStudySettings(kind, settings)) throw new Error('invalid study settings');
  createStudyInstance._seq = (createStudyInstance._seq || 0) + 1;
  const source = kind === 'vwap' ? (settings.source || 'hlc3') : 'close';
  return {
    instanceId: `${kind}-${createStudyInstance._seq}-${MODULE_MINT_TOKEN}`,
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
    // The EXISTING session engine generalized by the anchor input (C050):
    // 'session' is the unchanged engine path; week/month/quarter/year use
    // the SAME sessionVwap math per period group (anchorStudies — one engine).
    const anchor = instance.settings.anchor === undefined ? 'session' : instance.settings.anchor;
    const opts = { source: instance.settings.source, bandBasis: instance.settings.bandBasis, multipliers: instance.settings.multipliers, anchor };
    const values = anchoredVwapValues(list, opts);
    const specs = [{ ...base, id: `${instance.instanceId}-vwap`, band: null, label: `VWAP ${instance.settings.source} · ${anchor}`, points: pointsOf(values) }];
    if (instance.settings.bands) {
      // EVERY selected multiplier pair is plotted (C116 fix — the old bridge
      // returned only the FIRST upper and the LAST lower, so a [1,2,3]
      // instance rendered 2 lines instead of 6). One upper + one lower spec
      // PER multiplier, each id'd and labeled by its own multiplier.
      const bands = anchoredVwapBands(list, opts);
      const perFrame = (pick) => bands.map((b, i) => ({ time: times[i], value: b ? pick(b) : null }));
      for (const m of instance.settings.multipliers) {
        const mStr = String(m);
        specs.push({ ...base, id: `${instance.instanceId}-upper-${mStr}`, band: 'upper', multiplier: m, label: `VWAP band ${mStr}${instance.settings.bandBasis === 'percent' ? '%' : 'σ'}`, points: perFrame((pairs) => {
          const pair = pairs.find((p) => p && p.m === m);
          return pair && Number.isFinite(pair.upper) ? pair.upper : null;
        }) });
        specs.push({ ...base, id: `${instance.instanceId}-lower-${mStr}`, band: 'lower', multiplier: m, label: `VWAP band ${mStr}${instance.settings.bandBasis === 'percent' ? '%' : 'σ'}`, points: perFrame((pairs) => {
          const pair = pairs.find((p) => p && p.m === m);
          return pair && Number.isFinite(pair.lower) ? pair.lower : null;
        }) });
      }
    }
    return specs;
  }
  if (instance.kind === 'volume') return [];
  return [];
}
