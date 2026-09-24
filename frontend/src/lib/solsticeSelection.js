/**
 * solsticeSelection — identity selection {ticker, wallId} resolved against the
 * CURRENT snapshot (P05/R4-06).
 *
 * - Retains selection across compatible refreshes (asof change, metric switch,
 *   expand) by wall_id; values always resolved from the current snapshot.
 * - Cross-symbol clears immediately (never leaks SPY walls into QQQ).
 * - A missing wall is WALL_GONE with its last observation retained — never a
 *   silent nearest-wall substitute.
 * - Scenarios/interactions filtered to the selected wall (never scenarios[0]
 *   of a different wall).
 */

export function resolveSelectedWall(data, selectedCell) {
  if (!selectedCell || !data) return { status: "empty", wall: null, interaction: null, scenarios: [] };
  if (selectedCell.ticker && data.ticker && selectedCell.ticker !== data.ticker) {
    return { status: "cleared", reason: "CROSS_SYMBOL", wall: null, interaction: null, scenarios: [] };
  }
  const walls = (data.metrics && data.metrics.walls) || [];
  const interactions = data.interactions || [];
  const allScenarios = data.scenarios || [];
  const wid = selectedCell.wall_id || selectedCell.wallId || null;
  let wall = null;
  if (wid) {
    wall = walls.find((w) => w && w.wall_id === wid) || null;
    if (!wall) {
      return {
        status: "gone", reason: "WALL_GONE", wall: null,
        lastWallId: wid, interaction: null, scenarios: [],
      };
    }
  } else if (selectedCell.strike != null) {
    const strike = Number(selectedCell.strike);
    wall = walls.find((w) => strike >= Number(w.low) && strike <= Number(w.high)) || null;
    if (!wall) {
      return { status: "gone", reason: "WALL_GONE", wall: null, interaction: null, scenarios: [] };
    }
  } else {
    return { status: "empty", wall: null, interaction: null, scenarios: [] };
  }
  const interaction =
    interactions.find((i) => i && i.wall_id === wall.wall_id) || null;
  const scenarios = allScenarios.filter((s) => !s.wall_id || s.wall_id === wall.wall_id);
  return { status: "ok", wall, interaction, scenarios };
}

export function wallPositionOf(wall, spot) {
  if (!wall || spot == null) return "unknown";
  const lo = Number(wall.low);
  const hi = Number(wall.high);
  const s = Number(spot);
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || !Number.isFinite(s)) return "unknown";
  if (hi <= s) return "below";
  if (lo >= s) return "above";
  return "inside";
}
