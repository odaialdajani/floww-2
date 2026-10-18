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

test("session coverage toggle offers regular and all sessions", async () => {
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  // 2026-10-18: picker hidden while Chart tools is closed; open first.
  expect(screen.getByLabelText("Session coverage")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Chart tools" }));
  const picker = screen.getByLabelText("Session coverage");
  expect(picker).toBeVisible();
  expect(picker).toHaveTextContent(/regular/i);
  expect(picker).toHaveTextContent(/all sessions/i);
});

test("selecting all sessions drives the sessions param", async () => {
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Chart tools" }));
  fireEvent.change(screen.getByLabelText("Session coverage"), { target: { value: "all" } });
  await waitFor(() => {
    const hit = axios.get.mock.calls.filter(call =>
      String(call[0]).includes("price-history") && call[1].params.sessions === "all");
    expect(hit.length).toBeGreaterThan(0);
  });
});

test("regular sessions is the default param", async () => {
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  const priceCalls = axios.get.mock.calls.filter(call => String(call[0]).includes("price-history"));
  expect(priceCalls.length).toBeGreaterThan(0);
  priceCalls.forEach(call => expect(call[1].params.sessions).toBe("regular"));
});
