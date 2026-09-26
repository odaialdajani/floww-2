/**
 * @jest-environment jsdom
 *
 * Smoke test for SkylitDashboard (the layout mounted by the default
 * `page === "heatseeker"` route in App.js, which is what users actually
 * land on). Confirms the skylit chrome + the steal-list bottom band
 * (rank #1 Dual-GEX, #5 IV-Mid, #3 Wheel income) all mount cleanly. Pairs
 * with HeatseekerDashboard.test.jsx so coverage spans both layouts.
 */
import React from "react";
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";

// Mock IntersectionObserver — harmless for a smoke test, but defensive in
// case any lazy subcomponent gets pulled in via transitive imports.
global.IntersectionObserver = class IntersectionObserver {
  constructor(callback) { this.callback = callback; }
  observe() { this.callback([{ isIntersecting: true }]); }
  disconnect() {}
  unobserve() {};
};

// Mock axios: the overlay wide-band fetch must never hit the network in
// tests (CRA resetMocks wipes factory impls, so (re)arm in beforeEach).
jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));

// Mock Zenith sub-components to null-mounts (no network calls; faster).
// Ticker bar + control bar echoes the tickers prop so the universe
// pass-through is pinnable (2026-09-12: the Solstice bar/control silently
// fell back to 23/10 featured sets because nothing passed tickers down).
jest.mock("./SkylitTickerBar",       () => (props) => (
  <div data-testid="mock-ticker-bar" data-tickers={JSON.stringify(props.tickers ?? null)} />
));
jest.mock("./SkylitControlBar",      () => (props) => (
  <div data-testid="mock-control-bar" data-tickers={JSON.stringify(props.tickers ?? null)} data-spot={JSON.stringify(props.spot ?? null)} data-live={String(props.isLive)}><button data-testid="mock-activity" onClick={()=>props.onMetricChange("activity")}>Activity</button></div>
));
jest.mock("./SkylitHeatmapGrid",     () => ({ onCellClick, onStrikeClick, windowRows, density, spot }) => (
  <div data-testid="mock-heatmap" data-window={windowRows} data-density={density} data-spot={JSON.stringify(spot ?? null)}>
    <button data-testid="mock-strike" onClick={()=>onStrikeClick?.(650)}>Strike</button>
    <button
      data-testid="mock-heatmap-cell"
      onClick={() => onCellClick && onCellClick(650, "2026-09-18", 123.4)}
    >
      cell
    </button>
  </div>
));
jest.mock("./SkylitMetricsSidebar",  () => (props) => <div data-testid="mock-metrics" data-spot={JSON.stringify(props.spot ?? null)} data-regime={JSON.stringify(props.regime ?? null)} />);
jest.mock("./ExposureStrip", () => () => null);
jest.mock("../flowseeker/AlertEngineStrip", () => () => null);

// Mock the steal-list top-3 components (they fetch from :8000 which is not
// running in tests). Use the same data-testids the components expose in
// production so this test also serves as a reality-check on those ids.
jest.mock("./DualGEXBadge",              () => () => <div data-testid="hs-dual-gex" />);
jest.mock("./IVMidBadge",                () => () => <div data-testid="hs-iv-mid" />);
jest.mock("./WheelIncomeScreenerPanel",  () => () => <div data-testid="hs-wheel-income" />);
jest.mock("./MaxPainBadge",              () => () => <div data-testid="hs-max-pain" />);
// Per-expiry max-pain-drift multi-line chart tile (steal-list #9 rich
// visualization; fetches /api/max_pain_drift/{ticker}/per_expiry_history).
jest.mock("./MaxPainPerExpiryDriftTile",  () => () => <div data-testid="hs-max-pain-per-expiry-drift" />);
// NEW (2026-07-16): steal-list #10 (strike cone) + #8 (opportunity
// engine) — mocks mirror the production component data-testids so
// these assertions also serve as a reality-check on those ids.
jest.mock("./StrikeConeBadge",              () => () => <div data-testid="hs-strike-cone" />);
jest.mock("./OpportunityBadge",             () => () => <div data-testid="hs-opportunity" />);
// NEW (2026-07-16): News pulse (catalyst + headline count) and the
// full-width Risk-Neutral Density tile — both fetch on mount so the
// mocks keep the test synchronous + side-effect-free.
jest.mock("./NewsBadge",                    () => () => <div data-testid="hs-news" />);
jest.mock("./RndDensityPanel",              () => () => <div data-testid="hs-rnd-density" />);

