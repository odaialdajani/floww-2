/**
 * solsticeExplain — deterministic selected-wall explanation (R6-4).
 *
 * No model: five inspector blocks interpolated from typed snapshot fields.
 * Numbers come from the snapshot; nothing is authored with free numerics.
 * Callers key the rendered block by snapshot+wall so a stale explanation
 * unmounts on selection/scope change instead of lingering.
 */

export function explainWall({ snapshotId = null, wall = null, metric = "raw", mode = "live",
                              interaction = null, scenarios = [], quality = null,
                              wallWindow = null, windowReason = null } = {}) {
  if (!wall) return null;
  const fmt = (v) => {
    if (v == null || Number.isNaN(v)) return "—";
    const a = Math.abs(v);
    if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    if (a >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
    return `$${v}`;
  };
  const why = `Zone ${wall.low}–${wall.high} holds ${fmt(wall.gross)} gross ` +
    `(${fmt(wall.call)} call / ${fmt(wall.put)} put, net ${fmt(wall.net)} USD per 1% move, ${wall.exposure_basis || "OI"} basis).`;
  const changed = wallWindow
    ? `Recent window activity ${fmt(wallWindow.window_daddex)} over ` +
      `${wallWindow.coverage.active_strikes}/${wallWindow.coverage.member_strikes} member strikes.`
    : (windowReason === "VOLUME_REBASE"
      ? "Window unavailable: volume rebase, new baseline required."
      : "Window unavailable: no comparable baseline for this wall.");
  const price = interaction
    ? `Price interaction is ${interaction.state}` +
      `${interaction.event ? ` (${interaction.event})` : ""}` +
      `${interaction.first_seen === false ? " with continuity." : " on first sighting."}`
    : "Price interaction unobserved: no qualifying encounter on record.";
  const paths = (scenarios || []).slice(0, 2).map((s) =>
    `${s.name}: confirm on ${s.confirmation}; invalid on ${s.invalidation}.`);
  const limits = quality && quality.state !== "usable"
    ? `Limits the reading: ${(quality.reasonCodes || []).join(", ") || quality.state}.`
    : "Limits the reading: trade side unknown; activity is turnover, not flow.";
  return { snapshotId, wallId: wall.wall_id || null, metric, mode,
    blocks: [
      { id: "why", title: "Why this wall", text: why },
      { id: "changed", title: "What changed here", text: changed },
      { id: "price", title: "What price did", text: price },
      { id: "paths", title: "Confirm / invalidate", text: paths.join(" ") || "No scenario pair on record." },
      { id: "limits", title: "What limits the reading", text: limits },
    ] };
}
