/** @jest-environment jsdom */
import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import axios from 'axios';
import TrinityView from './TrinityView';

jest.mock('../config/api', () => ({
  API: '/api',
  BACKEND_URL: '',
  BACKEND_BASE: '',
}));

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));

function heatmapFixture() {
  const grid = { "2026-10-02": { 760: 5000000, 765: 9000000 } };
  return {
    ticker: "SPY", spot: 767.9, asof: "2026-09-28T12:00:00Z",
    formula_version: "gex.v2", snapshotId: "snap-triad-1",
    data_source: "public_api",
    grid: { expiries: ["2026-10-02"], strikes: [760, 765], grid },
    metrics: {
      walls: [{ wall_id: "w1", low: 760, high: 766, mid: 763, members: [760, 765], gross: 14e6, net: 4e6, call: 9e6, put: 5e6, distance: 4.9, distance_pct: 0.64, rank: 1 }],
      grids: {
        raw: { expiries: ["2026-10-02"], strikes: [760, 765], grid },
        delta: { expiries: ["2026-10-02"], strikes: [760, 765], grid: { "2026-10-02": { 760: 3000000, 765: 5400000 } } },
      },
    },
    scout: { shortlist: { CALLS: [
      { osi: "SPY261002C00760000", type: "call", strike: 760, expiry: "2026-10-02", bid: 1.2, ask: 1.35, delta: .55 },
    ], PUTS: [] } },
    scenarios: [
      { wall_id: "w1", wall_position: "below", name: "Bounce watch", type: "reversal_watch", confirmation: "reclaim and hold above 760", invalidation: "sustained acceptance below 760" },
      { wall_id: "w1", wall_position: "below", name: "Breakdown continuation", type: "continuation", confirmation: "acceptance beyond zone", invalidation: "reclaim and hold above 760" },
    ],
    nodes: { king: { strike: 765 }, regime: "positive" },
    quality: { state: "usable", reasonCodes: [] },
  };
}

const LEADERBOARD = [
  { ticker: "SPY", conviction: 72.5, tier: "MED", direction: "BULL" },
  { ticker: "QQQ", conviction: 41.0, tier: "WATCH", direction: "NEUTRAL" },
];

beforeEach(() => {
  window.sessionStorage.clear();
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) return { data: heatmapFixture() };
    if (u.includes("universe/leaderboard")) return { data: { leaderboard: LEADERBOARD } };
    if (u.includes("/api/contract/")) {
      return { data: { ticker: "SPY", contracts: [
        { osi: "SPY261002C00760000", type: "call", strike: 760, expiry: "2026-10-02", bid: 1.2, ask: 1.35, iv: 0.2, delta: 0.55, open_interest: 1200 },
      ] } };
    }
    if (u.includes("/decisions")) return { data: { decisions: [] } };
    return { data: {} };
  });
  axios.post.mockImplementation(async () => ({ data: { durability: "durable" } }));
});

test("renders backend packet values verbatim with units; no invented fields", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
  // Raw pane header names the metric + units; adjusted pane too.
  expect(screen.getByTestId("triad-pane-raw").textContent).toContain("USD/1% move");
  expect(screen.getByTestId("triad-pane-adjusted").textContent).toContain("dadgex");
  // Backend cell value passes through (5.0M), not recomputed client-side.
  expect(screen.getByTestId("triad-pane-raw").textContent).toContain("$5,000.0K");
  // Source line carries snapshot + formula provenance.
  expect(screen.getByTestId("triad-source").textContent).toContain("snap-triad-1");
});

test("handoff selects the wall and shows its two-sided scenario", async () => {
  window.sessionStorage.setItem("solstice.triadHandoff", JSON.stringify({
    ticker: "SPY", wall_id: "w1", strike: 760, expiry: "2026-10-02",
    snapshotId: "snap-triad-1", ts: Date.now(),
  }));
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-scenario")).toBeInTheDocument());
  expect(screen.getByTestId("triad-scenario-zone").textContent).toContain("760–766");
  expect(screen.getByTestId("triad-scenario-first").textContent).toContain("Bounce watch");
  expect(screen.getByTestId("triad-scenario-first").textContent).toContain("Invalidate:");
  expect(screen.getByTestId("triad-scenario-second").textContent).toContain("Breakdown continuation");
  // Handoff is consumed once.
  expect(window.sessionStorage.getItem("solstice.triadHandoff")).toBeNull();
});

test("wall chips select; drawer lists recorded candidates before any exact-detail request", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-walls")).toBeInTheDocument());
  await act(async () => { fireEvent.click(screen.getByTestId("triad-wall-w1")); });
  await waitFor(() => expect(screen.getByTestId("triad-scenario")).toBeInTheDocument());
  await act(async () => { fireEvent.click(screen.getByTestId("triad-contracts-btn")); });
  await waitFor(() => expect(screen.getByTestId("triad-contract-drawer")).toBeInTheDocument());
  const row = screen.getByTestId("triad-contract-row");
  expect(row.textContent).toContain("SPY261002C00760000");
  expect(row.textContent).toContain("0.55");
  expect(row.textContent).toContain("0.15"); // spread 1.35-1.20
  expect(axios.get.mock.calls.some(([url]) => String(url).includes('/api/contract/'))).toBe(false);
});

test("missing adjusted surface renders unavailable, raw untouched", async () => {
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) {
      const f = heatmapFixture();
      delete f.metrics.grids.delta;
      return { data: f };
    }
    if (u.includes("universe/leaderboard")) return { data: { leaderboard: [] } };
    if (u.includes("/decisions")) return { data: { decisions: [] } };
    return { data: {} };
  });
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-adjusted-unavailable")).toBeInTheDocument());
  expect(screen.getByTestId("triad-pane-raw").textContent).toContain("$5,000.0K");
});

