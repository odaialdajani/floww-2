/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent, act, waitFor, within } from "@testing-library/react";
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

test("Triad follows the shared symbol and clears a wall on a header symbol change",async()=>{
 let view;
 await act(async()=>{view=render(<><TrinityView ticker="QQQ"/><Context/></>);});
 expect(JSON.parse(screen.getByTestId("r11-context").textContent).ticker).toBe("QQQ");
 fireEvent.click(screen.getByTestId("triad-wall-wall"));
 await act(async()=>view.rerender(<><TrinityView ticker="SPY"/><Context/></>));
 expect(JSON.parse(screen.getByTestId("r11-context").textContent)).toMatchObject({ticker:"SPY",selectedWall:null,selectedContract:null});
});

test("Triad starts with same-session scope and session Volume × absolute delta, not copied OI", async () => {
 await mount();
 expect(screen.getByLabelText("Triad expiry scope")).toHaveValue("0dte");
 expect(screen.getByLabelText("Adjusted context")).toHaveValue("session_delta_volume");
 expect(screen.getByTestId("triad-activity-coverage")).toHaveTextContent("Volume window: unavailable");
 expect(axios.get.mock.calls.some(([url])=>String(url).includes("dte=0"))).toBe(true);
 expect(screen.getByTestId("triad-pane-adjusted")).toHaveTextContent("$5.0K");
});

test("a requested 0DTE scope cannot relabel an explicitly loaded multi-expiry observation",async()=>{
 const ordinary=axios.get.getMockImplementation();
 axios.get.mockImplementation(async(url,opts)=>String(url).includes("/heatmap/")?{data:{...packet(),map_query:{mode:"day",expiries:4,dte:null}}}:ordinary(url,opts));
 await mount();
 expect(screen.getByTestId("triad-scope-admission")).toHaveTextContent("Same-day admission unavailable");
 expect(JSON.parse(screen.getByTestId("r11-context").textContent).dte).toBe("all");
});

test("Raw and adjusted share expiry/strike rails and a zero-anchored range without borrowing missing activity",async()=>{
 await mount();
 const raw=screen.getByTestId("triad-pane-raw"),adjusted=screen.getByTestId("triad-pane-adjusted");
 expect(within(adjusted).getByRole("gridcell",{name:new RegExp(`^101 by ${E1},`)})).toHaveTextContent("—");
 const labels=p=>[...p.querySelectorAll(".trin-legend-label")].map(e=>e.textContent);
 expect(labels(adjusted)).toEqual(labels(raw));
 expect(raw.querySelector(".trin-legend-scale")).toHaveTextContent("locked scale");
});

test("Triad timeline restores the stored pair without fetching live Greeks and returns deliberately to live", async () => {
 const p=packet();
 const ordinary=axios.get.getMockImplementation();
 axios.get.mockImplementation(async(url,opts)=>{
  if(String(url).includes("/manifest/"))return {data:{day:"2031-01-16",snapshots:[{id:"stored-pair",asof:p.asof}],gaps:[]}};
  if(String(url).includes("/replay/stored-pair"))return {data:{snapshot:{snapshot_id:"stored-pair",ticker:"SPY",asof_ts:p.asof,spot:p.spot},
   grids:{grid:p.grid,...p.metrics.grids},metrics_full:p.metrics,walls:p.metrics.walls,strikes:p.strikes,
   context:{display:{map_query:{dte:0,mode:"day",expiries:4}}}}};
  return ordinary(url,opts);
 });
 await mount();
 await act(async()=>fireEvent.click(screen.getByTestId("solstice-replay-load")));
 const liveReads=axios.get.mock.calls.filter(([url])=>String(url).includes("/heatmap/")).length;
 await act(async()=>fireEvent.click(screen.getByTestId("solstice-replay-play")));
 expect(JSON.parse(screen.getByTestId("r11-context").textContent)).toMatchObject({displayMode:"replay",snapshotId:"stored-pair"});
 expect(screen.getByTestId("triad-pane-adjusted")).toHaveTextContent("$5.0K");
 expect(screen.getByTestId("triad-pane-raw")).toHaveTextContent("$100.0K");
 expect(axios.get.mock.calls.filter(([url])=>String(url).includes("/heatmap/")).length).toBe(liveReads);
 expect(axios.get.mock.calls.some(([url])=>/greeks|quotes/.test(String(url)))).toBe(false);
 await act(async()=>fireEvent.click(screen.getByTestId("solstice-replay-exit")));
 expect(JSON.parse(screen.getByTestId("r11-context").textContent)).toMatchObject({displayMode:"live",snapshotId:"SPY-snap"});
 expect(axios.get.mock.calls.filter(([url])=>String(url).includes("/heatmap/")).length).toBe(liveReads+1);
});

