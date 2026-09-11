import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import TradeJournal, { mergeJournalRows } from "./TradeJournal";

afterEach(() => { localStorage.clear(); jest.restoreAllMocks(); });

it("refreshes a cached broker fill after its reserved close is reconciled", async () => {
  const cached = { id: "cached-row", ticker: "SPY", type: "equity", action: "buy",
    strike: 0, expiry: "", quantity: "2", entry_price: 500, exit_price: "",
    entry_date: "2026-09-11T10:00:00Z", exit_date: "", broker_order_id: "alpaca-order:one",
    updated_at: "2026-09-11T10:00:00Z" };
  localStorage.setItem("floww_trades_v2", JSON.stringify([cached]));
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ trades: [
    { ...cached, exit_price: 501, exit_date: "2026-09-11T11:00:00Z", updated_at: "2026-09-11T11:00:00Z" },
  ] }) });
  render(<TradeJournal />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "Closed", exact: true }));
  await waitFor(() => expect(screen.getByText("SPY")).toBeTruthy());
});

const openFill = { id: "stable-local", ticker: "SPY", type: "equity", action: "buy",
  strike: 0, expiry: "", quantity: "2", entry_price: 500, exit_price: "", exit_date: "",
  entry_date: "", broker_order_id: "alpaca-order:one", updated_at: "2026-09-11 10:00:00",
  notes: "My reason", tags: "watch", setup: "local setup", key_levels: { target: 510 } };

it("refreshes execution values and unknown fill time without losing local notes or card identity", () => {
  const server = { ...openFill, id: undefined, entry_date: "2026-09-11T10:01:00Z",
    quantity: "3", exit_price: 502, exit_date: "2026-09-11T11:00:00Z",
    updated_at: "2026-09-11 11:00:00", notes: "server note", tags: "", setup: "", key_levels: null };
  const merged = mergeJournalRows([openFill], [server]);
  expect(merged).toHaveLength(1);
  expect(merged[0]).toMatchObject({ id: "stable-local", quantity: "3", exit_price: 502,
    entry_date: server.entry_date, notes: "My reason", tags: "watch", setup: "local setup",
    key_levels: { target: 510 }, _broker_updated_at: server.updated_at });
});

it("does not let stale, equal or unknown server timestamps replace a confirmed close", () => {
  const closed = { ...openFill, exit_price: 502, exit_date: "2026-09-11T11:00:00Z",
    updated_at: "2026-09-11T11:00:00Z", _broker_updated_at: "2026-09-11T11:00:00Z" };
  for (const updated_at of ["2026-09-11 10:59:59", "2026-09-11 11:00:00", "", "invalid"]) {
    expect(mergeJournalRows([closed], [{ ...openFill, updated_at }])[0]).toEqual(closed);
  }
});

it("uses the saved broker clock despite newer local annotation edits", () => {
  const annotated = { ...openFill, updated_at: "2026-09-11T12:00:00Z",
    _broker_updated_at: "2026-09-11 10:00:00", notes: "new local note" };
  const result = mergeJournalRows([annotated], [{ ...openFill, updated_at: "2026-09-11 11:00:00",
    exit_date: "2026-09-11T11:00:00Z", exit_price: 502 }]);
  expect(result[0]).toMatchObject({ exit_price: 502, notes: "new local note", id: annotated.id });
});

it("establishes a broker clock for an older cache despite a later local edit", () => {
  const legacy = { ...openFill, updated_at: "2026-09-11T12:00:00Z", notes: "edited locally" };
  const result = mergeJournalRows([legacy], [{ ...openFill, updated_at: "2026-09-11 11:00:00",
    exit_date: "2026-09-11T11:00:00Z", exit_price: 502 }]);
  expect(result[0]).toMatchObject({ exit_price: 502, notes: "edited locally",
    _broker_updated_at: "2026-09-11 11:00:00" });
});

it("orders DuckDB microseconds within one millisecond and rejects the reverse", () => {
  const cached = { ...openFill, _broker_updated_at: "2026-09-11 11:00:00.123100" };
  const closed = { ...openFill, updated_at: "2026-09-11 11:00:00.123900",
    exit_date: "2026-09-11T11:00:00Z", exit_price: 502 };
  const forward = mergeJournalRows([cached], [closed]);
  expect(forward[0].exit_price).toBe(502);
  expect(mergeJournalRows(forward, [{ ...openFill, updated_at: cached._broker_updated_at }])[0]).toEqual(forward[0]);
});

it("keeps manual rows and separate orders while repeated server reads do not duplicate fills", () => {
  const manual = { ...openFill, broker_order_id: "", id: "manual", notes: "manual note" };
  const other = { ...openFill, broker_order_id: "alpaca-order:two", id: "other" };
  const server = [{ ...openFill, updated_at: "2026-09-11 11:00:00" }, other,
    { ...manual, notes: "server must not win", updated_at: "2026-09-11 12:00:00" }];
  const first = mergeJournalRows([manual, openFill], server);
  const repeated = mergeJournalRows(first, server);
  expect(repeated).toHaveLength(3);
  expect(repeated.find(row => row.id === "manual").notes).toBe("manual note");
  expect(repeated.filter(row => row.broker_order_id)).toHaveLength(2);
});
