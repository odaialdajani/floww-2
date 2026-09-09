/**
 * exposureBadges — badge descriptors for backend exposure rules.
 *
 * Backend producers (main): RULE_TOXIC_FLOW, RULE_VEX_WALL,
 * RULE_CHARM_PIN, RULE_LIQUIDITY_STRESS in backend/services/
 * exposure_alerts.py; RULE_GAMMA_FLIP fires from BOTH
 * exposure_alerts.py (kind gamma_flip_approach = price pressing the flip
 * level) and backend/alert_engine.py (GAMMA_FLIP regime-change alert).
 * The feed `rule` field carries no producer split, so the GAMMA_FLIP and
 * VEX_WALL badge titles name both meanings instead of claiming one.
 * The Blademap v3 feed (/api/flowseeker/alerts/feed) carries these
 * rows with a `rule` field; this module maps rule → badge. Unknown
 * rules map to null: never invent a badge for a rule with no wired
 * producer.
 *
 * Copy rule: heuristic labels only, no invented precision (F5/F6/F11/F19
 * style). Do NOT conflate CHARM_PIN (exposure) with CHARM_PINNING
 * (alert_engine 0DTE), or GAMMA_FLIP (flip zone: approach or regime
 * change) with GAMMA_FLIP_PROXIMITY (alert_engine spot-within-0.3%).
 *
 * CLUSTER is a flow_alerts-pipeline rule (not exposure_alerts.py) but shares
 * the persisted feed `rule` column (_mk_alert(best, "CLUSTER", ...) in
 * backend/services/flow_alerts.py), so both badge call sites already see it.
 */

const BADGES = {
  TOXIC_FLOW: {
    rule: "TOXIC_FLOW",
    label: "TOXIC FLOW",
    title:
      "Toxic flow — VPIN in the high regime: makers adversely selected, spreads/vol may widen (heuristic, not a direction call)",
  },
  GAMMA_FLIP: {
    rule: "GAMMA_FLIP",
    label: "GAMMA FLIP",
    title:
      "Gamma flip zone — price pressing or through the dealer flip level: flip approach (exposure path) or regime change pos-to-neg (alert-engine path), heuristic, not a direction call",
  },
  VEX_WALL: {
    rule: "VEX_WALL",
    label: "VEX WALL",
    title:
      "VEX wall event — formed (dealers defending, vol suppression) or broken (suppression released, regime may shift); feed carries no formed/broken split, heuristic",
  },
  CHARM_PIN: {
    rule: "CHARM_PIN",
    label: "CHARM PIN",
    title:
      "Charm pin — delta-hedging concentration into expiry, price magnet (heuristic)",
  },
  LIQUIDITY_STRESS: {
    rule: "LIQUIDITY_STRESS",
    label: "LIQUIDITY STRESS",
    title:
      "Liquidity stress — Kyle/Amihud impact regime elevated, wider effective spreads likely (heuristic)",
  },
  CLUSTER: {
    rule: "CLUSTER",
    label: "CLUSTER",
    title:
      "Cluster — laddered same-bias accumulation in one snapshot (heuristic, not a direction call)",
  },
};

export const EXPOSURE_RULES = Object.freeze(Object.keys(BADGES));

export function exposureBadgeFor(rule) {
  if (rule == null) return null;
  const key = String(rule).trim().toUpperCase();
  if (!key) return null;
  const b = BADGES[key];
  return b ? { ...b } : null;
}
