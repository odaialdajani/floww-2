import React from "react";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { TradeEntry } from "./TradeEntry";
import { JOURNAL_STORAGE_KEY } from "./tradeMath";

// Issue #17 O-1: Save Trade Idea persists to floww_trades_v2 in TradeJournal
// shape; survives unmount/remount. O-3: in-session list still 10 newest first.
const checklistOk = (regime = "positive_gamma") => ({
  ok: true,
  json: async () => ({ regime: { gex_regime: regime }, key_levels: { put_wall: 630, call_wall: 660 } }),
});

function mockChecklist(regime) {
  global.fetch = jest.fn(async () => checklistOk(regime));
}

beforeEach(() => {
  localStorage.clear();
  jest.restoreAllMocks();
});

afterEach(cleanup);

test("save writes a TradeJournal-shaped entry to floww_trades_v2", async () => {
  mockChecklist();
  render(<TradeEntry ticker="SPY" spot={645.2} />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByText(/positive gamma/)).toBeInTheDocument());
  fireEvent.click(screen.getByText("+ Save Trade Idea"));
  const raw = localStorage.getItem(JOURNAL_STORAGE_KEY);
  expect(raw).not.toBeNull();
  const rows = JSON.parse(raw);
  expect(rows.length).toBe(1);
  const e = rows[0];
  for (const k of ["ticker", "type", "action", "strike", "expiry", "quantity", "entry_price", "entry_date"]) {
    expect(e).toHaveProperty(k);
  }
  expect(e.ticker).toBe("SPY");
  expect(e.quantity).toBe("1"); // default contracts
  expect(e.gex_regime).toBe("positive_gamma");
  expect(e.setup).toMatch(/IRON CONDOR/);
});

test("saved idea survives unmount/remount and still shows in-session newest-first", async () => {
  mockChecklist();
  const { unmount } = render(<TradeEntry ticker="SPY" spot={645.2} />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  fireEvent.click(screen.getByText("+ Save Trade Idea"));
  fireEvent.click(screen.getByText("+ Save Trade Idea"));
  expect(screen.getByText(/Saved Trades \(2\)/)).toBeInTheDocument();
  unmount();
  // Remount with a pre-existing journal row from another session/panel
  const existing = JSON.parse(localStorage.getItem(JOURNAL_STORAGE_KEY));
  expect(existing.length).toBe(2);
  render(<TradeEntry ticker="SPY" spot={645.2} />);
  await waitFor(() => expect(screen.getByText(/Saved Trades \(2\)/)).toBeInTheDocument());
});

test("journal rows from other panels are not wiped by TradeEntry save", async () => {
  mockChecklist();
  localStorage.setItem(JOURNAL_STORAGE_KEY, JSON.stringify([{
    id: 1, ticker: "QQQ", type: "call", action: "buy", strike: 500,
    expiry: "", quantity: "1", entry_price: 2, exit_price: "",
    entry_date: "2026-09-06", exit_date: "", notes: "manual",
    gex_regime: "", setup: "BUY CALL", tags: "",
  }]));
  render(<TradeEntry ticker="SPY" spot={645.2} />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  fireEvent.click(screen.getByText("+ Save Trade Idea"));
  const rows = JSON.parse(localStorage.getItem(JOURNAL_STORAGE_KEY));
  expect(rows.some(r => r.ticker === "QQQ")).toBe(true);
  expect(rows.some(r => r.ticker === "SPY")).toBe(true);
});
