import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import PriceNodeHistory from "../../PriceNodeHistory";

jest.mock("axios", () => ({ get: jest.fn() }));

const frames = ["14:00", "14:01"].map(t => ({ time: `2026-09-10T${t}:00+00:00`,
  open: 100, high: 102, low: 99, close: 101, nodes: [] }));

beforeEach(() => {
  window.localStorage.clear();
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
});
afterEach(() => jest.restoreAllMocks());

test("history period offers quarter, year and five-year provider-max horizons", async () => {
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  // 2026-10-18: pickers live inside Chart tools now — verify hidden while
  // closed, then open before asserting content.
  expect(screen.getByLabelText("History sessions")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Chart tools" }));
  const picker = screen.getByLabelText("History sessions");
  expect(picker).toBeVisible();
  expect(picker).toHaveTextContent(/3 months/);
  expect(picker).toHaveTextContent(/1 year/);
  // Provider-verified maximum: api.public.com historicdata rejects TEN_YEARS
  // (400) and serves at most FIVE_YEARS. The label must say what it serves.
  expect(picker).toHaveTextContent(/5 years/);
  expect(picker).not.toHaveTextContent(/10 years/);
});

test("selecting a long horizon drives the days param", async () => {
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Chart tools" }));
  fireEvent.change(screen.getByLabelText("History sessions"), { target: { value: "260" } });
  await waitFor(() => {
    const daysCalls = axios.get.mock.calls.filter(call =>
      String(call[0]).includes("price-history") && call[1].params.days === 260);
    expect(daysCalls.length).toBeGreaterThan(0);
  });
});
