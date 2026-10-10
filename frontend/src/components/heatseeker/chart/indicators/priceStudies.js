// B08 price studies: MA + qualified VWAP + exposure-VWAP (Atlas exact copy).
// Recorded-only. Missing stays gap, never carry. Exposure-VWAP is board-weighted,
// price VWAP is volume-weighted. Opening envelope needs 8 measured minutes and
// freezes; session envelope only widens.
export function sma(values, period) {
  const out = new Array(values.length).fill(null);
  if (period < 1) return out;
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    const v = values[i];
    if (typeof v !== 'number' || !Number.isFinite(v)) return new Array(values.length).fill(null);
    sum += v;
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

export function ema(values, period) {
  const out = new Array(values.length).fill(null);
  if (period < 1 || !values.length) return out;
  const k = 2 / (period + 1);
  let prev = null;
  for (let i = 0; i < values.length; i += 1) {
    const v = values[i];
    if (typeof v !== 'number' || !Number.isFinite(v)) return new Array(values.length).fill(null);
    prev = prev === null ? v : v * k + prev * (1 - k);
    out[i] = i >= period - 1 ? prev : null;
  }
  return out;
}

function sessionDay(time) {
  const d = new Date(time);
  if (!Number.isFinite(d.valueOf())) return null;
  return d.toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
}

// Multi-session VWAP values aligned to input frames: cumulative Σ(hlc3·v)/Σv
// resetting at each New York session open. Missing volume yields null (gap);
// zero volume with history holds the last value. Never fabricates.
export function sessionVwapValues(frames, opts = {}) {
  const out = new Array((frames || []).length).fill(null);
  let day = null, group = [], at = [];
  const flush = () => {
    if (!group.length) return;
    sessionVwap(group, opts).forEach((r, i) => { out[at[i]] = r.vwap; });
    group = []; at = [];
  };
  (frames || []).forEach((bar, i) => {
    const key = sessionDay(bar?.time);
    if (key === null) { out[i] = null; return; }
    if (day !== null && key !== day) flush();
    day = key; group.push(bar); at.push(i);
  });
  flush();
  return out;
}

// Aligned per-frame band sets for the chart (null where unavailable).
export function sessionVwapBands(frames, opts = {}) {
  const out = new Array((frames || []).length).fill(null);
  let day = null, group = [], at = [];
  const flush = () => {
    if (!group.length) return;
    sessionVwap(group, opts).forEach((r, i) => { out[at[i]] = r.bands; });
    group = []; at = [];
  };
  (frames || []).forEach((bar, i) => {
    const key = sessionDay(bar?.time);
    if (key === null) { out[i] = null; return; }
    if (day !== null && key !== day) flush();
    day = key; group.push(bar); at.push(i);
  });
  flush();
  return out;
}

function barPrice(bar, source) {
  if (!bar) return null;
  if (source === 'close') {
    return typeof bar.close === 'number' && Number.isFinite(bar.close) ? bar.close : null;
  }
  const { high, low, close } = bar;
  if ([high, low, close].some((v) => typeof v !== 'number' || !Number.isFinite(v))) return null;
  return (high + low + close) / 3;
}

// Session-anchored price VWAP with bands. Zero weight => unavailable, not zero.
// Bands carry real values: volume-weighted sigma (std) or fixed percent.
export function sessionVwap(bars, { source = 'hlc3', bandBasis = 'std', multipliers = [1, 2, 3] } = {}) {
  let cumPV = 0, cumPV2 = 0, cumV = 0;
  const bandsFor = (vwap) => {
    if (vwap === null || !multipliers?.length) return null;
    return multipliers.map((m) => {
      if (bandBasis === 'percent') {
        return { m, basis: bandBasis, upper: vwap * (1 + m / 100), lower: vwap * (1 - m / 100) };
      }
      const variance = Math.max(0, cumPV2 / cumV - vwap * vwap);
      const sigma = Math.sqrt(variance);
      return { m, basis: bandBasis, upper: vwap + m * sigma, lower: vwap - m * sigma };
    });
  };
  return (bars || []).map((bar) => {
    const price = barPrice(bar, source);
    const vol = typeof bar?.volume === 'number' && Number.isFinite(bar.volume) ? bar.volume : null;
    if (price === null || vol === null) return { vwap: null, bands: null, reason: 'unavailable' };
    if (vol === 0) {
      const held = cumV ? cumPV / cumV : null;
      return { vwap: held, bands: held === null ? null : bandsFor(held), reason: cumV ? 'ok' : 'unavailable' };
    }
    cumPV += price * vol;
    cumPV2 += price * price * vol;
    cumV += vol;
    if (!cumV) return { vwap: null, bands: null, reason: 'unavailable' };
    const vwap = cumPV / cumV;
    return { vwap, bands: bandsFor(vwap), reason: 'ok' };
  });
}

// Exposure-VWAP: per-minute eligible boards only. No board => gap object, never prior carry.
export function exposureVwap(minuteBoards, { band = true, envelope = 'off', openingMinutes = 15 } = {}) {
  const centres = [];
  let sessionHigh = null, sessionLow = null;
  let openingVals = [];
  return (minuteBoards || []).map((board, i) => {
    if (!board || board.eligible !== true || typeof board.centre !== 'number' || !Number.isFinite(board.centre)) {
      centres.push(null);
      return { centre: null, gap: true };
    }
    centres.push(board.centre);
    const upper = band ? board.upper ?? null : null;
    const lower = band ? board.lower ?? null : null;
    if (envelope === 'session') {
      sessionHigh = sessionHigh === null ? board.centre : Math.max(sessionHigh, board.centre);
      sessionLow = sessionLow === null ? board.centre : Math.min(sessionLow, board.centre);
    }
    if (envelope === 'opening') {
      if (i < openingMinutes) openingVals.push(board.centre);
      if (openingVals.length < 8) return { centre: board.centre, upper, lower, envelope: null, frozen: false };
      if (i >= openingMinutes) return { centre: board.centre, upper, lower, envelope: { high: Math.max(...openingVals), low: Math.min(...openingVals) }, frozen: true };
      return { centre: board.centre, upper, lower, envelope: null, frozen: false };
    }
    if (envelope === 'session') {
      return { centre: board.centre, upper, lower, envelope: { high: sessionHigh, low: sessionLow }, frozen: false };
    }
    return { centre: board.centre, upper, lower };
  });
}