// Import AFTER mocks are set up.
import SkylitDashboard from "./SkylitDashboard";
import useScreenContext from "../../agent/useScreenContext";

function ResearchSelection(){const [context]=useScreenContext();return <output data-testid="research-selection">{JSON.stringify(context)}</output>;}

function selectionMap(value = 123.4, asof = "2026-09-11T18:00:00Z") {
 return {ticker:"SPY",asof,map_query:{expiries:4,mode:"day",dte:null},strikes:[{strike:650}],
   grid:{strikes:[650],expiries:["2026-09-18"],grid:{"2026-09-18":{"650":value}}}};
}

test("same-scope polling retains the selected cell with the latest displayed value and map version",()=>{
 const mounted=render(<><SkylitDashboard ticker="SPY" data={selectionMap()} spot={650}/><ResearchSelection/></>);
 fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
 expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("123.4");
 mounted.rerender(<><SkylitDashboard ticker="SPY" data={selectionMap(567.8,"2026-09-11T18:01:00Z")} spot={650}/><ResearchSelection/></>);
 expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("567.8");
 expect(JSON.parse(screen.getByTestId("research-selection").textContent)).toMatchObject({selectedStrike:650,selectedExpiry:"2026-09-18",mapVersion:"2026-09-11T18:01:00Z"});
});

test("selection uses current exact data even when a response keeps the same version",()=>{
 const mounted=render(<SkylitDashboard ticker="SPY" data={selectionMap()} spot={650}/>);
 fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
 mounted.rerender(<SkylitDashboard ticker="SPY" data={selectionMap(0)} spot={650}/>);
 expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("0.0");
});

test.each([null,NaN,Infinity])("a missing or invalid selected value clears its identity permanently (%s)",(value)=>{
 const mounted=render(<><SkylitDashboard ticker="SPY" data={selectionMap()} spot={650}/><ResearchSelection/></>);
 fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
 mounted.rerender(<><SkylitDashboard ticker="SPY" data={selectionMap(value)} spot={650}/><ResearchSelection/></>);
 expect(screen.queryByTestId("skylit-selected-cell")).not.toBeInTheDocument();
 expect(JSON.parse(screen.getByTestId("research-selection").textContent).selectedStrike).toBeNull();
 mounted.rerender(<><SkylitDashboard ticker="SPY" data={selectionMap()} spot={650}/><ResearchSelection/></>);
 expect(screen.queryByTestId("skylit-selected-cell")).not.toBeInTheDocument();
});

test.each(["ticker","measure","expiry","visible rows"])("changing %s out of the selected scope clears and does not restore an old choice",(change)=>{
 const original={ticker:"SPY",data:selectionMap(),spot:650};
 const mounted=render(<><SkylitDashboard {...original}/><ResearchSelection/></>);
 fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
 let next={...original};
 if(change==="ticker")next={...next,ticker:"QQQ",data:{...next.data,ticker:"QQQ"}};
 if(change==="measure")next={...next,viewMode:"vex",data:{...next.data,grid:{...next.data.grid,vex_grid:{"2026-09-18":{"650":999}}}}};
 if(change==="expiry")next={...next,data:{...next.data,grid:{...next.data.grid,expiries:["2026-09-25"]}}};
 if(change==="visible rows")next={...next,spot:600,data:{...next.data,grid:{...next.data.grid,strikes:Array.from({length:51},(_,i)=>600+i)}}};
 mounted.rerender(<><SkylitDashboard {...next}/><ResearchSelection/></>);
 expect(screen.queryByTestId("skylit-selected-cell")).not.toBeInTheDocument();
 expect(JSON.parse(screen.getByTestId("research-selection").textContent).selectedStrike).toBeNull();
 mounted.rerender(<><SkylitDashboard {...original}/><ResearchSelection/></>);
 expect(screen.queryByTestId("skylit-selected-cell")).not.toBeInTheDocument();
});

