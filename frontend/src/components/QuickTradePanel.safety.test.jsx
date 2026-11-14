import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import QuickTradePanel from "./QuickTradePanel";

const baseSelection = {
  ticker: "SPY",
  strike: 500,
  spot: 500,
  expiry: "2026-12-18",
  oi_symbol: "SPY261218P00500000",
  call_bid: 1.1,
  call_ask: 1.3,
  put_bid: 1.2,
  put_ask: 1.5,
};

beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue({ json: () => Promise.resolve({}) });
  localStorage.clear();
});

function beginReview(selection, strategy = null) {
  const onSubmit = jest.fn();
  const controls = render(<QuickTradePanel selection={selection} onSubmit={onSubmit} onClose={jest.fn()} />);
  if (strategy) fireEvent.click(screen.getByRole("button", { name: new RegExp(strategy, "i") }));
  const review = screen.getByRole("button", { name: /review|enter valid limit|multi-leg orders unavailable|quantity must/i });
  return { onSubmit, review, ...controls };
}

test("fails closed when only an IV estimate exists", () => {
  const { onSubmit, review } = beginReview({ ...baseSelection, call_bid: 0, call_ask: 0, call_last: 0, iv: 0.2 });
  expect(review).toBeDisabled();
  expect(onSubmit).not.toHaveBeenCalled();
});

test("does not reinterpret an entered zero limit as a quoted order", () => {
  const { onSubmit, review } = beginReview(baseSelection);
  fireEvent.change(screen.getAllByRole("spinbutton")[1], { target: { value: "0" } });
  expect(review).toBeDisabled();
  expect(onSubmit).not.toHaveBeenCalled();
});

test("requires an in-range quantity and closes review when strategy changes", () => {
  const { review } = beginReview(baseSelection);
  fireEvent.click(review);
  expect(screen.getByRole("button", { name: /confirm order/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /straddle/i }));
  expect(screen.queryByRole("button", { name: /confirm order/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /multi-leg orders unavailable/i })).toBeDisabled();
});

test("blocks quantities above the paper ticket limit", () => {
  const { review } = beginReview(baseSelection);
  fireEvent.change(screen.getAllByRole("spinbutton")[0], { target: { value: "101" } });
  expect(review).toBeDisabled();
});

test("edits to quantity after review close the reviewed snapshot", () => {
  const { review } = beginReview(baseSelection);
  fireEvent.click(review);
  expect(screen.getByRole("button", { name: /confirm order/i })).toBeInTheDocument();
  fireEvent.change(screen.getAllByRole("spinbutton")[0], { target: { value: "101" } });
  expect(screen.queryByRole("button", { name: /confirm order/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /quantity must be 1–100/i })).toBeDisabled();
});

test("contract identity changes close confirmation even when strike is unchanged", () => {
  const { review, rerender } = beginReview(baseSelection);
  fireEvent.click(review);
  expect(screen.getByRole("button", { name: /confirm order/i })).toBeInTheDocument();
  rerender(<QuickTradePanel
    selection={{ ...baseSelection, ticker: "QQQ", oi_symbol: "QQQ261218P00500000" }}
    onSubmit={jest.fn()}
    onClose={jest.fn()}
  />);
  expect(screen.queryByRole("button", { name: /confirm order/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /review/i })).toBeEnabled();
});

test.each(["Straddle", "Iron Condor"])("does not offer single-contract review for %s", (strategy) => {
  const { onSubmit, review } = beginReview(baseSelection, strategy);
  expect(review).toBeDisabled();
  expect(onSubmit).not.toHaveBeenCalled();
});

test.each([
  ["Buy Put", "buy", 1.5, "ask"],
  ["Sell Call", "sell", 1.1, "bid"],
])("submits a limit ticket with the correct executable side for %s", (strategy, orderSide, price, priceSource) => {
  const { onSubmit, review } = beginReview(baseSelection, strategy);
  expect(review).toBeEnabled();
  fireEvent.click(review);
  fireEvent.click(screen.getByRole("button", { name: /confirm order/i }));
  expect(onSubmit).toHaveBeenCalledTimes(1);
  expect(onSubmit.mock.calls[0][0]).toMatchObject({
    strategy: strategy === "Buy Put" ? "buy_put" : "sell_call",
    orderSide,
    orderType: "limit",
    effectivePrice: price,
    priceSource,
  });
  expect(global.fetch.mock.calls.every(([url, options]) => !String(url).includes("/alpaca/order") && options?.method !== "POST")).toBe(true);
});

test("does not call the paper-order callback when journal persistence fails", () => {
  const { onSubmit, review } = beginReview(baseSelection);
  const setItem = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("storage full"); });
  const log = jest.spyOn(console, "error").mockImplementation(() => {});
  fireEvent.click(review);
  fireEvent.click(screen.getByRole("button", { name: /confirm order/i }));
  expect(onSubmit).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent(/journal could not be saved/i);
  setItem.mockRestore();
  log.mockRestore();
});
