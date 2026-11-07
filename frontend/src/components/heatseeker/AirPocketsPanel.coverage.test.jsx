/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import AirPocketsPanel from "./AirPocketsPanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

function mock(data) {
  useHeatseeker.mockReturnValue({ data, loading: false, error: null, refresh: jest.fn() });
}

describe("AirPocketsPanel ladder coverage", () => {
  test("a loaded ladder with missing exposure identifies the missing readings", () => {
    mock({air_pockets: [], coverage_status: "unknown", strikes_observed: 3,
      strikes_unknown_exposure: 1, expected_step: 1, n_omitted_strikes: 0});
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.getByText(/exposure unavailable at 1 observed strike/i)).toBeInTheDocument();
    expect(screen.queryByText(/strike ladder not loaded/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no air pockets detected/i)).not.toBeInTheDocument();
  });
  test("discloses the loaded ladder a pocket was measured over", () => {
    mock({
      air_pockets: [{ low: 99, high: 101, span_pct: 0.02, max_abs_gex_in_run: 1e9 }],
      basis: "gross_exposure",
      coverage_status: "ok",
      strikes_observed: 5,
      expected_step: 1,
      n_omitted_strikes: 1,
    });
    render(<AirPocketsPanel ticker="SPY" />);
    // The pocket itself is still rendered.
    expect(screen.getByText((_, el) => (el?.textContent || "").replace(/\s/g, "") === "$99–$101")).toBeInTheDocument();
    // The coverage of the same loaded observation is visible, not implied.
    const coverage = screen.getByTestId("hs-air-pockets-coverage");
    expect(coverage.textContent).toMatch(/5 strikes observed/i);
    expect(coverage.textContent).toMatch(/1 unobserved strike/i);
    expect(coverage.textContent).toMatch(/gross exposure/i);
    expect(coverage.textContent).toMatch(/expected spacing \$1\.00/i);
  });

  test("a complete ladder reports no unobserved strikes", () => {
    mock({
      air_pockets: [],
      basis: "gross_exposure",
      coverage_status: "ok",
      strikes_observed: 11,
      expected_step: 1,
      n_omitted_strikes: 0,
    });
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.getByText(/no air pockets/i)).toBeInTheDocument();
    expect(screen.getByText(/0 unobserved strikes/i)).toBeInTheDocument();
  });

  test("unknown coverage is not read as a measured empty result", () => {
    mock({
      air_pockets: [],
      basis: "gross_exposure",
      coverage_status: "unknown",
      strikes_observed: 0,
      expected_step: null,
      n_omitted_strikes: 0,
      reason: "NO_OBSERVED_STRIKES",
    });
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.queryByText(/no air pockets/i)).not.toBeInTheDocument();
    expect(screen.getByText(/coverage unknown/i)).toBeInTheDocument();
  });

  test("a degraded payload is not read as a pocket-free market", () => {
    useHeatseeker.mockReturnValue({
      data: null,
      loading: false,
      error: "network down",
      refresh: jest.fn(),
    });
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.getByText(/error/i)).toBeInTheDocument();
    expect(screen.queryByText(/no air pockets/i)).not.toBeInTheDocument();
  });
});
