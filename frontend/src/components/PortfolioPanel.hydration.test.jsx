/**
 * @jest-environment jsdom
 *
 * The Portfolio page used to keep its own position list: it never read the
 * stored book, a failed read looked like an empty book, and removal sent the
 * local row index to an endpoint that pops the server's stored array. These
 * checks pin the panel to the stored book: hydration, an explicit read state,
 * and a removal that resolves the stored row before it deletes.
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import PortfolioPanel from "./PortfolioPanel";

const mockGet = jest.fn();
const mockPost = jest.fn(() => Promise.resolve({ data: { status: "added", positions: 1 } }));
const mockDelete = jest.fn(() => Promise.resolve({ data: { status: "removed" } }));

jest.mock("axios", () => ({
  get: (...args) => mockGet(...args),
  post: (...args) => mockPost(...args),
  delete: (...args) => mockDelete(...args),
}));

const position = (overrides = {}) => ({
  symbol: "SPY",
  option_type: "call",
  strike: 600,
  expiry: "2026-12-18",
  quantity: 2,
  entry_price: 3.5,
  entry_iv: 0.15,
  underlying_price: 600,
  added_at: "2026-11-03T10:00:00Z",
  ...overrides,
});

const rawBook = (positions) => ({ name: "main", positions });

const pricedBook = (overrides = {}) => ({
  name: "main",
  positions: 1,
  positions_priced: 1,
  positions_skipped: 0,
  skipped: [],
  greeks: { delta: 1, gamma: 2, vega: 3, theta: 4 },
  pnl: {
    status: "ok",
    reason: null,
    total_pnl: 1200,
    pct_pnl: 12.5,
    pct_reason: null,
    total_entry_value: 9600,
    total_current_value: 10800,
    currency: "USD",
    unit: "USD",
    coverage: { stored: 1, priced: 1, skipped: 0 },
  },
  valuation_basis: "local_bs_model_at_spot_iv",
  spot: 600,
  iv: 0.15,
  ...overrides,
});

const isStoredRead = (config) => !config?.params?.spot;

const routeReads = (book, priced = pricedBook()) => {
  mockGet.mockImplementation(async (url, config) =>
    isStoredRead(config) ? { data: book } : { data: priced });
};

const deferred = () => {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
};

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockClear();
  mockDelete.mockClear();
});

test("reads the stored book without a spot and shows the stored positions", async () => {
  routeReads(rawBook([position()]));
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(screen.getByText("2026-12-18")).toBeInTheDocument());
  expect(screen.getByText("SPY")).toBeInTheDocument();
  expect(mockGet.mock.calls.some(([url, config]) =>
    String(url).includes("/portfolio/main") && isStoredRead(config))).toBe(true);
  expect(screen.getByTestId("portfolio-read-state")).toHaveTextContent(/read #1/);
});

test("a failed read is not shown as an empty book", async () => {
  mockGet.mockRejectedValue(Object.assign(new Error("network down"), { response: { status: 503 } }));
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(screen.getByTestId("portfolio-read-state")).toHaveTextContent(/failed/i));
  expect(screen.queryByText(/No positions yet/i)).toBeNull();
  expect(screen.getByText(/Open positions are unknown/i)).toBeInTheDocument();
});

test("a missing stored portfolio is distinct from an empty book", async () => {
  mockGet.mockRejectedValue(Object.assign(new Error("not found"), { response: { status: 404 } }));
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(screen.getByTestId("portfolio-read-state")).toHaveTextContent(/no stored portfolio/i));
  expect(screen.getByTestId("portfolio-read-state")).not.toHaveTextContent(/failed/i);
});

test("an empty stored book still reads as empty", async () => {
  routeReads(rawBook([]));
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(screen.getByText(/No positions yet/i)).toBeInTheDocument());
  expect(screen.getByTestId("portfolio-read-state")).toHaveTextContent(/read #1/);
});

test("removal resolves the stored row instead of sending the local row index", async () => {
  let storedRead = 0;
  mockGet.mockImplementation(async (url, config) => {
    if (isStoredRead(config)) {
      storedRead += 1;
      return {
        data: storedRead === 1
          ? rawBook([position({ added_at: "2026-11-03T10:00:00Z" }), position({ added_at: "2026-11-03T11:00:00Z", strike: 610 })])
          : rawBook([position({ added_at: "2026-11-03T11:00:00Z", strike: 610 }), position({ added_at: "2026-11-03T10:00:00Z" })]),
      };
    }
    return { data: pricedBook() };
  });
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(screen.getAllByRole("button", { name: /Remove position SPY call 600/i })).toHaveLength(1));
  fireEvent.click(screen.getByRole("button", { name: /Remove position SPY call 600/i }));
  await waitFor(() => expect(mockDelete).toHaveBeenCalled());
  expect(String(mockDelete.mock.calls[0][0])).toMatch(/\/portfolio\/main\/position\/1$/);
});

test("an ambiguous stored row is not removed", async () => {
  routeReads(rawBook([position({ added_at: "2026-11-03T10:00:00Z" }), position({ added_at: "2026-11-03T10:00:00Z" })]));
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(screen.getAllByRole("button", { name: /Remove position SPY call 600/i })).toHaveLength(2));
  fireEvent.click(screen.getAllByRole("button", { name: /Remove position SPY call 600/i })[0]);
  await waitFor(() => expect(screen.getByTestId("portfolio-action-status")).toHaveTextContent(/stable position id/i));
  expect(mockDelete).not.toHaveBeenCalled();
});

test("a late read cannot overwrite a newer read", async () => {
  const books = [rawBook([position({ strike: 111 })]), rawBook([position({ strike: 222 })])];
  const pending = [deferred(), deferred()];
  let storedRead = 0;
  mockGet.mockImplementation(async (url, config) => {
    if (isStoredRead(config)) {
      const index = storedRead;
      storedRead += 1;
      return pending[index].promise.then(() => ({ data: books[index] }));
    }
    return { data: pricedBook() };
  });
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(storedRead).toBe(1));
  fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
  await waitFor(() => expect(storedRead).toBe(2));
  pending[1].resolve();
  await waitFor(() => expect(screen.getByText("222")).toBeInTheDocument());
  pending[0].resolve();
  await waitFor(() => expect(screen.queryByText("111")).toBeNull());
  expect(screen.getByText("222")).toBeInTheDocument();
});

test("a failed priced read keeps the last priced values and says so", async () => {
  let pricedRead = 0;
  mockGet.mockImplementation(async (url, config) => {
    if (isStoredRead(config)) return { data: rawBook([position()]) };
    pricedRead += 1;
    if (pricedRead === 1) return { data: pricedBook() };
    throw Object.assign(new Error("price service down"), { response: { status: 503 } });
  });
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(document.body.textContent).toContain("1,200"));
  fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
  await waitFor(() => expect(screen.getByTestId("portfolio-read-state")).toHaveTextContent(/priced read failed/i));
  expect(document.body.textContent).toContain("1,200");
  expect(screen.getByTestId("portfolio-read-state")).toHaveTextContent(/read #1/);
});

test("the money lines disclose one spot for the whole stored book", async () => {
  routeReads(rawBook([position({ symbol: "QQQ" })]));
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  await waitFor(() => expect(screen.getByTestId("portfolio-valuation-note")).toBeInTheDocument());
  expect(screen.getByTestId("portfolio-valuation-note")).toHaveTextContent(/one spot/i);
  expect(screen.getByTestId("portfolio-valuation-note")).toHaveTextContent(/QQQ/);
});
