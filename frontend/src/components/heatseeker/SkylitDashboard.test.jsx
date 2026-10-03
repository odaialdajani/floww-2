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
import { render, screen, act, fireEvent, waitFor, cleanup } from "@testing-library/react";
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
  <div data-testid="mock-control-bar" data-tickers={JSON.stringify(props.tickers ?? null)} data-spot={JSON.stringify(props.spot ?? null)} data-live={String(props.isLive)}><button data-testid="mock-activity" onClick={()=>props.onMetricChange("activity")}>Activity</button><button data-testid="mock-window" onClick={()=>props.onMetricChange("window")}>Window</button></div>
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
import coverageFixture from "../../fixtures/integration/coverage-read.v1.json";

test('listed expiry admission is an explicit read, not a new map or selection', async () => {
  axios.get.mockResolvedValue({ data: coverageFixture.expiries });
  render(<SkylitDashboard ticker="SPY" data={selectionMap()} />);
  const before = screen.getByTestId('skylit-loaded-scope').textContent;
  fireEvent.click(screen.getByText('Listed 14–60 DTE coverage'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Read listed coverage' })));
  expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/price-paths/expiries?ticker=SPY&min_dte=14&max_dte=60&expirations=12'), expect.objectContaining({ signal: expect.anything() }));
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('2026-10-30');
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('28 DTE');
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('BELOW_WINDOW');
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('first 12 listed');
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('2026-10-02T14:05:00Z');
  expect(screen.getByTestId('skylit-loaded-scope')).toHaveTextContent(before);
});

test.each([
  [{ ticker: 'QQQ' }, 'EXPIRY_IDENTITY_MISMATCH'],
  [{ version: 'coverage-read.v2' }, 'COVERAGE_VERSION_UNSUPPORTED'],
  [{ window: { min_dte: 0, max_dte: 30 } }, 'EXPIRY_WINDOW_MISMATCH'],
  [{ stale: true }, 'EXPIRY_OBSERVATION_STALE'],
  [{ stale: null }, 'EXPIRY_FRESHNESS_UNKNOWN'],
  [{ fetched_at: null }, 'EXPIRY_OBSERVATION_UNDECLARED'],
])('expiry disclosure refuses mismatched or non-fresh inventory', async (override, reason) => {
  axios.get.mockResolvedValue({ data: { ...coverageFixture.expiries, ...override } });
  render(<SkylitDashboard ticker="SPY" data={selectionMap()} />);
  fireEvent.click(screen.getByText('Listed 14–60 DTE coverage'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Read listed coverage' })));
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent(reason);
  expect(screen.queryByRole('table', { name: 'Listed expiry admission' })).toBeNull();
});

test('ticker change aborts expiry inventory and discards late success', async () => {
  let release;
  axios.get.mockImplementation(url => String(url).includes('/price-paths/expiries') ? new Promise(resolve => { release = resolve; }) : Promise.resolve({ data: {} }));
  const ui = render(<SkylitDashboard ticker="SPY" data={selectionMap()} />);
  fireEvent.click(screen.getByText('Listed 14–60 DTE coverage'));
  fireEvent.click(screen.getByRole('button', { name: 'Read listed coverage' }));
  const signal = axios.get.mock.calls.find(([url]) => String(url).includes('/price-paths/expiries'))[1].signal;
  ui.rerender(<SkylitDashboard ticker="QQQ" data={{ ...selectionMap(), ticker: 'QQQ' }} />);
  expect(signal.aborted).toBe(true);
  await act(async () => release({ data: coverageFixture.expiries }));
  expect(screen.queryByRole('table', { name: 'Listed expiry admission' })).toBeNull();
});

function expandedCoverage() {
  const rows = coverageFixture.expiries.expiries.slice(0, 2).map(row => ({ ...row, display_envelope: true }));
  rows.push({ expiry: '2026-11-16', dte: 45, admitted: true, reason: 'ADMITTED', display_envelope: false });
  return { ...coverageFixture.expiries, expiries: rows, n_admitted: 2, coverage: {
    requested_expiries: 12, n_listed: 3, n_display_envelope: 2,
    listing_capped: false, lower_edge_observed: true, upper_edge_observed: false,
  } };
}

async function readExpiryResponse(data) {
  axios.get.mockResolvedValue({ data });
  render(<SkylitDashboard ticker="SPY" data={selectionMap()} />);
  fireEvent.click(screen.getByText('Listed 14–60 DTE coverage'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Read listed coverage' })));
}

test('expiry metadata distinguishes policy admission, optional filter and unobserved range edge', async () => {
  await readExpiryResponse(expandedCoverage());
  const table = screen.getByRole('table', { name: 'Listed expiry admission' });
  expect(table).toHaveTextContent('≤30 DTE filter');
  expect(table.querySelector('tbody').lastChild).toHaveTextContent('45 DTEADMITTEDOutside');
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('3 returned / 12 requested');
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('Upper edge not observed');
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('not complete range coverage');
});

test('capped expiry listing is disclosed without claiming an exhaustive range', async () => {
  const data = expandedCoverage();
  const rows = Array.from({ length: 12 }, (_, i) => ({ ...data.expiries[1], expiry: `2026-10-${String(20 + i).padStart(2, '0')}` }));
  await readExpiryResponse({ ...data, expiries: rows, n_admitted: 12, coverage: { ...data.coverage, n_listed: 12, n_display_envelope: 12, listing_capped: true, lower_edge_observed: false } });
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('Listing capped');
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('Lower edge not observed');
});

test('legacy expiry metadata remains unknown rather than complete or filter-eligible', async () => {
  await readExpiryResponse({ ...coverageFixture.expiries, coverage: undefined, expiries: coverageFixture.expiries.expiries.map(({ display_envelope, ...row }) => row) });
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('Coverage metadata unavailable');
  expect(screen.getByRole('table', { name: 'Listed expiry admission' })).toHaveTextContent('Unknown');
});

test.each([
  ['count mismatch', { n_listed: 99 }],
  ['string admission flag', { upper_edge_observed: 'true' }],
  ['different requested cap', { requested_expiries: 16 }],
])('invalid expiry coverage is refused: %s', async (_name, override) => {
  const data = expandedCoverage();
  await readExpiryResponse({ ...data, coverage: { ...data.coverage, ...override } });
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent('EXPIRY_COVERAGE_UNAVAILABLE');
  expect(screen.queryByRole('table', { name: 'Listed expiry admission' })).toBeNull();
});

test.each(['chain_unavailable', 'REVERSED_WINDOW'])('structured top-level refusal stays visible: %s', async error => {
  axios.get.mockRejectedValue({ response: { status: error === 'chain_unavailable' ? 502 : 422, data: { version: 'coverage-read.v1', error } } });
  render(<SkylitDashboard ticker="SPY" data={selectionMap()} />);
  fireEvent.click(screen.getByText('Listed 14–60 DTE coverage'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Read listed coverage' })));
  expect(screen.getByTestId('solstice-expiry-coverage')).toHaveTextContent(error);
});

test('R12: strike review callback requires explicitly armed Trade mode', () => {
  const onStrikeClick = jest.fn();
  render(<SkylitDashboard ticker="SPY" data={selectionMap()} onStrikeClick={onStrikeClick} />);
  fireEvent.click(screen.getByTestId('mock-strike'));
  expect(onStrikeClick).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId('skylit-trade-btn'));
  fireEvent.click(screen.getByTestId('mock-strike'));
  expect(onStrikeClick).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByTestId('skylit-trade-btn'));
  fireEvent.click(screen.getByTestId('mock-strike'));
  expect(onStrikeClick).toHaveBeenCalledTimes(1);
});

function ResearchSelection(){const [context]=useScreenContext();return <output data-testid="research-selection">{JSON.stringify(context)}</output>;}

function selectionMap(value = 123.4, asof = "2026-09-11T18:00:00Z") {
 return {ticker:"SPY",asof,map_query:{expiries:4,mode:"day",dte:null},strikes:[{strike:650}],
   grid:{strikes:[650],expiries:["2026-09-18"],grid:{"2026-09-18":{"650":value}}}};
}

test("window context carries server baseline/interval selectors and clears them with basis change", () => {
 const section={strikes:[650],expiries:["2026-09-18"],grid:{"2026-09-18":{"650":0}},status:"ok",
   comparison:{previous_snapshot_id:"prior"},interval:{start:"2026-09-11T17:59:00Z",end:"2026-09-11T18:00:00Z"}};
 const data={...selectionMap(),snapshotId:"current",data_source:"fixture",formula_version:"gex.v2",metrics:{grids:{window:section}}};
 const mounted=render(<><SkylitDashboard ticker="SPY" data={data} spot={650}/><ResearchSelection/></>);
 fireEvent.click(screen.getByTestId("mock-window"));
 fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
 const current=()=>JSON.parse(screen.getByTestId("research-selection").textContent);
 expect(current()).toMatchObject({overlayMetric:"window",windowBaselineId:"prior",windowInterval:section.interval,selectedStrike:650});
 expect(current()).not.toHaveProperty("windowNet");
 mounted.rerender(<><SkylitDashboard ticker="SPY" data={{...data,metrics:{grids:{window:{status:"unavailable",reason:"NO_BASELINE"}}}}} spot={650}/><ResearchSelection/></>);
 expect(current().windowBaselineId).toBeNull();
 expect(current().selectedStrike).toBeNull();
 fireEvent.click(screen.getByTestId("mock-activity"));
 expect(current().windowInterval).toBeNull();
});

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
afterEach(async () => { await act(async () => {}); });

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

test.each(["vex", "charm"])("%s mounted replay publishes its stored envelope, value and independent owning identity", async metric => {
 const main={...selectionMap().grid,[metric+"_grid"]:{"2026-09-18":{"650":-7}},[metric+"_meta"]:{record_version:"metric-record.v1",status:"ok"}};
 axios.get.mockImplementation(async url=>({data:String(url).includes("/manifest/") ? {snapshots:[{id:"record"}]} : String(url).includes("/replay/") ? {
   snapshot:{ticker:"SPY",snapshot_id:"record",asof_ts:"2026-09-11T18:00:00Z",spot:650,data_source:"fixture",formula_version:"gex.v2"},
   grids:{grid:main},metrics_full:{},context:{display:{map_query:selectionMap().map_query}},strikes:[{strike:650}]
 } : {}}));
 const mounted=render(<><SkylitDashboard ticker="SPY" data={selectionMap(999)} spot={650} viewMode={metric}/><ResearchSelection/></>);
 await act(async()=>fireEvent.click(screen.getByTestId("solstice-replay-load")));
 await act(async()=>fireEvent.click(screen.getByTestId("solstice-replay-next")));
 fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
 expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("-7.0");
 const current=()=>JSON.parse(screen.getByTestId("research-selection").textContent);
 expect(current()).toMatchObject({metric,displayMode:"replay",snapshotId:"record",recordedMetricVersion:"metric-record.v1",selectedStrike:650});
 mounted.rerender(<><SkylitDashboard ticker="SPY" data={selectionMap(12345)} spot={700} viewMode={metric}/><ResearchSelection/></>);
 expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("-7.0");
 fireEvent.click(screen.getByTestId("solstice-replay-exit"));
 expect(current().recordedMetricVersion).toBeNull();
 expect(current().selectedStrike).toBeNull();
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

test("R11: Raw+Δ toggle mounts raw-left/adjustment-right over one snapshot", async () => {
  const data = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    metrics: { walls: [], grids: { delta: { expiries: ["2026-09-18"], grid: { "2026-09-18": { 650: 500 } } } } },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-rawdelta-toggle")); });
  expect(screen.getByTestId("skylit-compare-desk")).toBeInTheDocument();
  expect(screen.queryAllByTestId("mock-heatmap").length).toBe(2);
  // Raw left, adjustment right — same symbol panes, never multi-symbol.
  expect(screen.getByTestId("skylit-pane-gex-header").textContent).toContain("Raw OI");
  expect(screen.getByTestId("skylit-pane-delta-header").textContent).toContain("Δ-weighted OI");
  expect(screen.getByTestId("skylit-pane-delta-header").textContent).toContain("USD/1% move");
  expect(screen.queryByTestId("skylit-pane-vex")).not.toBeInTheDocument();
  // Clicking the right pane makes it own the readout with its own basis:
  // the readout resolves 500 (Δ surface), not 1000 (raw surface).
  const cells = screen.getAllByTestId("mock-heatmap-cell");
  await act(async () => { fireEvent.click(cells[1]); });
  expect(screen.getByTestId("skylit-selected-cell").textContent).toContain("500.0");
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-rawdelta-toggle")); });
  expect(screen.queryAllByTestId("mock-heatmap").length).toBe(1);
  expect(screen.queryByTestId("skylit-compare-desk")).not.toBeInTheDocument();
});

test("R11: Raw+Δ right pane follows the active adjustment basis", async () => {
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
  await act(async () => { fireEvent.click(screen.getByTestId("mock-activity")); });
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-rawdelta-toggle")); });
  expect(screen.getByTestId("skylit-pane-gex-header").textContent).toContain("Raw OI");
  expect(screen.getByTestId("skylit-pane-delta-header").textContent).toContain("Session volume");
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
  // O2: review UI lives in the selection-opened drawer — select a cell first.
  await act(async () => { fireEvent.click(screen.getByTestId("mock-heatmap-cell")); });
  await waitFor(() => { expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument(); });
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
  await act(async () => { fireEvent.click(screen.getByTestId("mock-heatmap-cell")); });
  await waitFor(() => { expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument(); });
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
  await act(async () => { fireEvent.click(screen.getByTestId("mock-heatmap-cell")); });
  await waitFor(() => { expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument(); });
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
  // O2: save controls live in the selection-opened drawer.
  await act(async () => {
    fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]);
  });
  await waitFor(() => { expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument(); });
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
  await act(async () => {
    fireEvent.click(screen.getAllByTestId("mock-heatmap-cell")[0]);
  });
  await waitFor(() => { expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument(); });
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

// The actual historical chart must never borrow a current map for research.
jest.mock("react-plotly.js", () => () => <div data-testid="history-plot" />);
test("open history blocks research through loading and live refresh; close uses latest map", async()=>{
 axios.get.mockImplementation(()=>new Promise(()=>{}));
 const mounted=render(<><SkylitDashboard ticker="SPY" data={selectionMap()} spot={650}/><ResearchSelection/></>);
 fireEvent.click(screen.getByText("Price chart + historical nodes"));
 let context=JSON.parse(screen.getByTestId("research-selection").textContent);
 expect(context).toMatchObject({displayMode:"price-history",mapVersion:null,mapQuery:null,selectedStrike:null});
 mounted.rerender(<><SkylitDashboard ticker="SPY" data={selectionMap(999,"LATEST")} spot={650}/><ResearchSelection/></>);
 expect(JSON.parse(screen.getByTestId("research-selection").textContent).displayMode).toBe("price-history");
 fireEvent.click(screen.getByText("Price chart + historical nodes"));
 expect(JSON.parse(screen.getByTestId("research-selection").textContent)).toMatchObject({displayMode:"live",mapVersion:"LATEST"});
 fireEvent.click(screen.getByText("Price chart + historical nodes"));
 mounted.rerender(<><SkylitDashboard ticker="QQQ" data={{...selectionMap(),ticker:"QQQ"}} spot={650}/><ResearchSelection/></>);
 expect(screen.getByText("Price chart + historical nodes")).toHaveAttribute("aria-expanded","true");
 expect(JSON.parse(screen.getByTestId("research-selection").textContent)).toMatchObject({ticker:"QQQ",displayMode:"price-history",mapVersion:null});
});


test('selected wall receives the current VEX surface and separate contract gross',async()=>{
 const base=selectionMap();
 const payload={...base,grid:{...base.grid,vex_grid:{'2026-09-18':{'650':0}},
    vex_strike_gross:[{strike:650,vex_gross:400}],vex_meta:{status:'ok'}},
   metrics:{walls:[{wall_id:'selected',low:650,high:650,members:[650],gross:1000,net:1000}],grids:{}}};
 const mounted=render(<SkylitDashboard ticker="SPY" data={payload} spot={650}/>);
 fireEvent.click(screen.getByTestId('mock-heatmap-cell'));
 expect(screen.getByText('VEX gross / net').closest('tr').textContent).toContain('$400 / $0');
 const next={...payload,grid:{...payload.grid,vex_grid:{'2026-09-18':{'650':25}},vex_strike_gross:[{strike:650,vex_gross:525}]}};
 mounted.rerender(<SkylitDashboard ticker="SPY" data={next} spot={650}/>);
 expect(screen.getByText('VEX gross / net').closest('tr').textContent).toContain('$525 / $25');
 const old={...payload,grid:{...payload.grid}};delete old.grid.vex_strike_gross;
 mounted.rerender(<SkylitDashboard ticker="SPY" data={old} spot={650}/>);
 expect(screen.getByText('VEX gross / net').closest('tr').textContent).toContain('— / $0');
 await act(async()=>{});
});

describe("SkylitDashboard O1 layout ownership", () => {
  let observed = [];
  beforeEach(() => {
    observed = [];
    global.ResizeObserver = class ResizeObserver {
      constructor(callback) { this.callback = callback; }
      observe(target) { observed.push(target); }
      disconnect() {}
      unobserve() {}
    };
  });
  afterEach(() => { delete global.ResizeObserver; });

  test("compare desk does not re-apply zoom (single application at the area)", async () => {
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" />);
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-zoom-in"));
    });
    expect(screen.getByTestId("skylit-heatmap-area").style.zoom).toBe("1.25");
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-compare-toggle"));
    });
    const desk = screen.getByTestId("skylit-compare-desk");
    // jsdom has no `zoom` CSS property: absent reads undefined, and any
    // re-applied style={{zoom}} would come back as a value. Zoom must live
    // only on the heatmap area (asserted 1.25 above).
    expect(desk.style.zoom).toBeUndefined();
  });

  test("fitRows observer watches the allocated parent box, not the grid itself", async () => {
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" />);
    });
    const area = screen.getByTestId("skylit-heatmap-area");
    expect(observed.length).toBeGreaterThan(0);
    // The measured box must be the flex parent (stable allocated height),
    // never the heatmap area whose descendants change with fitRows.
    expect(observed[0]).toBe(area.parentElement);
    expect(observed[0]).not.toBe(area);
  });
});

describe("SkylitDashboard O2 inspector drawer", () => {
  const drawerData = {
    ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "snap-o2-1",
    metrics: { walls: [{ wall_id: "w1", low: 648, high: 652, members: [650], gross: 1000, net: 1000 }], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true },
  };
  beforeEach(() => {
    axios.get.mockImplementation(async () => ({ data: { strikes: [] } }));
    window.sessionStorage.clear();
  });

  test("selection opens the drawer with inspector + Open in Triad; close and Esc shut it", async () => {
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" data={drawerData} spot={650} />);
    });
    expect(screen.queryByTestId("skylit-inspector-drawer")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
    });
    await waitFor(() => {
      expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument();
    });
    expect(screen.getByTestId("skylit-open-triad")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-drawer-close"));
    });
    expect(screen.queryByTestId("skylit-inspector-drawer")).not.toBeInTheDocument();
    // Same selection must NOT yank it back open (explicit close wins).
    await act(async () => {
      fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
    });
    await act(async () => {});
    expect(screen.queryByTestId("skylit-inspector-drawer")).not.toBeInTheDocument();
    // Fresh selection context reopens; Esc closes.
    cleanup();
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" data={drawerData} spot={650} />);
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
    });
    await waitFor(() => {
      expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.keyDown(window, { key: "Escape" });
    });
    expect(screen.queryByTestId("skylit-inspector-drawer")).not.toBeInTheDocument();
  });

  test("Open in Triad writes a sessionStorage handoff for Triad to consume", async () => {
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" data={drawerData} spot={650} />);
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
    });
    await waitFor(() => {
      expect(screen.getByTestId("skylit-open-triad")).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("skylit-open-triad"));
    });
    const raw = window.sessionStorage.getItem("solstice.triadHandoff");
    expect(raw).not.toBeNull();
    const handoff = JSON.parse(raw);
    expect(handoff).toMatchObject({ ticker: "SPY", strike: 650, snapshotId: "snap-o2-1" });
    expect(typeof handoff.ts).toBe("number");
  });
});

