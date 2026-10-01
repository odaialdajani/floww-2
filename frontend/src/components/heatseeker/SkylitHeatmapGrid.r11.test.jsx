/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import SkylitHeatmapGrid, { fmtK } from "./SkylitHeatmapGrid";
import { sumProfile } from "../../lib/solsticeMetrics";

const STRIKES = [660, 658, 656, 654, 652, 650, 648, 646, 644, 642];
const EXPS = ["2031-01-17", "2031-01-24"];

function data() {
  const grid = {};
  for (const e of EXPS) {
    grid[e] = {};
    for (const s of STRIKES) grid[e][String(s)] = (s - 650) * 1000;
  }
  return { ticker: "SPY", asof: "2031-01-10T00:00:00Z", grid: { expiries: EXPS, strikes: STRIKES, grid } };
}

function bodyRows(container) {
  return Array.from(container.querySelectorAll("tbody tr"));
}

test("spot line sits between the two strikes that bracket spot", () => {
  const { container } = render(<SkylitHeatmapGrid data={data()} spot={651.3} ticker="SPY" />);
  const rows = bodyRows(container);
  const idx = rows.findIndex((r) => r.classList.contains("trin-spot-rail"));
  expect(idx).toBeGreaterThan(0);
  expect(rows[idx - 1].textContent).toContain("652");
  expect(rows[idx + 1].textContent).toContain("650");
  expect(screen.getByTestId("skylit-spot-line").textContent).toContain("651.30");
  // The nearest-strike chip is a different element from the line.
  expect(screen.getByTestId("skylit-spot-chip").textContent).toBe("652.0");
});

test("spot exactly on a strike draws no between-row line and never duplicates a row", () => {
  const { container } = render(<SkylitHeatmapGrid data={data()} spot={650} ticker="SPY" />);
  expect(container.querySelector("tr.trin-spot-between")).toBeNull();
  const strikes = Array.from(container.querySelectorAll("tr.trin-row td.trin-strike-cell")).map((td) => td.textContent);
  expect(new Set(strikes).size).toBe(strikes.length);
});

test("spot outside the shown window is marked above/below instead of snapping", () => {
  const { container } = render(<SkylitHeatmapGrid data={data()} spot={700} ticker="SPY" windowRows={4} anchorStrike={650} />);
  expect(container.querySelector("tr.trin-spot-above")).not.toBeNull();
  expect(screen.getByTestId("skylit-grid-window-note").textContent).toContain("follow paused");
});

test("selected cell and strike get a restrained outline and aria-selected", () => {
  const { container } = render(
    <SkylitHeatmapGrid data={data()} spot={651} ticker="SPY" selected={{ strike: 650, expiry: EXPS[1] }}
      wallBand={{ low: 648, high: 652 }} />
  );
  const sel = container.querySelectorAll("td.trin-selected");
  expect(sel).toHaveLength(1);
  expect(sel[0].getAttribute("aria-selected")).toBe("true");
  expect(sel[0].getAttribute("aria-label")).toContain(EXPS[1]);
  expect(container.querySelectorAll("tr.trin-row-selected")).toHaveLength(1);
  expect(container.querySelectorAll("td.trin-wall-member")).toHaveLength(3);
});

test("partial and delta-unknown cells are marked, never shown as zero", () => {
  const d = data();
  d.metrics = { grids: { delta: {
    exposure_basis: "OI_DELTA_WEIGHTED", expiries: EXPS, strikes: STRIKES,
    grid: { [EXPS[0]]: { 650: 500 } },
    cell_missing_delta: { [EXPS[0]]: { 650: 2, 652: 1 } },
  } } };
  const { container } = render(<SkylitHeatmapGrid data={d} spot={651} ticker="SPY" metric="delta" />);
  const partial = container.querySelectorAll("td.trin-partial");
  expect(partial).toHaveLength(1);
  expect(partial[0].getAttribute("aria-label")).toMatch(/partial: 2 excluded/);
  const unknown = Array.from(container.querySelectorAll("td.trin-missing"))
    .filter((td) => /delta unknown/.test(td.getAttribute("aria-label")));
  expect(unknown).toHaveLength(1);
  expect(unknown[0].textContent).not.toMatch(/\$0/);
});

test("invalid delta cells carry the distinct δ! marker, never merged into missing", () => {
  const d = data();
  d.metrics = { grids: { delta: {
    exposure_basis: "OI_DELTA_WEIGHTED", expiries: EXPS, strikes: STRIKES,
    grid: { [EXPS[0]]: { 650: 500 } },
    cell_missing_delta: { [EXPS[0]]: { 652: 1 } },
    cell_invalid_delta: { [EXPS[0]]: { 650: 1, 648: 2 } },
  } } };
  const { container } = render(<SkylitHeatmapGrid data={d} spot={651} ticker="SPY" metric="delta" />);
  const marked = container.querySelectorAll("td.trin-invalid");
  expect(marked).toHaveLength(2); // valued cell keeps its exclusion note; absent cell is unavailable, not zero
  expect(marked[0].getAttribute("aria-label")).toMatch(/1 excluded for invalid delta/);
  expect(container.querySelectorAll("td.trin-partial")).toHaveLength(0);
  const bad = Array.from(container.querySelectorAll("td.trin-missing"))
    .filter((td) => /delta invalid/.test(td.getAttribute("aria-label")));
  expect(bad).toHaveLength(1); // value-less cell with invalid readings: unavailable, not zero
  expect(bad[0].textContent).toContain("δ!");
});

