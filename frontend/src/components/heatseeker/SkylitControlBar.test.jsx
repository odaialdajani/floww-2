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

test("prev/next arrows cycle the tape list; open-universe tickers wrap from the boundary", () => {
  const onTickerChange = jest.fn();
  const { unmount } = render(
    <SkylitControlBar ticker="SPY" onTickerChange={onTickerChange} tickers={["SPY", "QQQ", "HOOD"]} />
  );
  fireEvent.click(screen.getByTestId("skylit-next-ticker"));
  expect(onTickerChange).toHaveBeenCalledWith("QQQ");
  fireEvent.click(screen.getByTestId("skylit-prev-ticker"));
  expect(onTickerChange).toHaveBeenLastCalledWith("HOOD");
  unmount();

  // Open-universe symbol not in the list: arrows wrap from the boundary
  // (forward → first, back → last) instead of silently doing nothing.
  const onTickerChange2 = jest.fn();
  render(<SkylitControlBar ticker="RIVN" onTickerChange={onTickerChange2} tickers={["SPY", "QQQ"]} />);
  fireEvent.click(screen.getByTestId("skylit-next-ticker"));
  expect(onTickerChange2).toHaveBeenCalledWith("SPY");
  fireEvent.click(screen.getByTestId("skylit-prev-ticker"));
  expect(onTickerChange2).toHaveBeenLastCalledWith("QQQ");
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

test("O2: one family control GEX/VEX/Charm; basis is a compact GEX-only menu", () => {
  const onViewModeChange = jest.fn();
  const onMetricChange = jest.fn();
  render(<SkylitControlBar ticker="SPY" viewMode="gex" metric="raw" onViewModeChange={onViewModeChange} onMetricChange={onMetricChange} />);
  // Single permanent family tab set (no Raw/Delta/Activity tower).
  expect(screen.queryByTestId("skylit-metric-switch")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTitle("Charm Exposure"));
  expect(onViewModeChange).toHaveBeenCalledWith("charm");
  // GEX basis menu present on the GEX family, carrying the same contract.
  const basis = screen.getByTestId("skylit-basis-select");
  expect(basis.value).toBe("raw");
  fireEvent.change(basis, { target: { value: "activity" } });
  expect(onMetricChange).toHaveBeenCalledWith("activity");
});

test("O2: basis menu hides on single-basis families (VEX/Charm)", () => {
  render(<SkylitControlBar ticker="SPY" viewMode="vex" metric="raw" />);
  expect(screen.queryByTestId("skylit-basis-select")).not.toBeInTheDocument();
  render(<SkylitControlBar ticker="SPY" viewMode="charm" metric="raw" />);
  expect(screen.queryByTestId("skylit-basis-select")).not.toBeInTheDocument();
});

test("2026-10-19: missing, nonfinite and zero percentage readings stay distinct", () => {
  // Missing percentage: the change renders, the percentage slot is an em-dash — never a fabricated 0.00%.
  const missing = render(<SkylitControlBar ticker="SPY" spot={650} change={1.25} changePct={null} />);
  expect(screen.getByText(/\(—\)/)).toBeInTheDocument();
  missing.unmount();
  // A nonfinite percentage is unknown too — NaN must never reach the pixels.
  const nonfinite = render(<SkylitControlBar ticker="SPY" spot={650} change={1.25} changePct={NaN} />);
  expect(screen.getByText(/\(—\)/)).toBeInTheDocument();
  expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  nonfinite.unmount();
  // A real zero reading renders as an honest 0.00%, distinct from missing.
  const zero = render(<SkylitControlBar ticker="SPY" spot={650} change={0} changePct={0} />);
  expect(screen.getByText(/0\.00%/)).toBeInTheDocument();
  zero.unmount();
  // Nonfinite change/spot never render NaN; the spot falls back to —.
  const invalid = render(<SkylitControlBar ticker="SPY" spot={NaN} change={NaN} />);
  expect(screen.getByText(/^\$—$/)).toBeInTheDocument();
  expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
});

test("2026-10-19: source clock is primary when parseable; local clock is labelled, including invalid as-of fallback", () => {
  const sourced = render(<SkylitControlBar ticker="SPY" lastUpdate="2026-10-19T14:03:05Z" />);
  expect(screen.getByTitle("Source clock")).toBeInTheDocument();
  expect(screen.queryByTitle("Local ticking clock")).not.toBeInTheDocument();
  sourced.unmount();
  const localOnly = render(<SkylitControlBar ticker="SPY" />);
  expect(screen.getByTitle("Local ticking clock")).toBeInTheDocument();
  localOnly.unmount();
  // An unparseable as-of value is an unknown clock: labelled local fallback, never "Invalid Date" pixels.
  const invalid = render(<SkylitControlBar ticker="SPY" lastUpdate="not-a-timestamp" />);
  expect(screen.getByTitle("Local ticking clock")).toBeInTheDocument();
  expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
});

test("2026-10-19: share failures are visible, never a silent false Copied", async () => {
  // Clipboard API absent entirely.
  Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
  const noApi = render(<SkylitControlBar ticker="SPY" />);
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-share-btn")); });
  expect(screen.getByTestId("skylit-copy-status")).toHaveTextContent("Clipboard unavailable");
  expect(screen.getByTestId("skylit-share-btn")).toHaveAttribute("title", "Copy page link");
  noApi.unmount();
  // Clipboard present but the write is rejected.
  const reject = jest.fn(async () => { throw new Error("denied"); });
  Object.defineProperty(navigator, "clipboard", { value: { writeText: reject }, configurable: true });
  const denied = render(<SkylitControlBar ticker="SPY" />);
  await act(async () => { fireEvent.click(screen.getByTestId("skylit-share-btn")); });
  expect(screen.getByTestId("skylit-copy-status")).toHaveTextContent("Copy denied");
  expect(screen.getByTestId("skylit-share-btn")).toHaveAttribute("title", "Copy page link");
});
