import { alertEngineBadgeFor, ALERT_ENGINE_RULES } from "./alertEngineBadges";

describe("alertEngineBadges (RED: module does not exist yet)", () => {
  test("catalog count: 11 non-GAMMA_FLIP types (GAMMA_FLIP stays in exposureBadges)", () => {
    expect(ALERT_ENGINE_RULES).toHaveLength(11);
    expect(ALERT_ENGINE_RULES).not.toContain("GAMMA_FLIP");
  });

  test.each([
    "GAMMA_SQUEEZE",
    "MOMENTUM_EXTREME",
    "WALL_BREACH",
    "GEX_MAGNITUDE_SHIFT",
    "GAMMA_FLIP_PROXIMITY",
    "PIN_RISK",
    "CHARM_PINNING",
    "VANNA_REGIME_CHANGE",
    "UNUSUAL_PC_OI_RATIO",
    "MAX_PAIN_MAGNET",
    "VOLUME_SPIKE",
  ])("maps %s to a heuristic badge", (rule) => {
    const b = alertEngineBadgeFor(rule);
    expect(b).not.toBeNull();
    expect(b.rule).toBe(rule);
    expect(typeof b.label).toBe("string");
    expect(b.label.length).toBeGreaterThan(0);
    expect(b.title.toLowerCase()).toContain("heuristic");
    expect(["HIGH", "MEDIUM", "LOW"]).toContain(b.priority);
  });

  test("priorities match ALERT_TYPE_CATALOG", () => {
    expect(alertEngineBadgeFor("GAMMA_SQUEEZE").priority).toBe("HIGH");
    expect(alertEngineBadgeFor("WALL_BREACH").priority).toBe("MEDIUM");
    expect(alertEngineBadgeFor("PIN_RISK").priority).toBe("LOW");
    expect(alertEngineBadgeFor("MAX_PAIN_MAGNET").priority).toBe("LOW");
  });

  test("unknown / null / blank rules map to null (never invent a badge)", () => {
    expect(alertEngineBadgeFor("CLUSTER")).toBeNull();
    expect(alertEngineBadgeFor("TOXIC_FLOW")).toBeNull();
    expect(alertEngineBadgeFor("NO_SUCH_RULE")).toBeNull();
    expect(alertEngineBadgeFor(null)).toBeNull();
    expect(alertEngineBadgeFor(undefined)).toBeNull();
    expect(alertEngineBadgeFor("   ")).toBeNull();
  });

  test("case/whitespace tolerant", () => {
    expect(alertEngineBadgeFor("  gamma_squeeze ").rule).toBe("GAMMA_SQUEEZE");
    expect(alertEngineBadgeFor("pin_risk").rule).toBe("PIN_RISK");
  });

  test("returns a copy (caller cannot mutate the table)", () => {
    const a = alertEngineBadgeFor("WALL_BREACH");
    a.label = "MUTATED";
    expect(alertEngineBadgeFor("WALL_BREACH").label).not.toBe("MUTATED");
  });

  test("conflation traps stay split", () => {
    expect(alertEngineBadgeFor("CHARM_PINNING").rule).toBe("CHARM_PINNING");
    expect(alertEngineBadgeFor("CHARM_PIN")).toBeNull();
    expect(alertEngineBadgeFor("GAMMA_FLIP_PROXIMITY").rule).toBe(
      "GAMMA_FLIP_PROXIMITY"
    );
    expect(alertEngineBadgeFor("GAMMA_FLIP")).toBeNull();
    expect(alertEngineBadgeFor("PIN_RISK").rule).toBe("PIN_RISK");
  });
});
