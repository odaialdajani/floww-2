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
export function sessionVwap(bars, { source = 'hlc3', bandBasis = 'std', multipliers = [1, 2, 3] } = {}) {
  let cumPV = 0, cumV = 0;
  return (bars || []).map((bar) => {
    const price = barPrice(bar, source);
    const vol = typeof bar?.volume === 'number' && Number.isFinite(bar.volume) ? bar.volume : null;
    if (price === null || vol === null) return { vwap: null, reason: 'unavailable' };
    if (vol === 0) return { vwap: cumV ? cumPV / cumV : null, reason: cumV ? 'ok' : 'unavailable' };
    cumPV += price * vol;
    cumV += vol;
    if (!cumV) return { vwap: null, reason: 'unavailable' };
    const vwap = cumPV / cumV;
    return { vwap, bands: multipliers.map((m) => ({ m, basis: bandBasis })), reason: 'ok' };
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
