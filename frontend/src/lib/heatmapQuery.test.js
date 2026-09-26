import { buildHeatmapQuery, heatmapQueryKey } from "./heatmapQuery";

// Contract: the ONE query string used by BOTH the 25s /api/data poll and the
// manual-refresh /api/heatmap fetch, so the DTE + Expiries + mode controls
// survive every poll tick (Round-8 regression: naked `/data/${ticker}` poll
// overwrote the parameterized fetch with backend defaults).
describe("buildHeatmapQuery", () => {
  test("defaults: expiries + mode only, no dte", () => {
    expect(buildHeatmapQuery({ expiries: 4, mode: "day", dte: null })).toBe(
      "expiries=4&mode=day"
    );
  });

  test("dte=0 (0DTE) IS included — zero is a real value, not falsy-omitted", () => {
    expect(buildHeatmapQuery({ expiries: 4, mode: "day", dte: 0 })).toBe(
      "expiries=4&mode=day&dte=0"
    );
  });

  test("dte=1 (1DTE) and dte=7 (Week) included", () => {
    expect(buildHeatmapQuery({ expiries: 6, mode: "day", dte: 1 })).toBe(
      "expiries=6&mode=day&dte=1"
    );
    expect(buildHeatmapQuery({ expiries: 6, mode: "day", dte: 7 })).toBe(
      "expiries=6&mode=day&dte=7"
    );
  });

  test("dte undefined behaves like null (All)", () => {
    expect(buildHeatmapQuery({ expiries: 8, mode: "day", dte: undefined })).toBe(
      "expiries=8&mode=day"
    );
  });

  test("expiries selection is passed through (2/4/6/8/12)", () => {
    for (const n of [2, 4, 6, 8, 12]) {
      expect(buildHeatmapQuery({ expiries: n, mode: "day", dte: null })).toBe(
        `expiries=${n}&mode=day`
      );
    }
  });

  test("mode swing/scalp passed through", () => {
    expect(buildHeatmapQuery({ expiries: 4, mode: "swing", dte: null })).toBe(
      "expiries=4&mode=swing"
    );
    expect(buildHeatmapQuery({ expiries: 4, mode: "scalp", dte: null })).toBe(
      "expiries=4&mode=scalp"
    );
  });

  test("missing fields fall back to backend defaults (4, day)", () => {
    expect(buildHeatmapQuery({})).toBe("expiries=4&mode=day");
  });
});

// P13/R4-03: query identity carries every scope dimension so refresh/expand
// can never show a response under the wrong heading.
describe("heatmapQueryKey", () => {
  test("dte and scalp change the key (0DTE is distinct from All)", () => {
    const a = heatmapQueryKey({ ticker: "SPY", expiries: 4, mode: "day", dte: null, scalp: false });
    const b = heatmapQueryKey({ ticker: "SPY", expiries: 4, mode: "day", dte: 0, scalp: false });
    const c = heatmapQueryKey({ ticker: "SPY", expiries: 4, mode: "day", dte: null, scalp: true });
    const d = heatmapQueryKey({ ticker: "QQQ", expiries: 4, mode: "day", dte: null, scalp: false });
    expect(new Set([a, b, c, d]).size).toBe(4);
  });
});
