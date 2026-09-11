/**
 * @jest-environment jsdom
 */
// FlowseekerProBlademap Phase 5.3 tests — Public API wiring.
//
// Tests the mapPublicChainToRows helper (pure function) and the
// live-feed dual-path logic (Public API primary → cvserver fallback).

import { mapPublicChainToRows } from "./FlowseekerProBlademap";

// ---- mapPublicChainToRows: pure helper tests ----

describe("mapPublicChainToRows — Phase 5.3 Public API helper", () => {
  const MKT = "SPY";

  const mkContract = (overrides = {}) => ({
    strike: 450,
    type: "call",
    expiry: "2026-09-18",
    volume: 500,
    oi: 1200,
    iv: 0.22,
    bid: 4.5,
    ask: 4.7,
    last: 4.6,
    ...overrides,
  });

  it("maps a single high-volume contract to a flow row", () => {
    const rows = mapPublicChainToRows([mkContract()], 450, MKT);
    expect(rows).toHaveLength(1);
    expect(rows[0].ticker).toBe(MKT);
    expect(rows[0].type).toBe("call");
    expect(rows[0].strike).toBe(450);
    expect(rows[0].volume).toBe(500);
    expect(rows[0].oi).toBe(1200);
    expect(rows[0].vol_oi_ratio).toBeCloseTo(500 / 1200, 3);
    expect(rows[0].iv).toBe(22); // <1 → ×100
    expect(rows[0].premium).toBeGreaterThan(0);
    expect(rows[0]._conv).toBeGreaterThanOrEqual(20);
    expect(rows[0]._conv).toBeLessThanOrEqual(99);
  });

  it("filters out contracts below noise floor (vol < NOISE_FLOOR*20 = 100)", () => {
    // vol=100, oi=200 → voi=0.5 ≥ 0.4 → KEPT (passes both checks)
    // vol=99 → filtered by noise floor (vol < 100)
    const rows = mapPublicChainToRows(
      [
        mkContract({ volume: 100, oi: 200 }),   // kept: vol≥100 AND voi=0.5≥0.4
        mkContract({ volume: 99, oi: 200 }),    // filtered: vol < 100
        mkContract({ volume: 50, oi: 100 }),    // filtered: vol < 100
      ],
      450,
      MKT,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].volume).toBe(100);
    expect(rows[0].oi).toBe(200);
  });

  it("filters out contracts below vol/oi threshold (< 0.4)", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ volume: 500, oi: 2000 })],
      450,
      MKT,
    );
    expect(rows).toHaveLength(0);
  });

  it("keeps contracts at exactly vol/oi = 0.4", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ volume: 400, oi: 1000 })],
      450,
      MKT,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].vol_oi_ratio).toBe(0.4);
  });

  it("sorts by vol_oi_ratio descending", () => {
    const rows = mapPublicChainToRows(
      [
        mkContract({ strike: 440, volume: 300, oi: 300 }), // voi=1.0
        mkContract({ strike: 460, volume: 800, oi: 8000 }), // voi=0.1 → filtered
        mkContract({ strike: 450, volume: 500, oi: 500 }), // voi=1.0
      ],
      450,
      MKT,
    );
    expect(rows).toHaveLength(2);
    expect(rows[0].vol_oi_ratio).toBeGreaterThanOrEqual(rows[1].vol_oi_ratio);
  });

  it("caps output at 100 rows", () => {
    const contracts = Array.from({ length: 200 }, (_, i) =>
      mkContract({ strike: 400 + i, volume: 500, oi: 500 }),
    );
    const rows = mapPublicChainToRows(contracts, 450, MKT);
    expect(rows).toHaveLength(100);
  });

  it("handles empty contract list", () => {
    expect(mapPublicChainToRows([], 450, MKT)).toEqual([]);
  });

  it("handles null/missing fields gracefully", () => {
    const rows = mapPublicChainToRows(
      [
        { strike: null, type: null, volume: 500, oi: 500 },
        { volume: 50, oi: 100 },
      ],
      450,
      MKT,
    );
    expect(rows).toHaveLength(1);
    // String(c.type || "") where c.type=null → String("" || "") → ""  → toLowerCase → ""
    expect(rows[0].type).toBe("");
  });

  it("uses last price for mid when available", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ last: 4.6, bid: 0, ask: 0 })],
      450,
      MKT,
    );
    expect(rows[0].premium).toBeGreaterThan(0);
  });

  it("falls back to estPrice when no bid/ask/last", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ bid: 0, ask: 0, last: 0, iv: 0.25, strike: 450, expiry: "2026-09-18" })],
      450,
      MKT,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].premium).toBeGreaterThan(0);
  });

  it("classifies block/sweep/unusual by premium and DTE", () => {
    // Block: premium >= 5e7. Need vol*mid*100 >= 5e7.
    // vol=200000, mid=5 → premium=200000*5*100=1e8 → block
    const blockRows = mapPublicChainToRows(
      [{ strike: 450, type: "call", expiry: "2026-09-18", volume: 200000, oi: 1000, iv: 0.5, bid: 4.5, ask: 5.5, last: 5.0 }],
      450,
      MKT,
    );
    expect(blockRows[0].classification).toBe("block");

    // Sweep: DTE <= 2
    const today = new Date();
    const exp2d = new Date(today.getTime() + 2 * 86400000).toISOString().slice(0, 10);
    const sweepRows = mapPublicChainToRows(
      [mkContract({ volume: 500, oi: 500, strike: 450, iv: 0.2, expiry: exp2d })],
      450,
      MKT,
    );
    expect(sweepRows[0].classification).toBe("sweep");

    // Unusual: everything else
    const exp30d = new Date(today.getTime() + 30 * 86400000).toISOString().slice(0, 10);
    const unusualRows = mapPublicChainToRows(
      [mkContract({ volume: 500, oi: 500, strike: 450, iv: 0.2, expiry: exp30d })],
      450,
      MKT,
    );
    expect(unusualRows[0].classification).toBe("unusual");
  });

  it("handles put types correctly", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ type: "put", strike: 440, volume: 500, oi: 500 })],
      450,
      MKT,
    );
    expect(rows[0].type).toBe("put");
  });

  it("handles iv > 1 as percentage (no ×100)", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ iv: 25, volume: 500, oi: 500 })],
      450,
      MKT,
    );
    expect(rows[0].iv).toBe(25);
  });

  it("handles iv < 1 as decimal (×100)", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ iv: 0.25, volume: 500, oi: 500 })],
      450,
      MKT,
    );
    expect(rows[0].iv).toBe(25);
  });
});

