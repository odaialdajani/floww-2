/**
 * @jest-environment jsdom
 *
 * SkylitControlBar action buttons (2026-09-03): Playback arms interval
 * refresh, Grid opens the full-page overlay via onExpand, Share copies
 * the URL. Refresh was already alive.
 */
import React from "react";
import { render, screen, act, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import SkylitControlBar from "./SkylitControlBar";

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

test("refresh button calls onRefresh", () => {
  const onRefresh = jest.fn();
  render(<SkylitControlBar ticker="SPY" onRefresh={onRefresh} />);
  fireEvent.click(screen.getByTitle("Refresh"));
  expect(onRefresh).toHaveBeenCalledTimes(1);
});

test("playback arms interval refresh and toggles off", () => {
  const onRefresh = jest.fn();
  render(<SkylitControlBar ticker="SPY" onRefresh={onRefresh} playbackIntervalMs={15000} />);

  fireEvent.click(screen.getByTestId("skylit-playback-btn"));
  act(() => { jest.advanceTimersByTime(30000); });
  expect(onRefresh.mock.calls.length).toBeGreaterThanOrEqual(2);

  fireEvent.click(screen.getByTestId("skylit-playback-btn"));
  const n = onRefresh.mock.calls.length;
  act(() => { jest.advanceTimersByTime(60000); });
  expect(onRefresh.mock.calls.length).toBe(n);
});

test("grid button calls onExpand and degrades silently without it", () => {
  const onExpand = jest.fn();
  const { unmount } = render(<SkylitControlBar ticker="SPY" onExpand={onExpand} />);
  fireEvent.click(screen.getByTestId("skylit-expand-toolbar-btn"));
  expect(onExpand).toHaveBeenCalledTimes(1);
  unmount();

  // Frozen App.js call sites omit onExpand — must not throw.
  render(<SkylitControlBar ticker="SPY" />);
  expect(() => fireEvent.click(screen.getByTestId("skylit-expand-toolbar-btn"))).not.toThrow();
});

test("share button copies the URL and shows confirmation", async () => {  const writeText = jest.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  render(<SkylitControlBar ticker="SPY" />);
  await act(async () => {
    fireEvent.click(screen.getByTestId("skylit-share-btn"));
  });
  expect(writeText).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("skylit-share-btn")).toHaveAttribute("title", "Copied!");
});

test("prev/next arrows cycle the tape list and ignore unknown tickers", () => {  const onTickerChange = jest.fn();
  const { unmount } = render(
    <SkylitControlBar ticker="SPY" onTickerChange={onTickerChange} tickers={["SPY", "QQQ", "HOOD"]} />
  );
  fireEvent.click(screen.getByTestId("skylit-next-ticker"));
  expect(onTickerChange).toHaveBeenCalledWith("QQQ");
  fireEvent.click(screen.getByTestId("skylit-prev-ticker"));
  expect(onTickerChange).toHaveBeenLastCalledWith("HOOD");
  unmount();

  // Open-universe symbol not in the list: arrows stay put.
  const onTickerChange2 = jest.fn();
  render(<SkylitControlBar ticker="RIVN" onTickerChange={onTickerChange2} tickers={["SPY", "QQQ"]} />);
  fireEvent.click(screen.getByTestId("skylit-next-ticker"));
  fireEvent.click(screen.getByTestId("skylit-prev-ticker"));
  expect(onTickerChange2).not.toHaveBeenCalled();
});

test("info button toggles the grid explainer popover", () => {
  render(<SkylitControlBar ticker="SPY" />);
  expect(screen.queryByTestId("skylit-info-popover")).not.toBeInTheDocument();

  fireEvent.click(screen.getByTestId("skylit-info-btn"));
  const pop = screen.getByTestId("skylit-info-popover");
  expect(pop.textContent).toContain("GEX");
  expect(pop.textContent).toContain("Trade");

  fireEvent.click(screen.getByTestId("skylit-info-btn"));
  expect(screen.queryByTestId("skylit-info-popover")).not.toBeInTheDocument();
});
