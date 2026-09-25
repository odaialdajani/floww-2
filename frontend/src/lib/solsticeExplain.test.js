import { explainWall } from "./solsticeExplain";

const WALL = { wall_id: "w_x", low: 498, high: 502, gross: 2000000, net: 1000000,
  call: 1500000, put: -500000, exposure_basis: "OI" };

describe("solsticeExplain (R6-4)", () => {
  test("null wall yields null explanation", () => {
    expect(explainWall({ wall: null })).toBeNull();
  });

  test("five blocks interpolate snapshot numbers, keyed by snapshot+wall", () => {
    const out = explainWall({
      snapshotId: "s1", wall: WALL, metric: "raw", mode: "live",
      interaction: { state: "testing", event: "first_touch", first_seen: true },
      scenarios: [{ name: "Bounce watch", confirmation: "reclaim", invalidation: "accept" }],
      quality: { state: "usable", reasonCodes: [] },
      wallWindow: { window_daddex: 2500000, coverage: { member_strikes: 3, active_strikes: 2 } },
    });
    expect(out.wallId).toBe("w_x");
    expect(out.blocks.map((b) => b.id)).toEqual(["why", "changed", "price", "paths", "limits"]);
    const all = out.blocks.map((b) => b.text).join(" ");
    expect(all).toContain("498–502");
    expect(all).toContain("2/3 member strikes");
    expect(all).toContain("first sighting");
  });

  test("missing window and unusable quality render honest limits", () => {
    const out = explainWall({
      wall: WALL, interaction: null, scenarios: [],
      quality: { state: "stale", reasonCodes: ["STALE_ASK"] },
      wallWindow: null, windowReason: "VOLUME_REBASE",
    });
    const byId = Object.fromEntries(out.blocks.map((b) => [b.id, b.text]));
    expect(byId.changed).toContain("volume rebase");
    expect(byId.price).toContain("unobserved");
    expect(byId.paths).toContain("No scenario pair");
    expect(byId.limits).toContain("STALE_ASK");
  });
});