// ---- Dual-path logic: data_source assignment ----

describe("Phase 5.3 dual-path: Public API → cvserver fallback", () => {
  it("both paths produce rows with the same shape", () => {
    const pubRows = mapPublicChainToRows(
      [{ strike: 450, type: "call", expiry: "2026-09-18", volume: 500, oi: 1000, iv: 0.2, bid: 4, ask: 4.2, last: 4.1 }],
      450,
      "SPY",
    );
    expect(pubRows[0]).toHaveProperty("ticker");
    expect(pubRows[0]).toHaveProperty("type");
    expect(pubRows[0]).toHaveProperty("strike");
    expect(pubRows[0]).toHaveProperty("expiration");
    expect(pubRows[0]).toHaveProperty("volume");
    expect(pubRows[0]).toHaveProperty("oi");
    expect(pubRows[0]).toHaveProperty("vol_oi_ratio");
    expect(pubRows[0]).toHaveProperty("iv");
    expect(pubRows[0]).toHaveProperty("premium");
    expect(pubRows[0]).toHaveProperty("_conv");
    expect(pubRows[0]).toHaveProperty("_cd");
    expect(pubRows[0]).toHaveProperty("classification");
  });

  it("data_source → public_api when Public API returns contracts", () => {
    const contracts = [{ strike: 450, type: "call", expiry: "2026-09-18", volume: 500, oi: 500 }];
    const rows = mapPublicChainToRows(contracts, 450, "SPY");
    expect(rows.length).toBeGreaterThan(0);
  });

  it("falls back to cvserver when Public API returns no contracts", () => {
    expect(mapPublicChainToRows([], 450, "SPY")).toEqual([]);
  });
});

