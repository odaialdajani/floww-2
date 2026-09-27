/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import UniverseLeaderboard from "./UniverseLeaderboard";

jest.mock("axios");
import axios from "axios";

test("renders ranked rows with invalidation tooltip", async () => {
  axios.get.mockResolvedValueOnce({ data: { leaderboard: [
    { ticker: "SPY", rank: 1, conviction: 88, tier: "HIGH", direction: "BULL", trade_type: "debit_spread", invalidation: "lose 500" },
  ], leaderboard_age_s: 12 } });
  render(<UniverseLeaderboard />);
  await waitFor(() => expect(screen.getByText(/#1 SPY/)).toBeInTheDocument());
  expect(screen.getByText(/HIGH 88/)).toBeInTheDocument();
  expect(screen.getByTitle(/lose 500/)).toBeInTheDocument();
});

test("empty state invites a scan", async () => {
  axios.get.mockResolvedValueOnce({ data: { leaderboard: [], leaderboard_age_s: null } });
  render(<UniverseLeaderboard />);
  await waitFor(() => expect(screen.getByText(/press Scan/i)).toBeInTheDocument());
});

test("scan button sweeps next slice", async () => {
  axios.get.mockResolvedValueOnce({ data: { leaderboard: [], leaderboard_age_s: null } });
  axios.get.mockResolvedValueOnce({ data: { leaderboard: [], leaderboard_age_s: 1, cache: "miss", batch: { skipped: [] } } });
  render(<UniverseLeaderboard />);
  await waitFor(() => expect(screen.getByText(/press Scan/i)).toBeInTheDocument());
  fireEvent.click(screen.getByText("Scan"));
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/universe/scan")));
});
