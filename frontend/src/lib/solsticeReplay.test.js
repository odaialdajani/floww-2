import { replayIndexOf, replayToDisplay, shouldIgnoreLive, stepReplay } from "./solsticeReplay";

test("recorded request and provenance restore without deriving a live identity", () => {
  const display = { map_query: { expiries: 4, expiryScope: "next", sessionDate: "2026-10-01" },
    scope_selection: { kind: "next", selected_expiries: ["2026-10-02"] }, event_time: "2026-10-01T14:00:00Z" };
  const rep = { snapshot: { snapshot_id: "snap1", ticker: "SPY", data_source: "fixture", formula_version: "gex.v2" },
    context: { display }, grids: {}, metrics_full: {} };
  const out = replayToDisplay(rep, "SPY");
  expect(out.map_query).toEqual(display.map_query);
  expect(out.scope_selection).toEqual(display.scope_selection);
  expect(out.data_source).toBe("fixture");
  expect(out.formula_version).toBe("gex.v2");
  expect(out.event_time).toBe(display.event_time);
  const old = replayToDisplay({ snapshot: rep.snapshot, context: {} }, "SPY");
  expect(old.map_query).toBeNull();
});

test("VEX and Charm replay preserve stored signed cells and conventions without fallback", () => {
 const main={strikes:[100],expiries:["2026-10-02"],grid:{"2026-10-02":{"100":999}},
   vex_grid:{"2026-10-02":{"100":0}},charm_grid:{"2026-10-02":{"100":-7}},
   vex_meta:{unit:"USD delta-notional/+1 vol pt",record_version:"metric-record.v1"},charm_meta:{unit:"dollar_charm_1pct_per_year"}};
 const rep={snapshot:{ticker:"SPY",snapshot_id:"record"},grids:{grid:main},metrics_full:{},context:{}};
 const out=replayToDisplay(rep,"SPY");
 expect(out.grid.vex_grid).toEqual(main.vex_grid);
 expect(out.grid.charm_grid).toEqual(main.charm_grid);
 expect(out.grid.vex_meta).toEqual(main.vex_meta);
 expect(out.grid.charm_meta).toEqual(main.charm_meta);
 const old=replayToDisplay({snapshot:rep.snapshot,grids:{grid:{...main,vex_meta:undefined,charm_grid:undefined}},context:{}},"SPY");
 expect(old.grid.vex_meta).toBeUndefined();
 expect(old.grid.charm_grid).toBeUndefined();
});

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
      strikes: [{ strike: 500 }], walls: [{ wall_id: "w1" }], contracts: [{ osi: "X" }],
      quality: { state: "usable", reasonCodes: [] },
      scenarios: [{ wall_id: "w1" }], interactions: [{ wall_id: "w1" }],
      grids: { grid: { expiries: ["2030-01-15"], strikes: [500],
                       grid: { "2030-01-15": { 500: 1e6 } } } } };
    const d = replayToDisplay(rep, "SPY");
    expect(d.replay).toBe(true);
    expect(d.strikes.length).toBe(1);
    expect(d.metrics.walls[0].wall_id).toBe("w1");
    expect(d.asof).toBe("t1");
    expect(d.quality.state).toBe("usable");
    expect(d.scenarios.length).toBe(1);
    expect(d.interactions.length).toBe(1);
    // Main grid renders from d.grid (no consumer reads metrics.grids.grid;
    // the old assertion pinned an unused path).
    expect(d.grid.grid["2030-01-15"][500]).toBe(1e6);
    expect(replayToDisplay({ error: "not_found" }, "SPY")).toBeNull();
  });
  test("cross-ticker relabel rejected", () => {
    const rep = { snapshot: { snapshot_id: "a", ticker: "SPY", spot: 500, asof_ts: "t1" },
      strikes: [], walls: [] };
    expect(replayToDisplay(rep, "QQQ")).toBeNull();
    expect(replayToDisplay(rep, "SPY")).not.toBeNull();
  });
});

test("R7-03: context restore, dual ID spelling, projection status", () => {
  const full = {
    snapshot: { snapshot_id: "a", ticker: "SPY", spot: 500, asof_ts: "t1" },
    strikes: [], walls: [{ wall_id: "w1" }],
    quality: { state: "usable", reasonCodes: [] },
    scenarios: [], interactions: [],
    grids: { grid: { expiries: ["2030-01-15"], strikes: [500], grid: { "2030-01-15": { 500: 1e6 } } } },
    metrics_full: { wall_window: { w1: { window_daddex: 42 } }, nearest_walls: [{ wall_id: "w1" }] },
    context: { session: { entry_allowed: false, reasons: ["MARKET_CLOSED"] }, scout: { calls: 0 } },
  };
  const d = replayToDisplay(full, "SPY");
  expect(d.snapshot_id).toBe("a");
  expect(d.snapshotId).toBe("a");
  expect(d.metrics.wall_window).toEqual({ w1: { window_daddex: 42 } });
  expect(d.session).toEqual({ entry_allowed: false, reasons: ["MARKET_CLOSED"] });
  expect(d.scout).toEqual({ calls: 0 });
  expect(d.projection_status).toBe("complete");
  expect(d.projection_missing).toEqual([]);
  const legacy = replayToDisplay({
    snapshot: { snapshot_id: "b", ticker: "SPY", spot: 500, asof_ts: "t1" },
    strikes: [], walls: [], grids: {},
  }, "SPY");
  expect(legacy.snapshotId).toBe("b");
  expect(legacy.projection_status).toBe("partial");
  expect(legacy.projection_missing).toContain("metrics");
  expect(legacy.projection_missing).toContain("context");
});
