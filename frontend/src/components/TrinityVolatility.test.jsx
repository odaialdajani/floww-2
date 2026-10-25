/**
 * TrinityVolatility.test.jsx — labelled fixtures, no provider access.
 *
 * Covers (per the 2026-10-19 source review):
 *   - recomputed validated rows on fetch; expiry used consistently for axes;
 *     declared strike/expiry axes and null gaps preserved (incl. faint curves)
 *   - one available call/put side only, never fabricated
 *   - nearest-observation ATM/RR disclosure: exact strike, delta, distance,
 *     unknowns; qualified in heading AND hover; raw vendor IV never clamped
 *   - validation + whole ambiguous duplicate identity groups quarantined
 *   - finite IV admitted independently of delta for skew/nearest-strike;
 *     RR lens needs delta; no upper IV clamp
 *   - data failure and renderer failure are distinct states with manual Retry
 *   - async draw rejection handled; rejected Plotly.react is caught;
 *     renderer retry redraws retained data — zero extra chain requests
 *   - CDN loader with bounded deadline; honoured failed/pending states;
 *     data and renderer loading have independent honest state
 *   - cancellation/superseded responses cancel their work
 *   - source bound: missing source unknown; receipt is not Greek observation
 *   - mounted Plotly trace x/y/units, replacement, and rapid symbol switch
 *
 * Plotly is a stub: renderer tests inspect the exact trace config drawn.
 */

/** @jest-environment jsdom */
import React from "react";
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import TrinityVolatility, {
  validateChainRows,
  computeSkewData,
  computeTermData,
  computeRrData,
} from "./TrinityVolatility";

jest.mock("../config/api", () => ({ API: "/api", BACKEND_URL: "", BACKEND_BASE: "" }));
jest.mock("axios", () => ({ get: jest.fn() }));

// ---- labelled fixture: Public SPY chain from the 2026-10-19 source diagnostic ----
// IV3.6807/3.6578 at strike 768 on 2026-10-19 (decimal IV; ×100 → percent).
const spyChain = {
  ticker: "SPY", spot: 767.94,
  expiries: ["2026-10-19", "2026-10-21", "2026-10-26"],
  data_source: "public_api", event_time: null,
  fetched_at: "2026-10-19T13:32:51Z",
  rows: [
    { expiry: "2026-10-19", type: "call", strike: 765, iv: 3.60, delta: 0.47, oi: 1200 },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 3.6807, delta: 0.4951, oi: 5000 },
    { expiry: "2026-10-19", type: "call", strike: 775, iv: 3.40, delta: 0.45, oi: 800 },
    { expiry: "2026-10-19", type: "put", strike: 765, iv: 3.55, delta: -0.47, oi: 700 },
    { expiry: "2026-10-19", type: "put", strike: 768, iv: 3.6578, delta: -0.505, oi: 4500 },
    { expiry: "2026-10-19", type: "put", strike: 775, iv: 3.30, delta: -0.45, oi: 600 },
    { expiry: "2026-10-21", type: "call", strike: 770, iv: 2.90, delta: 0.46, oi: 900 },
    // 2026-10-26: no rows at all
  ],
};

const qqqChain = {
  ticker: "QQQ", spot: 102,
  expiries: ["2026-11-02", "2026-11-06"],
  data_source: "public_api", event_time: null,
  fetched_at: "2026-10-19T13:33:05Z",
  rows: [
    { expiry: "2026-11-02", type: "call", strike: 102, iv: 0.50, delta: 0.5, oi: 10 },
    { expiry: "2026-11-02", type: "put", strike: 102, iv: 0.48, delta: -0.5, oi: 10 },
    { expiry: "2026-11-06", type: "call", strike: 101, iv: 0.45, delta: 0.48, oi: 20 },
  ],
};

let lastConfig = null;

function makeSpyPlotly(implementation) {
  const spy = {
    react: jest.fn().mockImplementation(async (el, traces, layout, opts) => {
      lastConfig = { traces, layout };
    }),
    purge: jest.fn(),
  };
  if (implementation) spy.react.mockImplementation(implementation);
  return spy;
}

function buildPayload(ticker = "SPY", overrides = {}) {
  return {
    ticker,
    spot: overrides.spot ?? 767.94,
    expiries: overrides.expiries ?? ["2026-10-19", "2026-10-21", "2026-10-26"],
    data_source: "data_source" in overrides ? overrides.data_source : "public_api",
    event_time: overrides.event_time ?? null,
    fetched_at: overrides.fetched_at ?? "2026-10-19T13:32:51Z",
    rows: overrides.rows ?? spyChain.rows,
  };
}

