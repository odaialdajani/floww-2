/**
 * A failed ML prediction must not read as "no signal".
 *
 * AlertsPanel fetched /api/ml/predict with `catch { /* noop *\/ }` and
 * rendered the ML block only when `mlPrediction.prediction` was truthy.
 * So every failure mode — a corrupt model artifact (503), a missing model
 * (404), a server fault (500) — collapsed into the same visual as a
 * genuinely neutral reading: no ML row at all.
 *
 * That matters on a trading surface. "The model did not answer" and "the
 * model answered HOLD" must never look the same, because one invites a
 * decision and the other is the absence of one.
 *
 * The backend now returns a 503 whose body names the artifact and the
 * cause (see routes/ml_predict_api.py). This surfaces that state instead
 * of swallowing it.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import AlertsPanel from "./AlertsPanel";

const API = "http://localhost:8000/api";

// AlertsPanel does `import axios from "axios"`, so the module must be
// mocked at the module boundary — a global stub is bypassed by the ESM
// default import.
jest.mock("axios", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

const axios = require("axios").default;
const axiosGet = axios.get;

beforeEach(() => {
  axiosGet.mockReset();
  axiosGet.mockResolvedValue({ data: { alerts: [], triggered: [] } });
});

afterEach(() => {
  jest.clearAllMocks();
});

test("shows an explicit unavailable reason when the model artifact cannot load", async () => {
  axiosGet.mockImplementation(async (url) => {
    if (String(url).includes("/ml/predict")) {
      return Promise.reject({
        response: {
          status: 503,
          data: {
            error: "model_artifact_unloadable",
            artifact: "price_model_SPY.joblib",
            cause: "ModuleNotFoundError: No module named '_loss'",
          },
        },
      });
    }
    return { data: { alerts: [], triggered: [] } };
  });

  render(<AlertsPanel ticker="SPY" />);
  // open the collapsible
  const toggle = screen.getByRole("button");
  toggle.click();

  await waitFor(() => {
    expect(screen.getByTestId("ml-unavailable")).toBeInTheDocument();
  });
  const el = screen.getByTestId("ml-unavailable");
  // the reason must be visible, not a bare "unavailable"
  expect(el.textContent).toMatch(/artifact|model/i);
  // and it must NOT be rendered as a prediction
  expect(screen.queryByTestId("ml-prediction")).not.toBeInTheDocument();
});

test("a 404 says the model is missing rather than unavailable", async () => {
  axiosGet.mockImplementation(async (url) => {
    if (String(url).includes("/ml/predict")) {
      return Promise.reject({ response: { status: 404, data: {} } });
    }
    return { data: { alerts: [], triggered: [] } };
  });

  render(<AlertsPanel ticker="QQQ" />);
  screen.getByRole("button").click();

  await waitFor(() => {
    expect(screen.getByTestId("ml-unavailable")).toBeInTheDocument();
  });
  expect(screen.getByTestId("ml-unavailable").textContent).toMatch(/no model|not trained|missing/i);
});

test("a successful prediction still renders and does not show the unavailable row", async () => {
  axiosGet.mockImplementation(async (url) => {
    if (String(url).includes("/ml/predict")) {
      return {
        data: { ticker: "SPY", prediction: "HOLD", confidence: 0.55, spot: 765.4 },
      };
    }
    return { data: { alerts: [], triggered: [] } };
  });

  render(<AlertsPanel ticker="SPY" />);
  screen.getByRole("button").click();

  await waitFor(() => {
    expect(screen.getByTestId("ml-prediction")).toBeInTheDocument();
  });
  expect(screen.getByTestId("ml-prediction").textContent).toMatch(/HOLD/);
  expect(screen.queryByTestId("ml-unavailable")).not.toBeInTheDocument();
});
