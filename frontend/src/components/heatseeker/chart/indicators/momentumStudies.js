// RSI 14 / MACD 12-26-9 / ATR 14 (owner 13:40 slice 2): configurable pure
// math for the chart/indicators family. Conventional named methods —
// Wilder's smoothing for RSI and ATR (J. Welles Wilder, "New Concepts in
// Technical Trading Systems", 1978); MACD = EMA(fast) - EMA(slow) with an
// EMA(signal) — computed through the EXISTING priceStudies.ema primitive
// (the ONE engine rule; this module never re-implements an average).
//
// CONTRACTS (documented for H1's pane rendering):
// - Inputs: OWN LOADED OHLCV only. RSI/MACD read closes; ATR reads
//   high/low/close (the true range needs the PREVIOUS close; the first bar's
//   TR is high-low only).
// - Complete-sample semantics (the family convention, C047): ANY non-finite
//   input refuses the WHOLE series — all-null out, never a fabricated
//   window, never a bridged gap.
// - Warmup: RSI/ATR emit null before index `period`; MACD emits null line
//   before index slow-1 and null signal before slow-1+signal-1 within the
//   line's span. Warmup slots are null, never a guessed value.
// - Units: RSI is percent (0..100; zero average loss = 100, never NaN);
//   MACD line/signal/histogram are price deltas; ATR is price.
// - Bounds: period >= 2 for RSI (a 1-period average is degenerate),
//   period >= 1 for ATR, fast < slow for MACD — out of bounds refuses
//   (all-null), and the registry's validation is the interactive gate.

import { ema } from './priceStudies';

const nulls = (n) => new Array(n).fill(null);

// RSI — Wilder's smoothing on average gain/loss.
export function rsi(closes, period = 14) {
  const list = Array.isArray(closes) ? closes : [];
  if (!(Number.isInteger(period) && period >= 2)) return nulls(list.length);
  if (list.some((v) => typeof v !== 'number' || !Number.isFinite(v))) return nulls(list.length);
  const out = nulls(list.length);
  if (list.length <= period) return out;
  let gain = 0, loss = 0;
  for (let i = 1; i <= period; i += 1) {
    const d = list[i] - list[i - 1];
    if (d > 0) gain += d; else loss -= d;
  }
  let avgGain = gain / period, avgLoss = loss / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < list.length; i += 1) {
    const d = list[i] - list[i - 1];
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

// MACD — line = EMA(fast) - EMA(slow) through the ONE ema primitive;
// signal = EMA(signal) over the line's available span; histogram = line -
// signal. Nulls align to the input length.
export function macd(closes, { fast = 12, slow = 26, signal = 9 } = {}) {
  const list = Array.isArray(closes) ? closes : [];
  const rows = list.map(() => ({ line: null, signal: null, histogram: null }));
  if (!(Number.isInteger(fast) && Number.isInteger(slow) && Number.isInteger(signal)
    && fast >= 1 && slow > fast && signal >= 1)) return rows;
  if (list.some((v) => typeof v !== 'number' || !Number.isFinite(v))) return rows;
  if (list.length <= slow) return rows;
  const eFast = ema(list, fast), eSlow = ema(list, slow);
  const line = list.map((_, i) => (eFast[i] != null && eSlow[i] != null ? eFast[i] - eSlow[i] : null));
  const first = line.findIndex((v) => v !== null);
  if (first === -1) return rows;
  for (let i = first; i < list.length; i += 1) rows[i].line = line[i];
  const sig = ema(line.slice(first), signal);
  for (let i = 0; i < sig.length; i += 1) {
    const idx = first + i;
    rows[idx].signal = sig[i];
    if (rows[idx].line != null && sig[i] != null) rows[idx].histogram = rows[idx].line - sig[i];
  }
  return rows;
}

// ATR — true range with the previous close (first bar: high-low only),
// Wilder's smoothing: first ATR = the simple mean of the first `period`
// TRs, then ATR = (prev*(period-1) + TR)/period.
export function atr(bars, period = 14) {
  const list = Array.isArray(bars) ? bars : [];
  if (!(Number.isInteger(period) && period >= 1)) return nulls(list.length);
  const bad = (b) => !b || ['high', 'low', 'close'].some((k) => typeof b[k] !== 'number' || !Number.isFinite(b[k]));
  if (list.some(bad)) return nulls(list.length);
  if (list.length <= period) return nulls(list.length);
  const tr = list.map((b, i) => (i === 0
    ? b.high - b.low
    : Math.max(b.high - b.low, Math.abs(b.high - list[i - 1].close), Math.abs(b.low - list[i - 1].close))));
  const out = nulls(list.length);
  out[period - 1] = tr.slice(0, period).reduce((s, v) => s + v, 0) / period;
  for (let i = period; i < list.length; i += 1) {
    out[i] = (out[i - 1] * (period - 1) + tr[i]) / period;
  }
  return out;
}