test("context strip describes coverage, never prescribes size; SPX missing is labeled", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-context")).toBeInTheDocument());
  const note = screen.getByTestId("triad-coverage-note");
  expect(note.textContent).toContain("2/3 observed");
  expect(note.textContent).not.toMatch(/conviction|position|size/i);
  expect(screen.getByTestId("triad-context-SPX")) // ^SPX cell key strips the caret
    .toBeInTheDocument();
  expect(screen.getByTestId("triad-context-SPX").textContent).toContain("unscanned");
});

test("review saves through the journal with frozen context", async () => {
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) return { data: heatmapFixture() };
    if (u.includes("universe/leaderboard")) return { data: { leaderboard: [] } };
    if (u.includes("/decisions")) {
      return { data: { decisions: [{ decision_id: "d9", snapshot_id: "snap-triad-1", review_state: null }] } };
    }
    return { data: {} };
  });
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-review-save-reviewed")).toBeInTheDocument());
  await act(async () => { fireEvent.click(screen.getByTestId("triad-review-save-reviewed")); });
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(String(axios.post.mock.calls[0][0])).toContain("/api/solstice/SPY/decisions/d9/review");
  expect(axios.post.mock.calls[0][1].state).toBe("reviewed");
});

test("selected wall shows an actual price path with the zone shaded and VWAP labeled unavailable", async () => {
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) return { data: heatmapFixture() };
    if (u.includes("universe/leaderboard")) return { data: { leaderboard: [] } };
    if (u.includes("price-history")) {
      return { data: { ticker: "SPY", frames: [
        { time: "2026-09-21T14:00:00Z", close: 758 },
        { time: "2026-09-22T14:00:00Z", close: 762 },
        { time: "2026-09-23T14:00:00Z", close: 759 },
        { time: "2026-09-24T14:00:00Z", close: 764 },
      ] } };
    }
    if (u.includes("/decisions")) return { data: { decisions: [] } };
    return { data: {} };
  });
  window.sessionStorage.setItem("solstice.triadHandoff", JSON.stringify({
    ticker: "SPY", wall_id: "w1", strike: 760, expiry: "2026-10-02", ts: Date.now(),
  }));
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-price-path")).toBeInTheDocument());
  const svg = screen.getByTestId("triad-price-path-svg");
  // 4 closes -> 4-point polyline with real coordinates (not flat).
  const pts = svg.querySelector("polyline").getAttribute("points").trim().split(" ");
  expect(pts).toHaveLength(4);
  expect(new Set(pts.map((p) => p.split(",")[1])).size).toBeGreaterThan(1);
  // Wall zone 760-766 shaded; VWAP honestly unavailable.
  expect(screen.getByTestId("triad-price-zone")).toBeInTheDocument();
  expect(screen.getByTestId("triad-price-caption").textContent).toMatch(/VWAP unavailable/i);
});

test("no price candles renders an honest empty, not an empty chart", async () => {
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) return { data: heatmapFixture() };
    if (u.includes("universe/leaderboard")) return { data: { leaderboard: [] } };
    if (u.includes("price-history")) return { data: { ticker: "SPY", frames: [] } };
    if (u.includes("/decisions")) return { data: { decisions: [] } };
    return { data: {} };
  });
  window.sessionStorage.setItem("solstice.triadHandoff", JSON.stringify({
    ticker: "SPY", wall_id: "w1", ts: Date.now(),
  }));
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-price-empty")).toBeInTheDocument());
});

test("contract drawer moves focus in and restores it on close", async () => {
  window.sessionStorage.setItem("solstice.triadHandoff", JSON.stringify({
    ticker: "SPY", wall_id: "w1", strike: 760, expiry: "2026-10-02", ts: Date.now(),
  }));
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-scenario")).toBeInTheDocument());
  const btn = screen.getByTestId("triad-contracts-btn");
  btn.focus();
  await act(async () => { fireEvent.click(btn); });
  await waitFor(() => expect(screen.getByTestId("triad-contract-drawer")).toBeInTheDocument());
  expect(screen.getByTestId("triad-drawer-close")).toHaveFocus();
  await act(async () => { fireEvent.click(screen.getByTestId("triad-drawer-close")); });
  expect(btn).toHaveFocus();
});

test("wall region shows a Below/Spot/Above position strip bound to the zone", async () => {
  window.sessionStorage.setItem("solstice.triadHandoff", JSON.stringify({
    ticker: "SPY", wall_id: "w1", strike: 760, expiry: "2026-10-02", ts: Date.now(),
  }));
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-position")).toBeInTheDocument());
  // Fixture: spot 767.9 above wall 760-766.
  expect(screen.getByTestId("triad-position-state").textContent).toMatch(/above/i);
  const zone = screen.getByTestId("triad-position-zone");
  const spotMk = screen.getByTestId("triad-position-spot");
  const zLeft = parseFloat(zone.style.left);
  const zRight = zLeft + parseFloat(zone.style.width);
  const sLeft = parseFloat(spotMk.style.left);
  // Spot marker sits right of the zone band, both inside 0-100.
  expect(sLeft).toBeGreaterThan(zRight);
  for (const v of [zLeft, zRight, sLeft]) {
    expect(v).toBeGreaterThanOrEqual(0);
    expect(v).toBeLessThanOrEqual(100);
  }
  expect(screen.getByText("Below")).toBeInTheDocument();
  expect(screen.getByText("Above")).toBeInTheDocument();
});
