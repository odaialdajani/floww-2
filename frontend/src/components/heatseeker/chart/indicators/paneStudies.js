// C118/C121/C124-C126 residuals — the PANE STUDY CONFIGURATION layer.
// NEW pure module in H2's disjoint indicators lease. ONE ENGINE rule: every
// number comes from the EXISTING primitives — volumeProfile (the approximate
// profile engine), sma (the MA engine), tpoPeriods/sessionZones (the
// bar-resolution TPO/session engines), periodKey (the one NY anchor
// convention). This module only validates configuration and derives honest
// facts. Source-gated settings are TYPED REFUSALS — never a fake enabled
// button; the honest approximation labels always ride the outputs.
//
// Consumer handoff (H1's caller): the panel/dock binds these helpers to the
// real panes' settings — profileConfig for the volume-profile pane's
// mode/levels/VA controls, cvdConfig for the estimated-CVD pane's
// anchor/MA/zero-axis controls, tpoConfig for the Flow/profiles context.
// Each returns {status, reason?, ...} — 'refused' means render the typed
// reason, never a zero.

import { volumeProfile } from './profile';
import { sma } from './priceStudies';
import { tpoPeriods, sessionZones } from './ProfilePrimitives';
import { periodKey } from './anchorStudies';

// CHART-C121: the approximate volume profile's configuration. Modes:
// 'fixed-200' (the letter's fixed 200 rows) | 'visible' (the incumbent
// visible-window row count). vaPct default 0.68 (VA68%). A classified
// buy/sell basis is REFUSED — the bars carry only total volume; the
// admitted trade tape does not exist in this pane.
export function profileConfig(bars, { mode = 'visible', levels, vaPct = 0.68, basis = 'total' } = {}) {
  if (mode !== 'fixed-200' && mode !== 'visible') return { status: 'refused', reason: 'unsupported profile mode' };
  if (basis !== 'total') {
    return { status: 'refused', reason: 'classified buy/sell basis requires an admitted trade-tape source — total measured volume only' };
  }
  const list = Array.isArray(bars) ? bars : [];
  const rows = mode === 'fixed-200' ? 200 : Math.min(200, Math.max(8, list.length));
  const boundLevels = Number.isInteger(levels) ? levels : rows;
  if (!(boundLevels >= 8 && boundLevels <= 200)) return { status: 'refused', reason: 'levels out of bounds (8..200)' };
  if (!(vaPct >= 0.5 && vaPct <= 0.9)) return { status: 'refused', reason: 'value-area pct out of bounds (0.5..0.9)' };
  const out = volumeProfile(list, { rows: boundLevels, valueAreaPct: vaPct });
  if (out.status !== 'ok') return { status: 'refused', reason: out.reason || 'profile unavailable' };
  return {
    status: 'ok',
    mode, approximation: out.approximation, rows: out.rows, poc: out.poc,
    valueArea: out.value_area, totalVolume: out.total_volume,
    facts: {
      poc: out.poc, vah: out.value_area.high, val: out.value_area.low,
      totalVolume: out.total_volume, vaPct, levels: out.rows.length,
      note: 'approximate bar-range profile over the measured window; buy/sell split needs the classified tape',
    },
    coverage: { bars: list.length },
    holds: [{ field: 'basis', reason: 'per-side volume is source-gated (admitted trade tape absent)' }],
  };
}

// CHART-C118: the estimated CVD's configuration — session-anchor reset,
// zero-axis rebasing, MA smoothing — over the REAL estimated path. The
// 'estimated' approximation label is part of every output: this NEVER
// becomes a classified-tape claim.
export function cvdConfig(cvdLine, { anchor = 'none', maPeriod = 1, zeroAxis = 'free' } = {}) {
  const list = Array.isArray(cvdLine) ? cvdLine : [];
  const clean = list.filter((p) => p && typeof p.cvd === 'number' && Number.isFinite(p.cvd));
  if (!clean.length) return { status: 'refused', reason: 'no finite estimated CVD values on this pane' };
  if (anchor !== 'none' && anchor !== 'session') return { status: 'refused', reason: 'unsupported CVD anchor' };
  if (zeroAxis !== 'free' && zeroAxis !== 'zero-at-anchor') return { status: 'refused', reason: 'unsupported zero-axis mode' };
  if (!(Number.isInteger(maPeriod) && maPeriod >= 1 && maPeriod <= 200)) return { status: 'refused', reason: 'MA period out of bounds (1..200)' };
  const zeroAtAnchor = zeroAxis === 'zero-at-anchor' && anchor === 'session';
  let dayKey = null, offset = 0;
  const points = clean.map((p) => {
    if (anchor === 'session') {
      const key = periodKey(p.time, 'session');
      if (key === null) return null;
      if (key !== dayKey) { dayKey = key; offset = p.cvd; }        // a new session rebases
    }
    return { time: p.time, cvd: zeroAtAnchor ? p.cvd - offset : p.cvd };
  }).filter(Boolean);
  const ma = sma(points.map((p) => p.cvd), maPeriod);
  points.forEach((p, i) => { p.ma = ma[i]; });
  return {
    status: 'ok', approximation: 'estimated-bvc', anchor, zeroAxis, maPeriod,
    points,
    holds: [{ field: 'classified-tape', reason: 'true classified CVD needs the admitted trade tape; this pane carries the estimated path only' }],
  };
}

// CHART-C124-C126: TPO configuration. 'bar-resolution' is the credited
// approximation through the EXISTING tpoPeriods engine; 'tick-true' is a
// TYPED refusal (the admitted trade tape does not exist here — tickRows
// stays dormant until a source lands). Session high/low facts ride along
// from sessionZones.
export function tpoConfig(bars, { mode = 'bar-resolution', periodMinutes = 30 } = {}) {
  if (mode !== 'bar-resolution') {
    return { status: 'refused', reason: 'tick-true TPO requires an admitted trade-tape source — only the bar-resolution approximation is computable here' };
  }
  if (!(Number.isInteger(periodMinutes) && periodMinutes >= 1 && periodMinutes <= 480)) {
    return { status: 'refused', reason: 'period out of bounds (1..480 minutes)' };
  }
  const list = Array.isArray(bars) ? bars : [];
  if (!list.length) return { status: 'refused', reason: 'no eligible bars known at the cursor' };
  // Honest input guard: the tpoPeriods/sessionZones engines key periods off
  // NUMERIC bar times (epoch milliseconds). ISO-string times collapse every
  // bar into one NaN bucket — refuse with the exact expected shape instead
  // of rendering a one-letter garbage period.
  if (!list.every((b) => b && Number.isFinite(Number(b.time)))) {
    return { status: 'refused', reason: 'bar times must be epoch milliseconds for the TPO period engine' };
  }
  const out = tpoPeriods(list, { periodMinutes });
  if (out.status !== 'ok') return { status: 'refused', reason: out.reason || 'TPO unavailable' };
  const zones = sessionZones(list);
  return {
    status: 'ok', mode, approximation: out.approximation, note: out.note,
    periods: out.periods, periodMinutes,
    sessionFacts: zones.status === 'ok' ? { high: zones.high, low: zones.low, bars: zones.bars } : null,
    holds: [{ field: 'tick-true', reason: 'source-gated: no admitted trade tape in this pane' }],
  };
}
