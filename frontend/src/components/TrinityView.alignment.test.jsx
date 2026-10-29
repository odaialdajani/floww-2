/** @jest-environment jsdom */
// M1 behavioral regressions (Hermes-2, market-lane-20261023):
//   1. Same-strike alignment starts at the pane header: both panes reserve ONE
//      fixed header line, so the adjusted title can never wrap deeper than raw
//      and push its strike rows down. The full units/provenance string stays
//      available in a named details in each pane (never truncated away).
//   2. Desktop reading order: the Raw/Adjusted maps come first, the landmark
//      context and the exposure profile follow (UI-M03: map and selection
//      first, supporting context second; profile stays below the maps).
// Geometry (pair top <=300, maps >=360px, matching strike centers <=1px) is
// measured in the real rendered browser at 1470x950 and 1024x768.
import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import axios from 'axios';
import TrinityView from './TrinityView';

jest.mock('../config/api', () => ({ API: '/api', BACKEND_URL: '', BACKEND_BASE: '' }));
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));

function heatmapFixture() {
  const grid = { "2026-10-02": { 760: 5000000, 765: 9000000 } };
  return {
    ticker: "SPY", spot: 767.9, asof: "2026-09-28T12:00:00Z",
    formula_version: "gex.v2", snapshotId: "snap-triad-1", data_source: "public_api",
    grid: { expiries: ["2026-10-02"], strikes: [760, 765], grid },
    metrics: {
      walls: [{ wall_id: "w1", low: 760, high: 766, mid: 763, members: [760, 765], gross: 14e6, net: 4e6, call: 9e6, put: 5e6, distance: 4.9, distance_pct: 0.64, rank: 1 }],
      grids: {
        raw: { expiries: ["2026-10-02"], strikes: [760, 765], grid },
        session_delta_volume: { expiries: ["2026-10-02"], strikes: [760, 765], grid: { "2026-10-02": { 760: 2100000, 765: 3300000 } } },
        delta: { expiries: ["2026-10-02"], strikes: [760, 765], grid: { "2026-10-02": { 760: 3000000, 765: 5400000 } } },
      },
    },
    quality: { state: "usable", reasonCodes: [] },
  };
}

beforeEach(() => {
  window.sessionStorage.clear();
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/heatmap/")) return { data: heatmapFixture() };
    if (u.includes("solstice/scan/leaderboard")) return { data: { leaderboard: [], status: "not-scanned" } };
    if (u.includes("price-history")) return { data: { frames: [] } };
    if (u.includes("/decisions")) return { data: { decisions: [] } };
    return { data: {} };
  });
  axios.post.mockImplementation(async () => ({ data: {} }));
});

test("pane headers hold one line each; full units/provenance live in per-pane details", async () => {
  await act(async () => { render(<TrinityView ticker="SPY" />); });
  await act(async () => {
    fireEvent.change(screen.getByLabelText("Adjusted context"), { target: { value: "delta" } });
  });
  const rawPane = screen.getByTestId("triad-pane-raw");
  const adjPane = screen.getByTestId("triad-pane-adjusted");
  const rawTitle = rawPane.querySelector(".triad-pane-header .triad-pane-title");
  const adjTitle = adjPane.querySelector(".triad-pane-header .triad-pane-title");
  // Both visible titles stay single-line short reads with the shared unit.
  expect(rawTitle.textContent).toContain("USD/1% move");
  expect(adjTitle.textContent).toContain("USD/1% move");
  // The long provenance string never re-enters the header line (that wrap is
  // what offset same-strike rows by 13.17px at 1470x950 / 8.56px at 1024x768).
  expect(adjTitle.textContent).not.toContain("VOLUME_DELTA_WEIGHTED");
  expect(rawTitle.textContent).not.toContain("gex_net_v1");
  // Full units/provenance preserved in named, closed details in each pane.
  const rawUnits = screen.getByTestId("triad-pane-units-raw");
  const adjUnits = screen.getByTestId("triad-pane-units-adjusted");
  expect(rawUnits.open).toBe(false);
  expect(adjUnits.open).toBe(false);
  expect(rawPane.textContent).toContain("gex_net_v1");
  expect(adjPane.textContent).toContain("dadgex_net_v1");
  expect(adjPane.textContent).toContain("A weighting, not observed buying or selling.");
  fireEvent.click(adjUnits.querySelector("summary"));
  expect(adjUnits.open).toBe(true);
});

