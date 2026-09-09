/**
 * ExposureStrip — RED: component does not exist yet.
 *
 * Contract: given a ticker, fetches the persisted v3 feed
 * (/api/flowseeker/alerts/feed?ticker=X) and renders one badge per live
 * backend exposure rule. Unknown rules never render. Empty feed or fetch
 * failure renders nothing (fail-open, never blanks the dashboard).
 */
/** @jest-environment jsdom */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import ExposureStrip from "./ExposureStrip";

jest.mock("axios");

describe("ExposureStrip", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders badges for live exposure rules only", async () => {
    axios.get.mockResolvedValueOnce({
      data: {
        alerts: [
          { key: "exposure:toxic_flow:SPY::650", rule: "TOXIC_FLOW", under: "SPY" },
          { key: "exposure:gamma_flip_approach:SPY::650", rule: "GAMMA_FLIP", under: "SPY" },
          { key: "SCORE|SPY|650|2026-09-18", rule: "SCORE", under: "SPY" },
        ],
      },
    });
    render(<ExposureStrip ticker="SPY" />);
    await waitFor(() => expect(screen.getByText("TOXIC FLOW")).toBeInTheDocument());
    expect(screen.getByText("GAMMA FLIP")).toBeInTheDocument();
    expect(screen.queryByText("SCORE")).not.toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining("/flowseeker/alerts/feed?ticker=SPY"),
      expect.anything()
    );
  });

  test("dedupes repeated rule rows to one badge", async () => {
    axios.get.mockResolvedValueOnce({
      data: {
        alerts: [
          { key: "a", rule: "TOXIC_FLOW", under: "SPY" },
          { key: "b", rule: "TOXIC_FLOW", under: "SPY" },
        ],
      },
    });
    render(<ExposureStrip ticker="SPY" />);
    await waitFor(() => expect(screen.getAllByText("TOXIC FLOW")).toHaveLength(1));
  });

  test("empty feed renders nothing", async () => {
    axios.get.mockResolvedValueOnce({ data: { alerts: [] } });
    const { container } = render(<ExposureStrip ticker="SPY" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  test("fetch failure renders nothing (fail-open)", async () => {
    axios.get.mockRejectedValueOnce(new Error("network down"));
    const { container } = render(<ExposureStrip ticker="SPY" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  test("no ticker performs no fetch", async () => {
    render(<ExposureStrip ticker="" />);
    expect(axios.get).not.toHaveBeenCalled();
  });

  test("ticker change with failed fetch clears the previous ticker badges", async () => {
    axios.get
      .mockResolvedValueOnce({
        data: { alerts: [{ key: "a", rule: "TOXIC_FLOW", under: "SPY" }] },
      })
      .mockRejectedValueOnce(new Error("QQQ unavailable"));
    const { rerender } = render(<ExposureStrip ticker="SPY" />);
    await waitFor(() => expect(screen.getByText("TOXIC FLOW")).toBeInTheDocument());
    rerender(<ExposureStrip ticker="QQQ" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByText("TOXIC FLOW")).not.toBeInTheDocument()
    );
  });
});
