import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import StockDirectory from "./StockDirectory";

jest.mock("axios", () => ({ get: jest.fn() }));

test("browse loads all-provider counts and selecting a result opens that ticker", async () => {
  axios.get.mockResolvedValue({ data: { total: 13135, optionable_total: 8786, matches: 13135,
    complete_provider_catalog: true, has_more: true, instruments: [{ symbol: "BRK.B", options: true }] } });
  const select = jest.fn();
  render(<StockDirectory onSelect={select} />);
  fireEvent.click(screen.getByRole("button", { name: "Browse all stocks" }));
  expect(await screen.findByRole("button", { name: "BRK.B" })).toBeInTheDocument();
  expect(screen.getByText(/13,135 available/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "BRK.B" }));
  expect(select).toHaveBeenCalledWith("BRK.B");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("paging and options search are sent to the full directory", async () => {
  axios.get.mockResolvedValue({ data: { total: 15000, optionable_total: 9000, matches: 15000,
    complete_provider_catalog: true, has_more: true, instruments: [{ symbol: "A", options: true }] } });
  render(<StockDirectory />);
  fireEvent.click(screen.getByRole("button", { name: "Browse all stocks" }));
  fireEvent.click(await screen.findByRole("button", { name: "Next", exact: true }));
  await waitFor(() => expect(axios.get.mock.calls.at(-1)[1].params.page).toBe(2));
  await screen.findByRole("button", { name: "A", exact: true });
  fireEvent.change(screen.getByLabelText("Search full stock list"), { target: { value: "ZZZ" } });
  fireEvent.click(screen.getByLabelText("Options enabled"));
  await waitFor(() => expect(axios.get.mock.calls.at(-1)[1].params).toMatchObject({ page: 1, q: "ZZZ", options_only: true }));
});

test("provider failure is visible and can be retried", async () => {
  axios.get.mockRejectedValue(new Error("offline"));
  render(<StockDirectory />);
  fireEvent.click(screen.getByRole("button", { name: "Browse all stocks" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});
