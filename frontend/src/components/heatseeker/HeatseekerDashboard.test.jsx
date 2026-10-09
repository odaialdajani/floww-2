/**
 * @jest-environment jsdom
 */
import React from "react";
import axios from "axios";
import { render, screen, act, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import useScreenContext, { publishScreenContext } from "../../agent/useScreenContext";
var mockPublishRich = false;
function ReadContext() { const [context] = useScreenContext(); return <output data-testid="screen-context">{JSON.stringify(context)}</output>; }
function readContext() { return JSON.parse(screen.getByTestId("screen-context").textContent); }
jest.mock("./NodeConfluencePanel", () => {
 const React = require("react");
 const { usePublishScreenContext } = require("../../agent/useScreenContext");
 return React.memo(function RichChild({ticker}) {
  const context = React.useMemo(() => mockPublishRich ? {contextVersion:2,page:"heatseeker",ticker,study:"Recorded map",dte:7,displayMode:"replay",observedAt:"2026-10-01T14:00:00Z",snapshotId:"fixture-snapshot",provider:"fixture",formula:"fixture-formula",activePane:"gex",mapExpiries:["2026-10-16"],mapQuery:{},mapVersion:"2026-10-01T14:00:00Z",reading:{netGex:123}} : null, [ticker]);
  usePublishScreenContext(context);
  return <div data-testid="rich-child"/>;
 });
});

// Study navigation checks must not read a real account or market service.
jest.mock("axios", () => ({get: jest.fn().mockRejectedValue(new Error("Read unavailable"))}));

// Mock IntersectionObserver — trigger immediately so LazyRow renders children
global.IntersectionObserver = class IntersectionObserver {
  constructor(callback) { this.callback = callback; }
  observe() { this.callback([{ isIntersecting: true }]); }
  disconnect() {}
  unobserve() {};
};

// Mock react-plotly.js (required by VannaChart and CharmChart)
jest.mock("react-plotly.js", () => {
  const React = require("react");
  return React.forwardRef(function MockPlot(props, ref) {
    return React.createElement("div", { "data-testid": "mock-plot", ref });
  });
});

// Mock useHeatseeker
jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

// Mock ErrorBoundary
jest.mock("../ErrorBoundary", () => ({
  __esModule: true,
  default: function MockErrorBoundary({ children }) { return <>{children}</>; },
}));

// Mock the steal-list top-3 components mounted into Row 3 (real fetch
// would hit the backend on mount; we just need to confirm presence).
jest.mock("./DualGEXBadge", () => () => <div data-testid="hs-dual-gex" />);
jest.mock("./IVMidBadge", () => () => <div data-testid="hs-iv-mid" />);
jest.mock("./WheelIncomeScreenerPanel", () => {
  const React = require("react");
  return function MockWheel() {
    const [choice, setChoice] = React.useState("Put income");
    return <div data-testid="hs-wheel-income"><button onClick={() => setChoice("Call income")}>{choice}</button></div>;
  };
});
jest.mock("./MaxPainBadge", () => () => <div data-testid="hs-max-pain" />);
// Per-expiry max-pain-drift multi-line chart tile (steal-list #9 rich
// visualization; fetches /api/max_pain_drift/{ticker}/per_expiry_history).
jest.mock("./MaxPainPerExpiryDriftTile", () => () => <div data-testid="hs-max-pain-per-expiry-drift" />);
// Row 4 mount — steal-list #10 (cone) + #8 (opportunity engine)
// + news pulse tile (catalyst + headlines count).
jest.mock("./StrikeConeBadge", () => () => <div data-testid="hs-strike-cone" />);
jest.mock("./OpportunityBadge", () => () => <div data-testid="hs-opportunity" />);
jest.mock("./NewsBadge", () => () => <div data-testid="hs-news" />);
// Row 4b mount — steal-list #4 (risk-neutral density). The component
// fetches /api/rnd/{ticker}?expiry_index=1 on mount (real network call
// to :8000) — we mock it so the test stays synchronous + side-effect-free.
jest.mock("./RndDensityPanel", () => () => <div data-testid="hs-rnd-density" />);

// Mock BriefingStrip — it calls fetch() on mount for /api/briefing/{ticker}
jest.mock("./BriefingStrip", () => () => <div data-testid="hs-briefing-strip" />);

// Mock lazy-loaded chart components
jest.mock("../VannaChart", () => () => <div data-testid="mock-vanna" />);
jest.mock("../CharmChart", () => () => <div data-testid="mock-charm" />);

// Import AFTER mocks are set up
import HeatseekerDashboard, { HeroSection } from "./HeatseekerDashboard";
import { useHeatseeker } from "../../hooks/useHeatseeker";

const IDLE = { data: null, loading: false, error: null, refresh: () => {} };

describe("HeatseekerDashboard", () => {
  beforeEach(() => {
    mockPublishRich = false;
    useHeatseeker.mockReturnValue(IDLE);
    axios.get.mockRejectedValue(new Error("Read unavailable"));
    global.fetch = jest.fn().mockRejectedValue(new Error("Read unavailable"));
  });

  test("shows one study choice without development captions", async () => {
    await act(async () => {
      render(<HeatseekerDashboard ticker="SPY" spot={500} />);
    });
    expect(screen.getAllByRole("combobox", { name: "Study" })).toHaveLength(1);
    expect(screen.getByRole("combobox", { name: "Study" })).toHaveValue("levels");
    expect(screen.queryByText(/Wave 1 \+ 2 \+ 3/i)).not.toBeInTheDocument();
  });

  test("every original panel remains reachable without stacking every study", async () => {
    await act(async () => {
      render(<HeatseekerDashboard ticker="SPY" spot={500} />);
    });
    expect(screen.getByTestId("heatseeker-dashboard")).toBeInTheDocument();
    // The old all-at-once layout was intentionally replaced by one visible
    // family. Every old panel is still checked after choosing its family.
    const families = {
      levels: ["hs-flip-zones", "hs-node-lifecycle", "hs-air-pockets", "rich-child"],
      patterns: ["hs-beach-ball", "hs-reverse-rug", "hs-rainbow-road"],
      income: ["hs-dual-gex", "hs-iv-mid", "hs-wheel-income"],
      history: ["hs-velocity-mode", "hs-trinity-confluence", "hs-max-pain", "hs-max-pain-per-expiry-drift"],
      moves: ["hs-strike-cone", "hs-opportunity", "hs-news", "hs-rnd-density"],
      structure: ["hs-rolling-floors-ceilings", "hs-tug-of-war", "hs-node-classification", "hs-stacked-nodes"],
      exposure: ["mock-vanna", "mock-charm"],
      briefing: ["hs-briefing-strip"],
    };
    for (const [family, ids] of Object.entries(families)) {
      await act(async () => fireEvent.change(screen.getByRole("combobox", {name:"Study"}), {target:{value:family}}));
      ids.forEach(id => expect(screen.getByTestId(id)).toBeVisible());
      expect(document.querySelectorAll('.study-family:not([hidden])')).toHaveLength(1);
    }
    [
      // Row 3 container — visual-regression sweep target (2026-07-15)
      "hs-row3-confluence-velocity",
      "hs-flip-zones",
      "hs-node-lifecycle",
      "hs-air-pockets",
      "hs-beach-ball",
      "hs-reverse-rug",
      "hs-rainbow-road",
      "hs-velocity-mode",
      "hs-trinity-confluence",
      // Steal-list top-3 (rank #1, #5, #3) mounted into Row 3 so the new
      // signals appear on the main Solstice page, not just /steal-three.
      "hs-dual-gex",
      "hs-iv-mid",
      "hs-wheel-income",
      "hs-max-pain",
      // Steal-list #10 + #8 + news mounted into Row 4 ("Expected Moves / Trade Ideas")
      // — news Badge tests-loaded count delta is whatever the file shows (24 → 25
      // in this revision; the user's "17→18" was a relative-count shorthand).
      "hs-strike-cone",
      "hs-opportunity",
      "hs-news",
      // Row 4b mount — steal-list #4 RND panel (full-width PDF/CDF viz).
      "hs-rnd-density",
      "hs-rnd-density-row",
      "hs-rolling-floors-ceilings",
      "hs-tug-of-war",
      "hs-node-classification",
      "hs-stacked-nodes",
      // NEW (2026-07-15): Row 3 steal-list wrappers — standardize on
      // hs-steal-<feature> so visual verifications can target tiles
      // by semantic purpose without screen-scraping the layout grid.
      "hs-steal-dual-gex",
      "hs-steal-iv-mid",
      "hs-steal-wheel-income",
      "hs-steal-max-pain",
      "hs-steal-max-pain-per-expiry-drift",
    ].forEach((tid) => expect(screen.getByTestId(tid)).toBeInTheDocument());
  });

  test("strips leading caret from index symbols like ^SPX", async () => {
    await act(async () => {
      render(<HeatseekerDashboard ticker="^SPX" />);
    });
    expect(screen.getByTestId("study-summary")).toHaveTextContent("SPX");
  });

  test("a missing reading never claims to be live", () => {
    render(<HeroSection ticker="SPY" />);
    expect(screen.getByTestId("study-summary")).toHaveTextContent("No reading");
    expect(screen.queryByText("Live")).not.toBeInTheDocument();
    expect(document.querySelector('.animate-pulse')).toBeNull();
  });

  test("already opened panels keep their reading and control state", async () => {
    await act(async () => render(<HeatseekerDashboard ticker="SPY" />));
    await act(async () => fireEvent.change(screen.getByRole("combobox", {name:"Study"}), {target:{value:"income"}}));
    const original = screen.getByTestId("hs-wheel-income");
    fireEvent.click(screen.getByRole("button", {name:"Put income"}));
    await act(async () => fireEvent.change(screen.getByRole("combobox", {name:"Study"}), {target:{value:"patterns"}}));
    expect(original).not.toBeVisible();
    await act(async () => fireEvent.change(screen.getByRole("combobox", {name:"Study"}), {target:{value:"income"}}));
    expect(screen.getByTestId("hs-wheel-income")).toBe(original);
    expect(screen.getByRole("button", {name:"Call income"})).toBeVisible();
  });

  test("supplied studies stay in their matching family and preserve control state", async () => {
    function Extra({family}) {
      const [choice,setChoice] = React.useState("First choice");
      return <div data-testid={`extra-${family}`}><button onClick={()=>setChoice("Saved choice")}>{family} {choice}</button></div>;
    }
    const families = ["levels","patterns","income","history","moves","structure","exposure","briefing"];
    const extras = Object.fromEntries(families.map(family=>[family,<Extra key={family} family={family}/>]));
    await act(async()=>render(<HeatseekerDashboard ticker="SPY" extraStudies={extras}/>));
    fireEvent.click(screen.getByRole("button",{name:"levels First choice"}));
    for (const family of families) {
      await act(async()=>fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:family}}));
      expect(screen.getByTestId(`extra-${family}`)).toBeVisible();
      families.filter(other=>other!==family).forEach(other=>{
        const extra=screen.queryByTestId(`extra-${other}`);
        if(extra) expect(extra).not.toBeVisible();
      });
      expect(screen.getAllByRole("combobox",{name:"Study"})).toHaveLength(1);
    }
    fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"levels"}});
    expect(screen.getByRole("button",{name:"levels Saved choice"})).toBeVisible();
  });
});


