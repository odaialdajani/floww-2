/** @jest-environment jsdom */
import React from "react";
import { render, screen, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import MarketInspectorDock from "./MarketInspectorDock";

jest.mock("axios");
jest.mock("../heatseeker/ExactContractReview", () => () => null);
jest.mock("../heatseeker/AskFlow", () => () => null);
jest.mock("../public/PublicHandoffReview", () => ({ GroundedPublicReview: () => null }));

const fs = require("fs");
const path = require("path");

const CONTROL_STACK_PX = 112;

const props = {
  ticker: "SPY",
  data: { snapshotId: "snap/1" },
  wall: { wall_id: "w1", low: 100, high: 101 },
  quality: { state: "usable" },
  onClose: jest.fn(),
  onContracts: jest.fn(),
};

const readCss = () => fs.readFileSync(path.join(__dirname, "MarketDesktop.css"), "utf8");

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockImplementation(async () => ({ data: { frames: [] } }));
});

test("the Market inspector reserves the global floating-control band", async () => {
  await act(async () => render(<MarketInspectorDock {...props} />));
  const dock = screen.getByTestId("triad-inspector-dock");
  expect(dock.className).toContain("tdk-dock");
  const clearance = readCss().match(/--tdk-floating-clearance:\s*(\d+)px/);
  expect(clearance).not.toBeNull();
  expect(Number(clearance[1])).toBeGreaterThanOrEqual(CONTROL_STACK_PX);
});

test("both Market inspector layouts apply the reserved band", () => {
  const css = readCss();
  const base = css.match(/^\.tdk-dock \{[^}]*\}/m);
  expect(base).not.toBeNull();
  expect(base[0]).toContain("max-height: calc(100vh - var(--tdk-floating-clearance))");
  const narrow = css.match(/\.trinity-desktop\.tdk-dock-open \.tdk-dock \{[^}]*\}/);
  expect(narrow).not.toBeNull();
  expect(narrow[0]).toContain("bottom: var(--tdk-floating-clearance)");
});
