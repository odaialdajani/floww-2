/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import TrinityConfluenceMeter from "./TrinityConfluenceMeter";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("TrinityConfluenceMeter", () => {
  test("renders score gauge and aligned/divergent lists", () => {
    useHeatseeker.mockReturnValue({
      data: {
        score: 72,
        verdict: "Aligned bull",
        aligned_dimensions: ["GEX", "Vol"],
        divergences: ["OI"],
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<TrinityConfluenceMeter />);
    expect(screen.getByText("Meridian alignment")).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText("Aligned bull")).toBeInTheDocument();
    expect(screen.getByText(/GEX/)).toBeInTheDocument();
    expect(screen.getByText(/OI/)).toBeInTheDocument();
  });

  test("renders with empty lists when missing", () => {
    useHeatseeker.mockReturnValue({
      data: { score: 0, verdict: "Neutral", aligned_dimensions: [], divergences: [] },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<TrinityConfluenceMeter />);
    // v2 renders the ✓/✗ list headers ONLY when at least one list is
    // non-empty. With both empty the panel shows score + verdict instead —
    // assert that, plus the absence of the list section.
    expect(screen.getByText("Neutral")).toBeInTheDocument();
    expect(screen.queryByText(/Aligned/)).not.toBeInTheDocument();
  });
});