beforeEach(()=>{mockPublishRich=false;useHeatseeker.mockReturnValue(IDLE);axios.get.mockRejectedValue(new Error("Read unavailable"));global.fetch=jest.fn().mockRejectedValue(new Error("Read unavailable"));});

test("Options map publishes only the chosen stock and study without inventing readings", async()=>{
 await act(async()=>render(<><HeatseekerDashboard ticker="SPY" spot={500}/><ReadContext/></>));
 expect(readContext()).toMatchObject({contextVersion:1,page:"heatseeker",ticker:"SPY",study:"Price levels",observedAt:null});
 expect(readContext().spot).toBeUndefined();
 expect(readContext().reading).toBeUndefined();
 await act(async()=>fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"patterns"}}));
 expect(readContext().study).toBe("Patterns");
});

test("a memoized current child keeps its real reading when the Options study changes",async()=>{
 mockPublishRich=true;
 const view=render(<><HeatseekerDashboard ticker="SPY"/><ReadContext/></>);
 expect(readContext()).toMatchObject({page:"heatseeker",ticker:"SPY",study:"Recorded map",dte:7,displayMode:"replay",reading:{netGex:123}});
 const selectedReading=readContext();
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"patterns"}});
 expect(readContext()).toEqual(selectedReading);
 expect(readContext().study).toBe("Recorded map");
 view.unmount();
});

