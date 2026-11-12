/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import MarketInspectorDock from "./MarketInspectorDock";

jest.mock("axios");
jest.mock("../heatseeker/ExactContractReview", () => () => null);
jest.mock("../heatseeker/AskFlow", () => () => null);
jest.mock("../public/PublicHandoffReview", () => ({ GroundedPublicReview: () => null }));

const props = { ticker: "SPY", data: { snapshotId: "snap/1" },
  wall: { wall_id: "w1", low: 100, high: 101 }, quality: { state: "usable" },
  onClose: jest.fn(), onContracts: jest.fn() };
const scope = { provider: "recorded-provider", scope_id: "scope-1", session_date: "2026-11-02", formula_version: "gex.v2", exposure_basis: "OI" };
const point = (id, value, overrides = {}) => ({ observation_id: id, value, status: "ok", source: "recorded-provider", scope,
  metric: { metric_id: "dadgex_net_v1", units: "USD/1% move" }, wall: { wall_id: "w1", definition_version: "def1" },
  clocks: { event_time: "2026-11-02T14:00:00Z", received_at: "2026-11-02T14:01:00Z", available_at: "2026-11-02T14:02:00Z" },
  coverage: { usable: 2, missing: 0, invalid: 0, n_contracts: 2 }, line: { status: "continuous" }, ...overrides });
const stored = { snapshot: { snapshot_id: "snap/1", ticker: "SPY", query_key: "exact-stored-scope", asof_ts: "2026-11-02T15:00:00Z" }, walls: [{ wall_id: "w1" }] };
const response = points => ({ version: "recorded-wall-curve.v1", status: "ok", metric_id: "dadgex_net_v1",
  series_key: { ticker: "SPY", query_key: "exact-stored-scope", wall_id: "w1", metric_id: "dadgex_net_v1", units: "USD/1% move" },
  points, gaps: [], coverage: { n_points: points.length, n_points_available: points.length, truncated: false } });
const recordedCalls = () => axios.get.mock.calls.filter(([url]) => String(url).includes("/solstice/"));
const mount = async () => { await act(async () => render(<MarketInspectorDock {...props} />)); };
const open = async () => {
  fireEvent.click(screen.getByText("Recorded adjusted exposure"));
  await waitFor(() => expect(recordedCalls().length).toBeGreaterThan(0));
};
beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockImplementation(async url => ({ data: String(url).includes("/replay/") ? stored : String(url).includes("/wall-curve/") ? response([point("obs-zero", 0)]) : { frames: [] } }));
});

test("loads only on disclosure and uses the selected stored scope and cutoff", async () => {
  await mount();
  expect(recordedCalls()).toHaveLength(0);
  await open();
  await waitFor(() => expect(screen.getByRole("img", { name: /recorded adjusted exposure/i })).toBeInTheDocument());
  expect(recordedCalls()[0][0]).toContain("/replay/snap%2F1");
  expect(recordedCalls()[1][1].params).toEqual({ wall_id: "w1", metric_id: "dadgex_net_v1", query_key: "exact-stored-scope", as_of: stored.snapshot.asof_ts, limit: 200 });
  expect(screen.getByTestId("recorded-wall-observations")).toHaveTextContent("0 USD/1% move");
  expect(screen.getByTestId("recorded-wall-observations")).toHaveTextContent("recorded-provider");
});

test.each([
  ["foreign ticker", { ...stored, snapshot: { ...stored.snapshot, ticker: "QQQ" } }],
  ["foreign snapshot", { ...stored, snapshot: { ...stored.snapshot, snapshot_id: "other" } }],
  ["missing scope", { ...stored, snapshot: { ...stored.snapshot, query_key: null } }],
  ["unknown cutoff zone", { ...stored, snapshot: { ...stored.snapshot, asof_ts: "2026-11-02T15:00:00" } }],
  ["wall absent", { ...stored, walls: [] }],
])("refuses %s rather than broadening history", async (_, saved) => {
  axios.get.mockResolvedValue({ data: saved });
  await mount(); await open();
  await waitFor(() => expect(screen.getByTestId("recorded-wall-state")).toHaveTextContent("SAVED_SCOPE_UNAVAILABLE"));
  expect(recordedCalls()).toHaveLength(1);
  expect(screen.queryByRole("img", { name: /recorded adjusted exposure/i })).toBeNull();
});