test("research follows the rendered wide map and never carries it into another ticker",async()=>{
 const stamp="2026-09-11T18:00:00Z";
 const query={expiries:4,mode:"day",dte:null,scalp:false,withTaps:true,maxStrikes:80};
 const base={...selectionMap(),asof:stamp,mode:"day",map_query:query};
 let resolveWide;
 axios.get.mockImplementation(()=>new Promise(resolve=>{resolveWide=resolve;}));
 const mounted=render(<><SkylitDashboard ticker="SPY" data={base} spot={500}/><ResearchSelection/></>);
 const current=()=>JSON.parse(screen.getByTestId("research-selection").textContent);
 expect(current().mapQuery.expiries).toBe(4);
 expect(current().mapStrikes).toEqual([650]);
 mounted.rerender(<><SkylitDashboard ticker="SPY" data={base} spot={500} expiries={8} dte={7}/><ResearchSelection/></>);
 expect(current().mapQuery).toEqual(query);
 fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
 expect(current().selectedStrike).toBe(650);
 fireEvent.click(screen.getByTestId("skylit-expand-btn"));
 expect(current().selectedStrike).toBe(650);
 await act(async()=>{resolveWide({data:{...base,mode:"swing",map_query:{...query,expiries:8,mode:"swing"},asof:"2026-09-11T18:01:00Z",grid:{strikes:[490,500,510],expiries:["2026-09-18"]}}});});
 expect(current().mapQuery).toMatchObject({expiries:8,mode:"swing",dte:null});
 expect(current().mapStrikes).toEqual([510,500,490]);
 expect(current().mapVersion).toBe("2026-09-11T18:01:00Z");
 expect(current().selectedStrike).toBeNull();
 mounted.rerender(<><SkylitDashboard ticker="QQQ" data={base} spot={600}/><ResearchSelection/></>);
 expect(current().ticker).toBe("QQQ");
 expect(current().mapVersion).toBeNull();
 expect(current().mapStrikes).toEqual([]);
});

beforeEach(() => {
  axios.get.mockImplementation(async () => ({ data: { strikes: [] } }));
});

