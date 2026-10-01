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

const complete = { contextVersion: 2, page: "heatseeker", ticker: "SPY", snapshotId: "snap1",
  mapQuery: { expiries: 4 }, mapVersion: "2026-10-01T14:00:00Z", provider: "fixture", formula: "gex.v2",
  metric: "gex", overlayMetric: "delta", displayMode: "live", activePane: "delta" };

test("verified adjusted selector is admitted, with server-owned numerical resolution", () => {
  expect(admissionBlock({ context: complete, overlayMetric: "delta", displayMode: "live" })).toBeNull();
});

test("replay admission requires a complete recorded identity and rejects changed selection", () => {
  const replay = { ...complete, displayMode: "replay" };
  expect(admissionBlock({ context: replay, overlayMetric: "delta", displayMode: "replay" })).toBeNull();
  expect(admissionBlock({ context: { ...replay, mapQuery: null }, overlayMetric: "delta", displayMode: "replay" })).toMatch(/recorded/i);
  expect(admissionBlock({ context: replay, overlayMetric: "raw", displayMode: "replay" })).toMatch(/selection|basis/i);
});

test("unsupported window and exact-contract contexts remain explicitly unavailable", () => {
  expect(admissionBlock({ context: { ...complete, overlayMetric: "window" }, overlayMetric: "window", displayMode: "live" })).toMatch(/unavailable|unsupported/i);
  expect(admissionBlock({ context: { ...complete, selectedContract: { osi: "X" } }, overlayMetric: "delta", displayMode: "live" })).toMatch(/contract/i);
});

test("missing published selection stays unavailable", () => {
  expect(admissionBlock({ context: {}, overlayMetric: "raw", displayMode: "live" }))
    .toMatch(/No published selection/);
});