test("basis change re-anchors the adjusted scroller to raw, never a solo re-center", async () => {
  await act(async () => { render(<TrinityView ticker="SPY" />); });
  const raw = screen.getByTestId("triad-pane-raw").querySelector(".skylit-heatmap-container");
  const adjusted = screen.getByTestId("triad-pane-adjusted").querySelector(".skylit-heatmap-container");
  raw.scrollTop = 123;
  fireEvent.scroll(raw);
  expect(adjusted.scrollTop).toBe(123);
  // Simulate the child grid's independent re-center on its own scope key
  // (observed in the real browser: raw 1059 vs adjusted 979 after a basis
  // change — an 80px same-strike offset). The pair must re-anchor to raw.
  adjusted.scrollTop = 456;
  await act(async () => {
    fireEvent.change(screen.getByLabelText("Adjusted context"), { target: { value: "delta" } });
  });
  expect(adjusted.scrollTop).toBe(123);
  // And the snapshot identity is untouched by the realignment.
  expect(screen.getByTestId("triad-source")).toHaveTextContent("snap-triad-1");
});

test("a payload reload re-anchors the adjusted scroller, not only a basis change", async () => {
  await act(async () => { render(<TrinityView ticker="SPY" />); });
  const raw = screen.getByTestId("triad-pane-raw").querySelector(".skylit-heatmap-container");
  const adjusted = screen.getByTestId("triad-pane-adjusted").querySelector(".skylit-heatmap-container");
  raw.scrollTop = 123;
  fireEvent.scroll(raw);
  expect(adjusted.scrollTop).toBe(123);
  // At 1024x768 the adjusted pane's legend wraps one line deeper, so each
  // grid's own load-time centering lands the pair ~13px apart (measured:
  // same-strike center delta 13px in the real browser). Every payload
  // reload re-runs both grids' independent centering — the pair must
  // re-anchor to raw on the payload change itself.
  adjusted.scrollTop = 456;
  await act(async () => {
    fireEvent.change(screen.getByLabelText("Market view expiry scope"), { target: { value: "week" } });
  });
  expect(adjusted.scrollTop).toBe(123);
  expect(screen.getByTestId("triad-source")).toHaveTextContent("snap-triad-1");
});

test("a grid re-center marker re-anchors the pair without any scroll event", async () => {
  await act(async () => { render(<TrinityView ticker="SPY" />); });
  const raw = screen.getByTestId("triad-pane-raw").querySelector(".skylit-heatmap-container");
  const adjusted = screen.getByTestId("triad-pane-adjusted").querySelector(".skylit-heatmap-container");
  raw.scrollTop = 200;
  fireEvent.scroll(raw);
  expect(adjusted.scrollTop).toBe(200);
  // Programmatic re-centers (Center on price, Show selected level, the
  // grids' own mount/scope centering) write scrollTop with NO user gesture,
  // and renderers that defer scroll events to rendering opportunities that
  // never arrive never fire the sync (measured headless: raw 978 vs
  // adjusted 991 — a 13px same-strike offset). The grid marks every
  // programmatic center on the container via data-centered-scroll, so the
  // pair must re-anchor off that marker alone, no scroll event at all.
  raw.scrollTop = 300;
  raw.dataset.centeredScroll = "300";
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  expect(adjusted.scrollTop).toBe(300);
  // A re-center of the ADJUSTED grid alone must also fall back to raw's
  // anchor (raw keeps the user's scroll; adjusted is the dependent pane).
  adjusted.scrollTop = 999;
  adjusted.dataset.centeredScroll = "999";
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  expect(adjusted.scrollTop).toBe(300);
});

test("supporting workspace panels follow the maps and open one at a time", async () => {
  await act(async () => { render(<TrinityView ticker="SPY" />); });
  const maps = screen.getByTestId("triad-raw-adjusted");
  fireEvent.click(screen.getByTestId("triad-tab-landmarks"));
  const landmarks = document.querySelector(".trinity-layout .heatmap-landmarks");
  expect(landmarks).not.toBeNull();
  expect(maps.compareDocumentPosition(landmarks) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  fireEvent.click(screen.getByTestId("triad-tab-profile"));
  expect(document.querySelector(".trinity-layout .heatmap-landmarks")).toBeNull();
  fireEvent.click(screen.getByTestId("triad-profile-disclosure").querySelector('summary'));
  const profile = screen.getByTestId("triad-signed-profile");
  expect(profile).toBeVisible();
  expect(maps.compareDocumentPosition(profile) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // UI-M03: the replay strip is supporting context (stored-session replay),
  // not map content — it must follow the maps, never push them down. At the
  // top it cost 47px + margin and put the loaded map top at 341px@1470x950 /
  // 374px@1024x768, breaking the <=300px start budget at both sizes.
  fireEvent.click(screen.getByTestId("triad-tab-replay"));
  expect(screen.queryByTestId("triad-signed-profile")).toBeNull();
  const replayStrip = document.querySelector('[data-testid="solstice-replay-strip"]');
  expect(replayStrip).not.toBeNull();
  expect(maps.compareDocumentPosition(replayStrip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

