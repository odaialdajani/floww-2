/**
 * @jest-environment jsdom
 *
 * SkylitTickerBar free-text search (2026-09-03, open universe): typing any
 * symbol + Enter/Go calls onTickerChange with the uppercased symbol.
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import SkylitTickerBar from "./SkylitTickerBar";

test("quick-tap buttons still call onTickerChange", () => {
  const onTickerChange = jest.fn();
  render(<SkylitTickerBar activeTicker="SPY" onTickerChange={onTickerChange} />);
  fireEvent.click(screen.getByText("QQQ"));
  expect(onTickerChange).toHaveBeenCalledWith("QQQ");
});

test("typing a symbol + Enter loads it (open universe)", () => {
  const onTickerChange = jest.fn();
  render(<SkylitTickerBar activeTicker="SPY" onTickerChange={onTickerChange} />);
  const input = screen.getByTestId("skylit-ticker-search");
  fireEvent.change(input, { target: { value: "hood" } });
  fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
  expect(onTickerChange).toHaveBeenCalledWith("HOOD");
});

test("Go button submits the query and blank submits nothing", () => {
  const onTickerChange = jest.fn();
  render(<SkylitTickerBar activeTicker="SPY" onTickerChange={onTickerChange} />);
  fireEvent.click(screen.getByTestId("skylit-ticker-go"));
  expect(onTickerChange).not.toHaveBeenCalled();

  const input = screen.getByTestId("skylit-ticker-search");
  fireEvent.change(input, { target: { value: "  coin  " } });
  fireEvent.click(screen.getByTestId("skylit-ticker-go"));
  expect(onTickerChange).toHaveBeenCalledWith("COIN");
});