test("Next listed requests server-owned scope and never sends a guessed date or zero DTE", async () => {
  await mount();
  expect(screen.getByRole("option", { name: /Next listed/ })).not.toBeDisabled();
  await act(async () => { fireEvent.change(screen.getByLabelText("Triad expiry scope"), { target: { value: "next" } }); });
  const urls = axios.get.mock.calls.map(([url]) => String(url));
  const next = urls.find(url => url.includes("expiry_scope=next"));
  expect(next).toBeDefined();
  expect(next).not.toMatch(/dte=|sessionDate=|expiry=/);
});

test("recorded Next listed scope restores without a second fetch or a live substitute", async () => {
  sessionStorage.setItem("solstice.triadHandoff", JSON.stringify({ ticker: "SPY", replayAsOf: "2031-01-16T15:00:00Z", snapshotId: "recorded-next" }));
  const p = packet();
  const query = { expiries: 4, mode: "day", dte: null, scalp: false, withTaps: true, maxStrikes: 80, expiryScope: "next", sessionDate: "2031-01-16" };
  axios.get.mockImplementation(async url => String(url).includes("/replay/") ? { data: {
    snapshot: { snapshot_id: "recorded-next", ticker: "SPY", asof_ts: p.asof, spot: p.spot, data_source: "fixture", formula_version: "gex.v2" },
    grids: { grid: p.grid, delta: p.metrics.grids.delta }, metrics_full: p.metrics, walls: p.metrics.walls,
    context: { display: { map_query: query } }, strikes: p.strikes,
  } } : { data: { rows: [], decisions: [] } });
  await mount();
  expect(screen.getByLabelText("Triad expiry scope")).toHaveValue("next");
  expect(screen.getByLabelText("Triad expiry scope")).toBeDisabled();
  expect(axios.get.mock.calls.filter(([url]) => String(url).includes("/replay/")).length).toBe(1);
  expect(axios.get.mock.calls.some(([url]) => String(url).includes("/heatmap/"))).toBe(false);
  expect(JSON.parse(screen.getByTestId("r11-context").textContent).mapQuery).toEqual(query);
});

test("raw-wall-first desk exposes top profile, one adjustment selector, and honest readiness", async () => {
  await mount();
  fireEvent.change(screen.getByLabelText("Adjusted context"), { target: { value: "delta" } });
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

test("resolved contract becomes the canonical Triad selection and basis changes invalidate it",async()=>{
 const ordinary=axios.get.getMockImplementation();
 axios.get.mockImplementation(async(url,opts)=>String(url).includes("/contract")?{data:{status:"ok",ticker:"SPY",snapshot_id:"SPY-snap",matched_identity:{...contract,strike:String(contract.strike)}}}:ordinary(url,opts));
 await mount();
 fireEvent.click(screen.getByTestId("triad-wall-wall"));
 fireEvent.click(screen.getByTestId("triad-contracts-btn"));
 fireEvent.click(screen.getByRole("button",{name:`Review ${contract.osi}`}));
 const current=()=>JSON.parse(screen.getByTestId("r11-context").textContent);
 await waitFor(()=>expect(current()).toMatchObject({selectedContract:{osi:contract.osi},selectedStrike:100.5,selectedExpiry:E2,contractResolution:"resolved"}));
 fireEvent.change(screen.getByLabelText("Adjusted context"),{target:{value:"delta"}});
 expect(current().selectedContract).toBeNull();
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
