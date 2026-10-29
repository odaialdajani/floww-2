import { openStockPanel } from '../../testUtils/openStockPanel';
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import PriceNodeHistory from "./PriceNodeHistory";

// B05 production mount (C2-PRODUCER-CONTRACTS-20261024.json): the pane's
// price-history read goes through the shared useChartData hook — one private
// session per pane, superseded identities aborted, manual reload honored,
// budget/outage badges surfaced honestly through the quality channel.
jest.mock("axios", () => ({ get: jest.fn() }));

const mkFrames = (n, base = 100) => Array.from({ length: n }, (_, i) => ({
  time: `2026-10-20T14:${String(i).padStart(2, "0")}:00Z`,
  open: base, high: base + 2, low: base - 1, close: base + 1, nodes: [],
}));

afterEach(() => { axios.get.mockReset(); });

test("per-pane sessions: a superseded pane read never lands; the other pane is never invalidated", async () => {
  const deferred = [];
  axios.get.mockImplementation((url) => new Promise(resolve => { deferred.push({ url, resolve }); }));
  const { getAllByTestId, getAllByRole } = render(<>
    <PriceNodeHistory ticker="SPY" primary />
    <PriceNodeHistory ticker="QQQ" primary />
  </>);
  await act(async () => {});
  expect(deferred.filter(d => d.url.includes("/price-history/SPY"))).toHaveLength(1);
  expect(deferred.filter(d => d.url.includes("/price-history/QQQ"))).toHaveLength(1);
  // Pane A changes interval while both reads are in flight: A's first read is superseded.
  fireEvent.change(getAllByRole("combobox", { name: "Candle interval" })[0], { target: { value: "15" } });
  await act(async () => {});
  const spy = deferred.filter(d => d.url.includes("/price-history/SPY"));
  expect(spy).toHaveLength(2);
  expect(spy[1].url).toContain("SPY");
  // The stale superseded response resolves late — it must never land on pane A.
  await act(async () => { spy[0].resolve({ data: { ticker: "SPY", frames: mkFrames(3), candles_with_recorded_nodes: 0 } }); });
  await act(async () => {});
  expect(getAllByTestId("recorded-price-chart")[0]).toHaveAttribute("data-candles", "0");
  // Pane B's read is untouched by pane A's refresh and lands normally.
  await act(async () => { deferred.filter(d => d.url.includes("/price-history/QQQ"))[0].resolve({ data: { ticker: "QQQ", frames: mkFrames(2), candles_with_recorded_nodes: 0 } }); });
  await waitFor(() => expect(getAllByTestId("recorded-price-chart")[1]).toHaveAttribute("data-candles", "2"));
  // Pane A's active (15-minute) generation lands last.
  await act(async () => { spy[1].resolve({ data: { ticker: "SPY", frames: mkFrames(1), candles_with_recorded_nodes: 0 } }); });
  await waitFor(() => expect(getAllByTestId("recorded-price-chart")[0]).toHaveAttribute("data-candles", "1"));
});

test("the Reload history control performs a fresh read through the mounted hook", async () => {
  axios.get.mockResolvedValueOnce({ data: { ticker: "SPY", frames: mkFrames(3), candles_with_recorded_nodes: 0 } })
    .mockResolvedValueOnce({ data: { ticker: "SPY", frames: mkFrames(1), candles_with_recorded_nodes: 0 } });
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles", "3"));
  openStockPanel('data');
  fireEvent.click(screen.getByRole("button", { name: "Reload history" }));
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles", "1"));
  const calls = axios.get.mock.calls.filter(([url]) => url.includes("/price-history/"));
  expect(calls).toHaveLength(2);
});

test("a live read surfaces the live badge on the pane and through the quality channel", async () => {
  const onQuality = jest.fn();
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames: mkFrames(2), candles_with_recorded_nodes: 0 } });
  render(<PriceNodeHistory ticker="SPY" primary onQuality={onQuality} />);
  await waitFor(() => expect(screen.getByTestId("price-node-history")).toHaveAttribute("data-read-badge", "live"));
  await waitFor(() => expect(onQuality).toHaveBeenCalledWith(expect.objectContaining({ status: "ready", badge: "live" })));
});

test("a budget refusal surfaces the budget-exhausted badge and the manual retry gate", async () => {
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames: [], price_status: "unavailable", price_failure: { reason: "token_bucket", retry_after_seconds: 120 } } });
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(screen.getByTestId("price-node-history")).toHaveAttribute("data-read-badge", "budget-exhausted"));
  await waitFor(() => expect(screen.getByRole("button", { name: /Retry price history/ })).toHaveTextContent("Retry in 120s"));
  expect(screen.getByText(/request allowance is temporarily used up/)).toBeInTheDocument();
});

test("a provider refusal surfaces the outage badge with the honest no-substitution message", async () => {
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames: [], price_status: "unavailable", price_failure: { reason: "provider_unavailable" } } });
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(screen.getByTestId("price-node-history")).toHaveAttribute("data-read-badge", "outage"));
  await screen.findByText(/could not be read from Public\. No old prices were substituted/);
});

test("a rejected read surfaces the outage badge, never live, and never invents data", async () => {
  axios.get.mockRejectedValue(new Error("network down"));
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(screen.getByTestId("price-node-history")).toHaveAttribute("data-read-badge", "outage"));
  expect(screen.getByRole("alert")).toHaveTextContent("History could not be loaded.");
  expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles", "0");
});

test("an off-ticker payload is refused and never renders", async () => {
  axios.get.mockResolvedValue({ data: { ticker: "QQQ", frames: mkFrames(3), candles_with_recorded_nodes: 0 } });
  render(<PriceNodeHistory ticker="SPY" primary />);
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("History could not be loaded."));
  expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles", "0");
});