test("Options unmount cannot clear a later screen owner",async()=>{
 const view=render(<><HeatseekerDashboard ticker="SPY"/><ReadContext/></>);
 let release; act(()=>{release=publishScreenContext({page:"flowseeker-pro",ticker:"QQQ"});});
 view.rerender(<ReadContext/>);
 expect(readContext()).toMatchObject({page:"flowseeker-pro",ticker:"QQQ"});
 act(()=>release());
});


test("a changed Options stock receives the new child reading without keeping the old stock",()=>{
 mockPublishRich=true;
 const view=render(<React.StrictMode><HeatseekerDashboard ticker="SPY"/><ReadContext/></React.StrictMode>);
 expect(readContext()).toMatchObject({page:"heatseeker",ticker:"SPY",dte:7,reading:{netGex:123}});
 view.rerender(<React.StrictMode><HeatseekerDashboard ticker="NVDA"/><ReadContext/></React.StrictMode>);
 expect(readContext()).toMatchObject({page:"heatseeker",ticker:"NVDA",dte:7,reading:{netGex:123}});
});


// Mount the actual App Options branch, with isolated study controls. If App
// drops a real study or routes it to the wrong family, these DOM checks fail.
function mockAppStudy(name) {
 return function IsolatedAppStudy() {
  const [choice,setChoice]=React.useState("First choice");
  return <div data-testid={"app-study-"+name}><button onClick={()=>setChoice("Saved choice")}>{name} {choice}</button></div>;
 };
}
var mockAppReading={ticker:"SPY",spot:500,asof:"2026-10-07T12:00:00Z",nodes:{king:{strike:500}},metrics:{gex_net_v1:100},velocity:{velocity_score:.2,snapshots_count:3}};
jest.mock("../../context/AuthContext",()=>({useAuth:()=>({token:"fixture",user:null,isAuthenticated:true,logout:()=>{}})}));
jest.mock("../../context/ThemeContext",()=>({useTheme:()=>({theme:"dark",toggleTheme:()=>{}})}));
jest.mock("../../shell/useWorkspaceNavigation",()=>({__esModule:true,default:()=>["skylit",()=>{},{}]}));
jest.mock("../../shell/AppShell",()=>{const React=require("react");return {__esModule:true,default:({children})=><div data-testid="actual-app-study-branch">{children}</div>};});
jest.mock("../../hooks/useWebSocketGex",()=>({useWebSocketGex:()=>({connected:false,reconnectAttempt:0,data:null})}));
jest.mock("../../hooks/useScopedReading",()=>({useScopedReading:(scope,options)=>[options?.retain?mockAppReading:scope==="SPY"?{spot:500}:null,()=>{},false]}));
jest.mock("../../hooks/useSolsticeReviewCallbacks",()=>({__esModule:true,default:()=>({})}));
jest.mock("./useTickerDirectory",()=>({__esModule:true,default:()=>({tickers:["SPY"],status:"available",retry:()=>{}})}));
jest.mock("./TickerPicker",()=>()=>null);
jest.mock("../AlertOverlay",()=>()=>null);
jest.mock("../PWAInstallBanner",()=>()=>null);
jest.mock("../SidebarPanels",()=>Object.fromEntries(["FlipZonesPanel","StackedNodesPanel","TugOfWarPanel","ScenarioPanel","RiskDashboardPanel","OpportunitiesPanel","ImpliedMovePanel","VolAnalyticsPanel","GreekReferencePanel","UsagePanel","LivePolicyPanel"].map(name=>[name,mockAppStudy(name)])));
jest.mock("../AdvancedAnalyticsPanel",()=>Object.fromEntries(["MarketRegimePanel","ImpliedPDFPanel","HedgeImpulsePanel","PressureCloudPanel","CharmIntegralPanel"].map(name=>[name,mockAppStudy(name)])));
jest.mock("../MlDashboard",()=>({MlDashboard:mockAppStudy("MlDashboard")}));
jest.mock("../MultiTimeframeGEXPanel",()=>mockAppStudy("MultiTimeframeGEXPanel"));
jest.mock("../FlowTicker",()=>mockAppStudy("FlowTicker"));
jest.mock("../AlertsPanel",()=>mockAppStudy("AlertsPanel"));
jest.mock("../UOAPanel",()=>mockAppStudy("UOAPanel"));
jest.mock("../ToxicityGauge",()=>mockAppStudy("ToxicityGauge"));
jest.mock("../MorningBriefing",()=>({MorningBriefing:mockAppStudy("MorningBriefing")}));
jest.mock("../PositionSizing",()=>({PositionSizing:mockAppStudy("PositionSizing")}));
jest.mock("../TradeEntry",()=>({TradeEntry:mockAppStudy("TradeEntry")}));
jest.mock("../DashboardSummary",()=>({DashboardSummary:mockAppStudy("DashboardSummary")}));
jest.mock("../TradeAnalytics",()=>({TradeAnalytics:mockAppStudy("TradeAnalytics")}));

