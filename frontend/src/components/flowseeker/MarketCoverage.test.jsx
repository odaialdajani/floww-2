import React from "react";
import { act, render, screen } from "@testing-library/react";
import axios from "axios";
import MarketCoverage from "./MarketCoverage";

jest.mock("axios");

test("shows saved comparison limits without claiming trade arrival timing", async () => {
  axios.get.mockResolvedValue({ data: { status: "current", checked_at: new Date().toISOString() } });
  render(<MarketCoverage coverage={{ universe: 8786, history_contract_limit: 60, history_unavailable: 3, history_capped: 2, conflicting_contracts_excluded: 4 }} />);
  await act(async () => {});
  const coverage = screen.getByLabelText("Automatic scan coverage");
  expect(coverage).toHaveTextContent("up to 60 contracts per stock");
  expect(coverage).toHaveTextContent("do not prove when trades happened");
  expect(coverage).toHaveTextContent("unavailable for 3 stocks");
  expect(coverage).toHaveTextContent("2 stocks reached the saved-comparison limit");
  expect(coverage).toHaveTextContent("4 conflicting contract readings were excluded");
});

test("separates full directory from fresh scans and flags provider changes", async () => {
  axios.get.mockResolvedValue({ data: { status: "review_needed" } });
  render(<MarketCoverage coverage={{ universe: 8786, fresh: 12, never_scanned: 8773, latest_failed: 1,
    source: "public-instruments", expiries_per_ticker: 2, complete_realtime_market: false }} />);
  expect(screen.getByText(/8,786 stocks and funds/)).toBeInTheDocument();
  expect(screen.getByLabelText("Automatic scan coverage")).toHaveTextContent("12 checked within 1 minute(s) at the last scan");
  expect(await screen.findByText(/Provider changes found/)).toBeInTheDocument();
  expect(screen.getByLabelText("Automatic scan coverage")).toHaveTextContent("not a live feed of every trade");
  expect(screen.getByLabelText("Automatic scan coverage")).toHaveTextContent("1 without usable fresh data");
  expect(screen.getByLabelText("Automatic scan coverage")).not.toHaveTextContent("requests failed");
});

test("an open scanner receives later provider release changes", async () => {
  jest.useFakeTimers();
  try {
    axios.get.mockResolvedValueOnce({ data: { status: "current", checked_at: new Date().toISOString() } })
      .mockResolvedValueOnce({ data: { status: "review_needed", checked_at: new Date().toISOString() } });
    render(<MarketCoverage />);
    await act(async () => {});
    expect(screen.getByLabelText("Automatic scan coverage")).toHaveTextContent("no changes since the last review");
    await act(async () => { jest.advanceTimersByTime(300000); });
    expect(screen.getByLabelText("Automatic scan coverage")).toHaveTextContent("Provider changes found");
  } finally {
    jest.useRealTimers();
  }
});

test("missing coverage counts stay unknown rather than zero",async()=>{axios.get.mockResolvedValue({data:{status:"current",checked_at:new Date().toISOString()}});render(<MarketCoverage coverage={{universe:null,fresh:null,never_scanned:null,latest_failed:null}}/>);await act(async()=>{});const node=screen.getByLabelText("Automatic scan coverage");expect(node).toHaveTextContent("Unknown stocks and funds");expect(node).toHaveTextContent("Unknown still waiting");expect(node).not.toHaveTextContent("0 stocks and funds");});
test("saved progress and option eligibility are visible without claiming fresh readings",async()=>{axios.get.mockResolvedValue({data:{status:"current",checked_at:new Date().toISOString()}});render(<MarketCoverage coverage={{universe:40,fresh:0,never_scanned:32,latest_failed:3,scope_kind:"provider_option_enabled",provider_listed_tickers:50,eligible_option_tickers:40,progress:{status:"durable",pending:32,deferred:2}}}/>);await act(async()=>{});const node=screen.getByLabelText("Automatic scan coverage");expect(node).toHaveTextContent("Scan position is saved");expect(node).toHaveTextContent("32 names remain");expect(node).toHaveTextContent("50 names in the provider list");expect(node).toHaveTextContent("0 checked within");expect(screen.getByText("Scan coverage and limits")).toBeInTheDocument();});
