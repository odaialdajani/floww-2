/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import TrinityView from "./TrinityView";
import useScreenContext from "../agent/useScreenContext";

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("./triad/useReviewJournal", () => ({ useReviewJournal: () => ({ reviewQueue: [], reviewState: null }) }));
const E1 = "2031-01-17", E2 = "2031-01-24";
const contract = { osi: "SPY310124C00100500", strike: 100.5, expiry: E2, type: "call", delta: .5, bid: 1, ask: 1.2 };
function packet(ticker = "SPY") { return { ticker, spot: 102, snapshotId: `${ticker}-snap`, asof: "2031-01-16T15:00:00Z",
  strikes: [{ strike: 101 }, { strike: 100.5 }], grid: { expiries: [E1, E2], strikes: [101, 100.5], grid: { [E1]: { 101: -20000 }, [E2]: { "100.5": 100000 } } },
  metrics: { walls: [{ wall_id: "wall", low: 100, high: 101, mid: 100.75, members: [101, 100.5], gross: 120000, net: 80000 }],
    wall_metrics: { wall: { daddex_net: 40000, daddex_gross: 60000, daddex_usable: 2, daddex_missing: 0, session_delta_volume_net: 5000, session_delta_volume_gross: 5000, session_delta_volume_usable: 1, session_delta_volume_missing: 0 } },
    grids: { delta: { expiries: [E1, E2], strikes: [101, 100.5], grid: { [E1]: { 101: -10000 }, [E2]: { "100.5": 50000 } } },
      session_delta_volume: { expiries: [E2], strikes: [101, 100.5], grid: { [E2]: { "100.5": 5000 } } } } },
  quality: { state: "usable", setupEligible: false, reasonCodes: ["PRICE_HISTORY_MISSING"] },
  scout: { shortlist: { CALLS: [contract], PUTS: [] } } }; }
function Context() { const [c] = useScreenContext(); return <output data-testid="r11-context">{JSON.stringify(c)}</output>; }
beforeEach(() => {
  sessionStorage.clear();
  axios.get.mockImplementation(async url => String(url).includes("/heatmap/") ? { data: packet(String(url).includes("QQQ") ? "QQQ" : "SPY") } : { data: { decisions: [], frames: [], rows: [] } });
});
const mount = async () => { await act(async () => render(<><TrinityView /><Context /></>)); };

test("raw-wall-first desk exposes top profile, one adjustment selector, and honest readiness", async () => {
  await mount();
  expect(screen.getByTestId("triad-signed-profile")).toBeInTheDocument();
  expect(screen.getByLabelText("Adjusted context")).toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByTestId("triad-wall-wall")); });
  expect(screen.getByTestId("triad-readiness")).toHaveTextContent("Wait");
  expect(screen.getByTestId("triad-readiness")).toHaveTextContent("Bounce watch");
  fireEvent.change(screen.getByLabelText("Adjusted context"), { target: { value: "session_delta_volume" } });
  expect(screen.getByTestId("triad-pane-adjusted")).toHaveTextContent("$5.0K");
  expect(screen.getByTestId("triad-pane-raw").querySelector(".trin-wall-member")).not.toBeNull();
  expect(screen.getByTestId("triad-pane-adjusted").querySelector(".trin-wall-member")).not.toBeNull();
});

test("contract review requires choosing listed identity, not midpoint or first expiry", async () => {
  await mount();
  await act(async () => { fireEvent.click(screen.getByTestId("triad-wall-wall")); });
  fireEvent.click(screen.getByTestId("triad-contracts-btn"));
  expect(axios.get.mock.calls.some(([url]) => String(url).includes("/contract"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: `Review ${contract.osi}` }));
  await waitFor(() => expect(axios.get.mock.calls.some(([url]) => String(url).includes("/solstice/SPY/contract"))).toBe(true));
  const req = axios.get.mock.calls.find(([url]) => String(url).includes("/solstice/SPY/contract"));
  expect(req[1].params).toEqual({ osi: contract.osi, snapshot_id: "SPY-snap" });
  expect(req[1].params.strike).toBeUndefined();
});

test("changing symbol releases wall and exact-contract response ownership, including late errors", async () => {
  let rejectOld;
  const defaultMock = axios.get.getMockImplementation();
  axios.get.mockImplementation((url, opts) => String(url).includes("/solstice/SPY/contract") ? new Promise((resolve, reject) => { rejectOld = reject; }) : defaultMock(url, opts));
  await mount();
  await act(async () => { fireEvent.click(screen.getByTestId("triad-wall-wall")); });
  fireEvent.click(screen.getByTestId("triad-contracts-btn"));
  fireEvent.click(screen.getByRole("button", { name: `Review ${contract.osi}` }));
  fireEvent.change(screen.getByTestId("triad-symbol-input"), { target: { value: "QQQ" } });
  await act(async () => { fireEvent.click(screen.getByTestId("triad-symbol-go")); });
  await act(async () => { rejectOld(new Error("old SPY detail failure")); });
  expect(screen.queryByTestId("triad-contract-drawer")).not.toBeInTheDocument();
  expect(JSON.parse(screen.getByTestId("r11-context").textContent)).toMatchObject({ page: "trinity", ticker: "QQQ", selectedWall: null });
});
