/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import SolsticeLeaderboard from "./SolsticeLeaderboard";
import { mutatingHeaders } from "../../utils/appKey";

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("../../utils/appKey", () => ({ mutatingHeaders: jest.fn() }));
beforeEach(() => { mutatingHeaders.mockReturnValue({ "X-API-Key": "fixture-only" }); });
const mount = async () => { await act(async () => render(<SolsticeLeaderboard />)); };

test("not scanned is explicit and reading never requests a legacy scan", async () => {
  axios.get.mockResolvedValue({ data: { status: "not-scanned", leaderboard: [] } });
  await mount();
  expect(screen.getByRole("status")).toHaveTextContent("Not scanned");
  expect(axios.get.mock.calls[0][0]).toContain("/solstice/scan/leaderboard");
  expect(axios.post).not.toHaveBeenCalled();
});

test("explicit scan uses authenticated bounded POST and keeps ranking unvalidated", async () => {
  axios.get.mockResolvedValue({ data: { status: "not-scanned", leaderboard: [] } });
  axios.post.mockResolvedValue({ data: { status: "partial-budget", rank_method: "solstice-rank.v1", leaderboard_age_s: 2,
    leaderboard: [{ ticker: "QQQ", conviction: 55.5, rank: 1, evidence: { flow_status: "ok", ml_status: "missing" } }] } });
  await mount();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Scan" })); });
  expect(axios.post.mock.calls[0][0]).toContain("/solstice/scan");
  expect(axios.post.mock.calls[0][1]).toEqual({ limit: 12, max_expiries: 2, dte: null, refresh: true });
  expect(axios.post.mock.calls[0][2].headers).toEqual({ "X-API-Key": "fixture-only" });
  expect(screen.getByRole("status")).toHaveTextContent("Partial budget");
  expect(screen.getByText(/#1 QQQ/)).toBeInTheDocument();
  expect(screen.getByText(/Unvalidated research ranking/)).toBeInTheDocument();
});

test.each(["no-eligible-rows", "stale", "source-error"])("%s stays legible", async status => {
  axios.get.mockResolvedValue({ data: { status, leaderboard: [], availability: [{ ticker: "SPX", reason: "ENTITLEMENT_UNVERIFIED" }] } });
  await mount();
  expect(screen.getByRole("status").textContent).not.toBe("");
  expect(screen.getByText(/SPX · ENTITLEMENT_UNVERIFIED/)).toBeInTheDocument();
});

test("declining authentication cannot spend; NaN is not a displayed ranking", async () => {
  mutatingHeaders.mockReturnValue(null);
  axios.get.mockResolvedValue({ data: { status: "no-eligible-rows", leaderboard: [{ ticker: "SPX", conviction: NaN }] } });
  await mount();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Scan" })); });
  expect(axios.post).not.toHaveBeenCalled();
  expect(screen.getByRole("status")).toHaveTextContent("Authentication required");
  expect(screen.queryByText(/#.*SPX/)).not.toBeInTheDocument();
});
