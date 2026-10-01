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

test("window admission requires the owning recorded baseline and declared interval", () => {
  const window = { ...complete, overlayMetric: "window", windowBaselineId: "prior", windowInterval: { start: "2026-10-01T13:59:00Z", end: "2026-10-01T14:00:00Z" } };
  expect(admissionBlock({ context: window, overlayMetric: "window", displayMode: "live" })).toBeNull();
  expect(admissionBlock({ context: { ...window, windowBaselineId: null }, overlayMetric: "window", displayMode: "live" })).toMatch(/unavailable|baseline/i);
  expect(admissionBlock({ context: { ...window, windowInterval: null }, overlayMetric: "window", displayMode: "live" })).toMatch(/unavailable|interval/i);
  expect(admissionBlock({ context: { ...window, windowBaselineId: "snap1" }, overlayMetric: "window", displayMode: "live" })).toMatch(/unavailable|baseline/i);
});

test.each(["vex", "charm"])("%s replay requires a recorded metric-envelope selector", (metric) => {
 const context={...complete,metric,overlayMetric:"raw",displayMode:"replay",recordedMetricVersion:"metric-record.v1"};
 expect(admissionBlock({context,overlayMetric:"raw",displayMode:"replay"})).toBeNull();
 expect(admissionBlock({context:{...context,recordedMetricVersion:null},overlayMetric:"raw",displayMode:"replay"})).toMatch(/unavailable|recorded/i);
});

test("missing published selection stays unavailable", () => {
  expect(admissionBlock({ context: {}, overlayMetric: "raw", displayMode: "live" }))
    .toMatch(/No published selection/);
});
