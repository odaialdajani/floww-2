/** @jest-environment jsdom */
// Market desktop composition regressions (market-desktop-20261025): the ONE
// selected-object inspector dock, its concise empty state, and the grouped
// command header. These pin the NEW structure only; every pre-existing data,
// refusal and selection behavior stays covered by the TrinityView/r11/
// alignment suites.
import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import axios from 'axios';
import TrinityView from './TrinityView';

jest.mock('../config/api', () => ({ API: '/api', BACKEND_URL: '', BACKEND_BASE: '' }));
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));

function deskFixture() {
  const grid = { "2026-10-02": { 760: 5000000, 765: 9000000 } };
  return {
    ticker: "SPY", spot: 767.9, asof: "2026-09-28T12:00:00Z",
    formula_version: "gex.v2", snapshotId: "snap-desk-1", data_source: "public_api",
    grid: { expiries: ["2026-10-02"], strikes: [760, 765], grid },
    metrics: {
      walls: [{ wall_id: "w1", low: 760, high: 766, mid: 763, members: [760, 765], gross: 14e6, net: 4e6, call: 9e6, put: 5e6, distance: 4.9, distance_pct: 0.64, rank: 1 }],
      wall_metrics: { w1: { session_delta_volume_usable: 2, session_delta_volume_gross: 5400000, session_delta_volume_net: 2100000 } },
      grids: {
        raw: { expiries: ["2026-10-02"], strikes: [760, 765], grid },
        session_delta_volume: { expiries: ["2026-10-02"], strikes: [760, 765], grid: { "2026-10-02": { 760: 2100000, 765: 3300000 } } },
      },
    },
    scout: { shortlist: { CALLS: [], PUTS: [] } },
    scenarios: [
      { wall_id: "w1", wall_position: "below", name: "Bounce watch", type: "reversal_watch", confirmation: "reclaim and hold above 760", invalidation: "sustained acceptance below 760" },
    ],
    nodes: { king: { strike: 765 }, regime: "positive" },
    quality: { state: "usable", reasonCodes: [] },
  };
}

beforeEach(() => {
  window.sessionStorage.clear();
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) return { data: deskFixture() };
    if (u.includes("solstice/scan/leaderboard")) return { data: { leaderboard: [], status: "not-scanned" } };
    if (u.includes("/decisions")) return { data: { decisions: [] } };
    return { data: {} };
  });
  axios.post.mockImplementation(async () => ({ data: {} }));
});

test("desktop composition: dock mounts with a concise selection prompt before anything is selected", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-inspector-dock")).toBeInTheDocument());
  const dock = screen.getByTestId("triad-inspector-dock");
  expect(screen.getByTestId("triad-no-wall")).toBeInTheDocument();
  expect(dock).toContainElement(screen.getByTestId("triad-no-wall"));
  // The prompt teaches exactly one concrete action, and the honest
  // adjusted-only note is retained verbatim.
  expect(screen.getByTestId("triad-no-wall").textContent).toMatch(/click a cell in either map/i);
  expect(screen.getByTestId("triad-no-wall").textContent).toMatch(/adjusted-only peak/i);
  // The comparison maps stay first in the reading order and the dock sits
  // after the main column, not inside it.
  const maps = screen.getByTestId("triad-raw-adjusted");
  const dockPos = maps.compareDocumentPosition(dock);
  expect(dockPos & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("desktop composition: one grouped header carries focus, scope, basis, assistant and identity", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-command-bar")).toBeInTheDocument());
  const head = screen.getByTestId("triad-command-bar");
  for (const control of [
    screen.getByLabelText("Focused symbol"),
    screen.getByLabelText("Market view expiry scope"),
    screen.getByLabelText("Adjusted context"),
    screen.getByTestId("triad-symbol-go"),
    screen.getByTestId("triad-loaded-dates"),
    screen.getByTestId("triad-source"),
  ]) {
    expect(head).toContainElement(control);
  }
  // Compact status and deliberately opened exact provenance retain both facts.
  expect(screen.getByTestId("triad-observation-line")).toHaveTextContent("LIVE · quality usable");
  const provenance = screen.getByTestId("triad-provenance-details");
  fireEvent.click(provenance.querySelector('summary'));
  expect(screen.getByText("snap-desk-1", { selector: 'dd' })).toBeVisible();
  expect(screen.getByText("public_api", { selector: 'dd' })).toBeVisible();
});

test("selecting a wall fills the dock: compact human-scale readings, the wall card, and gated review tabs", async () => {
  await act(async () => { render(<TrinityView />); });
  fireEvent.click(await screen.findByTestId("triad-tab-walls"));
  await waitFor(() => expect(screen.getByTestId("triad-walls")).toBeInTheDocument());
  await act(async () => { fireEvent.click(screen.getByTestId("triad-wall-w1")); });
  const dock = screen.getByTestId("triad-inspector-dock");
  // Readable labeled readings with the exact value in the title.
  const values = screen.getByTestId("triad-dock-values");
  expect(values.textContent).toContain("Raw gross");
  expect(values.textContent).toContain("Raw net");
  const adj = values.lastElementChild;
  expect(adj.title).toContain("exact value 2100000");
  expect(adj.textContent).toContain("$2.1M");
  // The selected-wall card lives INSIDE the dock with its full honest content.
  expect(dock).toContainElement(screen.getByTestId("triad-scenario"));
  expect(dock).toContainElement(screen.getByTestId("triad-scenario-first"));
  expect(dock).toContainElement(screen.getByTestId("triad-contracts-btn"));
  // Contract/Flow/Public panels are gated behind the deliberate review
  // action: no exact-contract request happens merely because a wall was
  // selected (request parity with the drawer contract).
  expect(dock.textContent).toMatch(/Review contracts.*action|“Review contracts” action/);
  const exactCalls = axios.get.mock.calls.filter(([url]) => String(url).includes("/solstice/SPY/contract"));
  expect(exactCalls).toHaveLength(0);
  // The deliberate review action mounts the exact-contract panel in the dock
  // and flips the drawer semantics on (same authoritative selection).
  await act(async () => { fireEvent.click(screen.getByTestId("triad-contracts-btn")); });
  await waitFor(() => expect(screen.getByTestId("triad-contract-drawer")).toBeInTheDocument());
  expect(screen.getByRole("tabpanel", { name: "Contract" }).textContent.length).toBeGreaterThan(0);
});

test("the inspector toggle collapses and restores the dock without touching the maps", async () => {
  await act(async () => { render(<TrinityView />); });
  await waitFor(() => expect(screen.getByTestId("triad-view")).toBeInTheDocument());
  const toggle = screen.getByTestId("triad-inspector-toggle");
  expect(toggle).toHaveAttribute("aria-pressed", "false");
  await act(async () => { fireEvent.click(toggle); });
  expect(toggle).toHaveAttribute("aria-pressed", "true");
  await act(async () => { fireEvent.click(toggle); });
  expect(screen.getByTestId("triad-view")).toHaveClass("tdk-dock-closed");
  expect(screen.getByTestId("triad-raw-adjusted")).toBeInTheDocument();
  await act(async () => { fireEvent.click(toggle); });
  expect(screen.getByTestId("triad-view")).toHaveClass("tdk-dock-open");
  expect(screen.getByTestId("triad-inspector-dock")).toBeInTheDocument();
});
