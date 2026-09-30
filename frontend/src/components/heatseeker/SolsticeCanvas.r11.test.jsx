/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent, act, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import SkylitDashboard from "./SkylitDashboard";

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("./SkylitTickerBar", () => ({ __esModule: true, default: () => null, TICKER_SETS: { popular: ["SPY", "QQQ"] } }));
jest.mock("./StockDirectory", () => () => null);
jest.mock("./PriceNodeHistory", () => () => null);
jest.mock("./ExposureStrip", () => () => null);
jest.mock("../flowseeker/AlertEngineStrip", () => () => null);
jest.mock("./SkylitMetricsSidebar", () => () => null);
const E1 = "2031-01-17", E2 = "2031-01-24";
const fixture = () => ({ ticker: "SPY", spot: 100.25, asof: "2031-01-16T15:00:00Z", snapshotId: "r11-canvas",
  strikes: [{ strike: 101 }, { strike: 100 }, { strike: 99 }],
  grid: { expiries: [E1, E2], strikes: [101, 100, 99], grid: { [E1]: { 101: -20000, 100: 100000, 99: 0 }, [E2]: { 100: 20000 } },
    vex_grid: { [E1]: { 101: -300, 100: 400 } }, charm_grid: { [E1]: { 101: 50, 100: -80 } } },
  metrics: { walls: [{ wall_id: "w", low: 100, high: 101, mid: 100.5, members: [100, 101], gross: 140000, net: 100000 }],
    grids: { delta: { expiries: [E1, E2], strikes: [101, 100, 99], grid: { [E1]: { 101: -10000, 100: 50000 }, [E2]: { 100: 10000 } } },
      session_delta_volume: { expiries: [E1], strikes: [101, 100, 99], grid: { [E1]: { 100: 5000 } } } },
    surface_coverage: { raw: { status: "ok" }, delta: { status: "ok" }, session_delta_volume: { status: "partial" }, window: { status: "unavailable", reason: "NO_BASELINE" } } },
  quality: { state: "usable", setupEligible: false, reasonCodes: ["PRICE_HISTORY_MISSING"] } });
beforeEach(() => { axios.get.mockResolvedValue({ data: { snapshots: [], decisions: [] } }); });
const mount = async () => { await act(async () => render(<SkylitDashboard ticker="SPY" spot={100.25} data={fixture()} />)); };

test("profile layout sums the exact loaded scope, aligns selection, and does not fetch a new exposure", async () => {
  await mount();
  const calls = axios.get.mock.calls.length;
  fireEvent.change(screen.getByLabelText("Canvas layout"), { target: { value: "profile" } });
  const header = screen.getByTestId("skylit-profile-header");
  expect(header).toHaveTextContent("All loaded · 2 expiries");
  const row = screen.getAllByTestId("skylit-profile-cell").find(e => e.dataset.strike === "100");
  expect(row.querySelector(".trin-prof").title).toContain("Raw $120.0K");
  fireEvent.click(screen.getByRole("gridcell", { name: /^100 by 2031-01-17,/ }));
  expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("100000.0");
  expect(row.parentElement).toHaveClass("trin-row-selected");
  expect(axios.get.mock.calls.length).toBe(calls);
});

test("calendar shows only loaded dates and keeps basis switching on the same snapshot", async () => {
  await mount();
  const calls = axios.get.mock.calls.length;
  fireEvent.change(screen.getByLabelText("Canvas layout"), { target: { value: "calendar" } });
  expect(screen.getByTestId("skylit-loaded-scope")).toHaveTextContent(`${E1}, ${E2}`);
  fireEvent.change(screen.getByTestId("skylit-basis-select"), { target: { value: "session_delta_volume" } });
  expect(screen.getByRole("gridcell", { name: /^100 by 2031-01-17,/ })).toHaveTextContent("$5.0K");
  expect(screen.getByTestId("skylit-grid-basis")).toHaveTextContent("VOLUME");
  expect(axios.get.mock.calls.length).toBe(calls);
});

test("multi-map uses one packet with disclosed independent metric scales and one active selection", async () => {
  await mount();
  const calls = axios.get.mock.calls.length;
  fireEvent.change(screen.getByLabelText("Canvas layout"), { target: { value: "multi" } });
  expect(screen.getAllByRole("grid")).toHaveLength(4);
  const vex = screen.getByTestId("skylit-pane-vex");
  fireEvent.click(within(vex).getByRole("gridcell", { name: /^100 by 2031-01-17,/ }));
  expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("400.0");
  expect(screen.getByTestId("skylit-selected-cell").title).toContain("VEX");
  expect(axios.get.mock.calls.length).toBe(calls);
});

test("paused-follow selection and research scope stay on the displayed rows through spot polling", async () => {
  const data = fixture();
  data.grid.strikes = Array.from({ length: 100 }, (_, i) => i + 50);
  data.strikes = data.grid.strikes.map(strike => ({ strike }));
  data.grid.grid[E1] = Object.fromEntries(data.grid.strikes.map(s => [s, 1000]));
  let mounted;
  await act(async () => { mounted = render(<SkylitDashboard ticker="SPY" spot={100.25} data={data} />); });
  fireEvent.scroll(document.querySelector(".skylit-heatmap-container"));
  fireEvent.click(screen.getByRole("gridcell", { name: /^100 by 2031-01-17,/ }));
  await act(async () => { mounted.rerender(<SkylitDashboard ticker="SPY" spot={149} data={data} />); });
  expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("1000.0");
  expect(screen.getByRole("gridcell", { name: /^100 by 2031-01-17,/ })).toBeInTheDocument();
});


test("manual scrolling pauses follow spot; resume is explicit", async () => {
  await mount();
  fireEvent.scroll(document.querySelector(".skylit-heatmap-container"));
  expect(screen.getByTestId("skylit-follow-spot-toggle")).toHaveTextContent("Resume spot");
  fireEvent.click(screen.getByTestId("skylit-follow-spot-toggle"));
  expect(screen.getByTestId("skylit-follow-spot-toggle")).toHaveTextContent("Follow spot");
});