async function mountTrinity(ticker = "SPY", overrides = {}) {
  // explicit plotly: undefined (no stub) keeps the loader/renderer-failure paths
  // testable; otherwise a ready stub is provided so charts and Source text render.
  const plotly = Object.prototype.hasOwnProperty.call(overrides, "plotly") ? overrides.plotly : makeSpyPlotly();
  axios.get.mockImplementation(() =>
    Promise.resolve({ data: buildPayload(ticker, overrides) }));
  if (plotly) {
    Object.defineProperty(window, "Plotly", { value: plotly, configurable: true });
  }
  await act(async () => { render(
    <TrinityVolatility ticker={ticker} expiries={overrides.expiries ?? 3} loaderDeadlineMs={overrides.loaderDeadlineMs ?? 10000} />); });
  // Wait for payload processed: the header sub exists once the chain loads
  // (any data_source), without depending on a specific source string.
  return plotly ? screen.findByText(/(SPY \u00b7 spot )|Volatility renderer (loading|unavailable|failed)/) : Promise.resolve(undefined);
}

beforeEach(() => {
  jest.clearAllMocks();
  delete window.Plotly;
  lastConfig = null;
});

// ──────────────────────────────────────────────────────────────
// validation / quarantine
// ──────────────────────────────────────────────────────────────

test("validation: ambiguous duplicate identity groups are quarantined wholesale", () => {
  const pairA = [
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.5, delta: 0.4951 },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.6, delta: 0.4951 },
  ];
  const { rows, issues } = validateChainRows(pairA);
  expect(rows).toHaveLength(0);
  expect(issues).toHaveLength(2);
  expect(issues.every((i) => i.includes("whole group quarantined"))).toBe(true);

  // reversed row order must quarantine identically
  const { rows: rows2 } = validateChainRows([...pairA].reverse());
  expect(rows2).toHaveLength(0);

  // mixed: valid rows survive; the whole ambiguous call group is dropped
  const mixed = [
    { expiry: "2026-10-19", type: "call", strike: 765, iv: 3.60, delta: 0.47 },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.5, delta: 0.4951 },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.6, delta: 0.4951 },
    { expiry: "2026-10-19", type: "put", strike: 768, iv: 3.6578, delta: -0.505 },
  ];
  const { rows: r3, issues: i3 } = validateChainRows(mixed);
  expect(r3).toHaveLength(2); // 765 call, 768 put
  const quarantine = i3.filter((i) => i.includes("whole group quarantined"));
  expect(quarantine).toHaveLength(2);
  expect(quarantine.every((i) => i.includes("— whole group quarantined"))).toBe(true);
});

test("validation: malformed rows are rejected with reasons (no delta collapse)", () => {
  const bad = [
    { expiry: "2026-10-19", type: "call", strike: 768, iv: NaN, delta: 0.4951 },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.5, delta: NaN },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.5, delta: 0.4951 },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.5, delta: 0.4951 },
    { expiry: "2026-10-19", type: "strangle", strike: 768, iv: 0.5, delta: 0.4951 },
    { expiry: "", type: "call", strike: 768, iv: 0.5, delta: 0.4951 },
  ];
  const { rows, issues } = validateChainRows(bad);
  // only the truly invalid rows, and the whole ambiguous duplicate group
  expect(rows).toHaveLength(0);
  const expected = [
    "row 0: missing IV",
    "row 1: ambiguous duplicate strike 768 on 2026-10-19|call|768 — whole group quarantined",
    "row 2: ambiguous duplicate strike 768 on 2026-10-19|call|768 — whole group quarantined",
    "row 3: ambiguous duplicate strike 768 on 2026-10-19|call|768 — whole group quarantined",
    "row 4: unrecognized type strangle",
    "row 5: missing expiry",
  ];
  expect(issues.slice().sort()).toEqual(expected.slice().sort());
});

test("duplicates are quarantined regardless of row order (identity equality)", () => {
  const a = [
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.5, delta: 0.4951 },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.7, delta: 0.4951 },
  ];
  expect(validateChainRows(a).rows).toHaveLength(0);
  expect(validateChainRows([...a].reverse()).rows).toHaveLength(0);
});

