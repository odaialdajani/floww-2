/**
 * @jest-environment jsdom
 */
import React from "react";
import axios from "axios";
import { render, screen, act, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

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
      levels: ["hs-flip-zones", "hs-node-lifecycle", "hs-air-pockets"],
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
