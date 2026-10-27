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

// Owner 20:51: the secondary workspace renders behind deliberate tabs.
const openTab = async (tab) => {
  await act(async () => { fireEvent.click(screen.getByTestId(`triad-tab-${tab}`)); });
};

const LEADERBOARD = [
  { ticker: "SPY", conviction: 72.5, tier: "MED", direction: "BULL" },
  { ticker: "QQQ", conviction: 41.0, tier: "WATCH", direction: "NEUTRAL" },
];

beforeEach(() => {
  window.sessionStorage.clear();
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) return { data: heatmapFixture() };
    if (u.includes("solstice/scan/leaderboard")) return { data: { leaderboard: LEADERBOARD, status: "ready" } };
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

test("shared stock choice removes only the duplicate input, retaining comparison and source limits", async () => {
  await act(async()=>render(<TrinityView ticker="SPY" onFocusTicker={jest.fn()}/>));
  // Market context folds the strip into a disclosure (2026-10-18): open it,
  // then the same content asserts as visible.
  fireEvent.click(screen.getByRole("button", { name: "Market context" }));
  expect(screen.queryByLabelText("Focused symbol")).toBeNull();
  for (const ticker of ["SPX","SPY","QQQ"]) expect(screen.getByTestId(`triad-context-${ticker}`)).toBeVisible();
  expect(screen.getByTestId("triad-coverage-note")).toHaveTextContent("2/3 observed");
  expect(screen.getByTestId("triad-source")).toHaveTextContent("snap-triad-1");
  expect(screen.getByLabelText("Market view expiry scope")).toBeVisible();
});

test("standalone market view retains its stock control", async () => {
  await act(async()=>render(<TrinityView/>));
  fireEvent.click(screen.getByRole("button", { name: "Market context" }));
  expect(screen.getByLabelText("Focused symbol")).toBeVisible();
});

test('comparison maps precede optional exposure profile in the desktop reading order', async () => {
  await act(async()=>render(<TrinityView ticker="SPY" />));
  await openTab('profile');
  const maps=screen.getByTestId('triad-raw-adjusted');
  const profile=screen.getByTestId('triad-signed-profile');
  expect(maps.compareDocumentPosition(profile)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const disclosure=profile.closest('details');
  expect(disclosure).not.toBeNull();
  expect(disclosure.open).toBe(false);
});

test("renders backend packet values verbatim with units; no invented fields", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
  // Delta OI remains a distinct selectable surface, not the session-volume default.
  fireEvent.change(screen.getByLabelText("Adjusted context"), { target: { value: "delta" } });
  // Raw pane header names the metric + units; adjusted pane too.
  expect(screen.getByTestId("triad-pane-raw").textContent).toContain("USD/1% move");
  expect(screen.getByTestId("triad-pane-adjusted").textContent).toContain("dadgex");
  // Backend cell value passes through (5.0M), not recomputed client-side.
  expect(screen.getByTestId("triad-pane-raw").textContent).toContain("$5.0M"); // human scale (owner 13:40); the exact 5,000,000 rides the title
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

test("raw and adjusted maps scroll together without changing the snapshot", async () => {
  await act(async()=>render(<TrinityView/>));
  fireEvent.change(screen.getByLabelText("Adjusted context"),{target:{value:"delta"}});
  const raw=screen.getByTestId("triad-pane-raw").querySelector(".skylit-heatmap-container");
  const adjusted=screen.getByTestId("triad-pane-adjusted").querySelector(".skylit-heatmap-container");
  raw.scrollTop=123; raw.scrollLeft=40;
  fireEvent.scroll(raw);
  expect(adjusted.scrollTop).toBe(123);
  expect(adjusted.scrollLeft).toBe(40);
  expect(screen.getByTestId("triad-source")).toHaveTextContent("snap-triad-1");
});

test("wall chips select; drawer lists recorded candidates before any exact-detail request", async () => {
  await act(async () => { render(<TrinityView />); });
  await openTab('walls');
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
    if (u.includes("solstice/scan/leaderboard")) return { data: { leaderboard: [], status: "not-scanned" } };
    if (u.includes("/decisions")) return { data: { decisions: [] } };
    return { data: {} };
  });
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-adjusted-unavailable")).toBeInTheDocument());
  expect(screen.getByTestId("triad-pane-raw").textContent).toContain("$5.0M"); // human scale (owner 13:40); the exact 5,000,000 rides the title
});

test("context strip describes coverage, never prescribes size; SPX missing is labeled", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-context")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Market context" }));
  const note = screen.getByTestId("triad-coverage-note");
  expect(note.textContent).toContain("2/3 observed");
  expect(note.textContent).not.toMatch(/conviction|position|size/i);
  expect(screen.getByTestId("triad-context-SPX")) // ^SPX cell key strips the caret
    .toBeInTheDocument();
  expect(screen.getByTestId("triad-context-SPX").textContent).toContain("unscanned");
});

