/**
 * X4 — pulseState + elapsedClock tests: pin the stale/retry classification
 * contract that drives the Blademap inline-surface pulse badge.
 *
 * These are pure functions from scanLogic.js (L501, L517) that classify
 * scanMeta into dot/label/tier/hint. The component renders what these return;
 * testing them directly pins the contract without rendering the full component.
 *
 * Scope: scanLogic.js pulseState + elapsedClock. No backend, no App.js.
 */

import { pulseState, elapsedClock } from "./scanLogic";

describe("X4 — elapsedClock (scanLogic.js:501)", () => {
  test("null/undefined/NaN/negative → em-dash", () => {
    expect(elapsedClock(null)).toBe("—");
    expect(elapsedClock(undefined)).toBe("—");
    expect(elapsedClock(NaN)).toBe("—");
    expect(elapsedClock(-1)).toBe("—");
    expect(elapsedClock(Infinity)).toBe("—");
  });

  test("seconds under 60 → 'Ns'", () => {
    expect(elapsedClock(0)).toBe("0s");
    expect(elapsedClock(1)).toBe("1s");
    expect(elapsedClock(59)).toBe("59s");
  });

  test("minutes under 60 → 'Nm'", () => {
    expect(elapsedClock(60)).toBe("1m");
    expect(elapsedClock(120)).toBe("2m");
    expect(elapsedClock(3540)).toBe("59m");
  });

  test("hours → 'Nh'", () => {
    expect(elapsedClock(3600)).toBe("1h");
    expect(elapsedClock(7200)).toBe("2h");
  });

  test("rounds to nearest integer", () => {
    expect(elapsedClock(1.4)).toBe("1s");
    expect(elapsedClock(1.6)).toBe("2s");
    // 59.6 → Math.round(59.6)=60 → 60 < 60 false → m=Math.round(60/60)=1 → "1m"
    expect(elapsedClock(59.6)).toBe("1m");
    // 3599 → Math.round(3599)=3599 → m=Math.round(3599/60)=60 → "1h"
    expect(elapsedClock(3599)).toBe("1h");
  });
});

describe("X4 — pulseState classification (scanLogic.js:517)", () => {
  test("error always wins", () => {
    const s = pulseState({ mode: "market", hasError: true, stale: true, retry: 45 });
    expect(s.dot).toBe("r");
    expect(s.label).toBe("ERRORED");
    expect(s.tier).toBe("err");
  });

  test("stale + retry → red ERR tier with retry elapsed", () => {
    const s = pulseState({ stale: true, retry: 45, ttl: 60 });
    expect(s.dot).toBe("r");
    expect(s.label).toContain("STALE");
    expect(s.label).toContain("retry");
    expect(s.tier).toBe("err");
    expect(s.hint).toContain("rate-limited");
  });

  test("stale without retry → yellow WARN tier", () => {
    const s = pulseState({ stale: true, retry: null });
    expect(s.dot).toBe("y");
    expect(s.label).toBe("STALE");
    expect(s.tier).toBe("warn");
    expect(s.hint).toContain("back-pressured");
  });

  test("no data + no mode → LOADING", () => {
    const s = pulseState({ hasData: false, mode: null });
    expect(s.dot).toBe("y");
    expect(s.label).toBe("LOADING");
    expect(s.tier).toBe("warn");
  });

  test("fallback mode → yellow WARN", () => {
    const s = pulseState({ mode: "fallback", hasData: true });
    expect(s.dot).toBe("y");
    expect(s.label).toBe("FALLBACK");
    expect(s.tier).toBe("warn");
  });

  test("market fresh (≤30s) → green LIVE", () => {
    const s = pulseState({ mode: "market", age: 12, ttl: 60 });
    expect(s.dot).toBe("g");
    expect(s.label).toBe("LIVE");
    expect(s.tier).toBe("fresh");
  });

  test("market slow (>30s, ≤90s) → yellow LIVE ·slow", () => {
    const s = pulseState({ mode: "market", age: 45, ttl: 60 });
    expect(s.dot).toBe("y");
    expect(s.label).toBe("LIVE ·slow");
    expect(s.tier).toBe("warn");
  });

  test("market stale-age (>90s) → yellow LIVE ·N", () => {
    const s = pulseState({ mode: "market", age: 120, ttl: 60 });
    expect(s.dot).toBe("y");
    expect(s.label).toContain("LIVE");
    expect(s.tier).toBe("warn");
  });

  test("stale + retry takes priority over market fresh", () => {
    const s = pulseState({ mode: "market", age: 12, stale: true, retry: 10, ttl: 60 });
    expect(s.dot).toBe("r");
    expect(s.label).toContain("STALE");
  });

  test("custom ttl shifts fresh/slow bounds", () => {
    // ttl=30 → freshBound=max(30,15)=30, slowBound=max(90,45)=90
    // age=10 ≤ freshBound(30) → fresh
    const fresh = pulseState({ mode: "market", age: 10, ttl: 30 });
    expect(fresh.tier).toBe("fresh");
    // age=30 ≤ freshBound(30) → still fresh (boundary inclusive)
    const boundary = pulseState({ mode: "market", age: 30, ttl: 30 });
    expect(boundary.tier).toBe("fresh");
    // age=60 > freshBound(30), ≤ slowBound(90) → slow
    const slow = pulseState({ mode: "market", age: 60, ttl: 30 });
    expect(slow.tier).toBe("warn");
    expect(slow.label).toBe("LIVE ·slow");
  });

  test("empty scan with stale mode is still STALE (partial-data edge)", () => {
    const s = pulseState({ mode: "market", stale: true, retry: null, hasData: false });
    expect(s.label).toBe("STALE");
    expect(s.tier).toBe("warn");
  });

  test("stale + retry is ERR tier even with hasData", () => {
    const s = pulseState({ mode: "market", stale: true, retry: 45, hasData: true, ttl: 60 });
    expect(s.dot).toBe("r");
    expect(s.label).toContain("STALE");
    expect(s.tier).toBe("err");
  });
});

describe("X4 — gap: no external stale indicator for inline surfaces", () => {
  test("pulseState can classify stale for any surface, but the component does not expose it separately for inline surfaces", () => {
    // The function CAN classify stale state for the Pulse table, overview
    // rollup, or filter chips — but the component (FlowseekerProBlademap.jsx)
    // only uses pulseState for the scan/market mode badge (L1583-1596), not
    // for the inline surfaces. This documents the gap: the classification
    // machinery exists, but the inline surfaces don't wire it up.
    const s = pulseState({ mode: "market", stale: true, retry: 45 });
    expect(s.label).toContain("STALE");
    expect(s.tier).toBe("err");
  });
});
