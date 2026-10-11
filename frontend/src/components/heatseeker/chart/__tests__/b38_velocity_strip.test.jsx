import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import PriceNodeHistory from "../../PriceNodeHistory";

jest.mock("axios", () => ({ get: jest.fn() }));

const frames = ["14:00", "14:01"].map(t => ({ time: `2026-09-10T${t}:00+00:00`,
  open: 100, high: 102, low: 99, close: 101, nodes: [] }));
const velocityOk = { ticker: "SPY", day: "2026-09-10", status: "ok",
  velocity_dt_seconds: 3600,
  velocities: [
    { strike: 500, before: 1e6, after: 2e6, delta: 1e6, velocity: 277.78, growth: 1.0, status: "retained" },
    { strike: 510, before: 2e6, after: 1e6, delta: -1e6, velocity: -277.78, growth: -0.5, status: "retained" },
  ]};

function mockBoth(attrPayload) {
  axios.get.mockImplementation(url => {
    if (String(url).includes("/attribute/")) return Promise.resolve({ data: attrPayload });
    return Promise.resolve({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
  });
}

beforeEach(() => { window.localStorage.clear(); });
afterEach(() => jest.restoreAllMocks());

test("chart page shows the fastest-moving nodes with their measured window", async () => {
  mockBoth(velocityOk);
  render(<PriceNodeHistory ticker="SPY" open />);
  const strip = await screen.findByTestId("velocity-strip");
  expect(strip).toHaveTextContent("500");
  expect(strip).toHaveTextContent("510");
  expect(strip).toHaveTextContent(/3600|60 min|1 h/);
});

test("single-snapshot history renders an honest unavailable note", async () => {
  mockBoth({ ticker: "SPY", status: "history_unavailable", reason: "need 2+ recorded snapshots for comparison" });
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  expect(await screen.findByTestId("velocity-unavailable")).toBeInTheDocument();
  expect(screen.queryByTestId("velocity-strip")).not.toBeInTheDocument();
});

test("a failed velocity read never breaks the chart", async () => {
  axios.get.mockImplementation(url => {
    if (String(url).includes("/attribute/")) return Promise.reject(new Error("down"));
    return Promise.resolve({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
  });
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  expect(await screen.findByTestId("velocity-unavailable")).toBeInTheDocument();
});

test("strip caps at five rows", async () => {
  const many = { ...velocityOk, velocities: Array.from({ length: 8 }, (_, i) => (
    { strike: 500 + i, before: 1e6, after: 2e6, delta: 1e6, velocity: 100 + i, growth: 1, status: "retained" })) };
  mockBoth(many);
  render(<PriceNodeHistory ticker="SPY" open />);
  const strip = await screen.findByTestId("velocity-strip");
  expect(strip.querySelectorAll('[data-testid="velocity-row"]')).toHaveLength(5);
});