describe("SkylitDashboard", () => {
  test("mounts the skylit chrome with NO bottom boxes (removed 2026-09-03)", async () => {
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" />);
    });

    // Zenith chrome (top → bottom)
    expect(screen.getByTestId("mock-ticker-bar")).toBeInTheDocument();
    expect(screen.getByTestId("mock-control-bar")).toBeInTheDocument();
    expect(screen.getByTestId("mock-heatmap")).toBeInTheDocument();
    expect(screen.getByTestId("mock-metrics")).toBeInTheDocument();

    // Meridian & Velocity band REMOVED from Solstice (Nav directive) —
    // neither the band, its toggle, nor any tile may mount here.
    // (Tiles still live in HeatseekerDashboard/Zenith + direct API use.)
    expect(screen.queryByTestId("skylit-steal-list-band")).not.toBeInTheDocument();
    expect(screen.queryByTestId("skylit-signals-toggle")).not.toBeInTheDocument();
    for (const tid of [
      "hs-dual-gex", "hs-iv-mid", "hs-wheel-income", "hs-max-pain",
      "hs-max-pain-per-expiry-drift", "hs-strike-cone", "hs-opportunity",
      "hs-news", "hs-rnd-density",
      "skylit-steal-dual-gex", "skylit-steal-iv-mid", "skylit-steal-max-pain",
      "skylit-steal-wheel-income", "skylit-steal-max-pain-per-expiry-drift",
      "skylit-steal-strike-cone", "skylit-steal-opportunity",
      "skylit-steal-news-band", "skylit-steal-rnd-density",
    ]) {
      expect(screen.queryByTestId(tid)).not.toBeInTheDocument();
    }

    // Expand control present (zoom removed 2026-09-03).
    expect(screen.getByTestId("skylit-expand-btn")).toBeInTheDocument();

    // In-frame grid is the compact windowed mode (fits on screen).
    const inlineGrid = screen.getAllByTestId("mock-heatmap")[0];
    expect(inlineGrid).toHaveAttribute("data-window", "21");
  });

  test("zoom controls scale the in-frame grid only", async () => {
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" />);
    });

    const area = screen.getByTestId("skylit-heatmap-area");
    expect(area.style.zoom).toBe("1");

    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-zoom-in"));
    });
    expect(screen.getByTestId("skylit-heatmap-area").style.zoom).toBe("1.25");

    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-zoom-out"));
      fireEvent.click(screen.getByTestId("skylit-zoom-out"));
    });
    expect(screen.getByTestId("skylit-heatmap-area").style.zoom).toBe("0.75");
  });

  test("expand button opens the full-page grid overlay and closes it", async () => {    await act(async () => {
      render(<SkylitDashboard ticker="SPY" />);
    });

    expect(screen.queryByTestId("skylit-grid-expanded")).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-expand-btn"));
    });
    expect(screen.getByTestId("skylit-grid-expanded")).toBeInTheDocument();
    // Overlay reuses the heatmap grid (mocked here) — inline + overlay.
    const grids = screen.getAllByTestId("mock-heatmap");
    expect(grids.length).toBeGreaterThanOrEqual(2);
    // Overlay grid is full-density with no row window (genuinely bigger).
    expect(grids[grids.length - 1]).toHaveAttribute("data-density", "full");
    expect(grids[grids.length - 1]).not.toHaveAttribute("data-window");

    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-expand-close"));
    });
    expect(screen.queryByTestId("skylit-grid-expanded")).not.toBeInTheDocument();
  });

  test("clicking a cell outside trade mode shows the selected-cell readout", async () => {
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" data={selectionMap()} spot={650} />);
    });

    expect(screen.queryByTestId("skylit-selected-cell")).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]);
    });
    const readout = screen.getByTestId("skylit-selected-cell");
    expect(readout.textContent).toContain("650");
    expect(readout.textContent).toContain("2026-09-18");
  });

  test("expand preserves scope by default; widen is explicit (F18)", async () => {    axios.get.mockImplementation(async (url) => ({
      data: {
        strikes: [{ strike: 100 }, { strike: 101 }],
        grid: {},
        spot: 100,
      },
    }));
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" />);
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-expand-btn"));
    });

    await waitFor(() => {
      const calls = axios.get.mock.calls.filter((c) => String(c[0]).includes("/heatmap/"));
      expect(calls.length).toBeGreaterThan(0);
      // Default preserves in-frame scope (day/4) — no silent swing/8 switch.
      expect(calls[0][0]).toContain("mode=day");
      expect(calls[0][0]).toContain("expiries=4");
      expect(calls[0][0]).not.toContain("mode=swing");
    });
    // Explicit widen action requests 8 expiries.
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-expand-widen"));
    });
    await waitFor(() => {
      const calls = axios.get.mock.calls.filter((c) => String(c[0]).includes("/heatmap/"));
      const widened = calls.filter((c) => String(c[0]).includes("expiries=8"));
      expect(widened.length).toBeGreaterThan(0);
    });
  });

  test("closing expand drops expanded data; reopen never shows stale pixels", async () => {
    // R5-B resweep: stale expanded scope must not drive inline clicks after
    // close. Reopening refetches (loading state) instead of flashing old data.
    let gate1 = null;
    let gate2 = null;
    let phase = 1;
    axios.get.mockImplementation(async (url) => {
      if (!String(url).includes("/heatmap/")) return { data: { strikes: [] } };
      if (phase === 1) {
        await new Promise((r) => { gate1 = r; });
        return { data: { strikes: [{ strike: 100 }], asof: "EXP1", spot: 100 } };
      }
      await new Promise((r) => { gate2 = r; });
      return { data: { strikes: [{ strike: 100 }, { strike: 101 }], asof: "EXP2", spot: 100 } };
    });
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" />);
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-expand-btn"));
    });
    await act(async () => { gate1(); });
    await waitFor(() => {
      expect(document.querySelector(".skylit-expanded-coverage").textContent).toContain("1 strikes");
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-expand-close"));
    });
    expect(screen.queryByTestId("skylit-grid-expanded")).not.toBeInTheDocument();
    phase = 2;
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-expand-btn"));
    });
    await waitFor(() => {
      expect(document.querySelector(".skylit-expanded-coverage").textContent).toContain("loading");
    });
    await act(async () => { gate2(); });
    await waitFor(() => {
      expect(document.querySelector(".skylit-expanded-coverage").textContent).toContain("2 strikes");
    });
  });

  test("expanded overlay mounts the same inspector as inline (R6-1 parity)", async () => {
    const data = {
      ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650,
      exposure_basis: "OI",
      strikes: [{ strike: 650, gex: 1000, call_gex: 600, put_gex: 400 }],
      metrics: { walls: [{ wall_id: "w_par", low: 640, high: 660, mid: 650, gross: 1000, net: 200, call: 600, put: 400 }] },
      interactions: [],
      scenarios: [],
      quality: { state: "usable", reasonCodes: [], setupEligible: true },
    };
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
    });
    await act(async () => {
      fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]);
    });
    expect(screen.getAllByTestId("wall-inspector").length).toBe(1);
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-expand-btn"));
    });
    // Same wall, same scenarios inline and expanded — never a lone grid.
    expect(screen.getAllByTestId("wall-inspector").length).toBe(2);
  });

  test("passes the full ticker universe to the bar and control bar (no fallback)", async () => {
    // 2026-09-12 regression: neither child received `tickers`, so the bar
    // fell back to 23 featured tickers and the arrows cycled 10 ("1/10")
    // while App.js held the 31k universe. An exotic symbol must flow through.
    const universe = { trinity: ["SPY"], default: [], popular: ["ZZZEXOTIC"] };
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" tickers={universe} />);
    });

    expect(screen.getByTestId("mock-ticker-bar")).toHaveAttribute(
      "data-tickers", JSON.stringify(universe)
    );
    expect(screen.getByTestId("mock-control-bar")).toHaveAttribute(
      "data-tickers", JSON.stringify(universe)
    );
  });
});

