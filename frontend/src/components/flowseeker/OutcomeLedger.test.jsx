import React from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import FlowseekerProBlademap from "./FlowseekerProBlademap";
import OutcomeLedger from "./OutcomeLedger";

const report = {
  ok: true, lookback_days: 60, horizon_sessions: 2, sigma_k: 0.75, min_alerts: 5, source: "cron",
  overall: { n_measured: 22, precision: 0.55 }, tickers_measured: ["SPY", "QQQ"],
  per_rule: {
    WHALE: { n_measured: 20, n_censored: 3, n_controls: 30, uncalibrated: false, precision: 0.6,
      control_rate: 0.4, lift: 0.2, lift_ci: [0.05, 0.35], median_mfe_sigma: 1.4, median_mae_sigma: -0.7,
      decayed: true, status: "AMBER" },
    PRIME: { n_measured: 2, n_censored: 1, uncalibrated: true, precision: 0.99 },
  },
};
const response = (data) => ({ ok: true, json: async () => data });
const originalFetch = global.fetch;
beforeEach(() => {
  localStorage.clear();
  global.fetch = jest.fn(async (url) => response(String(url).includes("/outcomes") ? report : { ok: true, stage: 0, n: 2 }));
});
afterEach(() => { global.fetch = originalFetch; jest.useRealTimers(); });

test("the retained desktop Trust section has an outcome ledger destination", () => {
  localStorage.clear();
  render(<FlowseekerProBlademap active={false} />);
  expect(within(document.getElementById("trust")).getByRole("button", { name: /outcome ledger/i })).toBeInTheDocument();
});

test("loading is explicit and preserves comparison figures, limits, and separate definitions", async () => {
  render(<OutcomeLedger />);
  expect(global.fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /outcome ledger/i }));
  const table = await screen.findByRole("table", { name: "Historical rule outcomes" });
  const whale = within(table).getByText(/WHALE/).closest("tr");
  expect(whale).toHaveTextContent("20 / 3");
  expect(whale).toHaveTextContent("60%");
  expect(whale).toHaveTextContent("40% (n 30)");
  expect(whale).toHaveTextContent("+20 pp");
  expect(whale).toHaveTextContent("+5 pp to +35 pp");
  expect(whale).toHaveTextContent("1.4 / -0.7");
  expect(whale).toHaveTextContent("Review: recent results weakened");
  expect(within(table).getByText("PRIME").closest("tr")).toHaveTextContent("Too few to judge");
  expect(table).not.toHaveTextContent("99%");
  expect(screen.getByText(/move in either direction/)).toHaveTextContent("not whether the alert got direction right");
  expect(screen.getByText(/Source: saved/)).toHaveTextContent("Market observation time: unknown");
  expect(screen.getByText(/Not calibrated/)).toHaveTextContent("sample 2");
  expect(screen.getByText(/Overall:/)).toHaveTextContent("55% across 22 measured alerts. 2 tickers covered.");
  expect(global.fetch.mock.calls.map(([url]) => url)).toEqual([expect.stringContaining("/outcomes?days=60"), expect.stringMatching(/\/model$/)]);
});

test("empty history and unavailable model stay distinct from successful measured results", async () => {
  global.fetch.mockImplementation(async (url) => String(url).includes("/outcomes")
    ? response({ ok: true, status: "no_alerts", per_rule: {} }) : { ok: false });
  render(<OutcomeLedger />);
  fireEvent.click(screen.getByRole("button", { name: /outcome ledger/i }));
  expect(await screen.findByText("No measured rule history is available yet.")).toBeInTheDocument();
  expect(await screen.findByText("Historical statistical estimate unavailable.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("Public-only refusal is shown without figures or a claimed model fit", async () => {
  global.fetch.mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: "Historical outcome comparison is unavailable in Public-only mode." }) });
  render(<OutcomeLedger />);
  fireEvent.click(screen.getByRole("button", { name: /outcome ledger/i }));
  expect(await screen.findByText(/No legacy history was read or recalculated/)).toBeInTheDocument();
  expect(await screen.findByText(/No legacy fit was started/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.queryByText(/Not calibrated/)).not.toBeInTheDocument();
});

test("failed reload withholds earlier figures and malformed numeric fields never become zero", async () => {
  global.fetch.mockImplementation(async (url) => response(String(url).includes("/outcomes")
    ? { ...report, per_rule: { WHALE: { ...report.per_rule.WHALE, precision: null, control_rate: "0.4", lift: null } } }
    : { ok: true, stage: 0, n: 0 }));
  render(<OutcomeLedger />);
  fireEvent.click(screen.getByRole("button", { name: /outcome ledger/i }));
  const table = await screen.findByRole("table");
  expect(table).toHaveTextContent("Unavailable");
  expect(table).not.toHaveTextContent("0%");
  global.fetch.mockResolvedValue({ ok: false });
  fireEvent.click(screen.getByRole("button", { name: /Reload history/ }));
  expect(await screen.findByText(/Historical outcomes unavailable/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("a missing response ends with unavailable", async () => {
  jest.useFakeTimers();
  global.fetch.mockImplementation(() => new Promise(() => {}));
  const view = render(<OutcomeLedger />);
  fireEvent.click(screen.getByRole("button", { name: /outcome ledger/i }));
  await act(async () => { jest.advanceTimersByTime(15001); });
  expect(screen.getByText(/Historical outcomes unavailable/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Reload history/ })).not.toBeDisabled();
  view.rerender(<OutcomeLedger active={false} />);
  expect(global.fetch).toHaveBeenCalledTimes(2);
});

test("leaving aborts the request and ignores late replies without automatically recalculating on return", async () => {
  const finish = [];
  global.fetch.mockImplementation(() => new Promise((resolve) => finish.push(resolve)));
  const view = render(<OutcomeLedger />);
  fireEvent.click(screen.getByRole("button", { name: /outcome ledger/i }));
  const signal = global.fetch.mock.calls[0][1].signal;
  view.rerender(<OutcomeLedger active={false} />);
  expect(signal.aborted).toBe(true);
  await act(async () => {
    finish[0](response(report));
    finish[1](response({ ok: true, stage: 1, n: 500 }));
  });
  view.rerender(<OutcomeLedger />);
  expect(global.fetch).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getByText(/Historical outcomes unavailable/)).toBeInTheDocument();
});
