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
jest.mock("axios", () => ({ get: jest.fn() }));

// Mock Zenith sub-components to null-mounts (no network calls; faster).
jest.mock("./SkylitTickerBar",       () => () => <div data-testid="mock-ticker-bar" />);
jest.mock("./SkylitControlBar",      () => () => <div data-testid="mock-control-bar" />);
jest.mock("./SkylitHeatmapGrid",     () => ({ onCellClick, windowRows, density }) => (
  <div data-testid="mock-heatmap" data-window={windowRows} data-density={density}>
    <button
      data-testid="mock-heatmap-cell"
      onClick={() => onCellClick && onCellClick(650, "2026-09-18", 123.4)}
    >
      cell
    </button>
  </div>
));
jest.mock("./SkylitMetricsSidebar",  () => () => <div data-testid="mock-metrics" />);
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

  test("expand fetches a wider swing band for the overlay", async () => {
    axios.get.mockImplementation(async (url) => ({
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
      expect(calls[0][0]).toContain("mode=swing");
      expect(calls[0][0]).toContain("expiries=8");
    });
  });
});
