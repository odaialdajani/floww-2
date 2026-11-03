/**
 * @jest-environment jsdom
 *
 * The Portfolio page reads pnl.total_pnl / pnl.pct_pnl /
 * pnl.total_entry_value / pnl.total_current_value. The endpoint used to
 * return pnl as a bare number, so the page rendered "undefined%" for every
 * money line. These checks pin the panel against the typed P&L object the
 * backend now returns and against an unavailable book, which must never be
 * shown as zero.
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

function summary(overrides = {}) {
  return {
    name: "main",
    positions: 1,
    positions_priced: 1,
    positions_skipped: 0,
    skipped: [],
    greeks: { delta: 1, gamma: 2, vega: 3, theta: 4 },
    total_pnl: 1200,
    valuation_basis: "local_bs_model_at_spot_iv",
    spot: 600,
    iv: 0.15,
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
    ...overrides,
  };
}

async function refreshWith(payload, book = { name: "main", positions: [] }) {
  mockGet.mockImplementation(async (url, config) =>
    (config?.params?.spot ? { data: payload } : { data: book }));
  render(<PortfolioPanel ticker="SPY" spot={600} />);
  fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
  await waitFor(() => expect(mockGet).toHaveBeenCalled());
}

describe("PortfolioPanel money contract", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockClear();
    mockDelete.mockClear();
  });

  test("renders the P&L fields the endpoint returns", async () => {
    await refreshWith(summary());
    await waitFor(() => expect(document.body.textContent).toContain("1,200"));
    expect(document.body.textContent).toContain("12.5%");
    expect(document.body.textContent).toContain("9,600");
    expect(document.body.textContent).toContain("10,800");
    expect(document.body.textContent).not.toMatch(/undefined/);
  });

  test("an unavailable book is never shown as zero money", async () => {
    await refreshWith(summary({
      positions: 0,
      positions_priced: 0,
      total_pnl: null,
      pnl: {
        status: "unavailable",
        reason: "NO_PRICED_POSITIONS",
        total_pnl: null,
        pct_pnl: null,
        pct_reason: null,
        total_entry_value: null,
        total_current_value: null,
        currency: "USD",
        unit: "USD",
        coverage: { stored: 0, priced: 0, skipped: 0 },
      },
    }));
    await waitFor(() => expect(document.body.textContent).toMatch(/unavailable/i));
    expect(document.body.textContent).not.toMatch(/undefined/);
    expect(document.body.textContent).not.toMatch(/\$0/);
  });

  test("a skipped position is disclosed next to the money", async () => {
    await refreshWith(summary({
      positions: 2,
      positions_priced: 1,
      positions_skipped: 1,
      skipped: [{ index: 1, reason: "INVALID_STRIKE", symbol: "BAD" }],
      pnl: {
        ...summary().pnl,
        coverage: { stored: 2, priced: 1, skipped: 1 },
      },
    }));
    await waitFor(() => expect(document.body.textContent).toMatch(/skipped/i));
    expect(document.body.textContent).not.toMatch(/undefined/);
  });
});
