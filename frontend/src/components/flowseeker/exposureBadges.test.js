/**
 * exposureBadges — RED: module does not exist yet.
 *
 * Contract: backend exposure rules (TOXIC_FLOW, GAMMA_FLIP, VEX_WALL,
 * CHARM_PIN, LIQUIDITY_STRESS) map to badge descriptors with heuristic
 * copy. Unknown/missing rules map to null — never invent a badge.
 */
import { exposureBadgeFor, EXPOSURE_RULES } from "./exposureBadges";

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
});
