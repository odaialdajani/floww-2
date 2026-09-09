/**
 * alertEngineBadges — badge descriptors for backend alert_engine rules.
 *
 * Producer: `Alert.type` strings from `ALERT_TYPE_CATALOG` in
 * backend/alert_engine.py (served via /api/alerts/*, NOT the persisted
 * flow_alerts feed). Priorities mirror the catalog verbatim.
 *
 * Pipeline boundary (do NOT cross it):
 * - This module owns the 11 NON-GAMMA_FLIP catalog types.
 * - GAMMA_FLIP stays in exposureBadges.js: the same string is fired by two
 *   producers (alert_engine regime change + exposure_alerts proximity) and
 *   cannot be split on the string alone. Known limitation, recorded in 1b.
 * - CLUSTER is a flow_alerts feed `rule`, not an Alert.type — it lives in
 *   exposureBadges.js, not here.
 *
 * Copy rule: heuristic labels only, no invented precision. Unknown types
 * map to null — never invent a badge for a rule with no wired producer.
 */

const BADGES = {
  GAMMA_SQUEEZE: {
    rule: "GAMMA_SQUEEZE",
    label: "GAMMA SQUEEZE",
    priority: "HIGH",
    title:
      "Gamma squeeze — negative gamma with spot near the flip, dealers chasing price (heuristic, not a direction call)",
  },
  MOMENTUM_EXTREME: {
    rule: "MOMENTUM_EXTREME",
    label: "MOMENTUM EXTREME",
    priority: "HIGH",
    title:
      "Momentum extreme — conviction score at an extreme, crowded tape (heuristic, not a direction call)",
  },
  WALL_BREACH: {
    rule: "WALL_BREACH",
    label: "WALL BREACH",
    priority: "MEDIUM",
    title:
      "Wall breached — spot crossed a dealer call/put wall (heuristic, not a direction call)",
  },
  GEX_MAGNITUDE_SHIFT: {
    rule: "GEX_MAGNITUDE_SHIFT",
    label: "GEX SHIFT",
    priority: "MEDIUM",
    title:
      "GEX shift — total gamma exposure changed by more than 40% (heuristic)",
  },
  GAMMA_FLIP_PROXIMITY: {
    rule: "GAMMA_FLIP_PROXIMITY",
    label: "NEAR FLIP",
    priority: "MEDIUM",
    title:
      "Near gamma flip — spot within 0.3% of the flip level (heuristic, not a direction call; distinct from GAMMA_FLIP regime change)",
  },
  PIN_RISK: {
    rule: "PIN_RISK",
    label: "PIN RISK",
    priority: "LOW",
    title:
      "Pin risk — spot near the max-gamma strike into expiry (heuristic)",
  },
  CHARM_PINNING: {
    rule: "CHARM_PINNING",
    label: "CHARM PINNING",
    priority: "HIGH",
    title:
      "Charm pinning — 0DTE delta-decay pinning flow (heuristic; distinct from CHARM_PIN exposure)",
  },
  VANNA_REGIME_CHANGE: {
    rule: "VANNA_REGIME_CHANGE",
    label: "VANNA SHIFT",
    priority: "HIGH",
    title:
      "Vanna regime change — sign flip in net VEX, vol-spot regime shifting (heuristic)",
  },
  UNUSUAL_PC_OI_RATIO: {
    rule: "UNUSUAL_PC_OI_RATIO",
    label: "PC OI SKEW",
    priority: "MEDIUM",
    title:
      "Unusual put/call OI — put open interest over 2x calls, downside hedge crowding (heuristic)",
  },
  MAX_PAIN_MAGNET: {
    rule: "MAX_PAIN_MAGNET",
    label: "MAX PAIN",
    priority: "LOW",
    title:
      "Max pain magnet — spot within 1% of max pain in positive gamma (heuristic)",
  },
  VOLUME_SPIKE: {
    rule: "VOLUME_SPIKE",
    label: "VOLUME SPIKE",
    priority: "MEDIUM",
    title:
      "Volume spike — real contract volume 3x at a near-ATM strike (heuristic)",
  },
};

export const ALERT_ENGINE_RULES = Object.freeze(Object.keys(BADGES));

export function alertEngineBadgeFor(type) {
  if (type == null) return null;
  const key = String(type).trim().toUpperCase();
  if (!key) return null;
  const b = BADGES[key];
  return b ? { ...b } : null;
}
