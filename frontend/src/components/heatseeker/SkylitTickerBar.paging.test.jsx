/**
 * @jest-environment jsdom
 *
 * A-Z paging (user request): the bar shows 500-button windows of the full
 * universe with prev/next page controls, so every symbol A-Z is reachable
 * by scrolling, not just the first 500. RENDER_CAP, full-universe search,
 * active-beyond-cap rendering, and free-text Go contracts are unchanged.
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

test("next page shows the following window of the universe", () => {
  render(<SkylitTickerBar activeTicker="SPY" onTickerChange={() => {}} tickers={bigUniverse()} />);
  expect(screen.queryByTestId("skylit-ticker-btn-T0500")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("skylit-ticker-page-next"));
  expect(screen.getByTestId("skylit-ticker-btn-T0500")).toBeInTheDocument();
  expect(screen.getByTestId("skylit-ticker-count").textContent).toMatch(/page 2\//);
});

test("prev is disabled on first page, next disabled on last", () => {
  render(<SkylitTickerBar activeTicker="SPY" onTickerChange={() => {}} tickers={bigUniverse()} />);
  expect(screen.getByTestId("skylit-ticker-page-prev")).toBeDisabled();
  fireEvent.click(screen.getByTestId("skylit-ticker-page-next"));
  expect(screen.getByTestId("skylit-ticker-page-next")).toBeDisabled();
  fireEvent.click(screen.getByTestId("skylit-ticker-page-prev"));
  expect(screen.getByTestId("skylit-ticker-btn-T0000")).toBeInTheDocument();
});

test("selecting a ticker beyond the window jumps the page to reveal it", () => {
  const { rerender } = render(
    <SkylitTickerBar activeTicker="SPY" onTickerChange={() => {}} tickers={bigUniverse()} />
  );
  expect(screen.queryByTestId("skylit-ticker-btn-T0559")).not.toBeInTheDocument();
  rerender(
    <SkylitTickerBar activeTicker="T0559" onTickerChange={() => {}} tickers={bigUniverse()} />
  );
  const btn = screen.getByTestId("skylit-ticker-btn-T0559");
  expect(btn).toBeInTheDocument();
  expect(btn.className).toMatch(/active/);
});

test("no paging controls when the universe fits in one window", () => {
  render(
    <SkylitTickerBar activeTicker="SPY" onTickerChange={() => {}} tickers={{ default: ["SPY", "QQQ"] }} />
  );
  expect(screen.queryByTestId("skylit-ticker-page-next")).not.toBeInTheDocument();
  expect(screen.queryByTestId("skylit-ticker-page-prev")).not.toBeInTheDocument();
});