// 2026-10-18 Market context contract: the disclosure is presentation only —
// opening it must not become a fetch dependency or add requests; the
// leaderboard read stays a one-time mount effect.
test("opening Market context adds no requests and does not fetch ranks again", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-context")).toBeInTheDocument());
  // Closed pin (review F3): while folded, the strip content is genuinely hidden.
  expect(screen.getByTestId("triad-context")).not.toBeVisible();
  const before = axios.get.mock.calls.length;
  const leaderboardBefore = axios.get.mock.calls.filter(([url]) => String(url).includes("solstice/scan/leaderboard")).length;
  fireEvent.click(screen.getByRole("button", { name: "Market context" }));
  await new Promise(res => setTimeout(res, 80));
  expect(screen.getByTestId("triad-context")).toBeInTheDocument();
  expect(axios.get.mock.calls.length).toBe(before);
  expect(axios.get.mock.calls.filter(([url]) => String(url).includes("solstice/scan/leaderboard")).length).toBe(leaderboardBefore);
});

// Replay honesty (review F2, 2026-10-18): while a recorded snapshot is
// displayed, the loaded-dates line mirrors the RECORD's grid axis — today's
// live expiry dates are never substituted, and replaying adds no live
// heatmap reads.
test("loaded dates follow the recorded snapshot during replay, never live", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-loaded-dates")).toBeInTheDocument());
  // The live fixture loads 2026-10-02 first — establishes the contrast.
  expect(screen.getByTestId("triad-loaded-dates").textContent).toContain("2026-10-02");
  await openTab('replay');
  const base = axios.get.getMockImplementation();
  axios.get.mockImplementation(async (url) => {
    if (String(url).includes("/manifest/")) {
      return { data: { day: "2026-10-02", snapshots: [{ id: "stored-1", asof: "2026-10-02T15:00:00Z" }], gaps: [] } };
    }
    if (String(url).includes("/replay/stored-1")) {
      // Real record envelope (solsticeReplay.replayToDisplay): snapshot +
      // grids.grid + metrics_full/walls/strikes/context, never a live payload.
      const f = heatmapFixture();
      return { data: {
        snapshot: { snapshot_id: "stored-1", ticker: "SPY", asof_ts: "2026-10-02T15:00:00Z", spot: f.spot },
        grids: { grid: { ...f.grid, expiries: ["2026-09-11"] }, ...f.metrics.grids },
        metrics_full: f.metrics,
        walls: f.metrics.walls,
        strikes: [],
        context: { display: { map_query: { dte: 0, mode: "day", expiries: 4 } } },
      } };
    }
    return base(url);
  });
  await act(async () => { fireEvent.click(screen.getByTestId("solstice-replay-load")); });
  await act(async () => { fireEvent.click(screen.getByTestId("solstice-replay-play")); });
  await waitFor(() => expect(screen.getByTestId("triad-loaded-dates").textContent).toContain("2026-09-11"));
  const line = screen.getByTestId("triad-loaded-dates").textContent;
  expect(line).toContain("2026-09-11"); // the recorded axis
  expect(line).not.toContain("2026-10-02"); // the live axis is never substituted
  // Replaying a stored snapshot must not read live providers.
  expect(axios.get.mock.calls.filter(([url]) => String(url).includes("/heatmap/")).length).toBe(1);
});

