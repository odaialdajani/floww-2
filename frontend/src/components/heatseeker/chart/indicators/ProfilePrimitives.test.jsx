// B23 profile primitives mirror tests: synthetic only.
import { initialBalance, nakedLevels, poc, tickRows, valueArea } from "./ProfilePrimitives";

test("tick bins fold equal prices without inventing a side", () => {
  const out = tickRows(
    [
      { price: 100.004, size: 10 },
      { price: 100.001, size: 5 },
      { price: 100.011, size: 7 },
      { price: 100.4, size: 3 },     // unclassified size guard below
    ],
    0.01
  );
  expect(out.status).toBe("ok");
  const bin100 = out.rows.find((r) => r.price === 100);
  const bin101 = out.rows.find((r) => r.price === 100.01); // Math.round(100.011 / 0.01) = 10001
  const bin104 = out.rows.find((r) => r.price === 100.4);
  expect(bin100.volume).toBe(15);
  expect(bin101.volume).toBe(7);
  expect(bin104.volume).toBe(3);
  expect(tickRows([{ price: 1, size: null }], 0.01).status).toBe("unknown");
  expect(tickRows([], 0.01).status).toBe("unknown");
  expect(tickRows([], null).status).toBe("unavailable");
  expect(tickRows([], 0).status).toBe("unavailable");
});

test("POC ties resolve downward", () => {
  const rows = [{ price: 100, volume: 10 }, { price: 101, volume: 10 }, { price: 102, volume: 5 }];
  expect(poc(rows).price).toBe(100);
  expect(poc([{ price: 50, volume: 3 }]).price).toBe(50);
  expect(poc([])).toBeNull();
});

test("value area expands from POC toward ~70% and stops honestly at gaps", () => {
  const rows = [{ price: 100, volume: 10 }, { price: 101, volume: 10 }, { price: 102, volume: 5 }];
  const va = valueArea(rows, 0.70);
  expect(va.status).toBe("ok");
  expect(va.low).toBe(100);
  expect(va.high).toBe(101);
  expect(va.attained).toBeGreaterThanOrEqual(0.7);
  expect(valueArea([], 0.7)).toEqual({ status: "unavailable" });
  expect(valueArea([{ price: 100, volume: 0 }], 0.7)).toEqual({ status: "unavailable" });
  // all-volume-at-poc degenerates to a one-row area with attained 1
  expect(valueArea([{ price: 100, volume: 10 }], 0.7)).toEqual({ status: "ok", low: 100, high: 100, attained: 1 });
});

test("naked levels end at first revisit and never at a future observation", () => {
  const levels = [
    { price: 100.0, session_start: "2026-10-06" },
    { price: 200.0, session_start: "2026-10-06" },
  ];
  const bars = [
    { time: "t1", low: 90.0, high: 95.0 },
    { time: "t2", low: 99.0, high: 101.0 },
  ];
  const out = nakedLevels(levels, bars);
  expect(out[0]).toEqual({ price: 100.0, visible_from: "2026-10-06", visible_until: "t2", naked: false });
  expect(out[1].naked).toBe(true);
  expect(out[1].visible_until).toBeNull();
  expect(nakedLevels([{ price: 1.0 }], bars)).toEqual([]); // no observed session start

  // observations after the cursor are future sessions: with the cursor at
  // t2 nothing beyond t2 may close a level even though a later session does
  const futureBars = [
    { time: "t2", low: 90.0, high: 95.0 },
    { time: "t3", low: 199.0, high: 201.0 },
  ];
  const atCursor = nakedLevels(levels, futureBars, { cursor: "t2" });
  expect(atCursor[0].naked).toBe(true);
  expect(atCursor[0].visible_until).toBeNull();
  expect(atCursor[1].naked).toBe(true);
  const beyond = nakedLevels(levels, futureBars);
  expect(beyond[0].naked).toBe(true); // no known bar ever revisits 100
  expect(beyond[1]).toEqual({ price: 200.0, visible_from: "2026-10-06", visible_until: "t3", naked: false });
});

test("initial balance uses opening bars only and never future ones", () => {
  const bars = [
    { time: "t1", low: 99, high: 101 },
    { time: "t2", low: 98, high: 103 },
    { time: "t3", low: 90, high: 120 },
  ];
  const ib = initialBalance(bars, { periods: 2 });
  expect(ib).toEqual({ status: "ok", low: 98, high: 103, periods: 2, approximation: "bar-resolution" });
  // cursor before the third bar: the future bar stays out of the range
  expect(initialBalance(bars, { periods: 3, cursor: "t2" })).toEqual({
    status: "ok", low: 98, high: 103, periods: 2, approximation: "bar-resolution",
  });
  expect(initialBalance([], {}).status).toBe("unknown");
});
