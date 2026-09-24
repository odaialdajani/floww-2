/**
 * solsticeReplay — pure replay stepping + contamination guards (P09/R4-15).
 *
 * - Steps chronologically through recorded snapshot IDs only.
 * - Never shows future/live data while replay is active.
 * - Live refresh is ignored during replay (caller must not merge live data).
 * - Return to live is deliberate (clearReplay), never automatic.
 */

export function replayIndexOf(snaps, id) {
  return (snaps || []).findIndex((s) => s && (s.id === id || s.snapshot_id === id));
}

export function stepReplay(snaps, currentId, dir) {
  const list = snaps || [];
  if (!list.length) return null;
  let i = replayIndexOf(list, currentId);
  if (i < 0) i = dir > 0 ? -1 : list.length;
  const j = i + dir;
  if (j < 0 || j >= list.length) return null;
  return list[j];
}

export function shouldIgnoreLive(isReplayActive) {
  return Boolean(isReplayActive);
}

/**
 * Adapt a /replay snapshot payload into grid-display shape so the SAME
 * grid/inspector/evidence components render stored content (not counts).
 * R5-B: recorded quality, scenarios, interactions and cell grids travel
 * with the replay (never dropped for empty defaults); the caller-supplied
 * ticker must match the stored snapshot ticker — a relabeled symbol is
 * rejected (null) instead of rendering SPY data under a QQQ heading.
 */
export function replayToDisplay(rep, ticker) {
  if (!rep || rep.error) return null;
  const snap = rep.snapshot || {};
  if (ticker && snap.ticker && ticker !== snap.ticker) return null;
  const strikes = rep.strikes || [];
  const walls = rep.walls || [];
  const grids = rep.grids || {};
  return {
    ticker: snap.ticker || ticker || null,
    asof: snap.asof_ts || snap.asof || null,
    spot: snap.spot ?? null,
    strikes,
    metrics: { walls, grids },
    quality: rep.quality || undefined,
    interactions: rep.interactions || [],
    scenarios: rep.scenarios || [],
    replay: true,
    replay_note: rep.replay_note || "available-at replay",
    snapshot_id: snap.snapshot_id || null,
  };
}
