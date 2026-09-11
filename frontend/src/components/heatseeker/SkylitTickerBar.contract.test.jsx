/**
 * @jest-environment jsdom
 *
 * SCROLL-1 bar behavior (2026-09-07): capped DOM with full reachability,
 * honest counts, and selected-item reveal.
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import SkylitTickerBar from "./SkylitTickerBar";

const bigUniverse = () => ({
  trinity: ["^SPX", "SPY", "QQQ"],
  default: ["IWM"],
  popular: Array.from({ length: 600 }, (_, i) => `T${String(i).padStart(4, "0")}`),
});

test("caps buttons at 500 but labels the full count honestly", () => {
  render(<SkylitTickerBar activeTicker="SPY" onTickerChange={() => {}} tickers={bigUniverse()} />);
  const label = screen.getByTestId("skylit-ticker-count");
  expect(label.textContent).toMatch(/showing 500 of 60\d/);
  const buttons = screen.getAllByTestId(/^skylit-ticker-btn-/);
  expect(buttons.length).toBe(500);
});

test("search finds a symbol past the render cap (filter before slice)", () => {
  const onTickerChange = jest.fn();
  render(<SkylitTickerBar activeTicker="SPY" onTickerChange={onTickerChange} tickers={bigUniverse()} />);
  fireEvent.change(screen.getByTestId("skylit-ticker-search"), { target: { value: "T0559" } });
  const hit = screen.getByTestId("skylit-ticker-suggest-T0559");
  expect(hit).toBeInTheDocument();
  fireEvent.click(hit);
  expect(onTickerChange).toHaveBeenCalledWith("T0559");
});

test("active ticker beyond the cap is still rendered and marked active", () => {
  render(<SkylitTickerBar activeTicker="T0559" onTickerChange={() => {}} tickers={bigUniverse()} />);
  const btn = screen.getByTestId("skylit-ticker-btn-T0559");
  expect(btn).toBeInTheDocument();
  expect(btn.className).toMatch(/active/);
});

test("free-text submit still loads open-universe symbols", () => {
  const onTickerChange = jest.fn();
  render(<SkylitTickerBar activeTicker="SPY" onTickerChange={onTickerChange} tickers={bigUniverse()} />);
  fireEvent.change(screen.getByTestId("skylit-ticker-search"), { target: { value: "vsat" } });
  fireEvent.click(screen.getByTestId("skylit-ticker-go"));
  expect(onTickerChange).toHaveBeenCalledWith("VSAT");
});