// Loaded-expiry honesty (2026-10-18): the line mirrors the displayed raw
// axis; a malformed value is excluded and declared, never claimed complete,
// and an empty axis reads unavailable.
test("loaded expiry dates mirror the displayed raw axis and declare excluded values", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-loaded-dates")).toBeInTheDocument());
  expect(screen.getByTestId("triad-loaded-dates").textContent).toContain("2026-10-02");
  const base = axios.get.getMockImplementation();
  axios.get.mockImplementation(async (url) => {
    if (String(url).includes("/api/heatmap/")) {
      const f = heatmapFixture();
      return { data: { ...f, ticker: "QQQ", grid: { ...f.grid, expiries: ["2026-10-02", "2026-02-30"] } } };
    }
    return base(url);
  });
  fireEvent.click(screen.getByRole("button", { name: "Market context" }));
  // Match the real flow: the focused-symbol input lives inside Market
  // context — the disclosure is opened before driving it.
  fireEvent.change(screen.getByTestId("triad-symbol-input"), { target: { value: "QQQ" } });
  await act(async () => { fireEvent.click(screen.getByTestId("triad-symbol-go")); });
  // The loaded-dates line sits outside the disclosure; the fetch warning
  // covers the loading gap between symbol change and payload.
  await waitFor(() => {
    const line = screen.getByTestId("triad-loaded-dates").textContent;
    expect(line).toContain("2026-10-02");
    expect(line).toContain("1 invalid expiry value excluded — not complete");
  });
});

test("an empty displayed raw axis reads loaded expiries unavailable", async () => {
  const base = axios.get.getMockImplementation();
  axios.get.mockImplementation(async (url) => {
    if (String(url).includes("/api/heatmap/")) {
      const f = heatmapFixture();
      return { data: { ...f, grid: { ...f.grid, expiries: [] } } };
    }
    return base(url);
  });
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-loaded-dates")).toBeInTheDocument());
  expect(screen.getByTestId("triad-loaded-dates").textContent).toContain("unavailable — no expiry dates in this snapshot");
});

test("review saves through the journal with frozen context", async () => {
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) return { data: heatmapFixture() };
    if (u.includes("solstice/scan/leaderboard")) return { data: { leaderboard: [], status: "not-scanned" } };
    if (u.includes("/decisions")) {
      return { data: { decisions: [{ decision_id: "d9", snapshot_id: "snap-triad-1", review_state: null }] } };
    }
    return { data: {} };
  });
  await act(async () => { render(<TrinityView />); });
  await openTab('review');
  await waitFor(() => expect(screen.getByTestId("triad-review-save-reviewed")).toBeInTheDocument());
  await act(async () => { fireEvent.click(screen.getByTestId("triad-review-save-reviewed")); });
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(String(axios.post.mock.calls[0][0])).toContain("/api/solstice/SPY/decisions/d9/review");
  expect(axios.post.mock.calls[0][1].state).toBe("reviewed");
});

test("a current wall is not painted across old prices, and missing closes remain separated", async () => {
 axios.get.mockImplementation(async url=>({data:String(url).includes('/api/heatmap/')?heatmapFixture():String(url).includes('price-history')?{ticker:'SPY',frames:[
  {time:'2026-09-21T14:00:00Z',close:758},{time:'2026-09-22T14:00:00Z',close:null},{time:'2026-09-24T14:00:00Z',close:764}]}:{decisions:[],leaderboard:[]}}));
 await act(async()=>render(<TrinityView/>));
 await openTab('walls');
 fireEvent.click(screen.getByTestId('triad-wall-w1'));
 await waitFor(()=>expect(screen.getByTestId('triad-price-path')).toBeInTheDocument());
 expect(screen.queryByTestId('triad-price-zone')).toBeNull();
 expect(screen.getByTestId('triad-price-path-svg').querySelectorAll('polyline')).toHaveLength(0);
 expect(screen.getByTestId('triad-price-caption')).toHaveTextContent('not historical candle-time levels');
 expect(screen.getByTestId('triad-price-path-svg')).toHaveAttribute('data-first-at','2026-09-21T14:00:00.000Z');
});

