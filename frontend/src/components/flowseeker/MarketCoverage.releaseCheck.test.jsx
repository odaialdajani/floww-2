/**
 * A failed provider-release check must not read as "not yet".
 *
 * MarketCoverage fetched /market/provider-updates with `.catch(() => {})` and
 * then rendered one message for every non-`current` outcome:
 *
 *   "Provider release check is not available yet."
 *
 * That single string covers three different states:
 *   1. the request has not completed yet (transient, will resolve)
 *   2. the request FAILED (server down, 5xx, offline) — will not self-resolve
 *   3. the request succeeded but the status is something unrecognised
 *
 * (1) and (2) are the dangerous pair. "not available yet" promises a
 * pending update; a permanent failure delivers nothing and says the same
 * thing, so an operator can believe the release state is merely stale when
 * in fact nothing is being checked at all.
 *
 * This component is in the read-only TidehunterPro surface, so the change
 * is limited to making the three states distinguishable in the text. No
 * data source, scoring, threshold, or store is touched.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import MarketCoverage from "./MarketCoverage";

jest.mock("axios", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));
const axios = require("axios").default;

const coverage = { universe: 40, fresh: 2, never_scanned: 38, latest_failed: 0 };

afterEach(() => jest.clearAllMocks());

test("a current provider check reads as current", async () => {
  axios.get.mockResolvedValue({
    data: { status: "current", checked_at: new Date().toISOString() },
  });
  render(<MarketCoverage coverage={coverage} />);
  await waitFor(() => {
    expect(screen.getByText(/no changes since the last review/i)).toBeInTheDocument();
  });
});

test("review_needed is reported as needing review, not as unavailable", async () => {
  axios.get.mockResolvedValue({
    data: { status: "review_needed", checked_at: new Date().toISOString() },
  });
  render(<MarketCoverage coverage={coverage} />);
  await waitFor(() => {
    expect(screen.getByText(/review needed/i)).toBeInTheDocument();
  });
  expect(screen.queryByText(/not available yet/i)).not.toBeInTheDocument();
});

test("a FAILED check says it failed and does not promise a pending update", async () => {
  axios.get.mockRejectedValue({ response: { status: 503 } });
  render(<MarketCoverage coverage={coverage} />);
  await waitFor(() => {
    expect(screen.getByTestId("release-check-failed")).toBeInTheDocument();
  });
  const el = screen.getByTestId("release-check-failed");
  expect(el.textContent).toMatch(/could not be checked|unreachable/i);
  // the misleading "not available yet" promise must be gone
  expect(el.textContent).not.toMatch(/not available yet/i);
});

test("a successful check with an unrecognised status is distinct from a failure", async () => {
  axios.get.mockResolvedValue({
    data: { status: "some_new_state", checked_at: new Date().toISOString() },
  });
  render(<MarketCoverage coverage={coverage} />);
  await waitFor(() => {
    expect(screen.getByTestId("release-check-unknown")).toBeInTheDocument();
  });
  expect(screen.getByTestId("release-check-unknown").textContent).toMatch(/some_new_state|unrecognised|unknown/i);
  expect(screen.queryByTestId("release-check-failed")).not.toBeInTheDocument();
});

test("still loading shows a pending message, not a failure", async () => {
  axios.get.mockReturnValue(new Promise(() => {})); // never settles
  render(<MarketCoverage coverage={coverage} />);
  expect(screen.getByTestId("release-check-pending")).toBeInTheDocument();
  expect(screen.queryByTestId("release-check-failed")).not.toBeInTheDocument();
});
