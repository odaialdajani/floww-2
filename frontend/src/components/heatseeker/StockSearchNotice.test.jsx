import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import useTickerDirectory from "./useTickerDirectory";
import StockSearchNotice from "./StockSearchNotice";
import { buildTickerUniverse } from "./tickerUniverse";

jest.mock("axios");

function StockSearch() {
  const { tickers, status, retry } = useTickerDirectory("/api");
  return <><StockSearchNotice status={status} onRetry={retry} />
    <span data-testid="names">{buildTickerUniverse(tickers).join(",")}</span></>;
}

afterEach(() => jest.resetAllMocks());

test("failed later pages show partial search and retry recovers the full list", async () => {
  axios.get.mockImplementation(async url => {
    if (url === "/api/tickers") return { data: { default: ["SPY"] } };
    if (url.endsWith("page=1")) return { data: { tickers: ["AAA"], total: 2, has_more: true, complete_provider_catalog: true } };
    throw new Error("offline");
  });
  render(<StockSearch />);
  expect(screen.getByText("Loading full stock search...")).toBeInTheDocument();
  expect(await screen.findByText(/Stock search is incomplete/)).toBeInTheDocument();
  expect(screen.getByTestId("names")).toHaveTextContent("SPY,AAA");
  axios.get.mockImplementation(async url => url === "/api/tickers"
    ? { data: { default: ["SPY"] } }
    : { data: { tickers: ["AAA", "ZZZ"], total: 2, has_more: false, complete_provider_catalog: true } });
  fireEvent.click(screen.getByRole("button", { name: "Retry stock list" }));
  await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  expect(screen.getByTestId("names")).toHaveTextContent("SPY,AAA,ZZZ");
});

test("a complete but stale provider list retains its warning", async () => {
  axios.get.mockImplementation(async url => url === "/api/tickers" ? { data: {} }
    : { data: { tickers: ["AAA"], total: 1, has_more: false, complete_provider_catalog: true, stale: true } });
  render(<StockSearch />);
  expect(await screen.findByText(/Stock search uses a saved provider list/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry stock list" })).toBeInTheDocument();
});

test("failed full list retains the usable featured list with an incomplete notice", async () => {
  axios.get.mockImplementation(async url => {
    if (url === "/api/tickers") return { data: { default: ["SPY", "QQQ"] } };
    throw new Error("offline");
  });
  render(<StockSearch />);
  expect(await screen.findByText(/Stock search is incomplete/)).toBeInTheDocument();
  expect(screen.getByTestId("names")).toHaveTextContent("SPY,QQQ");
});

test("unmount cancels requests before a delayed featured response starts paging", async () => {
  let resolve;
  axios.get.mockImplementation(() => new Promise(done => { resolve = done; }));
  const { unmount } = render(<StockSearch />);
  const signal = axios.get.mock.calls[0][1].signal;
  unmount();
  expect(signal.aborted).toBe(true);
  resolve({ data: { default: ["SPY"] } });
  await Promise.resolve();
  expect(axios.get).toHaveBeenCalledTimes(1);
});
