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
 * R5-B + R6-1 hydration: recorded quality, scenarios, interactions and FULL
 * cell grids (with axes) travel with the replay; the main data.grid is
 * rebuilt from the stored projection so raw AND delta render real cells.
 * A caller-supplied ticker must match the stored snapshot ticker — a
 * relabeled symbol is rejected (null) instead of rendering SPY data under
 * a QQQ heading.
 */
export function replayToDisplay(rep, ticker) {
  if (!rep || rep.error) return null;
  const snap = rep.snapshot || {};
  if (ticker && snap.ticker && ticker !== snap.ticker) return null;
  const strikes = rep.strikes || [];
  const walls = rep.walls || [];
  const grids = rep.grids || {};
  const main = grids.grid || {};
  const dataGrid = {
    expiries: main.expiries || Object.keys(main.grid || {}),
    strikes: main.strikes || strikes.map((s) => s.strike),
    grid: main.grid || {},
    exposure_basis: main.exposure_basis || snap.exposure_basis || "OI",
    formula_version: main.formula_version || "gex.v2",
  };
  const metricGrids = {};
  for (const [name, section] of Object.entries(grids)) {
    if (name === "grid" || name === "version") continue;
    if (section && typeof section === "object" && section.grid) metricGrids[name] = section;
  }
  // R7-03: restore wall-local comparison inputs + visible context recorded
  // alongside the cells (metrics_full/context); pre-migration records lack
  // them and are marked explicitly incomplete — never reconstructed.
  const metricsFull = rep.metrics_full && typeof rep.metrics_full === "object" ? rep.metrics_full : null;
  const ctx = rep.context && typeof rep.context === "object" ? rep.context : null;
  const missing = [];
  if (!metricsFull) missing.push("metrics");
  if (!ctx) missing.push("context");
  else for (const k of ["session", "scout"]) if (ctx[k] == null) missing.push(`context.${k}`);
  if (!Object.keys(metricGrids).length && !(main.grid && Object.keys(main.grid).length)) missing.push("grids");
  const sid = snap.snapshot_id || null;
  return {
    ticker: snap.ticker || ticker || null,
    asof: snap.asof_ts || snap.asof || null,
    spot: snap.spot ?? null,
    strikes,
    grid: dataGrid,
    expiries_used: snap.expiries_used || dataGrid.expiries,
    metrics: { ...(metricsFull || {}), walls, grids: metricGrids },
    quality: rep.quality || undefined,
    interactions: rep.interactions || [],
    scenarios: rep.scenarios || [],
    session: ctx?.session ?? null,
    playbook: ctx?.playbook ?? null,
    scout: ctx?.scout ?? null,
    gamma_regime_v1: ctx?.gamma_regime_v1 ?? null,
    patterns_v1: ctx?.patterns_v1 ?? null,
    vanna_v1: ctx?.vanna_v1 ?? null,
    moneyness: ctx?.moneyness ?? null,
    replay: true,
    replay_note: rep.replay_note || "available-at replay",
    snapshot_id: sid,
    snapshotId: sid,
    projection_status: missing.length ? "partial" : "complete",
    projection_missing: missing,
  };
}
