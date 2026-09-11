/**
 * exposureBadges — RED: module does not exist yet.
 *
 * Contract: backend exposure rules (TOXIC_FLOW, GAMMA_FLIP, VEX_WALL,
 * CHARM_PIN, LIQUIDITY_STRESS) map to badge descriptors with heuristic
 * copy. Unknown/missing rules map to null — never invent a badge.
 */
import {
  exposureBadgeFor,
  exposureKindOf,
  selectExposureBadges,
  EXPOSURE_RULES,
} from "./exposureBadges";

describe("exposureBadgeFor", () => {
  test("TOXIC_FLOW maps with heuristic disclaimer", () => {
    const b = exposureBadgeFor("TOXIC_FLOW");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("TOXIC_FLOW");
    expect(b.label).toBe("TOXIC FLOW");
    expect(b.title).toMatch(/heuristic/i);
  });

  test("GAMMA_FLIP maps with proximity disclaimer", () => {
    const b = exposureBadgeFor("GAMMA_FLIP");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("GAMMA_FLIP");
    expect(b.label).toBe("GAMMA FLIP");
    expect(b.title).toMatch(/proximity|flip/i);
  });

  test("VEX_WALL maps", () => {
    const b = exposureBadgeFor("VEX_WALL");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("VEX_WALL");
    expect(b.label).toBe("VEX WALL");
  });

  test("CHARM_PIN maps", () => {
    const b = exposureBadgeFor("CHARM_PIN");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("CHARM_PIN");
    expect(b.label).toBe("CHARM PIN");
  });

  test("LIQUIDITY_STRESS maps", () => {
    const b = exposureBadgeFor("LIQUIDITY_STRESS");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("LIQUIDITY_STRESS");
    expect(b.label).toBe("LIQUIDITY STRESS");
  });

  test("unknown rule maps to null — never invent a badge", () => {
    expect(exposureBadgeFor("FOLLOW")).toBeNull();
    expect(exposureBadgeFor("SOURCE")).toBeNull();
    expect(exposureBadgeFor("CHARM_PINNING")).toBeNull();
    expect(exposureBadgeFor("SOMETHING_NEW")).toBeNull();
  });

  test("missing/empty input maps to null", () => {
    expect(exposureBadgeFor(null)).toBeNull();
    expect(exposureBadgeFor(undefined)).toBeNull();
    expect(exposureBadgeFor("")).toBeNull();
  });

  test("lookup is case-insensitive (backend kinds are lowercase)", () => {
    expect(exposureBadgeFor("toxic_flow")).not.toBeNull();
    expect(exposureBadgeFor("gamma_flip")).not.toBeNull();
  });

  test("EXPOSURE_RULES lists exactly the wired feed rules (5 exposure + CLUSTER)", () => {
    expect([...EXPOSURE_RULES].sort()).toEqual(
      ["CHARM_PIN", "CLUSTER", "GAMMA_FLIP", "LIQUIDITY_STRESS", "TOXIC_FLOW", "VEX_WALL"].sort()
    );
  });

  test("CLUSTER (flow_alerts pipeline, same feed rule column) renders", () => {
    const b = exposureBadgeFor("CLUSTER");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("CLUSTER");
    expect(b.title.toLowerCase()).toContain("heuristic");
  });

  test("broken VEX rows describe released, not defending, walls", () => {
    const b = exposureBadgeFor("VEX_WALL", {
      key: "exposure:vex_wall_broken:SPY::65000",
    });
    expect(b.title.toLowerCase()).toContain("released");
    expect(b.title.toLowerCase()).not.toContain("defending");
  });

  test("gamma-approach rows do not claim a completed regime flip", () => {
    const b = exposureBadgeFor("GAMMA_FLIP", {
      context_json: JSON.stringify({ kind: "gamma_flip_approach" }),
    });
    expect(b.title.toLowerCase()).toContain("pressing");
    expect(b.title.toLowerCase()).not.toContain("regime change");
  });

  test("event kind resolves from context, context_json, or feed key", () => {
    expect(exposureKindOf({ context: { kind: "VEX_WALL_BROKEN" } })).toBe(
      "vex_wall_broken"
    );
    expect(exposureKindOf({ context_json: '{"kind":"gamma_flip_approach"}' })).toBe(
      "gamma_flip_approach"
    );
    expect(exposureKindOf({ key: "exposure:vex_wall_formed:SPY::65000" })).toBe(
      "vex_wall_formed"
    );
  });

  test("VEX_WALL without a kind stays honest about the unknown subtype", () => {
    const b = exposureBadgeFor("VEX_WALL", { key: "SCORE|SPY|650|2026-09-18" });
    expect(b.title.toLowerCase()).not.toMatch(/no .*split|carries no/);
    expect(b.title.toLowerCase()).toContain("formed");
    expect(b.title.toLowerCase()).toContain("broken");
  });

  test("selectExposureBadges prefers a broken wall over a formed one", () => {
    const rows = [
      { key: "exposure:vex_wall_formed:SPY::65000", rule: "VEX_WALL" },
      { key: "exposure:vex_wall_broken:SPY::65000", rule: "VEX_WALL" },
    ];
    const badges = selectExposureBadges(rows);
    expect(badges).toHaveLength(1);
    expect(badges[0].title.toLowerCase()).toContain("released");
    expect(badges[0].title.toLowerCase()).not.toContain("defending");
    // Order-independent: feed is conviction-sorted, not time-sorted.
    const flipped = selectExposureBadges([...rows].reverse());
    expect(flipped).toHaveLength(1);
    expect(flipped[0].title).toBe(badges[0].title);
  });

  test("selectExposureBadges prefers an explicit approach kind over a kindless row", () => {
    const rows = [
      { key: "SCORE|SPY|650|2026-09-18", rule: "GAMMA_FLIP" },
      { key: "exposure:gamma_flip_approach:SPY::650", rule: "GAMMA_FLIP" },
    ];
    const badges = selectExposureBadges(rows);
    expect(badges).toHaveLength(1);
    expect(badges[0].title.toLowerCase()).toContain("pressing");
    expect(badges[0].title.toLowerCase()).not.toContain("regime change");
  });

  test("selectExposureBadges drops unknown rules and keeps one badge per rule", () => {
    const rows = [
      { key: "a", rule: "TOXIC_FLOW" },
      { key: "b", rule: "TOXIC_FLOW" },
      { key: "c", rule: "SOMETHING_NEW" },
    ];
    const badges = selectExposureBadges(rows);
    expect(badges).toHaveLength(1);
    expect(badges[0].rule).toBe("TOXIC_FLOW");
  });
});
