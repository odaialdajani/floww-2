/**
 * AlertEngineStrip — mounted alert-engine detector badge consumer.
 *
 * Closes XH-1: proves alertEngineBadges (alertEngineBadgeFor) is wired to
 * a real mounted consumer that fetches /api/alerts/{ticker}, maps each
 * Alert.type, and renders badges. GAMMA_FLIP is excluded (stays in
 * exposureBadges/ExposureStrip) — the same string is fired by two producers.
 *
 * Contract-shaped synthetic fixtures only — no live feed.
 */

/** @jest-environment jsdom */
import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import axios from "axios";
import AlertEngineStrip from "./AlertEngineStrip";

jest.mock("axios");

describe("AlertEngineStrip (XH-1 mounted consumer)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders alert-engine badges for live detector types", async () => {
    axios.get.mockResolvedValueOnce({
      data: {
        alerts: [
          { type: "GAMMA_SQUEEZE", priority: "HIGH", message: "snap" },
          { type: "VOLUME_SPIKE", priority: "MEDIUM", message: "snap" },
          { type: "PIN_RISK", priority: "LOW", message: "snap" },
        ],
      },
    });
    render(<AlertEngineStrip ticker="SPY" />);
    await waitFor(() => expect(screen.getByText("GAMMA SQUEEZE")).toBeInTheDocument());
    expect(screen.getByText("VOLUME SPIKE")).toBeInTheDocument();
    expect(screen.getByText("PIN RISK")).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining("/alerts/SPY"),
      expect.anything()
    );
  });

  test("excludes GAMMA_FLIP (handled by ExposureStrip / exposureBadges)", async () => {
    axios.get.mockResolvedValueOnce({
      data: { alerts: [{ type: "GAMMA_FLIP", priority: "HIGH", message: "snap" }] },
    });
    render(<AlertEngineStrip ticker="SPY" />);
    await waitFor(() => expect(screen.queryByText("GAMMA FLIP")).not.toBeInTheDocument());
    expect(screen.queryByText(/alert-engine/i)).not.toBeInTheDocument();
  });

  test("renders nothing for empty feed (fail-open)", async () => {
    axios.get.mockResolvedValueOnce({ data: { alerts: [] } });
    const { container } = render(<AlertEngineStrip ticker="SPY" />);
    await waitFor(() => expect(screen.queryByText(/GAMMA/i)).not.toBeInTheDocument());
    expect(container.firstChild).toBeNull();
  });

  test("renders nothing on fetch failure (fail-open, stale-free)", async () => {
    axios.get.mockRejectedValueOnce(new Error("network"));
    const { container } = render(<AlertEngineStrip ticker="SPY" />);
    await waitFor(() => expect(screen.queryByText(/GAMMA/i)).not.toBeInTheDocument());
    expect(container.firstChild).toBeNull();
  });

  test("ticker switch aborts in-flight fetch and renders new ticker badges", async () => {
    // Queue two sequential mocks: first call (SPY) returns nothing (aborted),
    // second call (QQQ) returns VANNA_REGIME_CHANGE.
    let spying = true;
    axios.get.mockImplementation((url) => {
      if (spying && url.includes("/alerts/SPY")) {
        // Return a promise we can abort-reject after the ticker switch
        return new Promise((_res, rej) => {
          // Give the test a moment to switch tickers, then reject as aborted
          setTimeout(() => rej(new DOMException("Aborted", "AbortError")), 50);
        });
      }
      if (url.includes("/alerts/QQQ")) {
        return Promise.resolve({
          data: { alerts: [{ type: "VANNA_REGIME_CHANGE", priority: "HIGH", message: "snap" }] },
        });
      }
      return Promise.reject(new Error("unexpected"));
    });

    const { rerender } = render(<AlertEngineStrip ticker="SPY" />);
    // Switch to QQQ before SPY resolves
    rerender(<AlertEngineStrip ticker="QQQ" />);
    await act(async () => { await new Promise((r) => setTimeout(r, 100)); });

    expect(screen.getByText("VANNA SHIFT")).toBeInTheDocument();
    expect(screen.queryByText("GAMMA SQUEEZE")).not.toBeInTheDocument();
    // Both calls should have been made: SPY first, then QQQ
    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining("/alerts/SPY"),
      expect.anything()
    );
    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining("/alerts/QQQ"),
      expect.anything()
    );
  });

  test("missing ticker renders nothing", () => {
    const { container } = render(<AlertEngineStrip ticker="" />);
    expect(container.firstChild).toBeNull();
    expect(axios.get).not.toHaveBeenCalled();
  });

  test("accessibility: each badge has aria-label from heuristic title", async () => {
    axios.get.mockResolvedValueOnce({
      data: { alerts: [{ type: "MOMENTUM_EXTREME", priority: "HIGH", message: "snap" }] },
    });
    render(<AlertEngineStrip ticker="SPY" />);
    await waitFor(() => expect(screen.getByText("MOMENTUM EXTREME")).toBeInTheDocument());
    const badge = screen.getByText("MOMENTUM EXTREME");
    expect(badge).toHaveAttribute("aria-label");
    expect(badge.getAttribute("aria-label").toLowerCase()).toContain("momentum");
  });
});