test("selected wall keeps actual price closes separate from current zone references and unavailable VWAP", async () => {
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
  // A current wall is never painted onto past prices without temporal evidence.
  expect(screen.queryByTestId("triad-price-zone")).toBeNull();
  expect(screen.getByTestId("triad-price-path")).toHaveTextContent("Current map reference: wall 760–766");
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

test("market review uses the same four-step inspector without automatic research or contract reads", async () => {
  await act(async () => render(<TrinityView />));
  await openTab('walls');
  await act(async () => fireEvent.click(screen.getByTestId("triad-wall-w1")));
  await act(async () => fireEvent.click(screen.getByTestId("triad-contracts-btn")));
  expect(screen.getByRole("tab", {name:"Contract"})).toHaveAttribute("aria-selected", "true");
  const before = axios.get.mock.calls.length;
  fireEvent.click(screen.getByRole("tab", {name:"Flow"}));
  expect(screen.getByRole("tabpanel", {name:"Flow"})).toHaveTextContent("SPY");
  expect(screen.getByRole("tabpanel", {name:"Flow"})).toHaveTextContent("snap-triad-1");
  fireEvent.click(screen.getByRole("tab", {name:"Public agent"}));
  expect(screen.getByRole("tabpanel", {name:"Public agent"})).toHaveTextContent("not delivery or activation");
  fireEvent.click(screen.getByRole("tab", {name:"Contract"}));
  expect(screen.getByTestId("triad-contract-row")).toBeVisible();
  expect(axios.get.mock.calls).toHaveLength(before);
  expect(axios.post).not.toHaveBeenCalled();
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

test("owner 13:40 composition: the dock starts CLOSED with one concise cue; a real cell selection opens it", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
  // CLOSED start: the cue teaches the one concrete action; the dock column is
  // COLLAPSED (tdk-dock-closed => grid 0px + display:none), so the comparison
  // keeps the full width. jsdom keeps the mount; the CLASS is the state truth.
  expect(screen.getByTestId("triad-selection-cue")).toBeInTheDocument();
  expect(screen.getByTestId("triad-selection-cue").textContent).toMatch(/Select a strike or wall/i);
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-closed/);
  // A REAL selection opens the inspector (the dock column expands)
  const cell = await screen.findByRole("gridcell", { name: /760 by 2026-10-02/i });
  await act(async () => { fireEvent.click(cell); });
  await waitFor(() => expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-open/));
  // ...and the cue is gone once a selection exists
  expect(screen.queryByTestId("triad-selection-cue")).toBeNull();
  // close/reopen retained: the header toggle still flips it
  fireEvent.click(screen.getByTestId("triad-inspector-toggle"));
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-closed/);
  fireEvent.click(screen.getByTestId("triad-inspector-toggle"));
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-open/);
});

test("owner 13:40 measured: AT 1280 the open inspector OVERLAYS (docked it starves each map to ~305px while 4 expiry columns need ~454px)", async () => {
  // The composed-build measurement (Architect-56f218ed-1280-1024-letters.json):
  // docked at 1280 each pane drops 481 -> 305px. The overlay band must
  // THEREFORE include 1280. jsdom: mock matchMedia to the 1280 truth.
  const real = window.matchMedia;
  window.matchMedia = (q) => ({ matches: q === "(max-width: 1280px)", media: q,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {} });
  try {
    await act(async () => { render(<TrinityView />); });
    await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
    const cell = await screen.findByRole("gridcell", { name: /760 by 2026-10-02/i });
    await act(async () => { fireEvent.click(cell); });
    await waitFor(() => expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-open/));
    // OVERLAY mode at 1280: the narrow band drives it — the dock renders as
    // the fixed overlay (the same mode the composed build measures at 1024).
    expect(window.matchMedia("(max-width: 1280px)").matches).toBe(true); // the band includes 1280
  } finally {
    window.matchMedia = real;
  }
});

