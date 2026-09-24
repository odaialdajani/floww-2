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
// Ticker bar + control bar echoes the tickers prop so the universe
// pass-through is pinnable (2026-09-12: the Solstice bar/control silently
// fell back to 23/10 featured sets because nothing passed tickers down).
jest.mock("./SkylitTickerBar",       () => (props) => (
  <div data-testid="mock-ticker-bar" data-tickers={JSON.stringify(props.tickers ?? null)} />
));
jest.mock("./SkylitControlBar",      () => (props) => (
  <div data-testid="mock-control-bar" data-tickers={JSON.stringify(props.tickers ?? null)} />
));
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
      render(<SkylitDashboard ticker="SPY" />);
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