test("the original Gamma regime reading stays reachable in Market brief",async()=>{
 await act(async()=>render(<HeatseekerDashboard ticker="SPY" spot={500} data={{regime:{gex_regime:"positive"}}}/>));
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"briefing"}});
 const reading=screen.getByText(/Positive Gamma/);expect(reading).toBeVisible();
 expect(screen.getByText(/Positive-gamma backdrop\. Mean-reversion plays favored only with observed holding\./)).toBeVisible();
 expect(screen.queryByText(/Dealers/i)).toBeNull();
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"patterns"}});expect(reading).not.toBeVisible();
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"briefing"}});expect(screen.getByText(/Positive Gamma/)).toBe(reading);expect(reading).toBeVisible();
});

test("the actual Charm decay study keeps its supplied expiry reading when returning",async()=>{
 global.fetch=jest.fn().mockResolvedValue({ok:true,json:async()=>({grid:{strikes:[500],expiries:["2026-10-16","2026-10-23"],charm_grid:{"2026-10-16":{"500":123000000},"2026-10-23":{"500":456000000}}}})});
 await act(async()=>render(<HeatseekerDashboard ticker="SPY" spot={500}/>));
 await act(async()=>fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"exposure"}}));
 const reading=await screen.findByText("Charm Decay by Expiry");expect(reading).toBeVisible();expect(screen.getByTitle("Net charm 10-16")).toHaveTextContent("10-16 · $123.0M");
 expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/api/data/SPY?mode=day&expiries=6"),expect.anything());
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"patterns"}});expect(reading).not.toBeVisible();
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"exposure"}});expect(screen.getByText("Charm Decay by Expiry")).toBe(reading);expect(reading).toBeVisible();
});

