import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import { DashboardSummary } from "./DashboardSummary";

jest.mock("axios", () => ({
  get: jest.fn(() => Promise.reject(new Error("test"))),
  post: jest.fn(() => Promise.reject(new Error("test"))),
}));

describe("DashboardSummary", () => {
  beforeEach(() => { global.fetch = jest.fn(); });
  test("renders without crashing on null/undefined props", () => {
    const { container } = render(<DashboardSummary ticker="SPY" spot={null} />);
    expect(container).toBeTruthy();
  });

  test("missing exposure stays unavailable and an unknown regime has no negative color", async () => {
    global.fetch.mockResolvedValue({ok:true,json:async()=>({ticker:"SPY",nodes:{}})});
    render(<DashboardSummary ticker="SPY" />);
    const value = await screen.findByTitle("Net GEX unavailable");
    expect(value).toHaveTextContent("—");
    expect(screen.getByText("UNKNOWN")).toHaveClass("text-slate-400");
    expect(value).not.toHaveClass("text-emerald-400");
  });

  test("measured zero remains a measured value", async () => {
    global.fetch.mockResolvedValue({ok:true,json:async()=>({ticker:"SPY",nodes:{total_gex:0,regime:"positive"}})});
    render(<DashboardSummary ticker="SPY" />);
    const label = await screen.findByText("Net GEX");
    expect(within(label.parentElement).getByText("+0")).toBeInTheDocument();
    expect(screen.queryByTitle("Net GEX unavailable")).not.toBeInTheDocument();
  });

  test("a failed new-symbol read cannot display the old symbol's summary", async () => {
    global.fetch.mockResolvedValueOnce({ok:true,json:async()=>({ticker:"SPY",nodes:{total_gex:10}})})
      .mockResolvedValueOnce({ok:false,status:503});
    const view = render(<DashboardSummary ticker="SPY" />);
    await screen.findByText("Net GEX");
    view.rerender(<DashboardSummary ticker="QQQ" />);
    await waitFor(()=>expect(global.fetch).toHaveBeenCalledTimes(2));
    await screen.findByText("No dashboard data available");
    expect(screen.queryByText("Net GEX")).not.toBeInTheDocument();
  });
});
