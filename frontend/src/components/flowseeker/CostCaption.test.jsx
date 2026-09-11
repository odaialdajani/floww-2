/**
 * COST caption honesty (Step 1.4): the pooled Roll readout must render with
 * its mid-quote-not-executable caption on a single-ticker tape.
 *
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import FlowseekerProBlademap from "./FlowseekerProBlademap";

jest.setTimeout(30000); // 31 simulated poll cycles exceed the 5s default under parallel load

const contracts = [
  { strike: 450, type: "call", expiry: "2026-09-18", volume: 500, oi: 500, iv: 0.2, bid: 4, ask: 4.2, last: 4.1 },
  { strike: 450, type: "put", expiry: "2026-09-18", volume: 600, oi: 600, iv: 0.25, bid: 3.9, ask: 4.1, last: 4.0 },
];

beforeEach(() => {
  window.localStorage.clear();
  global.fetch = jest.fn().mockImplementation((url) => {
    if (String(url).includes("/public/chain/SPY")) {
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ ok: true, contracts, spot: 452 }),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  });
});

test("COST caption renders with honesty copy on single-ticker tape", async () => {
  jest.useFakeTimers();
  try {
    render(<FlowseekerProBlademap active={true} />);
    fireEvent.click(screen.getByText("Smart Order Flow"));
    const tickerInput = screen.getByTestId("fsb-ticker-search");
    fireEvent.change(tickerInput, { target: { value: "SPY" } });
    fireEvent.keyDown(tickerInput, { key: "Enter", code: "Enter" });
    await act(async () => { jest.advanceTimersByTime(0); });
    for (let i = 0; i < 10 && !screen.queryByText(/PIN 450/); i++) {
      await act(async () => { jest.advanceTimersByTime(1000); });
    }
    // Pin readout proves the single-ticker tape computed on fixture rows.
    expect(screen.getByText(/PIN 450/)).toBeInTheDocument();
    // Building state — a count, never a number before 30 deltas.
    expect(screen.getByText(/COST building \d+\/30/)).toBeInTheDocument();
  // Visible caption + tooltip honesty: mid-quote, not executable cost.
  const caption = screen.getByText("mid-quote, not executable");
  expect(caption).toBeInTheDocument();
  expect(caption.title).toMatch(/NOT an executable taker cost/);
  expect(screen.getByText(/COST building/).title).toMatch(/NOT an executable taker cost/);
  } finally {
    jest.useRealTimers();
  }
});

test("COST number state renders after the bucket fills (static quotes truncate)", async () => {
  jest.useFakeTimers();
  try {
    render(<FlowseekerProBlademap active={true} />);
    fireEvent.click(screen.getByText("Smart Order Flow"));
    const tickerInput = screen.getByTestId("fsb-ticker-search");
    fireEvent.change(tickerInput, { target: { value: "SPY" } });
    fireEvent.keyDown(tickerInput, { key: "Enter", code: "Enter" });
    await act(async () => { jest.advanceTimersByTime(0); });
    // First poll settles across several microtask rounds; bound the wait.
    for (let i = 0; i < 10 && !screen.queryByText(/PIN 450/); i++) {
      await act(async () => { jest.advanceTimersByTime(1000); });
    }
    // Pin readout proves the single-ticker tape computed on fixture rows.
    expect(screen.getByText(/PIN 450/)).toBeInTheDocument();
    for (let i = 0; i < 30; i++) await act(async () => { jest.advanceTimersByTime(15000); });
    // Static fixture mids => zero autocovariance => textbook truncation.
    expect(screen.getByText(/COST ~\$0\.00/)).toBeInTheDocument();
    expect(screen.getByText("mid-quote, not executable")).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});
