/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import NodeLifecyclePanel from "./NodeLifecyclePanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

function mock(data) {
  useHeatseeker.mockReturnValue({ data, loading: false, error: null, refresh: jest.fn() });
}

describe("NodeLifecyclePanel visit episodes", () => {
  test("shows visit episodes and the deduplicated sample count", () => {
    mock({
      nodes: [
        { strike: 500, net_gex: 2e9, taps: 1, visit_episodes: 1, visit_samples: 5, state: "tested" },
        { strike: 510, net_gex: -1.5e9, taps: 3, visit_episodes: 3, visit_samples: 3, state: "decaying" },
      ],
      history_samples: 12,
      duplicate_timestamps_dropped: 4,
    });
    render(<NodeLifecyclePanel ticker="SPY" />);
    // A sustained dwell is one visit: 5 samples are still 1 episode.
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === "$500")).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === "$510")).toBeInTheDocument();
    expect(screen.getByText("tested")).toBeInTheDocument();
    expect(screen.getByText("decaying")).toBeInTheDocument();
    // The episode ledger is disclosed, and repeats are not presented as taps.
    expect(screen.getByText(/12 distinct samples/i)).toBeInTheDocument();
    expect(screen.getByText(/4 repeated timestamps ignored/i)).toBeInTheDocument();
  });

  test("no probability-like tap percentage is shown", () => {
    mock({ nodes: [{ strike: 500, net_gex: 2e9, taps: 1, state: "tested" }] });
    render(<NodeLifecyclePanel ticker="SPY" />);
    expect(screen.queryByText(/tap%/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/80%/)).not.toBeInTheDocument();
  });

  test("unknown history stays unknown instead of 'fresh'", () => {
    mock({
      nodes: [
        { strike: 500, net_gex: 2e9, taps: null, state: "unknown", reason: "HISTORY_UNKNOWN" },
      ],
      history_status: "unknown",
      reason: "HISTORY_UNKNOWN",
      history_samples: 0,
    });
    render(<NodeLifecyclePanel ticker="SPY" />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
    expect(screen.queryByText("fresh")).not.toBeInTheDocument();
    expect(screen.getByText(/history unknown/i)).toBeInTheDocument();
  });

  test("a repeated timestamp is not a second visit", () => {
    mock({
      nodes: [{ strike: 500, net_gex: 2e9, taps: 1, visit_samples: 1, state: "tested" }],
      history_samples: 1,
      duplicate_timestamps_dropped: 2,
    });
    render(<NodeLifecyclePanel ticker="SPY" />);
    // Two dropped duplicate timestamps must not appear as two visits.
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.queryByText("3")).not.toBeInTheDocument();
  });
});
