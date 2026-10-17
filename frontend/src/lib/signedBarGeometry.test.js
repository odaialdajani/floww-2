/** Geometry contract for signed exposure bars (Command Code C1.3/OpenCode).

Mixed signs, all-negative, all-positive, zero, missing, and asymmetric
ranges use actual geometry only. Screenshots remain an OpenCode acceptance
item; this file pins the pixel-plan both sides must implement.
*/

const { signedBarGeometry, zeroLineVisible } = require("./signedBarGeometry");

describe("signed exposure bar geometry", () => {
  test("mixed signs measure from the same zero line in opposite directions", () => {
    const lo = -200;
    const hi = 300;
    const pos = signedBarGeometry(300, lo, hi);
    const neg = signedBarGeometry(-200, lo, hi);
    expect(pos.positive).toBe(true);
    expect(neg.positive).toBe(false);
    expect(pos.zeroFromBottom).toBeCloseTo(40, 10);
    expect(neg.zeroFromBottom).toBeCloseTo(40, 10);
    expect(pos.bottom).toBeCloseTo(40, 10);
    expect(neg.bottom).toBeCloseTo(0, 10);
    expect(pos.height).toBeCloseTo(60, 10);
    expect(neg.height).toBeCloseTo(40, 10);
    expect(zeroLineVisible(lo, hi)).toBe(true);
  });

  test("all-positive range keeps zero at the plot bottom", () => {
    const lo = 10;
    const hi = 110;
    const bar = signedBarGeometry(60, lo, hi);
    expect(bar.positive).toBe(true);
    expect(bar.zeroFromBottom).toBeCloseTo(-10, 10);
    expect(bar.bottom).toBeCloseTo(-10, 10);
    expect(zeroLineVisible(lo, hi)).toBe(false);
  });

  test("all-negative range keeps zero at the plot top", () => {
    const lo = -110;
    const hi = -10;
    const bar = signedBarGeometry(-60, lo, hi);
    expect(bar.positive).toBe(false);
    expect(bar.zeroFromBottom).toBeCloseTo(110, 10);
    expect(bar.bottom).toBeLessThan(bar.zeroFromBottom);
    expect(zeroLineVisible(lo, hi)).toBe(false);
  });

  test("zero and missing values do not invent a direction", () => {
    const zero = signedBarGeometry(0, -100, 100);
    expect(zero.height).toBe(0);
    expect(zero.bottom).toBeCloseTo(50, 10);
    expect(zero.positive).toBe(true);
    const missing = signedBarGeometry(Number.NaN, -100, 100);
    expect(Number.isNaN(missing.height)).toBe(true);
  });

  test("asymmetric ranges stay comparable on one shared scale", () => {
    const lo = -1000;
    const hi = 100;
    const small = signedBarGeometry(100, lo, hi);
    const large = signedBarGeometry(-1000, lo, hi);
    expect(large.height / small.height).toBeCloseTo(10, 8);
    expect(small.bottom).toBeGreaterThan(large.bottom);
  });
});
