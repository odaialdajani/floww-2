import { replayIndexOf, replayToDisplay, shouldIgnoreLive, stepReplay } from "./solsticeReplay";

describe("solsticeReplay (P09/R4-15)", () => {
  const snaps = [{ id: "a", asof: "t1" }, { id: "b", asof: "t2" }, { id: "c", asof: "t3" }];
  test("steps chronologically, stops at ends", () => {
    expect(stepReplay(snaps, null, 1).id).toBe("a");
    expect(stepReplay(snaps, "a", 1).id).toBe("b");
    expect(stepReplay(snaps, "c", 1)).toBeNull();
    expect(stepReplay(snaps, "b", -1).id).toBe("a");
    expect(replayIndexOf(snaps, "b")).toBe(1);
  });
  test("live refresh ignored during replay", () => {
    expect(shouldIgnoreLive(true)).toBe(true);
    expect(shouldIgnoreLive(false)).toBe(false);
  });
  test("replay content replaces grid data (not counts)", () => {
    const rep = { snapshot: { snapshot_id: "a", ticker: "SPY", spot: 500, asof_ts: "t1" },
      strikes: [{ strike: 500 }], walls: [{ wall_id: "w1" }], contracts: [{ osi: "X" }] };
    const d = replayToDisplay(rep, "SPY");
    expect(d.replay).toBe(true);
    expect(d.strikes.length).toBe(1);
    expect(d.metrics.walls[0].wall_id).toBe("w1");
    expect(d.asof).toBe("t1");
    expect(replayToDisplay({ error: "not_found" }, "SPY")).toBeNull();
  });
});
