/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import ExactContractReview from "./ExactContractReview";
import { admissionBlock } from "./AskLodestar";
import SkylitDashboard from "./SkylitDashboard";
import useScreenContext from "../../agent/useScreenContext";

jest.mock("./SkylitTickerBar", () => ({ __esModule: true, default: () => null, TICKER_SETS: { popular: ["SPY", "QQQ"] } }));
jest.mock("./StockDirectory", () => () => null);
jest.mock("./PriceNodeHistory", () => () => null);
jest.mock("./ExposureStrip", () => () => null);
jest.mock("../flowseeker/AlertEngineStrip", () => () => null);
jest.mock("./SkylitMetricsSidebar", () => () => null);

jest.mock("axios", () => ({ get: jest.fn() }));
const identity = { osi: "SPY260918C00100000", strike: "100.0000000000000000001", expiry: "2026-09-18", type: "call", series: "SPY" };
const data = { snapshotId: "snap1", grid: { expiries: [identity.expiry] }, scout: { shortlist: { CALLS: [{ ...identity, strike: 100 }] } } };
const body = { ticker: "SPY", snapshot_id: "snap1", status: "ok", matched_identity: identity,
  quote: { bid: 0, ask: 1, ages_s: { bid: 30, ask: 20 }, quote_source: "fixture" }, multiplier: { value: "100", source: "listed-spec" } };
const context = { contextVersion: 2, ticker: "SPY", snapshotId: "snap1", mapQuery: { mode: "day" },
  mapVersion: "2026-09-11T18:00:00Z", provider: "fixture", formula: "gex.v2", metric: "gex", activePane: "gex",
  overlayMetric: "raw", displayMode: "live", selectedStrike: 100, selectedExpiry: identity.expiry,
  mapStrikes: [100], mapExpiries: [identity.expiry], selectedContract: identity, contractResolution: "resolved" };
const props = { ticker: "SPY", data, wall: { wall_id: "w1", low: 99, high: 101 }, selectionScope: "gex|raw" };
const defer = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return {promise,resolve,reject}; };
beforeEach(() => axios.get.mockReset());
function ContextProbe() { const [context] = useScreenContext(); return <output data-testid="context-probe">{JSON.stringify(context)}</output>; }
function ControlledCanvas({scene}) { const [view,setView] = React.useState("gex"); return <><SkylitDashboard ticker="SPY" spot={100} data={scene} viewMode={view} onViewModeChange={setView} /><ContextProbe /></>; }

test("complete contract selector is admitted; missing, pending and cell-conflicting selectors are not", () => {
  expect(admissionBlock({ context, overlayMetric: "raw", displayMode: "live" })).toBeNull();
  for (const changes of [{contractResolution:"pending"}, {selectedContract:{osi:identity.osi}}, {selectedStrike:101}, {snapshotId:null}]) {
    expect(admissionBlock({ context: {...context,...changes}, overlayMetric:"raw", displayMode:"live" })).toMatch(/contract|selection|identity/i);
  }
});

test("recorded response publishes selectors only, including the exact decimal, and exposes zero/age/source with AI closed", async () => {
  axios.get.mockResolvedValue({data:body});
  const onSelection = jest.fn();
  render(<ExactContractReview {...props} onSelection={onSelection} />);
  fireEvent.click(screen.getByRole("button", {name:/Review SPY/}));
  await waitFor(() => expect(onSelection).toHaveBeenLastCalledWith(expect.objectContaining({ticker:"SPY",snapshotId:"snap1",wallId:"w1",identity,status:"resolved"})));
  const selection = onSelection.mock.calls.at(-1)[0];
  expect(selection).not.toHaveProperty("quote");
  expect(selection.identity).not.toHaveProperty("bid");
  expect(screen.getByTestId("exact-contract-result")).toHaveTextContent("0 / 1");
  expect(screen.getByTestId("exact-contract-result")).toHaveTextContent("30 / 20");
  expect(screen.getByTestId("exact-contract-result")).toHaveTextContent("listed-spec");
});

test("a conflicting owning snapshot is refused, not shown or published as resolved", async () => {
  axios.get.mockResolvedValue({data:{...body,snapshot_id:"other"}});
  const onSelection = jest.fn();
  render(<ExactContractReview {...props} onSelection={onSelection} />);
  fireEvent.click(screen.getByRole("button",{name:/Review SPY/}));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/identity|snapshot|selection/i));
  expect(screen.queryByTestId("exact-contract-result")).not.toBeInTheDocument();
  expect(onSelection.mock.calls.some(([s]) => s?.status === "resolved")).toBe(false);
});

test("mounted Solstice publishes the selected recorded contract, not quote numbers, and clears pane ownership", async () => {
  axios.get.mockImplementation(url => Promise.resolve({data:url.includes("/contract") ? body : {snapshots:[],decisions:[]}}));
  const scene = {...data,ticker:"SPY",spot:100,asof:context.mapVersion,event_time:context.mapVersion,
    data_source:"fixture",formula_version:"gex.v2",map_query:context.mapQuery,strikes:[{strike:100}],
    grid:{...data.grid,strikes:[100],grid:{[identity.expiry]:{100:3}},vex_grid:{[identity.expiry]:{100:2}}},
    metrics:{walls:[props.wall],surface_coverage:{raw:{status:"ok"}}}};
  await act(async () => render(<ControlledCanvas scene={scene} />));
  fireEvent.click(screen.getByRole("gridcell",{name:/^100 by 2026-09-18,/}));
  fireEvent.click(screen.getByRole("button",{name:/Review SPY/}));
  await waitFor(() => expect(JSON.parse(screen.getByTestId("context-probe").textContent).contractResolution).toBe("resolved"));
  const published = JSON.parse(screen.getByTestId("context-probe").textContent);
  expect(published.selectedContract).toEqual(identity);
  expect(published.selectedStrike).toBe(100);
  expect(published.selectedExpiry).toBe(identity.expiry);
  expect(published.selectedContract).not.toHaveProperty("bid");
  fireEvent.click(screen.getByRole("button",{name:"VEX"}));
  await waitFor(() => expect(JSON.parse(screen.getByTestId("context-probe").textContent).selectedContract).toBeNull());
});

test.each(["success","error"])("late %s cannot publish across a pane change or start another request", async kind => {
  const old = defer(); axios.get.mockReturnValue(old.promise);
  const onSelection = jest.fn();
  const mounted = render(<ExactContractReview {...props} onSelection={onSelection} />);
  fireEvent.click(screen.getByRole("button",{name:/Review SPY/}));
  mounted.rerender(<ExactContractReview {...props} selectionScope="vex|raw" onSelection={onSelection} />);
  await act(async () => { kind === "success" ? old.resolve({data:body}) : old.reject(new Error("old failure")); });
  expect(screen.queryByTestId("exact-contract-result")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(onSelection).toHaveBeenLastCalledWith(null);
  expect(axios.get).toHaveBeenCalledTimes(1);
});
