// B21 dark-pool mirror tests: synthetic only.
import { eligiblePrints, isExactEquityPrint, levelLabel, topLevels } from "./DarkPoolLevels";

const equityPrint = { price: 100.0, size: 1000, venue: "D", event_time: 1, asset_class: "equity" };

test("levels are exact single prints with unknown direction", () => {
  const prints = [
    equityPrint,
    { price: 101.0, size: 5, venue: "D", event_time: 2 }, // asset_class defaults equity
  ];
  const out = topLevels(prints, { topN: 2 });
  expect(out).toHaveLength(2);
  expect(out[0]).toEqual({
    price: 100.0, size: 1000, venue: "D", event_time: 1,
    notional: 100000, direction: "unknown",
  });
  expect(levelLabel(out[0])).toBe("100 × 1000 · venue D · notional 100000 · direction unknown");
  // largest notional wins (100 × 1000 = 100000 beats 99 × 500 = 49500)
  expect(topLevels([{ price: 99.0, size: 500, venue: "D", event_time: 3 }, equityPrint], { topN: 1 })[0].price).toBe(100.0);
});

test("non-equity prints and incomplete rows are refused", () => {
  expect(isExactEquityPrint({ ...equityPrint, asset_class: "option" })).toBe(false);
  expect(isExactEquityPrint({ price: 1, size: 1, event_time: 1, venue: null })).toBe(false);
  expect(isExactEquityPrint({ price: 1, size: null, event_time: 1, venue: "D" })).toBe(false);
  expect(topLevels([{ ...equityPrint, asset_class: "option" }, { ...equityPrint, venue: "X", price: null }], {})).toEqual([]);
  expect(eligiblePrints([{ price: 1, size: 1, event_time: 1 }], {})).toEqual([]); // no venue, not a print level
});

test("aggregated notional never masquerades as a single print", () => {
  const aggregate = { ...equityPrint, aggregate: true, price: 100.0, size: 99999 };
  const out = topLevels([aggregate, equityPrint], {});
  expect(out).toHaveLength(1);
  expect(out[0]).toEqual({ price: 100.0, size: 1000, venue: "D", event_time: 1, notional: 100000, direction: "unknown" });
  expect(isExactEquityPrint(aggregate)).toBe(false);
});

test("delay eligibility and corrections replace their originals", () => {
  const delayed = { ...equityPrint, print_id: "p2", delay_seconds: 600 };
  const fast = { ...equityPrint, print_id: "p1", delay_seconds: 30 };
  // no cap: both are present; with a 60s cap the slow one is honestly excluded
  expect(eligiblePrints([delayed, fast], {}).length).toBe(2);
  expect(eligiblePrints([delayed, fast], { maxDelaySeconds: 60 }).map((p) => p.print_id)).toEqual(["p1"]);
  // unknown delay inside an enforced cap is excluded, never assumed fast
  expect(eligiblePrints([{ ...equityPrint, print_id: "p3" }], { maxDelaySeconds: 60 })).toEqual([]);
  // a later corrected restatement replaces the original print
  const original = { ...equityPrint, print_id: "p1" };
  const correction = { ...equityPrint, print_id: "p1c", correction_of: "p1", size: 1200 };
  const out = topLevels([original, correction], { topN: 2 });
  expect(out).toHaveLength(1);
  expect(out[0].size).toBe(1200);
  expect(out[0].direction).toBe("unknown");
});
