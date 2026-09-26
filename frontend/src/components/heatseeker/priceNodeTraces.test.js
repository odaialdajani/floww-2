import { priceNodeTraces } from "./priceNodeTraces";

test("recorded nodes never bridge missing readings or overnight gaps", () => {
  const frames = [
    { time: "2026-09-10T14:00:00Z", nodes: [{ level: 100 }], nodes_known_at: "2026-09-10T14:00:00Z" },
    { time: "2026-09-11T14:00:00Z", nodes: [] },
  ];
  const traces = priceNodeTraces(frames);
  expect(traces[1].x).toEqual([frames[0].time, "2026-09-10T14:01:00.000Z", null]);
  expect(traces[1].y).toEqual([100, 100, null]);
  expect(traces[1].connectgaps).toBe(false);
});

test("hourly candles cannot extend old nodes beyond their known freshness", () => {
  const traces = priceNodeTraces([
    { time: "2026-09-10T14:00:00Z", duration_seconds: 3600, node_age_seconds: 840,
      nodes: [{ level: 100 }], nodes_known_at: "2026-09-10T13:46:00Z" },
  ]);
  expect(traces[1].x).toEqual(["2026-09-10T14:00:00Z", "2026-09-10T14:01:00.000Z", null]);
});

test("weekly readings cover five-minute candles when fresh", () => {
  const traces = priceNodeTraces([
    { time: "2026-09-10T14:00:00Z", duration_seconds: 300, node_age_seconds: 0,
      nodes: [{ level: 100 }], nodes_known_at: "2026-09-10T14:00:00Z" },
  ]);
  expect(traces[1].x).toEqual(["2026-09-10T14:00:00Z", "2026-09-10T14:05:00.000Z", null]);
});
