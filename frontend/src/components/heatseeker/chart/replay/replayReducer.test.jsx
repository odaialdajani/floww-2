// B15 replay mirror tests: synthetic only, honest unknown states.
import {
  ageOk,
  barAt,
  cacheAt,
  createReplayState,
  historyRatio,
  partialBar,
  reduceCaches,
  replayStep,
  routeEvent,
  sweepExtrema,
  visibleSnapshot,
} from "./replayReducer";

describe("known-at algebra", () => {
  test("snapshot absent before its known-at; late older never rewinds", () => {
    const snaps = [{ id: "a", known_at: 100 }, { id: "b", known_at: 90 }];
    expect(visibleSnapshot(snaps, 50)).toBeNull(); // nothing known yet
    expect(visibleSnapshot(snaps, 95)).toEqual({ id: "b", known_at: 90 });
    expect(visibleSnapshot(snaps, 105)).toEqual({ id: "a", known_at: 100 });
    // unknown known_at never becomes visible
    expect(visibleSnapshot([{ id: "x", known_at: null }, { id: "y" }], 999)).toBeNull();
  });
});

describe("age gate", () => {
  test("900s eligible, 901s absent, unknown as-of refused", () => {
    expect(ageOk(0, 900)).toBe(true);
    expect(ageOk(0, 901)).toBe(false);
    expect(ageOk(null, 10)).toBe(false);
    expect(ageOk("5", "10")).toBe(true);
  });
});

describe("future observations stay hidden", () => {
  test("extrema sweep excludes bars beyond the cursor", () => {
    const bars = [
      { time: 10, high: 101, low: 99 },
      { time: 20, high: 105, low: 98 },
      { time: 30, high: 120, low: 90 },
    ];
    expect(sweepExtrema(bars, 20)).toEqual({ status: "ok", high: 105, low: 98, count: 2, cursor: 20 });
    expect(sweepExtrema(bars, 5)).toEqual({ status: "unknown", reason: "no eligible bar at cursor" });
    expect(sweepExtrema([{ time: 10, high: null, low: null }], 20).status).toBe("unknown");
    // later ratio: the future leg leaves the ratio unavailable
    const past = { time: 10, value: 100 };
    const future = { time: 30, value: 50 };
    expect(historyRatio(past, past, 20)).toEqual({ status: "ok", ratio: 1 });
    expect(historyRatio(past, future, 20)).toEqual({ status: "unavailable", reason: "future or missing leg" });
  });
});

describe("replay events never feed live caches (and vice versa)", () => {
  test("reduceCaches keeps each cache separate and drops unknown origin", () => {
    const start = createReplayState(10);
    let next = replayStep(start, { type: "admit", event: { id: "e1", symbol: "SPY", origin: "replay", value: 5, time: 10 } });
    next = replayStep(next, { type: "admit", event: { id: "e2", symbol: "SPY", origin: "live", value: 7, time: 12 } });
    next = replayStep(next, { type: "admit", event: { id: "e3", symbol: "AAPL", origin: "replay", value: 9, time: 12 } });
    next = replayStep(next, { type: "admit", event: { id: "e4", origin: "unknown", value: 1 } });
    expect(cacheAt(next.caches, "live", "SPY").e2.value).toBe(7);
    expect(cacheAt(next.caches, "live", "SPY").e1).toBeUndefined(); // replay event not in live cache
    expect(cacheAt(next.caches, "replay", "SPY").e1.value).toBe(5);
    expect(cacheAt(next.caches, "replay", "AAPL").e3.value).toBe(9);
    expect(cacheAt(next.caches, "live", "SPY").e3).toBeUndefined(); // other symbol stays out
    expect(cacheAt(next.caches, "replay", "AAPL").e2).toBeUndefined();
    expect(next.dropped).toContain("e4");
    // routeEvent preserves the untouched live cache by identity
    const caches = { live: { SPY: {} }, replay: {} };
    const routed = routeEvent(caches, { id: "r1", symbol: "SPY", origin: "replay", value: 1, time: 1 });
    expect(routed.live).toBe(caches.live);
    expect(caches.replay).toEqual({});
  });

  test("cross-symbol gaps read as unknown, never borrowed", () => {
    const caches = reduceCaches(
      { live: {}, replay: {} },
      [{ id: "s1", symbol: "SPY", origin: "live", value: 3, time: 1 }]
    );
    expect(cacheAt(caches, "live", "SPY").s1.value).toBe(3);
    expect(cacheAt(caches, "live", "AAPL")).toBeNull();
  });
});

describe("partial versus completed bars", () => {
  test("partial admits only event_time and available_at <= cursor", () => {
    const events = [
      { event_time: 10, available_at: 10, open: 1, close: 2 },
      { event_time: 20, available_at: 30, open: 2, close: 3 },
    ];
    expect(partialBar(events, 25)).toEqual({ open: 1, close: 2, complete: false, count: 1 });
    expect(partialBar(events, 5)).toBeNull();
    // cursor 25 inside the window (end 30): explicitly partial
    expect(barAt(events, 25, 30)).toEqual({ open: 1, close: 2, complete: false, count: 1 });
    // window ended and the late leg arrived: completed with the last close
    expect(barAt(events, 40, 30)).toEqual({ open: 1, close: 3, complete: true, count: 2 });
    // window ended but a leg is still unavailable: stays partial, open only
    const halfKnown = [
      { event_time: 5, available_at: 5, open: 1, open_error: null },
      { event_time: 15, available_at: 60, open: 2, close: 4 },
    ];
    expect(barAt(halfKnown, 45, 30)).toEqual({ open: 1, close: null, complete: false, count: 1 });
    // no event known at the cursor at all
    expect(barAt([{ event_time: 10, available_at: 60, open: 1, close: 2 }], 50, 30)).toBeNull();
  });
});
