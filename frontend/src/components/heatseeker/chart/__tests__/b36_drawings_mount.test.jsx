import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import PriceNodeHistory from "../../PriceNodeHistory";

jest.mock("axios", () => ({ get: jest.fn() }));

const frames = ["14:00", "14:01"].map(t => ({ time: `2026-09-10T${t}:00+00:00`,
  open: 100, high: 102, low: 99, close: 101, nodes: [] }));

beforeEach(() => {
  window.localStorage.clear();
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
});
afterEach(() => jest.restoreAllMocks());

test("rendered chart page shows the drawings rail with persisted drawings", async () => {
  window.localStorage.setItem("floww.drawings.SPY", JSON.stringify([
    { id: "d1", tool: "trend", anchors: 2, visible: true, locked: false },
  ]));
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  const rail = screen.getByTestId("drawing-rail");
  expect(rail).toBeInTheDocument();
  expect(screen.getByTestId("rail-drawing")).toHaveTextContent("trend");
});

test("rail delete removes a persisted drawing and persists the removal", async () => {
  window.localStorage.setItem("floww.drawings.SPY", JSON.stringify([
    { id: "d1", tool: "horizontal", anchors: 1, visible: true, locked: false },
  ]));
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("rail-drawing")).toBeInTheDocument());
  fireEvent.click(screen.getByTestId("rail-delete-d1"));
  expect(screen.queryByTestId("rail-drawing")).not.toBeInTheDocument();
  expect(window.localStorage.getItem("floww.drawings.SPY")).toBe("[]");
});

test("unsupported persisted tools never reach the rail", async () => {
  window.localStorage.setItem("floww.drawings.SPY", JSON.stringify([
    { id: "dx", tool: "invented-17", anchors: 9 },
  ]));
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toBeInTheDocument());
  expect(screen.getByTestId("drawing-rail")).toBeInTheDocument();
  expect(screen.queryByTestId("rail-drawing")).not.toBeInTheDocument();
});