test("R7-03: vex readout resolves the vex surface, missing cell is unavailable", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: {
      expiries: ["2026-09-18"], strikes: [650],
      grid: { "2026-09-18": { 650: 9999 } },
      vex_grid: { "2026-09-18": { 650: 2500 } },
      vex_meta: { exposure_basis: "VEX_1VOLPT", status: "ok" },
    },
    metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} viewMode="vex" />);
  });
  await act(async () => {
    fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]);
  });
  const readout = screen.getByTestId("skylit-selected-cell");
  // VEX value (2500.0), never the GEX surface value (9999.0).
  expect(readout.textContent).toContain("2500.0");
  expect(readout.textContent).not.toContain("9999");
});

test("R7-03: readout for a cell absent from the current snapshot is unavailable", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [], grid: { expiries: [], strikes: [], grid: {} },
    metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  await act(async () => {
    fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]);
  });
  expect(screen.queryByTestId("skylit-selected-cell")).not.toBeInTheDocument();
});

test("R7-03: false eligibility without reasons shows a generic blocker, not permission", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [], grid: { expiries: [], strikes: [], grid: {} },
    metrics: { walls: [], grids: {} },
    quality: { state: "unavailable", reasonCodes: [], setupEligible: false },
  };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  const setup = screen.getByTestId("solstice-setup");
  expect(setup.textContent).toContain("Wait");
  expect(setup.textContent).not.toContain("Observe");
  expect(setup.title).not.toContain("No blockers");
});

test("R7-03: replay clicks never reach the live Trade callback; Trade disabled in replay", async () => {
  const onCellClick = jest.fn();
  const onStrikeClick = jest.fn();
  const onReplayChange = jest.fn();
  axios.get.mockImplementation(async (url) => {
    if (String(url).includes("/solstice/manifest/")) {
      return { data: { snapshots: [{ id: "s1" }] } };
    }
    if (String(url).includes("/solstice/replay/")) {
      return { data: {
        snapshot: { ticker: "SPY", snapshot_id: "s1", asof_ts: "2026-09-03T14:00:00Z", spot: null, exposure_basis: "OI" },
        strikes: [{ strike: 650, gex: 1000 }],
        walls: [{ wall_id: "w_r", low: 640, high: 660 }],
        grids: { grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1111 } } } },
        quality: { state: "usable", reasonCodes: [], setupEligible: false },
        interactions: [], scenarios: [],
      } };
    }
    if (String(url).includes("/solstice/recorder_health")) return { data: {} };
    return { data: {} };
  });
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={null} spot={999} regime="positive" isLive onCellClick={onCellClick} onStrikeClick={onStrikeClick} onReplayChange={onReplayChange} />);
  });
  // Arm Trade while LIVE, then enter replay (must disarm), then click.
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-trade-btn")); });
  await act(async () => { fireEvent.click(screen.getByTestId("solstice-replay-load")); });
  await act(async () => { fireEvent.click(screen.getByTestId("solstice-replay-next")); });
  expect(screen.getByTestId("solstice-replay-banner")).toBeInTheDocument();
  expect(onReplayChange).toHaveBeenLastCalledWith(true);
  await act(async () => {
    fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]);
  });
  // Historical click selected locally but never invoked the live callback.
  fireEvent.click(screen.getByTestId("mock-strike"));
  expect(onStrikeClick).not.toHaveBeenCalled();
  expect(screen.getByTestId("mock-heatmap")).toHaveAttribute("data-spot","null");
  expect(screen.getByTestId("mock-control-bar")).toHaveAttribute("data-spot","null");
  expect(screen.getByTestId("mock-control-bar")).toHaveAttribute("data-live","false");
  expect(screen.getByTestId("mock-metrics")).toHaveAttribute("data-regime","null");
  expect(screen.queryByText("$999.00")).not.toBeInTheDocument();
  expect(onCellClick).not.toHaveBeenCalled();
  expect(screen.getByTestId("skylit-trade-btn")).toBeDisabled();
  expect(screen.getByTestId("skylit-selected-cell")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("solstice-replay-exit"));
  expect(onReplayChange).toHaveBeenLastCalledWith(false);
});