test("O2 drawer anchors to the main area so toolbar controls stay clickable", async () => {
  axios.get.mockImplementation(async () => ({ data: { strikes: [] } }));
  // Minimal fixture (drawerData is scoped to the O2 describe above).
  const data = { ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "s-anchor", metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true } };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId("mock-heatmap-cell"));
  });
  await waitFor(() => {
    expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument();
  });
  // The drawer must live inside the main area (absolute anchor), never as a
  // viewport-fixed overlay covering the toolbar row above it.
  const drawer = screen.getByTestId("skylit-inspector-drawer");
  expect(drawer.closest(".skylit-main-area")).not.toBeNull();
  // Toolbar controls live outside the drawer's anchor box, so an open
  // drawer can never cover them (the real-browser failure this guards).
  const toggle = screen.getByTestId("skylit-compare-toggle");
  expect(drawer.contains(toggle)).toBe(false);
});

test("O5 drawer moves focus to its close control and restores prior focus on close", async () => {
  axios.get.mockImplementation(async () => ({ data: { strikes: [] } }));
  const data = { ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "s-focus", metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true } };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  const cell = screen.getByTestId("mock-heatmap-cell");
  cell.focus();
  await act(async () => { fireEvent.click(cell); });
  await waitFor(() => {
    expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument();
  });
  expect(screen.getByTestId("skylit-drawer-close")).toHaveFocus();
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-drawer-close")); });
  expect(cell).toHaveFocus();
});

test("O3 compare panes share one snapshot and identical geometry inputs", async () => {
  axios.get.mockImplementation(async () => ({ data: { strikes: [] } }));
  const data = { ticker: "SPY", asof: "2026-09-03T00:00:00Z", spot: 650, exposure_basis: "OI",
    strikes: [{ strike: 650, gex: 1000 }],
    grid: { expiries: ["2026-09-18"], strikes: [650], grid: { "2026-09-18": { 650: 1000 } } },
    snapshotId: "s-geo", metrics: { walls: [], grids: {} },
    quality: { state: "usable", reasonCodes: [], setupEligible: true } };
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={650} />);
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId("skylit-compare-toggle"));
  });
  const panes = screen.getAllByTestId("mock-heatmap");
  expect(panes).toHaveLength(2);
  // Same snapshot, same spot, same row window in both panes: row geometry is
  // identical by construction, so pixel-offset scroll sync is valid (S3).
  // A missing VEX surface renders its own unavailable state instead.
  const windows = panes.map((p) => p.getAttribute("data-window"));
  expect(windows[0]).toBe(windows[1]);
  const spots = panes.map((p) => p.getAttribute("data-spot"));
  expect(spots[0]).toBe(spots[1]);
  expect(spots[0]).toBe("650");
});