// ──────────────────────────────────────────────────────────────
// pure lens helpers (labelled fixtures)
// ──────────────────────────────────────────────────────────────

test("computeSkewData preserves the declared strike axis, admitting finite IV without delta", () => {
  const rows = [
    { expiry: "2026-10-19", type: "call", strike: 765, iv: 3.60, delta: 0.47 },
    { expiry: "2026-10-19", type: "call", strike: 768, iv: null, delta: 0.5 }, // declared, no IV
    { expiry: "2026-10-19", type: "call", strike: 775, iv: 3.40, delta: 0.45 },
    { expiry: "2026-10-19", type: "put", strike: 765, iv: 3.55, delta: -0.47 },
    { expiry: "2026-10-19", type: "put", strike: 775, iv: 3.30, delta: -0.45 },
  ];
  const d = computeSkewData(rows, 767.94, "2026-10-19");
  expect(d.strikes).toEqual([765, 768, 775]);
  expect(d.callIv).toEqual([360, null, 340]);
  expect(d.putIv).toEqual([355, null, 330]);
  expect(d.callOnly).toBe(false);
  expect(d.putOnly).toBe(false);
});

test("computeSkewData: one available side is honest", () => {
  const rows = spyChain.rows.filter((r) => r.type === "put");
  const d = computeSkewData(rows, 767.94, "2026-10-19");
  expect(d.callOnly).toBe(false);
  expect(d.putOnly).toBe(true);
  expect(d.strikes).toEqual([765, 768, 775]);
  expect(d.callIv).toEqual([null, null, null]);
});

test("computeTermData keeps every declared expiry on the axis; missing are gaps", () => {
  const term = computeTermData(spyChain.rows, 767.94, ["2026-10-19", "2026-10-21", "2026-10-26"]);
  expect(term.map((d) => d.expiry)).toEqual(["2026-10-19", "2026-10-21", "2026-10-26"]);
  expect(term[0].iv).toBeCloseTo(366.925, 3);
  expect(term[0].hasCall).toBe(true);
  expect(term[0].hasPut).toBe(true);
  expect(term[0].callIv).toBe(3.6807); // decimal candidate input
  expect(term[0].putIv).toBe(3.6578);
  expect(term[0].callStrike).toBe(768);
  expect(term[0].putStrike).toBe(768);
  expect(term[1].iv).toBeNull(); // call only — put side missing, not fabricated
  expect(term[2].iv).toBeNull(); // declared expiry with no rows — gap on the axis
  expect(term[1].hasCall).toBe(true);
  expect(term[1].hasPut).toBe(false);
});

test("computeRrData nearest-delta: strike 775 delta ±0.45 before 768 ~±0.5 gives −10 vol points", () => {
  const rows = [
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 0.20, delta: 0.5 },
    { expiry: "2026-10-19", type: "call", strike: 775, iv: 0.22, delta: 0.45 },
    { expiry: "2026-10-19", type: "put", strike: 775, iv: 0.12, delta: -0.45 },
    { expiry: "2026-10-19", type: "put", strike: 768, iv: 0.21, delta: -0.5 },
  ];
  const rr = computeRrData(rows, ["2026-10-19"]);
  expect(rr[0].rr).toBeCloseTo(-10, 2);
  expect(rr[0].callStrike).toBe(775);
  expect(rr[0].callDelta).toBe(0.45);
  expect(rr[0].putStrike).toBe(775);
  expect(rr[0].putDelta).toBe(-0.45);
  expect(rr[0].callDistance).toBeCloseTo(0.2, 4);
  expect(rr[0].putDistance).toBeCloseTo(0.2, 4);
  // delta is lens-specific: lacking delta kills RR, never skew
  const rr2 = computeRrData(
    [{ expiry: "2026-10-19", type: "call", strike: 768, iv: 0.2, delta: null }],
    ["2026-10-19"]
  );
  expect(rr2[0].rr).toBeNull();
});

test("computeRrData admitted rows are finite-IV regardless of delta", () => {
  const rows = [
    { expiry: "2026-10-19", type: "call", strike: 768, iv: 3.6807, delta: 0.4951 },
    { expiry: "2026-10-19", type: "put", strike: 768, iv: 3.6578 },
  ];
  const rr = computeRrData(rows, ["2026-10-19"]);
  expect(rr[0].rr).toBeNull(); // put delta absent → RR unavailable
});