test("R7-04: compare toggle mounts two real panes over one snapshot; back to one", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  expect(screen.queryAllByTestId("mock-heatmap").length).toBe(1);
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-compare-toggle")); });
  expect(screen.getByTestId("skylit-compare-desk")).toBeInTheDocument();
  expect(screen.queryAllByTestId("mock-heatmap").length).toBe(2);
  expect(screen.getByTestId("skylit-pane-gex-header").textContent).toContain("GEX");
  expect(screen.getByTestId("skylit-pane-vex-header").textContent).toContain("VEX");
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-compare-toggle")); });
  expect(screen.queryAllByTestId("mock-heatmap").length).toBe(1);
  expect(screen.queryByTestId("skylit-compare-desk")).not.toBeInTheDocument();
});

test("R7-04: clicking the VEX pane makes it own the readout; scroll syncs", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } }, vex_grid: { "2026-09-18": {650: 25} } },
    metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-compare-toggle")); });
  const cells = screen.getAllByTestId("mock-heatmap-cell");
  expect(cells.length).toBe(2);
  await act(async () => { fireEvent.click(cells[0]); });
  expect(screen.getByTestId("skylit-selected-cell").title).toContain("GEX pane");
  await act(async () => { fireEvent.click(cells[1]); });
  expect(screen.getByTestId("skylit-selected-cell").title).toContain("VEX pane");
  const gex = screen.getByTestId("skylit-pane-gex");
  const vex = screen.getByTestId("skylit-pane-vex");
  await act(async () => {
    gex.scrollTop = 42;
    fireEvent.scroll(gex);
  });
  expect(vex.scrollTop).toBe(42);
});

test("R7-04: expanded overlay keeps the same compare workspace and scope", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-compare-toggle")); });
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-expand-btn")); });
  const overlay = screen.getByTestId("skylit-grid-expanded");
  const desks = overlay.querySelectorAll('[data-testid="skylit-compare-desk"]');
  expect(desks.length).toBe(1);
  expect(overlay.querySelectorAll('[data-testid="mock-heatmap"]').length).toBe(2);
});

// ---- R8-02: follow-wall toggle ------------------------------------------------

test("R8-02: follow-wall toggle mounts and is disabled with no selection", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => { render(<SkylitDashboard ticker="SPY" data={data} spot={650} />); });
  const btn = screen.getByTestId("skylit-follow-wall-toggle");
  expect(btn).toBeInTheDocument();
  expect(btn).toBeDisabled(); // no cell selected
  expect(btn.textContent).toBe("Follow");
});

test("R8-02: follow-wall toggle seeds wall_id from selection on turn-on", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    metrics: { walls: [{ wall_id: "W1", low: 640, high: 660 }], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => { render(<SkylitDashboard ticker="SPY" data={data} spot={650} />); });
  // Click a cell to create a selection with wall_id
  await act(async () => { fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]); });
  const btn = screen.getByTestId("skylit-follow-wall-toggle");
  expect(btn).not.toBeDisabled();
  expect(btn.textContent).toBe("Follow this wall");
  // Turn it on — seeds followWallId from the selected cell's wall_id
  await act(async () => { fireEvent.click(btn); });
  expect(btn).toHaveClass("active");
  expect(btn.textContent).toBe("Following W1");
});

