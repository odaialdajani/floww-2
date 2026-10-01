/** @jest-environment jsdom */
import { admissionBlock } from "./AskLodestar";

test("live raw context is admitted", () => {
  expect(admissionBlock({ context: { ticker: "SPY" }, overlayMetric: "raw", displayMode: "live" })).toBeNull();
});

test("replay stays unavailable with an explicit reason", () => {
  expect(admissionBlock({ context: { ticker: "SPY" }, overlayMetric: "raw", displayMode: "replay" }))
    .toMatch(/recorded-snapshot resolution|return to Live/);
});

test("price-history stays unavailable with an explicit reason", () => {
  expect(admissionBlock({ context: { ticker: "SPY" }, overlayMetric: "raw", displayMode: "price-history" }))
    .toMatch(/price-history/);
});

test("adjusted overlays stay unavailable with an explicit reason", () => {
  for (const basis of ["delta", "session_delta_volume", "activity"]) {
    const reason = admissionBlock({ context: { ticker: "SPY" }, overlayMetric: basis, displayMode: "live" });
    expect(reason).toMatch(/Raw OI|adjusted/i);
  }
});

test("missing published selection stays unavailable", () => {
  expect(admissionBlock({ context: {}, overlayMetric: "raw", displayMode: "live" }))
    .toMatch(/No published selection/);
});