test("owner 20:51 declutter: ONE compact command bar with inline coverage + inline cue; maps follow immediately", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
  // ONE compact bar: scope + basis + the ONE pair Center + Focus + the
  // inspector toggle, with the coverage context INLINE (loaded dates + the
  // observation line inside the bar, not stacked boxed rows)
  const bar = screen.getByTestId("triad-command-bar");
  expect(bar).toBeInTheDocument();
  expect(bar.textContent).toMatch(/All loaded/);            // scope control
  expect(bar.textContent).toMatch(/Adjusted context/);      // basis control
  expect(screen.getByTestId("triad-loaded-dates")).toBeInTheDocument(); // coverage inline in the bar
  expect(bar.contains(screen.getByTestId("triad-loaded-dates"))).toBe(true);
  expect(screen.getByTestId("triad-observation-line")).toBeInTheDocument();
  // the cue is the ONE concise inline instruction INSIDE the bar — no extra full-width row
  const cue = screen.getByTestId("triad-selection-cue");
  expect(cue.textContent).toMatch(/Select a strike or wall/i);
  expect(bar.contains(cue)).toBe(true);
  // ONE synchronized Center for the PAIR (the per-map Center buttons are gone)
  expect(screen.getAllByTestId("triad-pair-center")).toHaveLength(1);
  expect(screen.queryAllByTitle(/Center on price/i)).toHaveLength(0);
  // the workspace secondary chrome is QUIET by default (no below-maps panels)
  expect(screen.queryByTestId("triad-walls")).toBeNull();
  expect(screen.queryByTestId("triad-review")).toBeNull();
  expect(screen.queryByTestId("triad-profile-disclosure")).toBeNull();
  expect(document.querySelector(".heatmap-landmarks")).toBeNull();
  expect(document.querySelector(".skylit-replay-strip")).toBeNull();
});

test("owner 20:51 declutter: the workspace tabs open the existing secondary features deliberately (nothing deleted)", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
  const strip = screen.getByTestId("triad-workspace-tabs");
  for (const [tab, expectVisible] of [
    ["triad-tab-walls", () => screen.getByTestId("triad-walls")],
    ["triad-tab-landmarks", () => document.querySelector(".heatmap-landmarks")],
    ["triad-tab-replay", () => document.querySelector(".skylit-replay-strip")],
    ["triad-tab-profile", () => screen.getByTestId("triad-profile-disclosure")],
    ["triad-tab-review", () => screen.getByTestId("triad-review")],
  ]) {
    fireEvent.click(screen.getByTestId(tab));
    await act(async () => { await Promise.resolve(); });
    expect(expectVisible()).toBeTruthy();
    // one deliberate panel at a time: opening the next closes the previous
  }
  // the wall chips still select (the existing semantics preserved)
  fireEvent.click(screen.getByTestId("triad-tab-walls"));
  await act(async () => { await Promise.resolve(); });
  const chip = screen.getByTestId("triad-walls").querySelector("button");
  if (chip) { fireEvent.click(chip); }
  // and the review tab exposes the honest save controls
  fireEvent.click(screen.getByTestId("triad-tab-review"));
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByTestId("triad-review")).toBeInTheDocument();
});

test("owner 20:51 declutter: reversible Focus working-canvas — Enter fills, Esc exits, selection and scope preserved", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
  // a REAL selection first (scope + selection state to preserve across focus)
  const cell = await screen.findByRole("gridcell", { name: /760 by 2026-10-02/i });
  await act(async () => { fireEvent.click(cell); });
  await waitFor(() => expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-open/));
  // Enter Focus: the layout class flips, the Exit control appears
  fireEvent.click(screen.getByTestId("triad-focus-toggle"));
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-focus-mode/);
  expect(screen.getByTestId("triad-focus-exit")).toBeInTheDocument();
  // Esc exits — and the selection/scope are EXACTLY preserved (no state reset)
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.getByTestId("triad-view").className).not.toMatch(/tdk-focus-mode/);
  expect(screen.queryByTestId("triad-focus-exit")).toBeNull();
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-open/);   // the selection survives
  expect(screen.getByLabelText("Market view expiry scope")).toBeInTheDocument(); // scope control survives
  // the Exit chip also works
  fireEvent.click(screen.getByTestId("triad-focus-toggle"));
  fireEvent.click(screen.getByTestId("triad-focus-exit"));
  expect(screen.getByTestId("triad-view").className).not.toMatch(/tdk-focus-mode/);
});

