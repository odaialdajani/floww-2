/**
 * WallInspector focused-context tests (2026-10-17).
 *
 * The compact same-wall summary must carry the exact missingness semantics
 * of the deeper CompareTable (shared helpers, so they cannot drift):
 *   - a measured zero (usable inputs present, value 0) renders "$0 / $0";
 *   - missing inputs (usable == 0) render "—" with the reason — never $0;
 *   - values are WALL-LOCAL: another wall's breakdown and scope-wide
 *     scalars must never appear in the summary;
 *   - bases are declared per family and the volume family is explicitly
 *     not trade-signed flow; nothing here is an entry or a guaranteed
 *     dealer reaction.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import WallInspector from "./WallInspector";

const wall = { wall_id: "w", low: 100, high: 100, members: [100], gross: 1_100_000, net: 900_000 };

const wbOf = (fields) => ({ wall_metrics: { w: fields } });

test("measured zero with usable inputs is a real $0 reading in the compact summary", () => {
  render(<WallInspector wall={wall} metrics={wbOf({
    daddex_gross: 0, daddex_net: 0, daddex_usable: 3, daddex_missing: 1, daddex_invalid: 0,
    session_delta_volume_gross: 0, session_delta_volume_net: 0,
    session_delta_volume_usable: 2, session_delta_volume_missing: 0, session_delta_volume_invalid: 0,
  })} />);
  const delta = screen.getByTestId("wall-focused-delta");
  expect(delta.textContent).toContain("$0 / $0");
  expect(delta.textContent).toContain("usable 3");
  expect(delta.textContent).toContain("1 δ-missing");
  const vol = screen.getByTestId("wall-focused-voldelta");
  expect(vol.textContent).toContain("$0 / $0");
  expect(vol.textContent).toContain("usable 2");
});

test("missing delta and missing volume stay missing — never a zero", () => {
  render(<WallInspector wall={wall} metrics={wbOf({
    daddex_gross: 0, daddex_net: 0, daddex_usable: 0, daddex_missing: 2, daddex_invalid: 1,
    session_delta_volume_gross: null, session_delta_volume_net: null,
    session_delta_volume_usable: 0, session_delta_volume_missing: 2, session_delta_volume_invalid: 0,
  })} />);
  const delta = screen.getByTestId("wall-focused-delta");
  expect(delta.textContent).not.toContain("$0");
  expect(delta.textContent).toContain("— (2 δ-missing, 1 δ-invalid (unusable reading))");
  expect(delta.textContent).toContain("usable 0");
  const vol = screen.getByTestId("wall-focused-voldelta");
  expect(vol.textContent).not.toContain("$0");
  expect(vol.textContent).toContain("—");
  expect(vol.textContent).toContain("usable 0");
  expect(vol.textContent).toContain("2 missing");
});

test("the summary is wall-local: this wall's breakdown only, never another wall or scope totals", () => {
  render(<WallInspector wall={wall} metrics={{
    // Scope-wide scalars and ratio — must never surface in the summary.
    dadgex_gross: 5_500_000, dadgex_net: 5_000_000,
    magnitude_ratio_delta_over_raw: 1.234,
    wall_metrics: {
      other: {
        daddex_gross: 9_900_000, daddex_net: 9_000_000, daddex_usable: 9, daddex_missing: 0, daddex_invalid: 0,
        session_delta_volume_gross: 8_800_000, session_delta_volume_net: 8_000_000,
        session_delta_volume_usable: 8, session_delta_volume_missing: 0, session_delta_volume_invalid: 0,
      },
      w: {
        daddex_gross: 1_200_000, daddex_net: 1_000_000, daddex_usable: 4, daddex_missing: 0, daddex_invalid: 0,
        session_delta_volume_gross: 700_000, session_delta_volume_net: 600_000,
        session_delta_volume_usable: 3, session_delta_volume_missing: 0, session_delta_volume_invalid: 0,
      },
    },
  }} />);
  const summary = screen.getByTestId("wall-focused-context");
  expect(summary.textContent).toContain("$1.1M / $900.0K"); // raw from the wall record
  expect(summary.textContent).toContain("$1.2M / $1.0M"); // this wall's OI × |Δ|
  expect(summary.textContent).toContain("$700.0K / $600.0K"); // this wall's vol × |Δ|
  expect(summary.textContent).not.toContain("$9.9M");    // other wall's Δ
  expect(summary.textContent).not.toContain("$8.8M");    // other wall's vol × |Δ|
  expect(summary.textContent).not.toContain("$5.5M");    // scope Δ gross
  expect(summary.textContent).not.toContain("1.234");    // scope Δ/raw ratio
});

test("bases are declared per family and the volume family is not trade-signed flow", () => {
  render(<WallInspector wall={wall} metrics={wbOf({
    daddex_gross: 1_200_000, daddex_net: 1_000_000, daddex_usable: 4, daddex_missing: 0, daddex_invalid: 0,
    session_delta_volume_gross: 700_000, session_delta_volume_net: 600_000,
    session_delta_volume_usable: 3, session_delta_volume_missing: 0, session_delta_volume_invalid: 0,
    bases: { daddex: "OI_DELTA_WEIGHTED", volume: "VOLUME", session_delta_volume: "VOLUME_DELTA_WEIGHTED" },
  })} />);
  const raw = screen.getByTestId("wall-focused-raw");
  expect(raw.textContent).toContain("USD/1% move · OI · gex.v2");
  const delta = screen.getByTestId("wall-focused-delta");
  expect(delta.textContent).toContain("OI_DELTA_WEIGHTED");
  const vol = screen.getByTestId("wall-focused-voldelta");
  expect(vol.textContent).toContain("VOLUME_DELTA_WEIGHTED");
  expect(vol.textContent).toContain("not trade-signed flow");
  const summary = screen.getByTestId("wall-focused-context");
  expect(summary.textContent).not.toMatch(/entry|guaranteed|will hedge/);
});

test("no wall breakdown renders the summary with honest gaps, not fabricated zeros", () => {
  render(<WallInspector wall={wall} metrics={null} />);
  const summary = screen.getByTestId("wall-focused-context");
  expect(summary.textContent).toContain("$1.1M / $900.0K"); // raw wall record survives
  expect(screen.getByTestId("wall-focused-delta").textContent).toContain("—");
  expect(screen.getByTestId("wall-focused-delta").textContent).toContain("no wall breakdown");
  expect(screen.getByTestId("wall-focused-voldelta").textContent).toContain("no wall breakdown");
  expect(summary.textContent).not.toContain("$0");
});

test("window activity chip shows the wall-local window value with member coverage", () => {
  render(<WallInspector wall={wall} metrics={{
    window_daddex_v1: 5_000_000, // scope scalar — never rendered as wall-local
    window_dadgex_reason: null,
    wall_window: {
      other: { window_daddex: 8_800_000, coverage: { active_strikes: 9, member_strikes: 9 } },
      w: { window_daddex: 250_000, coverage: { active_strikes: 2, member_strikes: 3 } },
    },
  }} />);
  const chip = screen.getByTestId("wall-focused-window");
  expect(chip.textContent).toContain("$250.0K");
  expect(chip.textContent).toContain("2/3 strikes");
  expect(chip.textContent).toContain("window Δ-weighted");
  expect(chip.textContent).not.toContain("$8.8M"); // other wall's window
  expect(chip.textContent).not.toContain("5,000,000"); // scope scalar
});

test("window absence states its reason — never a zero", () => {
  const { rerender } = render(<WallInspector wall={wall} metrics={{ window_dadgex_reason: "VOLUME_REBASE" }} />);
  let chip = screen.getByTestId("wall-focused-window");
  expect(chip.textContent).toContain("unavailable — volume rebase");
  expect(chip.textContent).not.toContain("$0");
  rerender(<WallInspector wall={wall} metrics={{ window_daddex_reason: "PROVIDER_MISMATCH" }} />);
  chip = screen.getByTestId("wall-focused-window");
  expect(chip.textContent).toContain("unavailable — PROVIDER_MISMATCH");
  rerender(<WallInspector wall={wall} metrics={{}} />);
  chip = screen.getByTestId("wall-focused-window");
  expect(chip.textContent).toContain("unavailable — no comparable window");
});
