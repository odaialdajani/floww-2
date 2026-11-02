/** @jest-environment jsdom */
import React from "react";
import { render, screen, within, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import SolsticeSymbolMaps from "./SolsticeSymbolMaps";
import useScreenContext from "../../agent/useScreenContext";

jest.mock("axios", () => ({ get: jest.fn() }));
jest.mock("./AskFlow", () => {
  const React = require("react");
  return {
    __esModule: true,
    default: ({ subject }) => React.createElement("output", { "data-testid": "askflow-subject" }, subject),
  };
});

const exp = "2031-01-17";
function packet(ticker, strike, value) {
  return { ticker, spot: strike + .25, snapshotId: `${ticker}-snapshot`, formula_version: "gex.v2", data_source: "fixture", asof: "2031-01-16T15:00:00Z",
    map_query: { expiries: 4, mode: "day", dte: null, scalp: false, withTaps: true, maxStrikes: 200 },
    grid: { strikes: [strike + 1, strike], expiries: [exp], grid: { [exp]: { [strike]: value } } },
    metrics: { walls: [{ wall_id: `${ticker}-wall`, low: strike, high: strike + 1, members: [strike], gross: value, net: value }] },
    quality: { state: "partial", reasonCodes: ["UNKNOWN_SOURCE_AGE"], setupEligible: false } };
}
function Context() { const [c] = useScreenContext(); return <output data-testid="symbol-context">{JSON.stringify(c)}</output>; }
const context = () => JSON.parse(screen.getByTestId("symbol-context").textContent);
const heading = () => screen.getByTestId("solstice-symbol-maps").querySelector(".solstice-symbol-heading");
const paneButtons = () => within(heading()).getAllByRole("button").filter(button => button.hasAttribute("aria-pressed"));
const pressedSymbol = () => (paneButtons().find(button => button.getAttribute("aria-pressed") === "true") || {}).textContent;

beforeEach(() => {
  axios.get.mockImplementation(async url => {
    const name = decodeURIComponent(String(url).split("/").pop());
    if (name === "SPY") return { data: packet("SPY", 100, 100000) };
    if (name === "QQQ") return { data: packet("QQQ", 400, 50000) };
    throw new Error("fixture unavailable");
  });
});

test("a ticker change moves the pane set, the inspector, the published context and the ask subject to the new ticker", async () => {
  let view;
  await act(async () => { view = render(<><SolsticeSymbolMaps ticker="SPY" data={packet("SPY", 100, 100000)} /><Context /></>); });
  expect(pressedSymbol()).toBe("SPY");
  await act(async () => { view.rerender(<><SolsticeSymbolMaps ticker="QQQ" data={packet("QQQ", 400, 50000)} /><Context /></>); });
  expect(pressedSymbol()).toBe("QQQ");
  expect(screen.getByTestId("symbol-map-inspector")).toHaveTextContent("QQQ");
  expect(context()).toMatchObject({ ticker: "QQQ" });
  expect(screen.getByTestId("askflow-subject")).toHaveTextContent("QQQ");
});

test("the active symbol never leaves the visible pane set after a pane-count change", async () => {
  await act(async () => render(<><SolsticeSymbolMaps ticker="SPY" data={packet("SPY", 100, 100000)} /><Context /></>));
  await act(async () => { fireEvent.click(within(heading()).getByRole("button", { name: "Four symbols" })); });
  const iwm = within(heading()).getAllByRole("button", { name: "IWM" }).find(button => button.hasAttribute("aria-pressed"));
  await act(async () => { fireEvent.click(iwm); });
  expect(pressedSymbol()).toBe("IWM");
  await act(async () => { fireEvent.click(within(heading()).getByRole("button", { name: "Two symbols" })); });
  expect(paneButtons().map(button => button.textContent)).toEqual(["SPY", "QQQ"]);
  expect(pressedSymbol()).toBe("SPY");
  expect(screen.getByTestId("symbol-map-inspector")).toHaveTextContent("SPY");
  expect(context()).toMatchObject({ ticker: "SPY" });
  expect(screen.getByTestId("askflow-subject")).toHaveTextContent("SPY");
});

test("independent symbols survive the ticker change: each pane keeps its own axis", async () => {
  let view;
  await act(async () => { view = render(<><SolsticeSymbolMaps ticker="SPY" data={packet("SPY", 100, 100000)} /><Context /></>); });
  await act(async () => { view.rerender(<><SolsticeSymbolMaps ticker="QQQ" data={packet("QQQ", 400, 50000)} /><Context /></>); });
  const spy = screen.getByTestId("symbol-map-SPY"), qqq = screen.getByTestId("symbol-map-QQQ");
  expect(within(spy).getByRole("gridcell", { name: /^100 by/ })).toBeInTheDocument();
  expect(within(qqq).getByRole("gridcell", { name: /^400 by/ })).toBeInTheDocument();
  expect(within(qqq).queryByRole("gridcell", { name: /^100 by/ })).not.toBeInTheDocument();
});