test("partial and unavailable observations break both adjacent segments; zero and signed values remain", async () => {
  const points = [point("a", 0), point("b", -4), point("partial", 8, { status: "partial", reason: "POPULATION_INCOMPLETE" }),
    point("c", 3), point("absent", null, { status: "unavailable", reason: "METRIC_NOT_STORED" }), point("d", 7)];
  axios.get.mockImplementation(async url => ({ data: String(url).includes("/replay/") ? stored : response(points) }));
  await mount(); await open();
  await waitFor(() => expect(screen.getByTestId("recorded-wall-chart")).toBeInTheDocument());
  expect(screen.getAllByTestId("recorded-wall-segment")).toHaveLength(1);
  expect(screen.getAllByTestId("recorded-wall-point")).toHaveLength(4);
  expect(screen.getByTestId("recorded-wall-observations")).toHaveTextContent("-4 USD/1% move");
  expect(screen.getByTestId("recorded-wall-observations")).toHaveTextContent("METRIC_NOT_STORED");
});

test("rejects a mismatched series instead of relabeling it", async () => {
  const wrong = response([point("a", 10)]); wrong.series_key.query_key = "other-scope";
  axios.get.mockImplementation(async url => ({ data: String(url).includes("/replay/") ? stored : wrong }));
  await mount(); await open();
  await waitFor(() => expect(screen.getByTestId("recorded-wall-state")).toHaveTextContent("RECORDED_SCOPE_MISMATCH"));
});

test("hiding the wall tab aborts a pending read and discards its late result", async () => {
  let resolve;
  axios.get.mockImplementation(() => new Promise(done => { resolve = done; }));
  await mount(); await open();
  const signal = recordedCalls()[0][1].signal;
  fireEvent.click(screen.getByRole("tab", { name: "Flow", exact: true }));
  expect(signal.aborted).toBe(true);
  await act(async () => resolve({ data: stored }));
  expect(recordedCalls()).toHaveLength(1);
});

test("declares unavailable data and result truncation without inferring fresh observations", async () => {
  const body = response([point("a", 0)]); body.status = "partial"; body.coverage = { n_points: 1, n_points_available: 240, truncated: true };
  axios.get.mockImplementation(async url => ({ data: String(url).includes("/replay/") ? stored : body }));
  await mount(); await open();
  await waitFor(() => expect(screen.getByTestId("recorded-wall-state")).toHaveTextContent("1 of 240"));
  expect(screen.getByTestId("recorded-wall-state")).toHaveTextContent("truncated");
});

test("malformed recorded points remain unavailable without crashing the inspector", async () => {
  const body = response([point("a", 10, { expiries: "not-an-array" })]);
  axios.get.mockImplementation(async url => ({ data: String(url).includes("/replay/") ? stored : body }));
  await mount(); await open();
  await waitFor(() => expect(screen.getByTestId("recorded-wall-state")).toHaveTextContent("RECORDED_SCOPE_MISMATCH"));
});

test("a future receipt cannot become a known-at-cutoff plotted observation", async () => {
  const body = response([point("future", 99, { clocks: { event_time: "2026-11-02T14:00:00Z", received_at: "2026-11-02T16:00:00Z", available_at: "2026-11-02T16:01:00Z" } })]);
  axios.get.mockImplementation(async url => ({ data: String(url).includes("/replay/") ? stored : body }));
  await mount(); await open();
  await waitFor(() => expect(screen.getByText("No comparable recorded readings for this measure.")).toBeInTheDocument());
  expect(screen.queryByTestId("recorded-wall-chart")).toBeNull();
  expect(screen.getByTestId("recorded-wall-observations")).not.toHaveTextContent("99 USD/1% move");
});

test("closing observation details does not close or refetch the outer disclosure", async () => {
  await mount(); await open();
  await waitFor(() => expect(screen.getByText("Observation details (1)")).toBeInTheDocument());
  const summary = screen.getByText("Observation details (1)");
  fireEvent.click(summary);
  await waitFor(() => expect(summary.parentElement.open).toBe(true));
  fireEvent.click(summary);
  await waitFor(() => expect(summary.parentElement.open).toBe(false));
  expect(screen.getByText("Recorded adjusted exposure").parentElement.open).toBe(true);
  expect(recordedCalls()).toHaveLength(2);
});

test("changing measures aborts and ignores an older response", async () => {
  let resolve;
  axios.get.mockImplementation(async url => {
    if (String(url).includes("/replay/")) return { data: stored };
    if (String(url).includes("/wall-curve/")) return new Promise(done => { resolve = done; });
    return { data: { frames: [] } };
  });
  await mount(); await open();
  await waitFor(() => expect(recordedCalls()).toHaveLength(2));
  const oldResolve = resolve;
  const oldSignal = recordedCalls()[1][1].signal;
  fireEvent.change(screen.getByLabelText("Measure"), { target: { value: "volume_gamma_v1" } });
  expect(oldSignal.aborted).toBe(true);
  await act(async () => oldResolve({ data: response([point("old-value", 777)]) }));
  expect(screen.queryByText(/777 USD/)).toBeNull();
  await waitFor(() => expect(recordedCalls()).toHaveLength(4));
  expect(recordedCalls()[3][1].params.metric_id).toBe("volume_gamma_v1");
});
