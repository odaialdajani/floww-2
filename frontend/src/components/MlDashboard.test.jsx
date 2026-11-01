import React from "react";
import {act,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {MlDashboard} from "./MlDashboard";

const reply = data => ({ok:true,json:async()=>data});
beforeEach(()=>{global.fetch=jest.fn();});

test("an absent signal or probability breakdown never becomes neutral or 33 percent",async()=>{
  global.fetch.mockResolvedValue(reply({ticker:"SPY"}));
  render(<MlDashboard ticker="SPY" />);
  await screen.findByText("Signal unavailable");
  expect(screen.getByText("Probability breakdown unavailable")).toBeInTheDocument();
  expect(screen.queryByText("NEUTRAL")).not.toBeInTheDocument();
  expect(screen.queryByText("0.33")).not.toBeInTheDocument();
});

test("non-string labels and invalid probabilities do not crash or fabricate a signal",async()=>{
  global.fetch.mockResolvedValue(reply({ticker:"SPY",prediction_label:42,confidence:1.5,
    probabilities:{up:1.5,down:-0.2,hold:"0.4"},feature_values:{bad:"private text"}}));
  render(<MlDashboard ticker="SPY" />);
  await screen.findByText("Signal unavailable");
  expect(screen.getByText("Probability breakdown unavailable")).toBeInTheDocument();
  expect(screen.queryByText("150%")).not.toBeInTheDocument();
  expect(screen.queryByText("private text")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"History"}));
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
});

test("recognized legacy labels and a measured zero probability remain valid",async()=>{
  global.fetch.mockResolvedValue(reply({ticker:"SPY",prediction:"up",confidence:0,
    probabilities:{up:0,down:1}}));
  render(<MlDashboard ticker="SPY" />);
  await screen.findAllByText("BULLISH");
  expect(screen.getByText("0%")).toBeInTheDocument();
  expect(screen.getByText("0.00")).toBeInTheDocument();
  expect(screen.getByText("1.00")).toBeInTheDocument();
  expect(screen.queryByText("HOLD")).not.toBeInTheDocument();
});

test("a failed refresh makes the current prediction unavailable",async()=>{
  global.fetch.mockResolvedValueOnce(reply({ticker:"SPY",prediction_label:"bullish"}))
    .mockResolvedValueOnce({ok:false,status:503});
  render(<MlDashboard ticker="SPY" />);
  await screen.findAllByText("BULLISH");
  fireEvent.click(screen.getByRole("button",{name:"↻"}));
  await screen.findByText(/ML service unavailable/);
  expect(screen.queryByText("BULLISH")).not.toBeInTheDocument();
  expect(screen.getByText("Prediction unavailable")).toBeInTheDocument();
});

test("a late response from the previous symbol cannot replace the new prediction",async()=>{
  let resolveOld;
  global.fetch.mockResolvedValueOnce({ok:true,json:()=>new Promise(resolve=>{resolveOld=resolve;})})
    .mockResolvedValueOnce(reply({ticker:"QQQ",prediction_label:"bullish"}));
  const view=render(<MlDashboard ticker="SPY" />);
  await waitFor(()=>expect(resolveOld).toBeDefined());
  view.rerender(<MlDashboard ticker="QQQ" />);
  await screen.findAllByText("BULLISH");
  await act(async()=>{resolveOld({ticker:"SPY",prediction_label:"bearish"});});
  expect(screen.queryByText("BEARISH")).not.toBeInTheDocument();
  expect(screen.getAllByText("BULLISH")).toHaveLength(2);
});