test("R8-02: follow-wall toggle turns off and clears", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    metrics: { walls: [{ wall_id: "W1", low: 640, high: 660 }], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => { render(<SkylitDashboard ticker="SPY" data={data} spot={650} />); });
  await act(async () => { fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]); });
  const btn = screen.getByTestId("skylit-follow-wall-toggle");
  await act(async () => { fireEvent.click(btn); });
  expect(btn.classList.contains("active")).toBe(true);
  await act(async () => { fireEvent.click(btn); });
  expect(btn.classList.contains("active")).toBe(false);
  // After turning off, the button reverts to "Follow this wall" because a
  // cell is still selected (the user can turn follow back on). It only says
  // "Follow" when no cell is selected.
  expect(btn.textContent).toBe("Follow this wall");
});

// ---- R8-04: review journal pill ----------------------------------------------

test("R8-04: review pill shows 'No review yet' for a snapshot with no decision", async () => {
  axios.get.mockResolvedValueOnce({ data: { ticker: "SPY", decisions: [] } });
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "snap-r8-04-1", metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => { render(<SkylitDashboard ticker="SPY" data={data} spot={650} />); });
  await waitFor(() => {
    expect(screen.getByTestId("skylit-review-pending")).toBeInTheDocument();
    expect(screen.getByTestId("skylit-review-pending").textContent).toBe("No review yet");
  });
  await waitFor(() => {
    expect(screen.queryByTestId("skylit-review-loading")).not.toBeInTheDocument();
  });
});

test("R8-04: review pill surfaces a saved review state", async () => {
  axios.get.mockImplementation(async () => ({
    data: { ticker: "SPY", decisions: [{ decision_id: "d1", snapshot_id: "snap-r8-04-2", review_state: "reviewed" }] },
  }));
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "snap-r8-04-2", metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => { render(<SkylitDashboard ticker="SPY" data={data} spot={650} />); });
  await waitFor(() => {
    expect(screen.queryByTestId("skylit-review-loading")).not.toBeInTheDocument();
  });
  await waitFor(() => {
    const pill = screen.getByTestId("skylit-review-pill");
    expect(pill.textContent).toContain("reviewed");
  });
});

test("R8-04: review pill clears on snapshot change and skips replay", async () => {
  // Start with a snapshot that has a reviewed decision
  axios.get.mockImplementation(async () => ({
    data: { ticker: "SPY", decisions: [{ decision_id: "d1", snapshot_id: "snap-r8-04-2", review_state: "reviewed" }] },
  }));
  const data2 = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "snap-r8-04-2", metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  const { rerender } = await act(async () => render(<SkylitDashboard ticker="SPY" data={data2} spot={650} />));
  await waitFor(() => { expect(screen.queryByTestId("skylit-review-loading")).not.toBeInTheDocument(); });
  await waitFor(() => {
    const pill = screen.getByTestId("skylit-review-pill");
    expect(pill.textContent).toContain("reviewed");
  });
  // Switch to a new snapshot with no decision — pill shows "No review yet"
  axios.get.mockImplementation(async () => {
    // All axios calls in this test should return empty decisions
    return { data: { ticker: "SPY", decisions: [] } };
  });
  const data3 = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "snap-r8-04-new", metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(() => rerender(<SkylitDashboard ticker="SPY" data={data3} spot={650} />));
  await waitFor(() => {
    expect(screen.getByTestId("skylit-review-pending")).toBeInTheDocument();
    expect(screen.getByTestId("skylit-review-pending").textContent).toBe("No review yet");
  });
});

// ---- R8-02/R8-04: Save review + Next to review ---------------------------
const R8_DECISIONS = {
  data: { ticker: "SPY", decisions: [
    { decision_id: "d-cur", snapshot_id: "snap-r8-save", scenario: "CALLS",
      side: "CALLS", at_ts: "2026-09-03T14:00:00Z", review_state: null,
      features: { wall_id: "w1" } },
    { decision_id: "d-old", snapshot_id: "snap-r8-old", scenario: "PUTS",
      side: "PUTS", at_ts: "2026-09-03T13:00:00Z", review_state: null },
    { decision_id: "d-done", snapshot_id: "snap-r8-done", scenario: "CALLS",
      side: "CALLS", at_ts: "2026-09-03T12:00:00Z", review_state: "reviewed" },
  ] },
};

