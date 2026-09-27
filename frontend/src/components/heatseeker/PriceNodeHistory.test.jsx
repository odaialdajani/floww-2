import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import PriceNodeHistory from "./PriceNodeHistory";

jest.mock("axios", () => ({ get: jest.fn() }));
jest.mock("react-plotly.js", () => ({ __esModule: true,
  default: ({ data }) => <div data-testid="price-plot" data-count={data[0].x.length} /> }));

const frames = ["14:00", "14:01", "14:02"].map(t => ({ time: `2026-09-10T${t}:00+00:00`,
  open: 100, high: 102, low: 99, close: 101, nodes: [] }));

test("chart opens on demand and replay position changes the visible candles", async () => {
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
  render(<PriceNodeHistory ticker="SPY" />);
  expect(axios.get).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Price chart + historical nodes" }));
  expect(await screen.findByTestId("price-plot")).toHaveAttribute("data-count", "3");
  fireEvent.change(screen.getByLabelText("Replay position"), { target: { value: "0" } });
  expect(screen.getByTestId("price-plot")).toHaveAttribute("data-count", "1");
  fireEvent.click(screen.getByRole("button", { name: "Show all" }));
  expect(screen.getByTestId("price-plot")).toHaveAttribute("data-count", "3");
  expect(screen.getByText(/Gaps mean no recent saved reading/)).toBeInTheDocument();
});

test("a ticker change clears the old chart before new data arrives", async () => {
  axios.get.mockResolvedValueOnce({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
  const { rerender } = render(<PriceNodeHistory ticker="SPY" />);
  fireEvent.click(screen.getByRole("button", { name: "Price chart + historical nodes" }));
  await screen.findByTestId("price-plot");
  axios.get.mockReturnValue(new Promise(() => {}));
  rerender(<PriceNodeHistory ticker="QQQ" />);
  await waitFor(() => expect(screen.queryByTestId("price-plot")).not.toBeInTheDocument());
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
});