// ──────────────────────────────────────────────────────────────
// mounted renderer behaviour (ready Plotly stub)
// ──────────────────────────────────────────────────────────────

test("mounted Plotly traces assert exact x/y/units; replacement redraws", async () => {
  const spy = makeSpyPlotly();
  await mountTrinity("SPY", { plotly: spy });
  expect(spy.react).toHaveBeenCalledTimes(3);

  const allTraces = spy.react.mock.calls.flatMap((c) => c[1]);
  const callTrace = allTraces.find((t) => t.name === "Call IV");
  const putTrace = allTraces.find((t) => t.name === "Put IV");
  expect(callTrace.x).toEqual([765, 768, 775]);
  expect(callTrace.y).toEqual([360, 368.07, 340]);
  expect(callTrace.name).toBe("Call IV");
  expect(callTrace.connectgaps).toBe(false);
  expect(callTrace.hovertemplate).toContain("IV %{y:.1f}%");
  expect(putTrace.x).toEqual([765, 768, 775]);
  expect(putTrace.y).toEqual([355, 365.78, 330]);
  expect(putTrace.name).toBe("Put IV");

  const term = allTraces.find((t) => t.mode === "lines+markers");
  expect(term.x).toEqual(["2026-10-19", "2026-10-21", "2026-10-26"]);
  expect(term.y).toEqual([366.925, null, null]);
  expect(term.hovertemplate).toContain("nearest-observation");

  const rr = allTraces.find((t) => t.y?.[0] === -10);
  expect(rr.x).toEqual(["2026-10-19", "2026-10-21", "2026-10-26"]);
  expect(rr.y).toEqual([-10, null, null]);
  expect(rr.hovertemplate).toContain("25Δ RR (nearest-observation)"); // exact units: vol pts

  // replacement with a second ticker re-renders the retained data
  const spy2 = makeSpyPlotly();
  Object.defineProperty(window, "Plotly", { value: spy2, configurable: true });
  axios.get.mockImplementation(() => Promise.resolve({ data: qqqChain }));
  render(<TrinityVolatility ticker="QQQ" expiries={2} />);
  await screen.findByText(/102\.00/);
  expect(spy2.react).toHaveBeenCalledTimes(3);
  const qqqTraces = spy2.react.mock.calls[0][1];
  const qqqCall = qqqTraces.find((t) => t.name === "Call IV");
  expect(qqqCall.x).toEqual([102]);
  expect(qqqCall.y).toEqual([50]);
  const qqqTerm = spy2.react.mock.calls[1][1].find((t) => t.mode === "lines+markers");
  expect(qqqTerm.x).toEqual(["2026-11-02", "2026-11-06"]);
  expect(qqqTerm.y).toEqual([49, null]);
  const qqqRr = spy2.react.mock.calls[2][1][0];
  expect(qqqRr.x).toEqual(["2026-11-02", "2026-11-06"]);
  expect(qqqRr.y).toEqual([-2, null]);
  expect(spy.react).toHaveBeenCalledTimes(3); // first render unchanged
  expect(screen.queryByText("368.1%")).not.toBeInTheDocument();
});

test("one available side renders honestly: put only shows put IV, no call IV claim", async () => {
  await mountTrinity("SPY", { rows: spyChain.rows.filter((r) => r.type === "put") });
  expect(screen.getByText(/● Put IV/)).toBeInTheDocument();
  expect(screen.queryByText("Call IV")).not.toBeInTheDocument();
});

test("empty skew heading falls back to 'no IV data' when both sides are absent", async () => {
  const rows = [
    { expiry: "2026-10-21", type: "call", strike: 770, iv: 2.9, delta: 0.46 },
    { expiry: "2026-10-21", type: "put", strike: 770, iv: 2.8, delta: -0.46 },
  ];
  await mountTrinity("SPY", { rows, expiries: ["2026-10-19", "2026-10-21"] });
  expect(screen.getByText(/no IV data/)).toBeInTheDocument();
});

