/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import BeachBallIndicator from "./BeachBallIndicator";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

function mock(data) {
  useHeatseeker.mockReturnValue({ data, loading: false, error: null, refresh: jest.fn() });
}

describe("BeachBallIndicator distance contract", () => {
  test("shows explicit distance in points and percent", () => {
    mock({
      active: true,
      king_node: 500,
      spot_distance_points: 4.0,
      spot_distance_pct: 0.008,
      direction: "above",
    });
    render(<BeachBallIndicator ticker="SPY" />);
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    // Distance is distance — points and percent, both visible.
    expect(screen.getByText(/\$4\.00 pts/)).toBeInTheDocument();
    expect(screen.getByText(/0\.80%/)).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === "$500")).toBeInTheDocument();
  });

  test("no probability-like confidence label or bar", () => {
    mock({
      active: true,
      king_node: 500,
      spot_distance_points: -4.0,
      spot_distance_pct: 0.008,
      direction: "below",
    });
    render(<BeachBallIndicator ticker="SPY" />);
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
    // No leftover percentage bar that would read like a probability.
    const bars = document.querySelectorAll("div[style*='width']");
    expect(bars.length).toBe(0);
  });

  test("a retired confidence field cannot reintroduce a percentage", () => {
    // A stale caller/payload still carrying confidence must not be rendered
    // as a probability.
    mock({
      active: true,
      king_node: 500,
      spot_distance_points: 4.0,
      spot_distance_pct: 0.008,
      direction: "above",
      confidence: 0.75,
    });
    render(<BeachBallIndicator ticker="SPY" />);
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText("75%")).not.toBeInTheDocument();
    expect(screen.getByText(/\$4\.00 pts/)).toBeInTheDocument();
  });

  test("inactive reading shows no distance instead of a fabricated zero", () => {
    useHeatseeker.mockReturnValue({
      data: { active: false, king_node: null, spot_distance_points: null, spot_distance_pct: null, direction: "at" },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<BeachBallIndicator ticker="SPY" />);
    expect(screen.getByText(/○ idle/i)).toBeInTheDocument();
    // King node and distance are both unread, not zero.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });
});
