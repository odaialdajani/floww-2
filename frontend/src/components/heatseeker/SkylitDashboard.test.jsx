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
