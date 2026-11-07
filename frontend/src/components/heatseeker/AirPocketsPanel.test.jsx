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

describe("AirPocketsPanel", () => {
  test("renders header during loading", () => {
    useHeatseeker.mockReturnValue({ data: null, loading: true, error: null, refresh: jest.fn() });
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.getByText("Air Pockets")).toBeInTheDocument();
  });

  test("renders pocket rows with low/high range", () => {
    useHeatseeker.mockReturnValue({
      data: {
        air_pockets: [
          { low: 495, high: 502, span_pct: 1.41, max_abs_gex_in_run: 3e9 },
          { low: 510, high: 514, span_pct: 0.78, max_abs_gex_in_run: 1e9 },
        ],
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<AirPocketsPanel ticker="SPY" />);
    // v2 renders "$495 – $502" with each price prefixed by $.
    expect(screen.getByText((_, el) => (el?.textContent || "").replace(/\s/g, "") === "$495–$502")).toBeInTheDocument();
    expect(screen.getByText((_, el) => (el?.textContent || "").replace(/\s/g, "") === "$510–$514")).toBeInTheDocument();
    expect(screen.getByText(/pathways, not targets/i)).toBeInTheDocument();
  });

  test("shows empty message when no pockets", () => {
    // Measured-empty requires a known ladder: the panel distinguishes a
    // measured "no pockets" from an unknown coverage (see the coverage test).
    useHeatseeker.mockReturnValue({
      data: {
        air_pockets: [],
        basis: "gross_exposure",
        coverage_status: "ok",
        strikes_observed: 11,
        expected_step: 1,
        n_omitted_strikes: 0,
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.getByText(/no air pockets/i)).toBeInTheDocument();
  });
});
