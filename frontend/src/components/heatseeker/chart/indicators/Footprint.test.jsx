// B22 footprint mirror tests: synthetic only.
import { CAPABILITIES, candleDelta, footprintCell, sessionCvd } from "./Footprint";

test("only classified buy/sell sizes produce rows; unclassified stays separate", () => {
  const out = sessionCvd([
    { buy: 100, sell: 40, unclassified: 25 },
    { buy: 10, sell: 20 },
    null,
    { buy: 5, sell: null },
  ]);
  expect(out.status).toBe("ok");
  expect(out.rows).toHaveLength(2);
  expect(out.rows[0]).toEqual({ open: 0, close: 60, delta: 60, unclassified: 25, time: null });
  expect(out.rows[1].close).toBe(50);
  expect(out.rows[1].unclassified).toBe(0);
  const cell = footprintCell({ buy: 30, sell: 10, unclassified: 8 });
  expect(cell).toEqual({ status: "ok", buy: 30, sell: 10, net: 20, unclassified: 8 });
  expect(footprintCell({ buy: 30, sell: null }).status).toBe("unknown");
  expect(footprintCell(null).status).toBe("unknown");
});

test("a new session re-zeros the running delta", () => {
  const out = sessionCvd([
    { time: "s1:1", buy: 100, sell: 40 },
    { time: "s1:2", buy: 10, sell: 20 },
    { time: "s2:1", buy: 5, sell: 2, session_reset: true },
  ]);
  expect(out.rows[0].open).toBe(0);
  expect(out.rows[2].open).toBe(0);        // session boundary re-zeroes
  expect(out.rows[2].delta).toBe(3);
  expect(out.rows[2].close).toBe(3);       // not the carried 50
});

test("a corrected restatement replaces its original, never double-counts", () => {
  const out = sessionCvd([
    { time: "t1", buy: 100, sell: 40 },
    { time: "t1", buy: 50, sell: 40, corrected: true },
  ]);
  expect(out.status).toBe("ok");
  expect(out.rows).toHaveLength(1);
  expect(out.rows[0]).toEqual({ open: 0, close: 10, delta: 10, unclassified: 0, time: "t1" });
});

test("disabled capability renders the whole read unavailable", () => {
  const out = sessionCvd([{ buy: 10, sell: 5 }], { capabilities: { classified_sizes: false } });
  expect(out.status).toBe("unavailable");
  expect(out.reason).toBe("capability disabled: classified_sizes");
  expect(out.rows).toEqual([]);
  expect(CAPABILITIES.classified_sizes).toBe(true);
});

test("no pseudo-CVD from candle direction", () => {
  const refusal = candleDelta();
  expect(refusal.status).toBe("unavailable");
  expect(refusal.reason).toContain("candle direction is not classified trade flow");
});