function mockR8Backend() {
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/decisions")) return R8_DECISIONS;
    if (u.includes("/solstice/manifest/")) return { data: { snapshots: [{ id: "snap-r8-old" }] } };
    if (u.includes("/solstice/replay/")) {
      return { data: {
        snapshot: { ticker: "SPY", snapshot_id: "snap-r8-old", asof_ts: "2026-09-03T13:00:00Z", spot: 650, exposure_basis: "OI" },
        strikes: [{ strike: 650, gex: 1000 }], walls: [], grids: {},
        quality: { state: "usable", reasonCodes: [], setupEligible: false },
        interactions: [], scenarios: [] } };
    }
    return { data: { strikes: [] } };
  });
  axios.post.mockImplementation(async () => ({ data: { durability: "durable" } }));
}

function r8Data() {
  return {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "snap-r8-save", metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
}

test("R8-02: save review posts frozen context and refetches reviewed state", async () => {
  // Stateful mock: POST flips the stored review; the refetch then observes
  // it. (Swapping the mock after the click races the refetch.)
  let saved = null;
  const baseDec = { ...R8_DECISIONS.data.decisions[0] };
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/decisions")) {
      return { data: { ticker: "SPY", decisions: [{ ...baseDec, review_state: saved }] } };
    }
    return { data: { strikes: [] } };
  });
  axios.post.mockImplementation(async (url, body) => {
    expect(String(url)).toContain("/api/solstice/SPY/decisions/d-cur/review");
    expect(body.state).toBe("reviewed");
    expect(body.reason).toBe("CONFIRMED_SETUP");
    expect(body.note).toContain("metric raw");
    saved = "reviewed";
    return { data: { durability: "durable" } };
  });
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={r8Data()} spot={650} />);
  });
  await waitFor(() => {
    expect(screen.getByTestId("skylit-review-save-reviewed")).toBeInTheDocument();
  });
  await act(async () => {
    fireEvent.change(screen.getByTestId("skylit-review-reason"), { target: { value: "CONFIRMED_SETUP" } });
  });
  await act(async () => {
    fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]);
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId("skylit-review-save-reviewed"));
  });
  expect(axios.post).toHaveBeenCalledTimes(1);
  await waitFor(() => {
    expect(screen.getByTestId("skylit-review-pill").textContent).toContain("reviewed");
  });
});

test("R8-04: next-to-review lists unreviewed only and jumps to replay", async () => {
  mockR8Backend();
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={r8Data()} spot={650} />);
  });
  await waitFor(() => {
    expect(screen.getByTestId("skylit-review-queue")).toBeInTheDocument();
  });
  expect(screen.queryByTestId("skylit-review-open-d-cur")).not.toBeInTheDocument();
  expect(screen.queryByTestId("skylit-review-open-d-done")).not.toBeInTheDocument();
  const jump = screen.getByTestId("skylit-review-open-d-old");
  expect(jump.textContent).toContain("PUTS");
  await act(async () => { fireEvent.click(jump); });
  await waitFor(() => {
    expect(screen.getByTestId("solstice-replay-banner")).toBeInTheDocument();
  });
  expect(screen.queryByTestId("skylit-review-save")).not.toBeInTheDocument();
});


test("activity selection and research share its own axes without raw fallback",()=>{
 const data={...selectionMap(999),metrics:{grids:{activity:{strikes:[650],expiries:["2026-09-18"],grid:{"2026-09-18":{"650":7}}}}}};
 const view=render(<><SkylitDashboard ticker="SPY" data={data} spot={650}/><ResearchSelection/></>);
 fireEvent.click(screen.getByTestId("mock-activity"));
 fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
 expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("7.0");
 expect(JSON.parse(screen.getByTestId("research-selection").textContent)).toMatchObject({overlayMetric:"activity",selectedStrike:650,mapStrikes:[650]});
 view.rerender(<><SkylitDashboard ticker="SPY" data={{...data,metrics:{grids:{}}}} spot={650}/><ResearchSelection/></>);
 expect(screen.queryByTestId("skylit-selected-cell")).not.toBeInTheDocument();
 expect(JSON.parse(screen.getByTestId("research-selection").textContent).selectedStrike).toBeNull();
});
