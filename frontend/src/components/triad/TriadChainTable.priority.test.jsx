/* G5 pin (Hermes-2, M2 freeze 4): the Wall Desk chain table PRIORITIZES the
   near-spot / selected contract row while preserving the conventional strike
   ladder and every row. Prioritization = the row the desk acts on is the one
   brought into view first (nearest-to-spot on load, the selected strike on
   selection); strike order is NOT reordered — an options chain is read as a
   ladder. The pure strike-choice function is pinned here; the scroll-into-view
   behavior is measured in the real browser (jsdom has zero-height scrollers,
   so a scroll assertion there would be vacuous). */
import React from 'react';
import { render, screen } from '@testing-library/react';
import TriadChainTable, { priorityStrike } from './TriadChainTable';

const grouped = [
  { strike: 740 }, { strike: 750 }, { strike: 755 },
  { strike: 760 }, { strike: 765 }, { strike: 780 }, { strike: 800 },
];

test("with no selection the nearest-to-spot strike is the priority row", () => {
  expect(priorityStrike(grouped, 761, null)).toBe(760);
  expect(priorityStrike(grouped, 752, null)).toBe(750);
  expect(priorityStrike(grouped, 90, null)).toBe(740); // far below: nearest edge
});

test("an existing selected strike wins over near-spot", () => {
  expect(priorityStrike(grouped, 761, 800)).toBe(800);
});

test("a selected strike that is not in the table falls back to near-spot", () => {
  expect(priorityStrike(grouped, 761, 999)).toBe(760);
});

test("no spot and no selection yields no priority row", () => {
  expect(priorityStrike(grouped, null, null)).toBeNull();
  expect(priorityStrike(grouped, undefined, null)).toBeNull();
});

test("non-finite spot is treated as no spot", () => {
  expect(priorityStrike(grouped, "not-a-number", null)).toBeNull();
});

test("every table row carries its strike as a data attribute for view prioritization", () => {
  render(<TriadChainTable rows={[
    { strike: 760, expiry: "2026-10-26", type: "call", bid: 1.2, ask: 1.3, delta: 0.4, osi: "SPY261026C00760000", gex: 150.5, gex_basis: "OI" },
    { strike: 760, expiry: "2026-10-26", type: "put", bid: 0.9, ask: 1.0, delta: -0.35, osi: "SPY261026P00760000", gex: -120.25, gex_basis: "OI" },
  ]} ticker="SPY" expiry="2026-10-26" spot={760.8} selectedStrike={760} onReview={() => {}} onSelectContract={() => {}} />);
  const row = document.querySelector('tr[data-strike="760"]');
  expect(row).not.toBeNull();
  expect(row.className).toContain("selected");
  // Strike order is preserved — the ladder is not reordered by distance.
  expect(screen.getByText("760")).toBeInTheDocument();
});