test("the actual App retains all twenty-five original side studies in their chosen families",async()=>{
 const App=require("../../App").default;localStorage.clear();
 await act(async()=>render(<App/>));
 const families={
  levels:["DashboardSummary","ScenarioPanel","GreekReferencePanel"],
  patterns:["OpportunitiesPanel","MarketRegimePanel","PressureCloudPanel"],
  income:["PositionSizing","TradeEntry","LivePolicyPanel"],
  history:["MlDashboard","MultiTimeframeGEXPanel","TradeAnalytics"],
  moves:["ImpliedMovePanel","VolAnalyticsPanel","ImpliedPDFPanel"],
  structure:["RiskDashboardPanel","HedgeImpulsePanel","CharmIntegralPanel"],
  exposure:["UOAPanel","FlowTicker","VelocityGauge","ToxicityGauge"],
  briefing:["MorningBriefing","AlertsPanel","UsagePanel"],
 };
 expect(Object.values(families).flat()).toHaveLength(25);
 fireEvent.click(screen.getByRole("button",{name:"DashboardSummary First choice"}));
 for(const [family,names] of Object.entries(families)){
  await act(async()=>fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:family}}));
  for(const name of names)expect(screen.getByTestId(name==="VelocityGauge"?"velocity-gauge":"app-study-"+name)).toBeVisible();
  expect(document.querySelectorAll('.study-family:not([hidden])')).toHaveLength(1);
 }
 fireEvent.change(screen.getByRole("combobox",{name:"Study"}),{target:{value:"levels"}});
 expect(screen.getByRole("button",{name:"DashboardSummary Saved choice"})).toBeVisible();
});
