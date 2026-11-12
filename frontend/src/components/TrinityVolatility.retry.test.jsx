/** @jest-environment jsdom */
import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import TrinityVolatility from "./TrinityVolatility";

jest.mock("../config/api", () => ({ API: "/api", BACKEND_URL: "", BACKEND_BASE: "" }));
jest.mock("axios", () => ({ get: jest.fn() }));

const chain = {
  ticker: "QQQ", spot: 100, expiries: ["2026-11-09"], data_source: "public_api",
  event_time: null, fetched_at: "2026-11-07T19:30:00Z",
  rows: [
    { expiry: "2026-11-09", type: "call", strike: 100, iv: 0.3, delta: 0.5, oi: 1 },
    { expiry: "2026-11-09", type: "put", strike: 100, iv: 0.31, delta: -0.5, oi: 1 },
  ],
};
function budgetFailure(seconds = 5, headers = {}) {
  return Object.assign(new Error("Request failed with status code 503"), {
    response: { status: 503, headers, data: {
      error: { degraded: true, error_type: "budget_exhausted", status: "degraded",
        reason: "budget_exhausted", budget_reason: "token_bucket",
        detail: "Public-path budget exhausted", retry_after: seconds,
        stale: true, asof: 1794079800, data: null, contracts: [], spot: null },
      status_code: 503, path: "/api/chain/SPY",
    } },
  });
}
async function show(ticker = "SPY") {
  let mounted;
  await act(async () => { mounted = render(<TrinityVolatility ticker={ticker} />); });
  return mounted;
}
beforeEach(() => {
  jest.useFakeTimers("modern");
  jest.setSystemTime(new Date("2026-11-07T19:30:00Z"));
  axios.get.mockReset();
  window.Plotly = { react: jest.fn().mockResolvedValue(undefined), purge: jest.fn() };
});
afterEach(() => { cleanup(); delete window.Plotly; jest.clearAllTimers(); jest.useRealTimers(); });

test("budget refusal blocks early clicks until its exact deadline and never retries automatically", async () => {
  axios.get.mockRejectedValueOnce(budgetFailure()).mockResolvedValue({ data: { ...chain, ticker: "SPY" } });
  await show();
  expect(screen.getByRole("alert")).toHaveTextContent("Market data is busy");
  expect(screen.getByRole("alert")).toHaveTextContent("Try again in 5s");
  const retry = screen.getByRole("button", { name: "Retry data" });
  expect(retry).toBeDisabled();
  fireEvent.click(retry);
  expect(axios.get).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(4999); });
  expect(retry).toBeDisabled();
  await act(async () => { jest.advanceTimersByTime(1); });
  expect(retry).toBeEnabled();
  expect(axios.get).toHaveBeenCalledTimes(1);
  await act(async () => { fireEvent.click(retry); });
  expect(screen.getByText(/SPY · spot 100\.00/)).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledTimes(2);
});

test.each([["delta seconds", "8"], ["HTTP date", "Sat, 07 Nov 2026 19:30:08 GMT"]])(
  "later Retry-After %s extends the body deadline without starting a provider request", async (_, header) => {
    axios.get.mockRejectedValue(budgetFailure(3, { "retry-after": header }));
    await show();
    const retry = screen.getByRole("button", { name: "Retry data" });
    expect(screen.getByRole("alert")).toHaveTextContent("Try again in 8s");
    await act(async () => { jest.advanceTimersByTime(3000); });
    expect(retry).toBeDisabled();
    await act(async () => { jest.advanceTimersByTime(5000); });
    expect(retry).toBeEnabled();
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

test("switching ticker clears the previous budget deadline and its countdown cannot replace the new chart", async () => {
  axios.get.mockRejectedValueOnce(budgetFailure()).mockResolvedValue({ data: chain });
  const mounted = await show();
  expect(screen.getByRole("button", { name: "Retry data" })).toBeDisabled();
  await act(async () => { mounted.rerender(<TrinityVolatility ticker="QQQ" />); });
  expect(screen.getByText(/QQQ · spot 100\.00/)).toBeInTheDocument();
  await act(async () => { jest.advanceTimersByTime(10000); });
  expect(screen.queryByText(/Market data is busy/)).not.toBeInTheDocument();
  expect(screen.getByText(/QQQ · spot 100\.00/)).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledTimes(2);
});

test("a superseded ticker's late budget refusal never gates the new ticker", async () => {
  let rejectOld;
  axios.get.mockImplementation(url => url.includes("/SPY")
    ? new Promise((_, reject) => { rejectOld = reject; })
    : Promise.resolve({ data: chain }));
  const mounted = await show();
  await act(async () => { mounted.rerender(<TrinityVolatility ticker="QQQ" />); });
  await act(async () => { rejectOld(budgetFailure()); });
  expect(screen.getByText(/QQQ · spot 100\.00/)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledTimes(2);
});

test("an untyped 503 keeps the original error and a manual retry without inventing a budget wait", async () => {
  const failure = budgetFailure();
  failure.response.data.error.reason = "provider_unavailable";
  axios.get.mockRejectedValue(failure);
  await show();
  expect(screen.getByRole("alert")).toHaveTextContent("Request failed with status code 503");
  expect(screen.queryByText(/Try again in/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry data" })).toBeEnabled();
});

test("invalid delay fields remain a manual busy state instead of a permanent or fabricated countdown", async () => {
  axios.get.mockRejectedValue(budgetFailure(false, { "Retry-After": "not a delay" }));
  await show();
  expect(screen.getByRole("alert")).toHaveTextContent("Market data is busy");
  expect(screen.queryByText(/Try again in/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry data" })).toBeEnabled();
});
