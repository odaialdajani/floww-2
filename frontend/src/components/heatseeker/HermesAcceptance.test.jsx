/** @jest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import SkylitHeatmapGrid from "./SkylitHeatmapGrid";
import WallInspector from "./WallInspector";
import { surfaceStatus, sumProfile } from "../../lib/solsticeMetrics";

const EXP = "2031-06-18";
function packet() {
  return {
    ticker: "HERMES", spot: 200,
    grid: { expiries: [EXP], strikes: [200, 210, 220, 230],
      grid: { [EXP]: { 200: 100000, 210: -100000 } } },
    metrics: {
      walls: [{ wall_id: "h", low: 200, high: 210, members: [200, 210, 220], gross: 0, net: -20000 }],
      grids: {
        delta: { expiries: [EXP], grid: { [EXP]: { 200: 40000, 210: -60000 } },
          usable: 2, missing_delta: 1, invalid_delta: 3,
          cell_missing_delta: { [EXP]: { 220: 1 } }, cell_invalid_delta: { [EXP]: { 210: 1, 230: 2 } },
          exposure_basis: "OI_DELTA_WEIGHTED", status: "ok" },
      },
      wall_metrics: { h: { daddex_gross: -20000, daddex_net: -20000, daddex_usable: 2,
        daddex_missing: 1, daddex_invalid: 1 } },
      surface_coverage: {
        delta: { status: "partial", usable: 2, missing_delta: 1, invalid_delta: 3 },
      },
    },
  };
}

test("coverage keeps invalid distinct and forces partial", () => {
  const s = surfaceStatus(packet(), "delta");
  expect(s).toMatchObject({ status: "partial", missing: 1, invalidDelta: 3 });
});

test("profile carries invalid strikes without inventing values", () => {
  const d = sumProfile(packet(), "delta", [EXP]);
  expect(d.values["200"]).toBe(40000);
  expect(d.values["220"]).toBeUndefined();
  expect(d.partial["220"]).toBe(1);
  expect(d.invalid["210"]).toBe(1);
  expect(d.invalid["230"]).toBe(2);
});

test("mounted grid marks unknown and invalid cells distinctly, never zero", () => {
  const { container } = render(<SkylitHeatmapGrid data={packet()} spot={205} ticker="HERMES" metric="delta" />);
  const bad = Array.from(container.querySelectorAll("td.trin-invalid"));
  expect(bad).toHaveLength(2); // valued partial cell + absent invalid cell
  expect(bad.every((td) => !/\$0/.test(td.textContent))).toBe(true);
  const unknown = Array.from(container.querySelectorAll("td.trin-missing"))
    .filter((td) => /delta unknown/.test(td.getAttribute("aria-label") || ""));
  expect(unknown).toHaveLength(1);
});

test("wall inspector names invalid delta readings explicitly", () => {
  const p = packet();
  render(<WallInspector wall={p.metrics.walls[0]} metrics={p.metrics} />);
  expect(screen.getByTestId("wall-compare-table").textContent).toMatch(/δ-invalid/);
});