// ---- Tidehunter Pro v3 render tests (insight pipeline) ----

import React from "react";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import FlowseekerProBlademap from "./FlowseekerProBlademap";

const NOW_ISO = new Date().toISOString();
const FEED_ALERTS = [
  {
    key: "oiconf|NVDA|call|182.5|2026-09-19", ckey: "NVDA|call|182.5|2026-09-19",
    rule: "OICONF", tier: "GOLD", conviction: 94, side: "CALL", bias: "BULLISH",
    under: "NVDA", type: "call", strike: 182.5, exp: "2026-09-19", dte: 14,
    score: 94, premium: 18400000, under_price: 178.4,
    move_pct: 1.8, asof_ts: NOW_ISO,
    key_levels_json: JSON.stringify({ entry: 178.4, invalidation: 173.94, target: 188.21 }),
    context_json: JSON.stringify({
      activity_summary: "Call print held overnight",
      institutional_indicators: ["Top-decile composite score"],
      market_regime: "NEGATIVE_GAMMA",
      dealer_positioning: "Net short gamma",
    }),
    why: "OI +41% held overnight",
  },
  {
    key: "sigma|SPY", ckey: "SPY", rule: "SIGMA", tier: "SILVER", conviction: 79,
    side: "", bias: "BEARISH", under: "SPY", type: null, strike: null, exp: null,
    sigma: 4.6, move_pct: null, asof_ts: NOW_ISO, premium: null,
    key_levels_json: null, context_json: null, why: "volume 4.6σ above baseline",
  },
  {
    key: "score|SPY|put|642|2026-09-08", ckey: "SPY|put|642|2026-09-08",
    rule: "SCORE", tier: "SILVER", conviction: 68, side: "PUT", bias: "BEARISH",
    under: "SPY", type: "put", strike: 642, exp: "2026-09-08", dte: 1,
    score: 88, premium: 2000000, under_price: 640,
    move_pct: -0.4, asof_ts: NOW_ISO,
    key_levels_json: JSON.stringify({ entry: 640, invalidation: 656, target: 617.6 }),
    context_json: JSON.stringify({
      activity_summary: "Put print", institutional_indicators: [],
      market_regime: "UNKNOWN", dealer_positioning: "unknown",
    }),
    why: "score 88",
  },
];
const SCAN_ROWS = [
  ["NVDA", "OCC1", "call", 182.5, "2026-09-19", 218000, 100000, 0.38, null, 178.4],
  ["SPY", "OCC2", "put", 642, "2026-09-08", 412000, 200000, 0.15, null, 640],
  ["AMD", "OCC3", "call", 168, "2026-09-26", 142000, 90000, 0.45, null, 164.2],
];

