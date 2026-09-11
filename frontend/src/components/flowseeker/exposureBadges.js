/**
 * exposureBadges — badge descriptors for backend exposure rules.
 *
 * Backend producers (main): RULE_TOXIC_FLOW, RULE_VEX_WALL,
 * RULE_CHARM_PIN, RULE_LIQUIDITY_STRESS in backend/services/
 * exposure_alerts.py; RULE_GAMMA_FLIP fires from BOTH
 * exposure_alerts.py (kind gamma_flip_approach = price pressing the flip
 * level) and backend/alert_engine.py (GAMMA_FLIP regime-change alert).
 * The feed row preserves the producer event kind in its key/context, so
 * subtype-aware copy can distinguish an approach from a completed flip and
 * a broken wall from a formed wall.
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
      "VEX wall event of unknown subtype — formed means dealers defending (vol suppression), broken means suppression released and regime may shift (heuristic, not a direction call)",
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

const KIND_TITLES = {
  "VEX_WALL:vex_wall_formed":
    "VEX wall formed — concentrated VEX exposure may suppress volatility (heuristic, not a direction call)",
  "VEX_WALL:vex_wall_broken":
    "VEX wall broken — volatility suppression released; regime may shift (heuristic, not a direction call)",
  "GAMMA_FLIP:gamma_flip_approach":
    "Gamma flip proximity — price pressing the modeled dealer flip level (heuristic, not a completed regime flip)",
};

export function exposureKindOf(rowOrKind) {
  if (rowOrKind == null) return "";
  if (typeof rowOrKind === "string") return rowOrKind.trim().toLowerCase();
  const row = rowOrKind;
  if (typeof row?.context?.kind === "string" && row.context.kind.trim()) {
    return row.context.kind.trim().toLowerCase();
  }
  const rawContext = row?.context_json;
  if (typeof rawContext === "string" && rawContext.trim()) {
    try {
      const parsed = JSON.parse(rawContext);
      if (typeof parsed?.kind === "string" && parsed.kind.trim()) {
        return parsed.kind.trim().toLowerCase();
      }
    } catch {
      // Malformed optional context is non-fatal; fall through to the key.
    }
  } else if (typeof rawContext?.kind === "string" && rawContext.kind.trim()) {
    return rawContext.kind.trim().toLowerCase();
  }
  if (typeof row?.key === "string") {
    const [namespace, kind] = row.key.split(":");
    if (namespace === "exposure" && kind?.trim()) {
      return kind.trim().toLowerCase();
    }
  }
  return "";
}

export function exposureBadgeFor(rule, rowOrKind) {
  if (rule == null) return null;
  const key = String(rule).trim().toUpperCase();
  if (!key) return null;
  const b = BADGES[key];
  if (!b) return null;
  const badge = { ...b };
  const title = KIND_TITLES[`${key}:${exposureKindOf(rowOrKind)}`];
  if (title) badge.title = title;
  return badge;
}

/**
 * Rank of an event kind when several feed rows share one rule. A broken
 * wall supersedes a formed one (the break is the newer regime state); any
 * explicitly recognized kind beats a kindless row. Unrecognized rows score
 * 0 and lose ties to the first row, keeping selection deterministic even
 * though the feed is conviction-sorted, not time-sorted.
 */
const KIND_PRIORITY = {
  vex_wall_broken: 2,
  vex_wall_formed: 1,
  gamma_flip_approach: 1,
};

function _kindRank(row) {
  const kind = exposureKindOf(row);
  if (!kind) return 0;
  if (Object.hasOwn(KIND_TITLES, `${String(row?.rule || "").trim().toUpperCase()}:${kind}`)) {
    return KIND_PRIORITY[kind] || 1;
  }
  return 0;
}

/**
 * One badge per live rule. Rows with unknown rules never produce a badge.
 * When several rows share a rule (e.g. a formed and a broken VEX wall in
 * the same 2-day window), the highest-ranked kind wins so the strip cannot
 * show a stale regime state.
 */
export function selectExposureBadges(rows) {
  const best = new Map();
  for (const row of rows || []) {
    const b = exposureBadgeFor(row?.rule, row);
    if (!b) continue;
    const rank = _kindRank(row);
    const prev = best.get(b.rule);
    if (!prev || rank > prev.rank) best.set(b.rule, { badge: b, rank });
  }
  return [...best.values()].map((v) => v.badge);
}