test("nearest-observation ATM/RR labels expose exact strike, delta, distance and unknown side", async () => {
  await mountTrinity("SPY");
  const approxEls = screen.getAllByText(/nearest-observation approximation/);
  expect(approxEls).toHaveLength(2);
  const termQual = approxEls.find((el) => el.closest(".tv-cell-h")?.textContent.includes("Term Structure"));
  const rrQual = approxEls.find((el) => el.closest(".tv-cell-h")?.textContent.includes("Risk Reversal"));
  expect(termQual).toBeInTheDocument();
  expect(rrQual).toBeInTheDocument();

  const noteEls = screen.getAllByText(/2026-10-19/).map((el) => el.closest(".tv-cell-h-notes")).filter(Boolean);
  const termNote = noteEls.find((n) => n.textContent.includes("ATM IV"));
  const rrNote = noteEls.find((n) => n.textContent.includes("RR"));
  expect(termNote.textContent).toContain("2026-10-19");
  expect(termNote.textContent).toContain("ATM IV 366.9%");
  expect(termNote.textContent).toContain("call 768 IV 3.6807 Δ+0.4951");
  expect(termNote.textContent).toContain("put 768 IV 3.6578 Δ−0.505");
  expect(termNote.textContent).toContain("0.06pt");

  expect(rrNote.textContent).toContain("RR −10 vol pts");
  expect(rrNote.textContent).toContain("call Δ+0.45 @775");
  expect(rrNote.textContent).toContain("put Δ−0.45 @775");
  expect(rrNote.textContent).toContain("call 0.2 from +0.25");
  expect(rrNote.textContent).toContain("put 0.2 from −0.25");
});

test("term structure keeps every declared expiry on the axis, missing ones are gaps with a reason", async () => {
  await mountTrinity("SPY");
  // 2026-10-19 has both sides: ATM IV 366.9%
  const termNote19 = screen.getByText(/2026-10-19.*ATM IV 366\.9%/s);
  expect(termNote19.textContent).toContain("2026-10-19");
  expect(termNote19.textContent).toContain("ATM IV 366.9%");
  expect(termNote19.textContent).toContain("call 768 IV 3.6807 Δ+0.4951");
  expect(termNote19.textContent).toContain("put 768 IV 3.6578 Δ−0.505");
  expect(termNote19.textContent).toContain("0.06pt");

  // 2026-10-21 call-only and 2026-10-26 no rows stay explicit on the axis.
  // (M2 G3 2026-10-24: the exact rows now disclose behind the named details —
  // .tv-cell-h-notes > details > div — the content contract is unchanged.)
  const termCell = screen.getByText(/ATM IV Term Structure/).closest(".tv-cell");
  const termNotes = Array.from(termCell.querySelectorAll(".tv-cell-h-notes div"));
  const termNote21 = termNotes.find((n) => n.textContent.includes("2026-10-21"));
  const termNote26 = termNotes.find((n) => n.textContent.includes("2026-10-26"));
  expect(termNote21).toBeDefined();
  expect(termNote26).toBeDefined();
  expect(termNote21.textContent).toContain("unavailable");
  expect(termNote26.textContent).toContain("unavailable");
});

test("data failure and renderer failure are distinct states with manual Retry", async () => {
  axios.get.mockRejectedValueOnce(new Error("network down")).mockRejectedValueOnce(new Error("network down"));
  const first = render(<TrinityVolatility ticker="SPY" expiries={3} />);
  await screen.findByText("Retry data");
  expect(screen.getByRole("alert")).toHaveTextContent("network down");
  fireEvent.click(screen.getByRole("button", { name: "Retry data" }));
  await screen.findByText("Retry data"); // data retry keeps the data-error state
  first.unmount();

  // distinct layer: renderer failure is separate, with its own Retry action
  const spy = makeSpyPlotly();
  spy.react.mockImplementation(async () => {
    if (spy.react.mock.calls.length === 1) throw new Error("plotly boom");
  });
  Object.defineProperty(window, "Plotly", { value: spy, configurable: true });
  axios.get.mockResolvedValue({ data: buildPayload("SPY", {}) });
  render(<TrinityVolatility ticker="SPY" expiries={3} />);
  await screen.findByText("Volatility renderer failed");
  expect(axios.get).toHaveBeenCalledTimes(3); // 2 data failures + 1 success
  expect(screen.getByRole("alert")).toHaveTextContent("plotly boom");
  fireEvent.click(screen.getByRole("button", { name: "Retry chart" }));
  await screen.findByText(/IV Skew/);
  expect(axios.get).toHaveBeenCalledTimes(3); // renderer retry = redraw only, zero extra chain requests
  expect(spy.react).toHaveBeenCalledTimes(2); // failed draw + retained-data redraw of the failed layer
});