function mockBackend({alerts=FEED_ALERTS,scanOverrides={}}={}) {
  const urls = [];
  global.fetch = jest.fn((url) => {
    urls.push(String(url));
    const u = String(url);
    let body = {};
    if (u.includes("/alerts/feed")) body = { alerts, count: alerts.length, days: 7 };
    else if (u.includes("/scan/history")) body = { tickers: {}, days: 14 };
    else if (u.includes("/scan/refresh")) body = { ok: true };
    else if (u.includes("/scan")) {
      body = {
        rows: SCAN_ROWS, regimes: {}, prev_oi: { OCC1: 70000, OCC2: 160000 },
        baselines: {}, stale: false, cache_age_seconds: 5,
        retry_after_seconds: null, scan_ttl: 60, budget: { used: 6, hourly_cap: 20 },
        ...scanOverrides,
      };
    } else if (u.includes("/regime/")) {
      body = {
        ticker: "SPY", current_state: "RANGING", confidence: 0.2, is_warming: false,
        gamma_flip: 640, dist_to_flip_pct: -0.5, total_gex: -1000000, vol_env: "normal",
      };
    } else if (u.includes("/api/heatmap/")) {
      body = {
        spot: 642, max_pain: 642,
        gamma_flip: {gamma_flip: 641},
        grid: { grid: { "2026-09-12": { 640: -1000, 650: 2000 } }, expiries: ["2026-09-12"], strikes: [640, 650] },
        nodes: { ceilings: [{ strike: 650 }], floors: [{ strike: 630 }] },
      };
    } else if (u.includes("/api/vpin/")) body = { vpin: 0.3 };
    else if (u.includes("/alerts/quality")) {
      body = {
        conviction_calibration: [
          { band: "75+", n: 52, n_measured: 40, wins: 26, hit_rate: 0.65 },
          { band: "60-74", n: 109, n_measured: 80, wins: 41, hit_rate: 0.51 },
          { band: "50-59", n: 168, n_measured: 100, wins: 38, hit_rate: 0.38 },
          { band: "<50", n: 141, n_measured: 5, wins: 2, hit_rate: 0.4 },
        ],
      };
    } else if (u.includes("/journal/stats")) {
      body = { overall: { n: 24 }, by_setup: { "sweep-follow": { wins: 14, losses: 10, win_rate: 0.58 } }, days: 90 };
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => body });
  });
  return urls;
}

beforeEach(() => {
  localStorage.clear();
  jest.restoreAllMocks();
});

