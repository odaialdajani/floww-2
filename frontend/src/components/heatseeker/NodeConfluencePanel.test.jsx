/** @jest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import NodeConfluencePanel from "./NodeConfluencePanel";
import { useHeatseeker } from "../../hooks/useHeatseeker";

jest.mock("../../hooks/useHeatseeker");

const ROW = {
  strike: 500,
  gex: 5.0e8,
  microstructure_skew: 0.67,
  microstructure_status: "ok",
  flow: { count: 2, window: 2, call_side: 2, put_side: 0, status: "ok" },
  confluence: {
    total: 12.1,
    direction: "neutral",
    dimensions: {
      flow: { value: 1, weight: 0.25, contribution: 25, inputs_status: "ok" },
      structure: { value: 0, weight: 0.25, contribution: 0, inputs_status: "context_only" },
      microstructure: { value: 0.67, weight: 0.15, contribution: 10.05, inputs_status: "ok" },
      ml: { value: 0, weight: 0.1, contribution: 0, inputs_status: "missing" },
      vol: { value: 0, weight: 0.1, contribution: 0, inputs_status: "missing" },
      time_delta: { value: 0, weight: 0.15, contribution: 0, inputs_status: "missing" },
    },
  },
};

const mockHook = (data) => useHeatseeker.mockReturnValue({ data, loading: false, error: null });

test("renders a level with its fused score and direction", () => {
  mockHook({ ticker: "SPY", rows: [ROW], flow_status: "ok", strikes_considered: 1 });
  render(<NodeConfluencePanel ticker="SPY" />);
  expect(screen.getByTestId("hs-node-confluence")).toBeInTheDocument();
  expect(screen.getByTestId("hs-confluence-row-500")).toBeInTheDocument();
  expect(screen.getByTestId("hs-confluence-row-500")).toHaveTextContent("+12.1 neutral");
  expect(screen.getByTestId("hs-confluence-row-500")).toHaveTextContent("alerts");
});

test("marks missing dimensions as unknown rather than as zero", () => {
  mockHook({ ticker: "SPY", rows: [ROW], flow_status: "ok" });
  render(<NodeConfluencePanel ticker="SPY" />);
  // ml / vol / time render with a dash, never a bare 0.00 that reads as
  // "measured and neutral".
  expect(screen.getByText(/ml ·—/)).toBeInTheDocument();
  expect(screen.getByText(/vol ·—/)).toBeInTheDocument();
  expect(screen.getByText(/time ·—/)).toBeInTheDocument();
});

test("labels structure as unsigned context", () => {
  mockHook({ ticker: "SPY", rows: [ROW], flow_status: "ok" });
  render(<NodeConfluencePanel ticker="SPY" />);
  expect(screen.getByText(/structure ·ctx/)).toBeInTheDocument();
});

test("shows no-tape honestly when microstructure input is missing", () => {
  mockHook({
    ticker: "SPY",
    flow_status: "no_prints",
    rows: [{ ...ROW, microstructure_skew: 0, microstructure_status: "missing", flow: { ...ROW.flow, count: 0, status: "no_prints" } }],
  });
  render(<NodeConfluencePanel ticker="SPY" />);
  const row = screen.getByTestId("hs-confluence-row-500");
  expect(row).toHaveTextContent("volume unknown");
  expect(row).toHaveTextContent("no alerts");
});

test("surfaces the degraded state instead of rendering an empty board as healthy", () => {
  mockHook({ ticker: "SPY", status: "degraded", rows: [], error: "chain fetch exploded" });
  render(<NodeConfluencePanel ticker="SPY" />);
  expect(screen.getByText(/levels unavailable/)).toBeInTheDocument();
});

test("explains a neutral score rather than implying a fault", () => {
  mockHook({ ticker: "SPY", rows: [ROW], flow_status: "ok" });
  render(<NodeConfluencePanel ticker="SPY" />);
  expect(screen.getByText(new RegExp("Call/put activity does not prove direction", "i"))).toBeInTheDocument();
});

test("empty level list is distinct from an error", () => {
  mockHook({ ticker: "SPY", rows: [], strikes_considered: 0, flow_status: "no_prints" });
  render(<NodeConfluencePanel ticker="SPY" />);
  expect(screen.getByText(/no levels with open interest/i)).toBeInTheDocument();
});


test("retains negative gamma and does not color call volume as bullish", () => {
  mockHook({ rows: [{ ...ROW, gex: -123, microstructure_status: "context_only",
    confluence: { total: null, direction: "insufficient_evidence", dimensions: {} } }] });
  render(<NodeConfluencePanel />);
  const row = screen.getByTestId("hs-confluence-row-500");
  expect(row).toHaveTextContent("GEX -1.23e+2");
  expect(row).toHaveTextContent("not enough evidence");
  expect(screen.getByText("call/put +0.67")).toHaveClass("text-slate-500");
});
