/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import WheelIncomeScreenerPanel from "./WheelIncomeScreenerPanel";

const payload = {
  spot: 500,
  puts: [{ strike: 480, expiry: "2026-08-21", dte: 37, mid: 4.2, iv: 0.22, volume: 120, breakeven_drop_pct: 4.8, annualized_return_pct: 8.6 }],
  calls: [{ strike: 520, expiry: "2026-08-21", dte: 37, mid: 3.1, iv: 0.19, volume: 90, otm_pct: 4.0, annualized_return_pct: 6.1 }],
};

beforeEach(() => {
  global.fetch = jest.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })
  );
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("WheelIncomeScreenerPanel", () => {
  test("renders distinct CSP and CC tab buttons", async () => {
    render(<WheelIncomeScreenerPanel ticker="SPY" />);
    await screen.findByText(/Wheel · SPY/i);
    // The put tab must read CSP and the call tab CC — not one merged label.
    expect(screen.getByRole("button", { name: "CSP" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CC" })).toBeInTheDocument();
  });

  test("put rows render by default with breakeven column", async () => {
    render(<WheelIncomeScreenerPanel ticker="SPY" />);
    expect(await screen.findByText("$480")).toBeInTheDocument();
    expect(screen.getByText(/BE ↓%/)).toBeInTheDocument();
  });

  test("null IV renders unknown, never 0.0% (INCOME-04)", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({
        spot: 500,
        puts: [{ strike: 480, expiry: "2026-08-21", dte: 37, mid: 4.2, iv: null, volume: 120, breakeven_drop_pct: 4.8, annualized_return_pct: 8.6 }],
        calls: [],
      }) })
    );
    const { container } = render(<WheelIncomeScreenerPanel ticker="SPY" />);
    expect(await screen.findByText("$480")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/0\.0%/);
  });

  test("genuine zero IV still renders 0.0%", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({
        spot: 500,
        puts: [{ strike: 480, expiry: "2026-08-21", dte: 37, mid: 4.2, iv: 0, volume: 120, breakeven_drop_pct: 4.8, annualized_return_pct: 8.6 }],
        calls: [],
      }) })
    );
    render(<WheelIncomeScreenerPanel ticker="SPY" />);
    expect(await screen.findByText("$480")).toBeInTheDocument();
    expect(screen.getByText("0.0%")).toBeInTheDocument();
  });
});
