/** RetryButton 404 contract: a 404 ("No options data for <ticker>") is permanent
 * for that ticker — auto-retrying it every few seconds forever with
 * "Data source busy" is wrong. 404 must not auto-retry and must say so.
 * 429/500 keep their existing auto-retry behavior.
 */
import React from "react";
import { render, screen, act } from "@testing-library/react";
import { RetryButton, ErrorState } from "./RetryButton";

jest.useFakeTimers();

afterEach(() => {
  jest.clearAllTimers();
});

test("404 error state does not auto-retry and names the cause", () => {
  const onRetry = jest.fn();
  render(
    <ErrorState
      error={{ status_code: 404, message: "No options data for ZOOM" }}
      onRetry={onRetry}
      title="Charm data unavailable"
    />
  );
  expect(screen.getByText(/no options data for this ticker/i)).toBeInTheDocument();
  expect(screen.queryByTestId("retry-countdown")).not.toBeInTheDocument();
  act(() => {
    jest.advanceTimersByTime(120000);
  });
  expect(onRetry).not.toHaveBeenCalled();
  expect(screen.getByTestId("retry-button")).toBeInTheDocument();
});

test("429 keeps auto-retry with 60s countdown", () => {
  const onRetry = jest.fn().mockResolvedValue(undefined);
  render(<ErrorState error={{ status_code: 429 }} onRetry={onRetry} />);
  expect(screen.getByTestId("retry-countdown")).toBeInTheDocument();
});

test("500 keeps auto-retry", () => {
  const onRetry = jest.fn().mockResolvedValue(undefined);
  render(<ErrorState error={{ status_code: 500 }} onRetry={onRetry} />);
  expect(screen.getByTestId("retry-countdown")).toBeInTheDocument();
});
