// B23 profile primitives mirror tests: synthetic only.
import { initialBalance, nakedLevels, poc, tickRows, valueArea, tpoPeriods, sessionZones } from "./ProfilePrimitives";

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
  // R21-04 mirror: 200 is OUTSIDE every observed bar (90-101) — it can
  // never be certified untouched, so it is honestly not-claimable rather
  // than claimed "naked" on data that cannot support the claim.
  expect(out[1].naked).toBeNull();
  expect(out[1].reason).toBe("level-outside-known-range");
  expect(out[1].visible_until).toBeNull();
  expect(nakedLevels([{ price: 1.0 }], bars)).toEqual([]); // no observed session start

  // observations after the cursor are future sessions: with the cursor at
  // t2 nothing beyond t2 may close a level even though a later session does
  const futureBars = [
    { time: "t2", low: 90.0, high: 95.0 },
    { time: "t3", low: 199.0, high: 201.0 },
  ];
  const atCursor = nakedLevels(levels, futureBars, { cursor: "t2" });
  // At the cursor only t2 is knowable (range 90-95): neither 100 nor 200 is
  // inside the KNOWN range, so neither can be certified untouched — honest
  // not-claimable (R21-04 mirror), and the future t3 session closes nothing.
  expect(atCursor[0].naked).toBeNull();
  expect(atCursor[0].reason).toBe("level-outside-known-range");
  expect(atCursor[0].visible_until).toBeNull();
  expect(atCursor[1].naked).toBeNull();
  expect(atCursor[1].reason).toBe("level-outside-known-range");
  const beyond = nakedLevels(levels, futureBars);
  // with t3 knowable the range covers 90-201: 100 is IN range and never
  // revisited — honestly naked; t3 does close 200.
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
  // cursor before the third bar: the future bar stays out of the range —
  // a TRUNCATED opening window is never "ok" (R21-04 mirror of the backend's
  // opening-history-truncated refusal; the observed bounds stay attached)
  expect(initialBalance(bars, { periods: 3, cursor: "t2" })).toEqual({
    status: "incomplete", reason: "opening-history-truncated",
    low: 98, high: 103, periods: 2, expectedPeriods: 3, approximation: "bar-resolution",
  });
  expect(initialBalance([], {}).status).toBe("unknown");
});


// R21-04 mirror: the client primitives name the same honest refusals as the
// backend admission contracts — never a softer local version.
test("naked levels outside the known range are not-claimable, never naked", () => {
  const bars = [{ time: "t1", low: 99, high: 103 }, { time: "t2", low: 98, high: 104 }];
  // touched inside the range stays a closed level
  const touched = nakedLevels([{ price: 100, session_start: "s" }], bars);
  expect(touched[0].naked).toBe(false);
  // a level outside every observed bar can NEVER be certified untouched
  const outside = nakedLevels([{ price: 500, session_start: "s" }], bars);
  expect(outside[0].naked).toBeNull();
  expect(outside[0].reason).toBe("level-outside-known-range");
  // no knowable bars at all: honest not-claimable for every level
  const none = nakedLevels([{ price: 100, session_start: "s" }], [], {});
  expect(none[0].naked).toBeNull();
  expect(none[0].reason).toBe("not-claimable");
});


// B23 TPO/session zones — bar-resolution approximation (per the block row,
// the labeled bar approximation proceeds without the classified-tape
// contract; it is NEVER claimed as tick-true TPO).
test("tpoPeriods groups knowable bars into 30-minute periods with letters", () => {
  const bars = [
    { time: 0, low: 99, high: 101 },
    { time: 15 * 60000, low: 100, high: 102 },
    { time: 31 * 60000, low: 98, high: 103 },   // second period
    { time: 62 * 60000, low: 97, high: 104 },   // third period
  ];
  const tpo = tpoPeriods(bars);
  expect(tpo.status).toBe("ok");
  expect(tpo.periods).toHaveLength(3);
  expect(tpo.periods.map(g => g.letter)).toEqual(["A", "B", "C"]);
  expect(tpo.periods[0].low).toBe(99);
  expect(tpo.periods[0].high).toBe(102);       // both bars of period A
  expect(tpo.approximation).toBe("bar-resolution");
  // bars beyond the cursor never join a period
  const atCursor = tpoPeriods(bars, { cursor: 20 * 60000 });
  expect(atCursor.periods).toHaveLength(1);
  // nothing knowable -> honest unavailable, never an empty ok
  expect(tpoPeriods([]).status).toBe("unavailable");
});

test("sessionZones covers only bars knowable at the cursor", () => {
  const bars = [
    { time: 0, low: 99, high: 101 },
    { time: 30 * 60000, low: 100, high: 105 },
    { time: 60 * 60000, low: 98, high: 103 },
  ];
  const zones = sessionZones(bars);
  expect(zones.status).toBe("ok");
  expect(zones.high).toBe(105);
  expect(zones.low).toBe(98);
  expect(zones.bars).toBe(3);
  expect(zones.firstKnownTime).toBe(0);
  expect(zones.lastKnownTime).toBe(60 * 60000);
  // partial session: the cursor cuts the envelope honestly
  const partial = sessionZones(bars, { cursor: 45 * 60000 });
  expect(partial.high).toBe(105);
  expect(partial.bars).toBe(2);
  expect(sessionZones([]).status).toBe("unavailable");
  // open/close stay honestly absent when the bars carry none
  expect(zones.open).toBeNull();
  expect(zones.close).toBeNull();
});

// H3 b23 residual: sessionZones assumed time-sorted frames. The envelope is
// order-independent by construction — first/last KNOWN must be true min/max.
test("sessionZones order-independence: unsorted frames still report true first/last known", () => {
  const bars = [
    { time: 60 * 60000, low: 98, high: 103 },
    { time: 0, low: 99, high: 101 },
    { time: 30 * 60000, low: 100, high: 105 },
  ];
  const zones = sessionZones(bars);
  expect(zones.firstKnownTime).toBe(0);
  expect(zones.lastKnownTime).toBe(60 * 60000);
  expect(zones.high).toBe(105);
  expect(zones.low).toBe(98);
});