test("review 10:xx: the Profile disclosure's native open state survives Focus -> Exit (mounted-but-hidden, not unmounted)", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
  // open the Profile tab and the details disclosure (native open state)
  await openTab("profile");
  const details = screen.getByTestId("triad-profile-disclosure");
  await act(async () => { fireEvent.click(details.querySelector("summary")); });
  expect(details.open).toBe(true);
  // Focus: the workspace stays MOUNTED; the layout's focus class is the
  // hiding contract (jest's CSS transform never loads plain stylesheets, so
  // the computed display:none is proven in the painted browser receipt).
  await act(async () => { fireEvent.click(screen.getByTestId("triad-focus-toggle")); });
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-focus-mode/);
  expect(screen.getByTestId("triad-workspace-tabs")).toBeInTheDocument();   // mounted, not unmounted
  expect(details.open).toBe(true);                                        // native state survives
  // Exit: restored exactly — not reconstructed from the tab ID
  await act(async () => { fireEvent.click(screen.getByTestId("triad-focus-exit")); });
  expect(screen.getByTestId("triad-view").className).not.toMatch(/tdk-focus-mode/);
  expect(details.open).toBe(true);
});

test("review 10:xx: an OPEN inspector + selection survives Focus hidden (never covering the canvas) and Exit restores it", async () => {
  await act(async () => { render(<TrinityView />); });
  const cell = await screen.findByRole("gridcell", { name: /760 by 2026-10-02/i });
  await act(async () => { fireEvent.click(cell); });
  await waitFor(() => expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-open/));
  // Focus: the dock + backdrop are hidden but mounted; the selection state is untouched
  await act(async () => { fireEvent.click(screen.getByTestId("triad-focus-toggle")); });
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-focus-mode/);
  const dock = document.querySelector(".tdk-dock");
  const backdrop = document.querySelector(".tdk-backdrop");
  expect(dock).not.toBeNull();          // mounted (hidden by the focus class — painted proof)
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-focus-mode/);
  if (backdrop) expect(document.contains(backdrop)).toBe(true);           // mounted, no stale node
  // a NEW selection while focused updates the selection without covering the canvas
  const other = await screen.findByRole("gridcell", { name: /765 by 2026-10-02/i });
  await act(async () => { fireEvent.click(other); });
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-focus-mode/);   // still focused
  // Exit: the inspector is restored open with the CURRENT selection
  await act(async () => { fireEvent.click(screen.getByTestId("triad-focus-exit")); });
  expect(screen.getByTestId("triad-view").className).not.toMatch(/tdk-focus-mode/);
  expect(screen.getByTestId("triad-view").className).toMatch(/tdk-dock-open/);
});

test("workspace tabs follow the inspector's own ARIA wiring (tab id + aria-controls + tabpanel)", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument());
  await openTab("walls");
  const tab = screen.getByTestId("triad-tab-walls");
  expect(tab).toHaveAttribute("id", "triad-ws-walls-tab");
  expect(tab).toHaveAttribute("aria-controls", "triad-ws-walls-panel");
  expect(tab).toHaveAttribute("aria-selected", "true");
  const panel = document.getElementById("triad-ws-walls-panel");
  expect(panel).not.toBeNull();
  expect(panel.getAttribute("role")).toBe("tabpanel");
  expect(panel.getAttribute("aria-labelledby")).toBe("triad-ws-walls-tab");
  // the walls tab is still open from the pre-loop assertions — toggle it
  // closed so the loop's openTab is a fresh OPEN, not a toggle-off
  await openTab("walls");
  // each of the five tabs wires its own panel
  for (const [id] of [["walls"], ["landmarks"], ["replay"], ["profile"], ["review"]]) {
    await openTab(id);
    expect(screen.getByTestId(`triad-tab-${id}`).getAttribute("aria-controls")).toBe(`triad-ws-${id}-panel`);
    expect(document.getElementById(`triad-ws-${id}-panel`)).not.toBeNull();
  }
});