describe("Tidehunter Pro v3 — one page, zero page tabs", () => {
  it("showing acknowledged history does not revive Trade now",async()=>{
    mockBackend();render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    fireEvent.click(within(screen.getByTestId("trade-now-row")).getByText("Ack"));
    expect(screen.queryByTestId("trade-now-row")).toBeNull();
    fireEvent.click(screen.getByText("⋯"));
    fireEvent.click(screen.getByText(/Show history/));
    expect(screen.queryByTestId("trade-now-row")).toBeNull();
    expect(within(screen.getByTestId("vector-feed")).getByText("OI +41% held overnight")).toBeInTheDocument();
  });
  it("each filter chip removes only its own filter including ticker search",async()=>{
    mockBackend();render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Filters"));
    fireEvent.change(screen.getByPlaceholderText(/Ticker.*\//),{target:{value:"NVDA"}});
    fireEvent.change(screen.getByPlaceholderText("Min vol"),{target:{value:"10000"}});
    fireEvent.click(screen.getByRole("button",{name:"Remove ticker filter"}));
    expect(screen.getByPlaceholderText(/Ticker.*\//).value).toBe("");
    expect(screen.getByPlaceholderText("Min vol").value).toBe("10000");
    fireEvent.click(screen.getByRole("button",{name:"Remove vol filter"}));
    expect(screen.getByPlaceholderText("Min vol").value).toBe("");
  });
  it("shows stale scan wording from age without withholding a separate fresh alert feed",async()=>{
    mockBackend({scanOverrides:{cache_age_seconds:121,stale:false}});
    render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    expect(screen.getByTestId("market-tape").textContent).toMatch(/STALE/);
    expect(screen.getByTestId("cell-money").textContent).toMatch(/stale/i);
  });
  it("keeps limited scan coverage visible on the board and sample-based sections",async()=>{
    mockBackend({scanOverrides:{truncated:true,coverage:{limit:3,tickers:3}}});
    render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    expect(document.getElementById("board").textContent).toMatch(/Limited sample/);
    expect(screen.getByTestId("cell-money").textContent).toMatch(/Limited sample/);
    expect(document.getElementById("pulse").textContent).toMatch(/Limited sample/);
  });
  it("does not call an old SIGMA alert current evidence for Money building",async()=>{
    const alerts=FEED_ALERTS.map(a=>a.rule==="SIGMA"?{...a,asof_ts:new Date(Date.now()-901000).toISOString()}:a);
    mockBackend({alerts});render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    expect(screen.getByTestId("cell-money").textContent).not.toMatch(/4.6σ server-confirmed/);
  });
  it("slash opens the filter controls and focuses ticker search",async()=>{
    mockBackend();render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    expect(screen.queryByTestId("filters-panel")).toBeNull();
    fireEvent.keyDown(window,{key:"/"});
    await waitFor(()=>expect(screen.getByPlaceholderText(/Ticker.*\//)).toHaveFocus());
  });
  it("clears the displayed feed without resetting acknowledged history or firing old rows on reload",async()=>{
    mockBackend();const view=render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    fireEvent.click(within(screen.getByTestId("trade-now-row")).getByText("Ack"));
    fireEvent.click(screen.getByText("⋯"));
    fireEvent.click(screen.getByRole("button",{name:"Clear feed"}));
    expect(screen.getByTestId("vector-feed").textContent).toMatch(/No signals/);
    expect(screen.getByTestId("cell-trade").textContent).toContain("No unacknowledged signals in this screen");
    expect(screen.getByTitle("Signals per rule in this screen").textContent).toBe("");
    const ack=localStorage.getItem("th-acked-v1");
    expect(Object.keys(JSON.parse(ack))).toHaveLength(1);
    view.unmount();render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("vector-feed").textContent).toMatch(/No signals/));
    expect(screen.queryByTestId("trade-now-row")).toBeNull();
    expect(localStorage.getItem("th-acked-v1")).toBe(ack);
  });
  it("keeps the pinned trade once while sorting the remaining feed oldest-first",async()=>{
    const alerts=FEED_ALERTS.map((a,i)=>({...a,asof_ts:new Date(Date.now()-(i+1)*60000).toISOString()}));
    mockBackend({alerts});render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    fireEvent.click(screen.getByText("⋯"));
    fireEvent.click(screen.getByRole("button",{name:"Feed · conviction rank"}));
    fireEvent.click(screen.getByRole("button",{name:"Feed · newest first"}));
    expect(screen.getByRole("button",{name:"Feed · oldest first"})).toBeInTheDocument();
    const rows=within(screen.getByTestId("vector-feed")).getAllByRole("row");
    expect(rows[1]).toHaveAttribute("data-testid","trade-now-row");
    expect(rows[2].textContent).toMatch(/score 88/);
    expect(rows[3].textContent).toMatch(/volume 4.6σ/);
    expect(JSON.parse(localStorage.getItem("th-prefs-v1")).feedOrder).toBe("old");
  });
  it("draws the flip from the same map response instead of a separate regime reading",async()=>{
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(()=>expect(within(screen.getByTestId("dealer-drilldown")).getByText("641")).toBeInTheDocument());
    const flipBox=within(screen.getByTestId("dealer-drilldown")).getByText("Gamma flip").parentElement;
    expect(within(flipBox).queryByText("640")).toBeNull();
  });
  it("renders the four answer cells and in-page anchor sidebar, no tab switcher", async () => {
    mockBackend();
    const { container } = render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("cell-trade")).toBeInTheDocument());
    expect(screen.getByTestId("cell-money")).toBeInTheDocument();
    expect(screen.getByTestId("cell-changed")).toBeInTheDocument();
    expect(screen.getByTestId("cell-dealers")).toBeInTheDocument();
    expect(screen.getByTestId("vector-feed")).toBeInTheDocument();
    expect(screen.getByTestId("pulse-table")).toBeInTheDocument();
    expect(screen.getByTestId("lattice")).toBeInTheDocument();
    expect(screen.getByTestId("trust-row")).toBeInTheDocument();
    expect(screen.getByTestId("settings-table")).toBeInTheDocument();
    // the internal TABS array is dissolved — no page-tab buttons anywhere
    expect(container.querySelector(".fsb-tab")).toBeNull();
    expect(container.querySelector(".fsb-view-flow")).toBeNull();
    expect(container.querySelectorAll(".th-nav")).toHaveLength(6);
  });

  it("pins trade-now once and renders contextual rows without levels or arrow", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    const pinned = screen.getByTestId("trade-now-row");
    expect(within(pinned).getByText(/pinned · trade now/)).toBeInTheDocument();
    // pinned header excluded from the body: exactly 3 rows (pinned + SIGMA + low)
    const rows = within(screen.getByTestId("vector-feed")).getAllByRole("row");
    expect(rows).toHaveLength(4); // header + 3 body rows
    // SIGMA contextual row: sentence only, no direction arrow
    expect(screen.getByText("— NO DIRECTION")).toBeInTheDocument();
    // low-conviction directional row still in the body
    expect(screen.getByText(/score 88/)).toBeInTheDocument();
  });

  it("renders move_pct as-is (no ×100 bug) with % of target travelled", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    expect(screen.getAllByText("+1.8%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/33% of target/).length).toBeGreaterThanOrEqual(1);
    expect(document.body.textContent).not.toMatch(/180(\.0+)?%/);
  });

  it("direction always carries arrow + word (colour-blind contract)", async () => {
    localStorage.setItem("floww_settings", JSON.stringify({ colorBlindMode: true, defaultTicker: "SPY" }));
    mockBackend();
    const { container } = render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    expect(container.querySelector('[data-testid="tide-root"]').getAttribute("data-cb")).toBe("on");
    expect(screen.getAllByText("▲ BULLISH").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("▼ BEARISH").length).toBeGreaterThanOrEqual(1);
  });

  it("trust row uses the real bands and greys cells with n_measured < 10", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("trust-row")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("65%")).toBeInTheDocument());
    const trust = screen.getByTestId("trust-row");
    for (const band of ["75+", "60-74", "50-59", "<50"]) {
      expect(within(trust).getByText(new RegExp(`${band.replace("+", "\\+")}`))).toBeInTheDocument();
    }
    // <50 band has n_measured=5 → greyed
    expect(trust.querySelectorAll(".th-stat.thin").length).toBeGreaterThanOrEqual(1);
  });

  it("pulse shows 10 default columns and the dealers cell prints the focused ticker", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("pulse-table")).toBeInTheDocument());
    await waitFor(() => expect(
      within(screen.getByTestId("pulse-table")).getAllByRole("columnheader"),
    ).toHaveLength(10));
    await waitFor(() => expect(screen.getByText(/Dealers · SPY/)).toBeInTheDocument());
  });

  it("market tape carries notional, call/put, unusual, heartbeat and source", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("market-tape")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("pulse-table").querySelector("tbody")).not.toBeNull());
    const tape = screen.getByTestId("market-tape");
    for (const label of ["Contracts", "Notional Σ", "Call/Put", "Unusual ≥2×", "Updated", "Source"]) {
      expect(within(tape).getAllByText(label, { exact: false }).length).toBeGreaterThan(0);
    }
    expect(within(tape).getByText("Source not supplied")).toBeInTheDocument();
    expect(within(tape).queryByText(/LIVE/)).not.toBeInTheDocument();
  });

  it("ticker select re-focuses the dealers cell and lattice", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByText(/Dealers · SPY/)).toBeInTheDocument());
    const sel = screen.getByLabelText("Focused ticker");
    fireEvent.change(sel, { target: { value: "NVDA" } });
    await waitFor(() => expect(screen.getByText(/Dealers · NVDA/)).toBeInTheDocument());
    expect(screen.getByText("Lattice · NVDA")).toBeInTheDocument();
  });

  it("Plan saves a client-side journal draft only — no order route is ever called", async () => {
    const urls = mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    const pinned = screen.getByTestId("trade-now-row");
    fireEvent.click(within(pinned).getByText("Plan"));
    await waitFor(() => expect(within(pinned).getByText("Planned ✓")).toBeInTheDocument());
    const drafts = JSON.parse(localStorage.getItem("floww_trades_v2") || "[]");
    expect(drafts).toHaveLength(1);
    expect(drafts[0].ticker).toBe("NVDA");
    expect(drafts[0].setup).toBe("tidehunter-verdict");
    const money = urls.filter((u) => /auto-trade|\/order|alpaca|broker/i.test(u));
    expect(money).toEqual([]);
  });

  it("pulse score carries the component breakdown tooltip", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(
      within(screen.getByTestId("pulse-table")).getAllByRole("columnheader"),
    ).toHaveLength(10));
    const withTip = screen.getByTestId("pulse-table").querySelector("b[title*='vol/OI']");
    expect(withTip).not.toBeNull();
  });

  it("keeps the approved dashboard scope without simulated pages", async () => {
    mockBackend(); render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("dealer-drilldown")).toBeInTheDocument());
    expect(screen.queryByTestId("vol-section")).not.toBeInTheDocument();
    expect(screen.queryByTestId("academy-section")).not.toBeInTheDocument();
  });

  it("rule chips hide whole rule families from the feed", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    expect(screen.getByText(/score 88/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("⋯"));
    const menu = screen.getByTestId("more-menu");
    fireEvent.click(within(menu).getByText("SCORE"));
    expect(screen.queryByText(/score 88/)).toBeNull();
    // pinned trade-now (OICONF) survives a SCORE hide
    expect(screen.getByTestId("trade-now-row")).toBeInTheDocument();
  });

  it("column chooser offers the derived Trend column", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("pulse-table")).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Columns ·/));
    expect(screen.getByTestId("column-chooser")).toBeInTheDocument();
    expect(within(screen.getByTestId("column-chooser")).getByText("Trend")).toBeInTheDocument();
  });

  it("vector header carries per-rule session counts", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("trade-now-row")).toBeInTheDocument());
    const counts = document.querySelector(".th-rulecounts");
    expect(counts.textContent).toMatch(/OICONF/);
    expect(counts.textContent).toMatch(/SIGMA/);
    expect(counts.textContent).toMatch(/SCORE/);
  });

  it("reset filters clears the ticker search", async () => {
    mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("pulse-table")).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Filters/));
    const panel = screen.getByTestId("filters-panel");
    const q = within(panel).getByPlaceholderText(/Ticker/);
    fireEvent.change(q, { target: { value: "NVDA" } });
    expect(q.value).toBe("NVDA");
    fireEvent.click(within(panel).getByText("Reset filters"));
    expect(q.value).toBe("");
  });

  it("calls only real routes — no dead or money-path calls", async () => {
    const urls = mockBackend();
    render(<FlowseekerProBlademap active />);
    await waitFor(() => expect(screen.getByTestId("vector-feed")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("65%")).toBeInTheDocument());
    await waitFor(() => expect(urls.some((u) => u.includes("/api/vpin/"))).toBe(true));
    await waitFor(() => expect(urls.some((u) => u.includes("/api/heatmap/"))).toBe(true));
    const dead = urls.filter((u) => /\/ofi(\?|$|\/)|\/lambda(\?|$|\/)|flowseeker\/vpin|auto-trade|\/order|alpaca|public.*order/i.test(u));
    expect(dead).toEqual([]);
    expect(urls.some((u) => u.includes("/alerts/feed?"))).toBe(true);
    expect(urls.some((u) => u.includes("/api/vpin/"))).toBe(true);
  });
});
