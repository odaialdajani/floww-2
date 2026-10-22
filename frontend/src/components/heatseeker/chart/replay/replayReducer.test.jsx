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
    expect(partialBar(events, 25)).toEqual({ open: 1, close: 2, complete: false, count: 1, pending: 1, lastAvailableAt: 10, bucketStart: 0, bucketEnd: 900 });
    // cursor 5: the bucket HAS legs but none is available yet — forming with
    // both pending, never a fabricated admission
    expect(partialBar(events, 5)).toEqual({ open: null, close: null, complete: false, count: 0, pending: 2, lastAvailableAt: null, bucketStart: 0, bucketEnd: 900 });
    // cursor 25 inside its 30s bucket with the second leg still unavailable
    expect(barAt(events, 25, 30)).toEqual({ open: 1, close: 2, complete: false, count: 1, pending: 1, lastAvailableAt: 10, bucketStart: 0, bucketEnd: 30 });
    // the [30,60) bucket has no events at all: honest null, no earlier leak
    expect(barAt(events, 50, 30)).toBeNull();
    // a leg of the owning bucket is still unavailable: stays partial, open only
    const halfKnown = [
      { event_time: 35, available_at: 35, open: 1, open_error: null },
      { event_time: 40, available_at: 60, open: 2, close: 4 },
    ];
    expect(barAt(halfKnown, 45, 30)).toEqual({ open: 1, close: null, complete: false, count: 1, pending: 1, lastAvailableAt: 35, bucketStart: 30, bucketEnd: 60 });
    // no event of the owning bucket known at the cursor at all
    expect(barAt([{ event_time: 10, available_at: 60, open: 1, close: 2 }], 50, 30)).toBeNull();
  });

  // R21-02: the owning bar is the bar_seconds bucket that contains the
  // cursor — events from an earlier bucket never aggregate into it.
  test("barAt aggregates only the owning bar_seconds bucket", () => {
    const events = [
      { event_time: 0, available_at: 900, open: 100, close: 110 },
      { event_time: 900, available_at: 1800, open: 200, close: 210 },
      { event_time: 1500, available_at: 1800, open: 205, close: 215 },
    ];
    // cursor 1500 sits inside the [900, 1800) bucket on a 900s chart:
    // the 0-bucket event must NOT leak into this bar.
    const bar = barAt(events, 1500, 900);
    expect(bar.open).toBe(null);   // the 900-bucket legs are available only at 1800
    expect(bar.close).toBe(null);
    expect(bar.count).toBe(0);
    expect(bar.pending).toBe(2);
    expect(bar.bucketStart).toBe(900);
    expect(bar.bucketEnd).toBe(1800);
    expect(bar.complete).toBe(false);
    // cursor inside the FIRST bucket sees only that bucket's event
    expect(barAt(events, 500, 900)).toEqual({ open: null, close: null, complete: false, count: 0, pending: 1, lastAvailableAt: null, bucketStart: 0, bucketEnd: 900 });
    // a cursor before any bucket event: honest null, no earlier-bar leak
    expect(barAt(events, -10, 900)).toBeNull();
  });

  // R21-02: unknown availability is never invented — an event without a
  // real available_at does not contribute at ANY cursor (no `: 1` default).
  test("unknown available_at never admits an event", () => {
    const events = [
      { event_time: 10, available_at: null, open: 1, close: 2 },
      { event_time: 15, open: 3, close: 4 },
    ];
    // both legs exist in the bucket but neither has a real availability:
    // nothing is admitted (count 0, all pending) — never a `: 1` invention
    expect(barAt(events, 50, 900)).toEqual({ open: null, close: null, complete: false, count: 0, pending: 2, lastAvailableAt: null, bucketStart: 0, bucketEnd: 900 });
    // the known one still aggregates honestly
    const known = [{ event_time: 10, available_at: 20, open: 1, close: 2 }];
    expect(barAt(known, 50, 900)).toEqual({ open: 1, close: 2, complete: false, count: 1, pending: 0, lastAvailableAt: 20, bucketStart: 0, bucketEnd: 900 });
  });

  // R21-02: a recorded frame is available when its window CLOSES (the
  // server-emitted end_time), never at its own open time.
  test("bar completion honors the emitted end_time availability", () => {
    const events = [
      { event_time: 900, available_at: 1800, open: 200, close: 210 },
    ];
    // cursor 1700: the bar's own values are final only at 1800 — forming,
    // nothing admitted, the leg honestly pending
    const forming = barAt(events, 1700, 900);
    expect(forming.complete).toBe(false);
    expect(forming.count).toBe(0);
    expect(forming.pending).toBe(1);
    // the close marker leg stays pending until its emitted availability:
    // an early leg shows while the window-close leg is still unavailable
    const withClose = [
      { event_time: 900, available_at: 1000, open: 200, close: 210 },
      { event_time: 950, available_at: 1800, close: 212, open: 200 },
    ];
    expect(barAt(withClose, 1700, 900)).toEqual({ open: 200, close: 210, complete: false, count: 1, pending: 1, lastAvailableAt: 1000, bucketStart: 900, bucketEnd: 1800 });
  });
});