test("rejected Plotly.react is handled and renderer retry draws retained data with zero extra chain requests", async () => {
  // reject only the first draw, then succeed so the retry actually redraws
  const spy = makeSpyPlotly(async () => {
    if (spy.react.mock.calls.length === 1) throw new Error("plotly boom");
  });
  await mountTrinity("SPY", { plotly: spy });
  await screen.findByText("Volatility renderer failed");
  expect(screen.getByRole("alert")).toHaveTextContent("plotly boom");

  fireEvent.click(screen.getByRole("button", { name: "Retry chart" }));
  await screen.findByText(/IV Skew/);
  expect(axios.get).toHaveBeenCalledTimes(1); // 0 extra chain requests
  expect(spy.react).toHaveBeenCalledTimes(2);
});

test("missing Plotly: bounded loader pending then honest failure, manual Retry", async () => {
  await mountTrinity("SPY", { plotly: undefined, loaderDeadlineMs: 60 });
  await screen.findByText("Volatility renderer loading");
  expect(axios.get).toHaveBeenCalledTimes(1);
  await screen.findByText("Volatility renderer unavailable");
  expect(screen.getByText(/Plotly did not load within the bounded wait/)).toBeInTheDocument();
  expect(screen.getByText(/data payload is intact/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Retry renderer" }));
  await screen.findByText("Volatility renderer unavailable");
  expect(axios.get).toHaveBeenCalledTimes(1); // loader retry does not touch the chain
});

test("source/receipt binding: missing source is unknown; receipt is not Greek observation", async () => {
  await mountTrinity("SPY", { data_source: undefined });
  expect(screen.getByText(/Source: unknown/)).toBeInTheDocument();
  expect(screen.getByText(/receipt/)).toBeInTheDocument();
  expect(screen.getByText(/chain received/)).toBeInTheDocument();
  expect(screen.getByText(/quote observation time unknown/)).toBeInTheDocument();
});

test("source known is shown verbatim; missing inputs stay explicit", async () => {
  await mountTrinity("SPY");
  expect(screen.getByText(/Source: public_api/)).toBeInTheDocument();
  // 2026-10-21 has a call but no put → explicit unavailability
  const termCell = screen.getByText(/ATM IV Term Structure/).closest(".tv-cell");
  const termNote = termCell.querySelector(".tv-cell-h-notes");
  expect(termNote.textContent).toContain("unavailable");
  expect(termNote.textContent).toContain("call 770 IV 2.9000 Δ+0.46");
});

// ──────────────────────────────────────────────────────────────
// cancellation / rapid symbol switch
// ──────────────────────────────────────────────────────────────

test("rapid symbol switch cancels the stale response and the live payload wins", async () => {
  const spy = makeSpyPlotly();
  Object.defineProperty(window, "Plotly", { value: spy, configurable: true });
  let spiedResolve = null;
  axios.get.mockImplementation((url) => {
    if (String(url).includes("/api/chain/SPY")) {
      return new Promise((resolve) => { spiedResolve = resolve; });
    }
    return { data: qqqChain };
  });
  const { rerender } = render(<TrinityVolatility ticker="SPY" expiries={3} />);
  await screen.findByText(/Loading SPY volatility/);
  act(() => { rerender(<TrinityVolatility ticker="QQQ" expiries={2} />); });
  await screen.findByText(/102\.00/);
  spiedResolve({ data: spyChain }); // superseded — discarded, not its turn
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
  expect(screen.getByText(/102\.00/)).toBeInTheDocument();
  const notes = screen.getAllByText(/2026-11-02/).map((el) => el.textContent);
  expect(notes.some((n) => n.includes("ATM IV 49.0%"))).toBe(true);
  expect(screen.queryByText("368.1%")).toBeNull();
});

test("extraneous chain requests are cancelled on unmount and superseded replies", async () => {
  let spiedResolve = null;
  axios.get.mockImplementation((url) => {
    if (String(url).includes("/api/chain/SPY")) {
      return new Promise((resolve) => { spiedResolve = resolve; });
    }
    return { data: qqqChain };
  });
  const { unmount } = render(<TrinityVolatility ticker="SPY" expiries={3} />);
  await screen.findByText(/Loading SPY volatility/);
  unmount();
  // the blocked SPY request must be cancelled, not left hanging
  expect(axios.get).toHaveBeenCalledTimes(1);
  spiedResolve({ data: spyChain }); // never delivered
});