test("profile column: rows align with strikes, zero axis at 50%, negatives left, gaps empty", () => {
  const d = data();
  delete d.grid.grid[EXPS[0]]["642"];
  delete d.grid.grid[EXPS[1]]["642"];
  const raw = sumProfile(d, "raw", EXPS);
  const { container } = render(
    <SkylitHeatmapGrid data={d} spot={651} ticker="SPY" profile={{ raw, scopeLabel: "Σ 2 loaded expiries" }} />
  );
  expect(screen.getByTestId("skylit-profile-header").textContent).toContain("Σ 2 loaded expiries");
  const cells = Array.from(container.querySelectorAll("[data-testid='skylit-profile-cell']"));
  const rows = Array.from(container.querySelectorAll("tr.trin-row"));
  expect(cells).toHaveLength(rows.length);
  const byStrike = Object.fromEntries(cells.map((c) => [c.dataset.strike, c]));
  const pos = byStrike["660"].querySelector(".trin-prof-bar.raw");
  const neg = byStrike["644"].querySelector(".trin-prof-bar.raw");
  expect(pos.classList.contains("pos")).toBe(true);
  expect(parseFloat(pos.style.left)).toBe(50);
  expect(neg.classList.contains("neg")).toBe(true);
  expect(parseFloat(neg.style.left) + parseFloat(neg.style.width)).toBeCloseTo(50, 6);
  // Largest |value| reaches the half-width; zero strike draws a zero-width bar.
  expect(parseFloat(pos.style.width)).toBeCloseTo(50, 6);
  expect(parseFloat(byStrike["650"].querySelector(".trin-prof-bar.raw").style.width)).toBe(0);
  // 642 has no cell in scope: gap, no bar at all.
  expect(byStrike["642"].querySelector(".trin-prof-bar")).toBeNull();
  // Profile value equals the sum of that row's cells over the scope.
  expect(raw.values["660"]).toBe(20000);
});

test("adjusted profile bar overlays the raw bar on the same row", () => {
  const d = data();
  d.metrics = { grids: { session_delta_volume: {
    exposure_basis: "VOLUME_DELTA_WEIGHTED", expiries: EXPS, grid: { [EXPS[0]]: { 660: -300, 650: 100 } },
  } } };
  const raw = sumProfile(d, "raw", EXPS);
  const adj = sumProfile(d, "session_delta_volume", EXPS);
  const { container } = render(
    <SkylitHeatmapGrid data={d} spot={651} ticker="SPY"
      profile={{ raw, adj, adjLabel: "Vol×|Δ|", scopeLabel: "Σ 2 loaded" }} />
  );
  const row660 = container.querySelector("[data-testid='skylit-profile-cell'][data-strike='660']");
  expect(row660.querySelector(".trin-prof-bar.raw.pos")).not.toBeNull();
  // Raw positive, adjusted negative at the same strike — both visible.
  expect(row660.querySelector(".trin-prof-bar.adj.neg")).not.toBeNull();
  const row656 = container.querySelector("[data-testid='skylit-profile-cell'][data-strike='656']");
  expect(row656.querySelector(".trin-prof-bar.adj")).toBeNull(); // gap on the adjusted surface
});

test("arrow keys move focus between measured cells", () => {
  const { container } = render(<SkylitHeatmapGrid data={data()} spot={651} ticker="SPY" onCellClick={() => {}} />);
  const first = container.querySelector("td.trin-cell[data-r='0'][data-c='0']");
  first.focus();
  fireEvent.keyDown(first, { key: "ArrowDown" });
  expect(document.activeElement).toBe(container.querySelector("td.trin-cell[data-r='1'][data-c='0']"));
  fireEvent.keyDown(document.activeElement, { key: "ArrowRight" });
  expect(document.activeElement).toBe(container.querySelector("td.trin-cell[data-r='1'][data-c='1']"));
});

test("fast formatter matches the previous toLocaleString output", () => {
  const legacy = (v) => {
    const sign = v < 0 ? "-" : "";
    const a = Math.abs(v);
    if (a < 50) return `${sign}$0.0K`;
    if (a >= 1e9) return `${sign}$${(a / 1e6).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`;
    return `${sign}$${(a / 1e3).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}K`;
  };
  for (const v of [0, 12, 49.9, 50, 777, 1234.56, -98765.4, 5e6, 123456789.9, -2.5e9, 7.77e12]) {
    expect(fmtK(v)).toBe(legacy(v));
  }
  expect(fmtK(null)).toBe("");
  expect(fmtK(NaN)).toBe("");
});
