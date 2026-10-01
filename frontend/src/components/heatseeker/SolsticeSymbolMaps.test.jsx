/** @jest-environment jsdom */
import React from "react";
import { render, screen, within, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import SolsticeSymbolMaps from "./SolsticeSymbolMaps";
import useScreenContext from "../../agent/useScreenContext";

jest.mock("axios", () => ({ get: jest.fn() }));
const exp = "2031-01-17";
function packet(ticker, strike, value) { return { ticker, spot: strike + .25, snapshotId: `${ticker}-snapshot`, formula_version: "gex.v2", data_source: "fixture", asof: "2031-01-16T15:00:00Z",
  map_query: { expiries: 4, mode: "day", dte: null, scalp: false, withTaps: true, maxStrikes: 200 },
  grid: { strikes: [strike + 1, strike], expiries: [exp], grid: { [exp]: { [strike]: value } } },
  metrics: { walls: [{ wall_id: `${ticker}-wall`, low: strike, high: strike + 1, members: [strike], gross: value, net: value }] },
  quality: { state: "partial", reasonCodes: ["UNKNOWN_SOURCE_AGE"], setupEligible: false } }; }
function Context() { const [c] = useScreenContext(); return <output data-testid="symbol-context">{JSON.stringify(c)}</output>; }
beforeEach(() => { axios.get.mockImplementation(async url => {
  if (String(url).includes("QQQ")) return { data: packet("QQQ", 400, 50000) };
  throw new Error("fixture unavailable");
}); });

test("two symbols use independent axes and active map owns the one inspector/context", async () => {
  await act(async () => render(<><SolsticeSymbolMaps ticker="SPY" data={packet("SPY", 100, 100000)} /><Context /></>));
  const spy = screen.getByTestId("symbol-map-SPY"), qqq = screen.getByTestId("symbol-map-QQQ");
  expect(within(spy).getByRole("gridcell", { name: /^100 by/ })).toBeInTheDocument();
  expect(within(qqq).getByRole("gridcell", { name: /^400 by/ })).toHaveTextContent("$50.0K");
  expect(within(qqq).queryByRole("gridcell", { name: /^100 by/ })).not.toBeInTheDocument();
  await act(async () => { fireEvent.click(within(qqq).getByRole("gridcell", { name: /^400 by/ })); });
  expect(screen.getByTestId("symbol-map-inspector")).toHaveTextContent("QQQ");
  expect(JSON.parse(screen.getByTestId("symbol-context").textContent)).toMatchObject({ ticker: "QQQ", selectedWall: "QQQ-wall", selectedStrike: 400 });
});

test("four-map missing SPX is explicit; never borrows SPY", async () => {
  await act(async () => render(<SolsticeSymbolMaps ticker="SPY" data={packet("SPY", 100, 100000)} />));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Four symbols" })); });
  const spx = screen.getByTestId("symbol-map-^SPX");
  expect(spx).toHaveTextContent("SPX unavailable");
  expect(within(spx).queryByRole("grid")).not.toBeInTheDocument();
});

test("replay uses only supplied recorded packet; no fresh cross-symbol requests", async () => {
  await act(async () => render(<SolsticeSymbolMaps ticker="SPY" data={packet("SPY", 100, 100000)} replay />));
  expect(axios.get).not.toHaveBeenCalled();
  expect(screen.getByTestId("symbol-map-QQQ")).toHaveTextContent("Recorded frame unavailable");
});
