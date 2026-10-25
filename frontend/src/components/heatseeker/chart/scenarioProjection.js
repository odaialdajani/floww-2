// B10 future-whitespace projection (b10_projection_contract v2 — H3 PASS,
// CHART-C044). The future axis extends in EXACT bar_seconds multiples of the
// pane's interval; the whitespace is EMPTY CANVAS — no probabilities, no
// pseudo-candles, no forecast values, no extrapolated zone edges. The scenario
// zone comes from sessionZones at its own known-at and is rendered as a
// recorded-context label; the projection NEVER extends high/low into the
// future. sourceAgeSeconds (cursor - lastKnownTime) is present on every ok
// response and ALWAYS rendered with the zone.
import { sessionZones } from './indicators/ProfilePrimitives';

function nySessionCheck(cursorMs) {
  // A cursor is eligible only inside a regular America/New_York session
  // (Mon–Fri 09:30–16:00). Offset resolved at the cursor's own instant, the
  // same technique the opening-envelope helper uses.
  const d = new Date(cursorMs);
  if (!Number.isFinite(d.valueOf())) return false;
  let offsetMinutes = -240;
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
      .formatToParts(d);
    const weekday = parts.find(p => p.type === 'weekday')?.value;
    const hour = Number(parts.find(p => p.type === 'hour')?.value);
    const minute = Number(parts.find(p => p.type === 'minute')?.value);
    if (weekday === 'Sat' || weekday === 'Sun') return false;
    const minutesOfDay = hour * 60 + minute;
    // 09:30 through the 16:00 closing print — the close bar is in-session.
    return minutesOfDay >= 570 && minutesOfDay <= 960;
  } catch {
    return offsetMinutes === -240; // fallback never silently admits
  }
}

// Contract signature: projectWhitespace(frames, { intervalMinutes,
// horizonMinutes, zoneSource }) -> { status, segments, sourceAgeSeconds, zone }.
// frames carry ISO time strings + OHLC (the pane's own bars); zoneSource may
// override the zone (a pre-computed sessionZones result) for callers that
// compute it elsewhere.
export function projectWhitespace(frames, { intervalMinutes, horizonMinutes = 120, zoneSource = null, supportedGrid = null, cursorMs = null } = {}) {
  const grid = Array.isArray(supportedGrid) ? supportedGrid : [];
  if (!grid.includes(intervalMinutes)) {
    return { status: 'refused', reason: 'no-eligible-interval', segments: [], sourceAgeSeconds: null, zone: null };
  }
  const list = Array.isArray(frames) ? frames : [];
  // zone at its OWN known-at: bars knowable at the cursor (epoch-ms times)
  const zone = zoneSource && typeof zoneSource === 'object'
    ? zoneSource
    : sessionZones(list.map(f => ({
        time: typeof f?.time === 'string' ? Date.parse(f.time) : f?.time,
        high: f?.high, low: f?.low, open: f?.open, close: f?.close,
      })), { cursor: typeof cursorMs === 'number' && Number.isFinite(cursorMs) ? cursorMs : null });
  if (zone.status !== 'ok') {
    // sessionZones' own reason propagates VERBATIM under the typed refusal
    return { status: 'refused', reason: 'zone-source-unavailable', segments: [], sourceAgeSeconds: null, zone };
  }
  if (typeof cursorMs !== 'number' || !Number.isFinite(cursorMs) || !nySessionCheck(cursorMs)) {
    return { status: 'refused', reason: 'cursor-ineligible', segments: [], sourceAgeSeconds: null, zone: null };
  }
  // EMPTY future slots: exact interval multiples from the last KNOWN bar,
  // never past the horizon. No values, no candles — kind carries the only meaning.
  const intervalMs = intervalMinutes * 60000;
  const horizonEnd = zone.lastKnownTime + horizonMinutes * 60000;
  const segments = [];
  for (let t = zone.lastKnownTime + intervalMs; t + intervalMs <= horizonEnd; t += intervalMs) {
    segments.push({ startMs: t, endMs: t + intervalMs, kind: 'future-whitespace' });
  }
  const sourceAgeSeconds = Math.max(0, Math.round((cursorMs - zone.lastKnownTime) / 1000));
  return { status: 'ok', segments, sourceAgeSeconds, zone };
}
