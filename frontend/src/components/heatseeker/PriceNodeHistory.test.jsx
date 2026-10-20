import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import PriceNodeHistory from "./PriceNodeHistory";

jest.mock("axios", () => ({ get: jest.fn() }));

const frames = ["14:00", "14:01", "14:02"].map(t => ({ time: `2026-09-10T${t}:00+00:00`,
  open: 100, high: 102, low: 99, close: 101, nodes: [] }));

test("failed node reads do not claim the recordings are absent", async () => {
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0,
    node_status: "unavailable", recording: { durable: true, status: "available", first_at: frames[0].time } } });
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(()=>expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles","3"));
  expect(screen.getByText(/Saved node history is currently unavailable/)).toBeInTheDocument();
  expect(screen.queryByText(/No recorded nodes match/)).not.toBeInTheDocument();
});

test("chart opens on demand and replay position changes the visible candles", async () => {
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
  render(<PriceNodeHistory ticker="SPY" />);
  expect(axios.get).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Price chart + historical nodes" }));
  await waitFor(()=>expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles","3"));
  fireEvent.click(screen.getByRole("button",{name:"Chart tools"}));fireEvent.change(screen.getByLabelText("Replay position"), { target: { value: "0" } });
  expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles", "1");
  fireEvent.click(screen.getByRole("button", { name: "Latest candle" }));
  expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles", "3");
  expect(screen.getByText(/Gaps mean no recent saved reading/)).toBeInTheDocument();
});

test("a ticker change clears the old chart before new data arrives", async () => {
  axios.get.mockResolvedValueOnce({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
  const { rerender } = render(<PriceNodeHistory ticker="SPY" />);
  fireEvent.click(screen.getByRole("button", { name: "Price chart + historical nodes" }));
  await screen.findByTestId("recorded-price-chart");
  axios.get.mockReturnValue(new Promise(() => {}));
  rerender(<PriceNodeHistory ticker="QQQ" />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles","0"));
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
});

test("saved node views show their recorded expiry dates instead of anonymous numbers",async()=>{
 const old="SPY:day:None:False|expiries=2026-09-28,2026-09-29|gex.v2|OI";const recent="SPY:4:day:None:False:True:80|expiries=2026-10-07,2026-10-08|gex.v2|OI";
 axios.get.mockResolvedValue({data:{ticker:"SPY",frames,candles_with_recorded_nodes:1,scopes:[old,recent],query_key:old}});render(<PriceNodeHistory ticker="SPY" open/>);
 await waitFor(()=>expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles","3"));fireEvent.click(screen.getByRole("button",{name:"Chart tools"}));const picker=await screen.findByRole("combobox",{name:"Saved node view"});expect(picker).toHaveTextContent("2026-09-28");expect(picker).toHaveTextContent("2026-10-07");expect(picker).not.toHaveTextContent("Saved view 1");
});

test("an old malformed expiry date does not crash stored-view selection",async()=>{
 const bad="SPY:day:None:False|expiries=2026-99-99|gex.v2|OI",good="SPY:day:None:False|expiries=2026-10-07|gex.v2|OI";axios.get.mockResolvedValue({data:{ticker:"SPY",frames,candles_with_recorded_nodes:0,scopes:[bad,good],query_key:good}});render(<PriceNodeHistory ticker="SPY" open/>);await waitFor(()=>expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles","3"));fireEvent.click(screen.getByRole("button",{name:"Chart tools"}));const picker=await screen.findByRole("combobox",{name:"Saved node view"});expect(picker).toHaveTextContent("expiry dates unavailable");expect(picker).toHaveTextContent("2026-10-07");
});


test("the primary stock chart opens directly with thirty-minute candles and no redundant toggle",async()=>{
 axios.get.mockResolvedValue({data:{ticker:"SPY",frames,candles_with_recorded_nodes:0,bar_seconds:1800}});render(<PriceNodeHistory ticker="SPY" primary/>);await screen.findByTestId("recorded-price-chart");expect(screen.queryByRole("button",{name:"Price chart + historical nodes"})).not.toBeInTheDocument();expect(screen.getByRole("combobox",{name:"Candle interval"})).toHaveValue("30");expect(axios.get.mock.calls[0][1].params.interval_minutes).toBe(30);fireEvent.change(screen.getByRole("combobox",{name:"Candle interval"}),{target:{value:"15"}});await waitFor(()=>expect(axios.get.mock.calls.at(-1)[1].params.interval_minutes).toBe(15));
});

// 2026-10-18 compact toolbar contract — meaningful behaviour, not CSS
// mirroring. jsdom hides closed details content, so the visibility
// assertions below are real: pickers hide while Chart tools is closed, the
// replay affordances stay visible on their own row, disclosure opening and
// closing never sends a request, and chosen values persist through a close
// and reopen.
test("Chart tools stays request-free while pickers hide closed and choices persist", async () => {
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles", "3"));
  const totalCalls = () => axios.get.mock.calls.length;
  await waitFor(() => expect(totalCalls()).toBeGreaterThan(0));
  const baseline = totalCalls();
  const horizon = screen.getByLabelText("History sessions");
  const coverage = screen.getByLabelText("Session coverage");
  // Closed tools: pickers hidden, replay visible with Tools shut.
  expect(horizon).not.toBeVisible();
  expect(coverage).not.toBeVisible();
  expect(screen.getByRole("button", { name: "Play replay" })).toBeVisible();
  expect(screen.getByTestId("price-history-summary")).toHaveTextContent("1 week · regular hours");
  // Opening the disclosure sends nothing.
  fireEvent.click(screen.getByRole("button", { name: "Chart tools" }));
  await waitFor(() => expect(horizon).toBeVisible());
  expect(baseline).toBe(totalCalls());
  // Driving the pickers sends the exact chosen parameters.
  fireEvent.change(horizon, { target: { value: "60" } });
  await waitFor(() => expect(axios.get.mock.calls.at(-1)?.[1]?.params.days).toBe(60));
  fireEvent.change(screen.getByLabelText("Session coverage"), { target: { value: "all" } });
  await waitFor(() => expect(axios.get.mock.calls.at(-1)?.[1]?.params.sessions).toBe("all"));
  // Closing and reopening keeps the choices and the compact summary.
  fireEvent.click(screen.getByRole("button", { name: "Chart tools" }));
  fireEvent.click(screen.getByRole("button", { name: "Chart tools" }));
  expect(screen.getByLabelText("History sessions")).toHaveValue("60");
  expect(screen.getByLabelText("Session coverage")).toHaveValue("all");
  expect(screen.getByTestId("price-history-summary")).toHaveTextContent("3 months · all sessions");
});

test("replay with Tools closed changes nothing on the wire", async () => {
  axios.get.mockResolvedValue({ data: { ticker: "SPY", frames, candles_with_recorded_nodes: 0 } });
  render(<PriceNodeHistory ticker="SPY" open />);
  await waitFor(() => expect(screen.getByTestId("recorded-price-chart")).toHaveAttribute("data-candles", "3"));
  const totalCalls = () => axios.get.mock.calls.length;
  await waitFor(() => expect(totalCalls()).toBeGreaterThan(0));
  const baseline = totalCalls();
  // Play and pause on the always-visible replay row while Tools stays shut.
  fireEvent.click(screen.getByRole("button", { name: "Play replay" }));
  await new Promise(res => setTimeout(res, 60));
  expect(screen.getByRole("button", { name: "Pause replay" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Pause replay" }));
  await new Promise(res => setTimeout(res, 60));
  expect(screen.getByRole("button", { name: "Play replay" })).toBeVisible();
  expect(baseline).toBe(totalCalls());
});
