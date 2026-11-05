import React from "react";
import { render, screen } from "@testing-library/react";
import ToxicityGauge from "./ToxicityGauge";

test("an uninitialized status never displays zero probabilities", () => {
  render(<ToxicityGauge ensemble={{ ticker: "SPY", status: "uninitialized" }} />);
  expect(screen.queryByText("0.0%")).toBeNull();
  expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
});

test("a measured zero remains zero while absent horizons stay unknown", () => {
  render(<ToxicityGauge ensemble={{ status: "active", ensemble_probabilities: { p_toxic_1min: 0 } }} />);
  expect(screen.getAllByText("0.0%")).toHaveLength(1);
  expect(screen.queryByText("LIVE")).toBeNull();
  expect(screen.queryByText("No anomalies detected")).toBeNull();
});

test("invalid probabilities never produce a percentage", () => {
  render(<ToxicityGauge ensemble={{ ensemble_probabilities: {
    p_toxic_1min: null, p_toxic_5min: NaN, p_toxic_15min: -0.1, p_toxic_60min: 1.1,
  } }} />);
  expect(screen.queryAllByText(/%$/)).toHaveLength(0);
});

test("partial component scores preserve a real zero without crashing on unknowns", () => {
  render(<ToxicityGauge ensemble={{ component_scores: {
    cnn_ae: null, statistical: 0, forecast_residual: NaN,
  } }} />);
  expect(screen.getByText("0.0000")).toBeInTheDocument();
  expect(screen.queryByText("NaN")).toBeNull();
});
