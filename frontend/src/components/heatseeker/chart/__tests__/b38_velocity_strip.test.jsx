import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import PriceNodeHistory from "../../PriceNodeHistory";

jest.mock("axios", () => ({ get: jest.fn() }));

const frames = ["14:00", "14:01"].map(t => ({ time: `2026-09-10T${t}:00+00:00`,
  open: 100, high: 102, low: 99, close: 101, nodes: [] }));
const scope = "SPY:day|expiries=2026-09-10|gex.v2|OI";
const velocityOk = { ticker: "SPY", day: "2026-09-10", status: "ok",
  query_key: scope,
  from: { id: "before", query_key: scope, asof: "2026-09-10T12:59:00Z", received_at: "2026-09-10T12:59:00Z" },
  to: { id: "after", query_key: scope, asof: "2026-09-10T13:59:00Z", received_at: "2026-09-10T13:59:00Z" },
  velocity_dt_seconds: 3600,
  velocities: [
    { strike: 500, before: 1e6, after: 2e6, delta: 1e6, velocity: 277.78, growth: 1.0, status: "retained" },
    { strike: 510, before: 2e6, after: 1e6, delta: -1e6, velocity: -277.78, growth: -0.5, status: "retained" },
  ]};

function mockBoth(attrPayload) {
  axios.get.mockImplementation(url => {
    if (String(url).includes("/attribute/")) return Promise.resolve({ data: attrPayload });
    return Promise.resolve({ data: { ticker: "SPY", query_key: scope, frames, candles_with_recorded_nodes: 0 } });
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
  await waitFor(() => expect(screen.getByTestId("velocity-unavailable")).toHaveTextContent("need 2+ comparable"));
  expect(screen.queryByTestId("velocity-strip")).not.toBeInTheDocument();
});

test("a failed velocity read never breaks the chart", async () => {
  axios.get.mockImplementation(url => {
    if (String(url).includes("/attribute/")) return Promise.reject(new Error("down"));
    return Promise.resolve({ data: { ticker: "SPY", query_key: scope, frames, candles_with_recorded_nodes: 0 } });
  });
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByTestId("velocity-unavailable")).toHaveTextContent("no verified comparison"));
});

test("strip caps at five rows", async () => {
  const many = { ...velocityOk, velocities: Array.from({ length: 8 }, (_, i) => (
    { strike: 500 + i, before: 1e6, after: 2e6, delta: 1e6, velocity: 100 + i, growth: 1, status: "retained" })) };
  mockBoth(many);
  render(<PriceNodeHistory ticker="SPY" open />);
  const strip = await screen.findByTestId("velocity-strip");
  expect(strip.querySelectorAll('[data-testid="velocity-row"]')).toHaveLength(5);
});

// Numeric readings must come from this view and be available at its candle.
test.each([
  ["wrong ticker", { ...velocityOk, ticker: "QQQ" }],
  ["different expiry scope", { ...velocityOk, to: { ...velocityOk.to, query_key: "other" } }],
  ["future observation", { ...velocityOk, to: { ...velocityOk.to, asof: "2026-09-10T15:00:00Z" } }],
  ["future receipt", { ...velocityOk, to: { ...velocityOk.to, received_at: "2026-09-10T15:00:00Z" } }],
  ["unknown receipt", { ...velocityOk, from: { ...velocityOk.from, received_at: null } }],
])("%s cannot be shown as chart velocity", async (_name, comparison) => {
  mockBoth(comparison);
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("velocity-unavailable")).toHaveTextContent("no verified comparison"));
  expect(screen.queryByTestId("velocity-strip")).not.toBeInTheDocument();
});

test("comparison uses the loaded saved scope and the selected replay time", async () => {
  mockBoth(velocityOk);
  render(<PriceNodeHistory ticker="SPY" open forcedScope="map-request-echo" />);
  await screen.findByTestId("velocity-strip");
  const reads = () => axios.get.mock.calls.filter(([url]) => String(url).includes("/attribute/"));
  expect(reads().at(-1)[1].params).toEqual({ query_key: scope, as_of: "2026-09-10T14:01:00+00:00" });
  fireEvent.click(screen.getByRole("button", { name: "Chart tools" }));
  fireEvent.change(screen.getByLabelText("Replay position"), { target: { value: "0" } });
  expect(screen.queryByTestId("velocity-strip")).not.toBeInTheDocument();
  await waitFor(() => expect(reads().at(-1)[1].params.as_of).toBe("2026-09-10T14:00:00+00:00"));
  await screen.findByTestId("velocity-strip");
  fireEvent.click(screen.getByRole("button", { name: "Play replay" }));
  expect(screen.queryByTestId("velocity-strip")).not.toBeInTheDocument();
});

test("a late comparison from the previous map scope cannot replace the current reading", async () => {
  let resolveOld;
  const nextScope = "SPY:day|expiries=2026-09-11|gex.v2|OI";
  axios.get.mockImplementation((url, config) => {
    if (String(url).includes("/attribute/")) {
      if (config.params.query_key === scope) return new Promise(resolve => { resolveOld = resolve; });
      return Promise.resolve({ data: { ...velocityOk, query_key: nextScope,
        from: { ...velocityOk.from, query_key: nextScope }, to: { ...velocityOk.to, query_key: nextScope },
        velocities: [{ strike: 600, velocity: 100, growth: 1, status: "retained" }] } });
    }
    return Promise.resolve({ data: { ticker: "SPY", query_key: config.params.query_key,
      frames, candles_with_recorded_nodes: 0 } });
  });
  const { rerender } = render(<PriceNodeHistory ticker="SPY" open forcedScope={scope} />);
  await waitFor(() => expect(resolveOld).toEqual(expect.any(Function)));
  rerender(<PriceNodeHistory ticker="SPY" open forcedScope={nextScope} />);
  expect(await screen.findByTestId("velocity-strip")).toHaveTextContent("600");
  await act(async () => { resolveOld({ data: velocityOk }); });
  expect(screen.getByTestId("velocity-strip")).toHaveTextContent("600");
  expect(screen.getByTestId("velocity-strip")).not.toHaveTextContent("500");
});


test.each([
  ["OBSERVATION_STALE", "older than 15 minutes"],
  ["SCOPE_UNVERIFIED", "scope or source details"],
  ["NO_MATCHING_OBSERVATIONS", "no recorded observations match"],
  ["CUTOFF_INVALID", "candle time could not be verified"],
])("%s keeps its own unavailable explanation", async (reason_code, message) => {
  mockBoth({ ticker: "SPY", status: "history_unavailable", reason_code });
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("velocity-unavailable")).toHaveTextContent(message));
  expect(screen.queryByTestId("velocity-strip")).not.toBeInTheDocument();
});
