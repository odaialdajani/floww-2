/**
 * @jest-environment jsdom
 *
 * The Market inspector must stay clear of the app's floating controls: the
 * "App health" chip and the Ask Flow opener both sit in the bottom-right
 * lane. These checks measure that lane from the real sources (the chip's
 * inline placement plus the shared stylesheet, the opener's stylesheet) and
 * compare the measured band with the clearance the dock actually applies,
 * including the narrow layout where the chip moves up.
 */

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

const LINE_HEIGHT_FACTOR = 1.2;
const DEFAULT_FONT_SIZE_PX = 16;
const EXPECTED_MARGIN_PX = 16;

const readSource = (relative) => fs.readFileSync(path.join(__dirname, relative), "utf8");

const numberIn = (text, pattern, group = 1) => {
  const match = String(text).match(pattern);
  expect(match).not.toBeNull();
  return Number(match[group]);
};

const pxNumbers = (text) => (String(text).match(/\d+px/g) || []).map((value) => Number(value.replace("px", "")));

const measureFloatingControls = () => {
  const problemStatus = readSource("../../diagnostics/ProblemStatus.jsx");
  const theme = readSource("../../NeutralTheme.css");
  const appCss = readSource("../../App.css");
  const indexCss = readSource("../../index.css");

  const healthBottomWide = numberIn(problemStatus, /bottom:\s*(\d+)/);
  const healthFontSize = numberIn(problemStatus, /fontSize:\s*(\d+)/);
  const healthRule = theme.match(/aside\[aria-label="App health"\] > button \{([^}]*)\}/)[1];
  const healthMinHeight = numberIn(healthRule, /min-height:\s*(\d+)px/);
  const healthPadding = numberIn(healthRule, /padding:\s*(\d+)px/);
  const healthBorder = numberIn(healthRule, /border:\s*(\d+)px/);
  const healthHeight = Math.max(
    healthMinHeight,
    Math.ceil(healthFontSize * LINE_HEIGHT_FACTOR) + healthPadding * 2 + healthBorder * 2,
  );
  const healthNarrow = theme.match(
    /@media screen and \(max-width: (\d+)px\) \{[\s\S]*?aside\[aria-label="App health"\] \{ bottom: calc\((\d+)px/,
  );
  expect(healthNarrow).not.toBeNull();

  const askRule = appCss.match(/\.lodestar-open \{([^}]*)\}/)[1];
  const askBottomWide = numberIn(askRule, /bottom:\s*(\d+)px/);
  const askPadding = numberIn(askRule, /padding:\s*(\d+)px/);
  const askBorder = numberIn(askRule, /border:\s*(\d+)px/);
  const bodyFontSize = indexCss.match(/body \{([\s\S]*?)\}/)[1].match(/font-size:\s*(\d+)px/);
  const askFontSize = bodyFontSize ? Number(bodyFontSize[1]) : DEFAULT_FONT_SIZE_PX;
  const askHeight = Math.ceil(askFontSize * LINE_HEIGHT_FACTOR) + askPadding * 2 + askBorder * 2;
  const askNarrow = appCss.match(
    /@media \(max-width: (\d+)px\) \{ \.lodestar-open \{ bottom:calc\((\d+)px/,
  );
  expect(askNarrow).not.toBeNull();

  return {
    healthBreakpoint: Number(healthNarrow[1]),
    askBreakpoint: Number(askNarrow[1]),
    healthHeight,
    askHeight,
    wide: Math.max(healthBottomWide + healthHeight, askBottomWide + askHeight),
    narrow: Math.max(Number(healthNarrow[2]) + healthHeight, Number(askNarrow[2]) + askHeight),
  };
};

const props = {
  ticker: "SPY",
  data: { snapshotId: "snap/1" },
  wall: { wall_id: "w1", low: 100, high: 101 },
  quality: { state: "usable" },
  onClose: jest.fn(),
  onContracts: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockImplementation(async () => ({ data: { frames: [] } }));
});

test("the inspector reserves the measured floating-control band", async () => {
  const measured = measureFloatingControls();
  await act(async () => render(<MarketInspectorDock {...props} />));
  const dock = screen.getByTestId("triad-inspector-dock");
  const style = dock.style;
  const topOffset = numberIn(style.getPropertyValue("--tdk-inspector-top-offset"), /(\d+)px/);
  const clearanceWide = numberIn(style.getPropertyValue("--tdk-floating-clearance-wide"), /(\d+)px/);
  const clearanceNarrow = numberIn(style.getPropertyValue("--tdk-floating-clearance-narrow"), /(\d+)px/);

  expect(clearanceWide).toBeGreaterThanOrEqual(measured.wide + EXPECTED_MARGIN_PX);
  expect(clearanceNarrow).toBeGreaterThanOrEqual(measured.narrow + EXPECTED_MARGIN_PX);

  const maxHeight = style.getPropertyValue("--tdk-dock-max-height");
  expect(pxNumbers(maxHeight)).toEqual([topOffset, clearanceWide]);
  expect(maxHeight).toContain("env(safe-area-inset-bottom)");
  const viewportVh = 100;
  const dockHeightVh = viewportVh - (topOffset + clearanceWide);
  const dockBottomVh = topOffset + dockHeightVh;
  expect(viewportVh - dockBottomVh).toBeGreaterThanOrEqual(measured.wide + EXPECTED_MARGIN_PX);

  expect(pxNumbers(style.getPropertyValue("--tdk-dock-bottom-wide"))).toEqual([clearanceWide]);
  expect(pxNumbers(style.getPropertyValue("--tdk-dock-bottom-compact"))).toEqual([clearanceNarrow]);
  expect(style.getPropertyValue("--tdk-dock-bottom-compact")).toContain("env(safe-area-inset-bottom)");
});

test("the inspector compact breakpoint matches the controls it clears", async () => {
  const measured = measureFloatingControls();
  const marketCss = readSource("MarketDesktop.css");
  const compactRule = marketCss.match(
    /@media screen and \(max-width: (\d+)px\) \{\s*\.trinity-desktop\.tdk-dock-open \.tdk-dock \{[^}]*bottom: var\(--tdk-dock-bottom-compact/,
  );
  expect(compactRule).not.toBeNull();
  expect(Number(compactRule[1])).toBe(measured.healthBreakpoint);
  expect(Number(compactRule[1])).toBe(measured.askBreakpoint);
});

test("the inspector stylesheet consumes the measured clearance", () => {
  const marketCss = readSource("MarketDesktop.css");
  expect(marketCss).toContain("top: var(--tdk-inspector-top-offset");
  expect(marketCss).toContain("max-height: var(--tdk-dock-max-height");
  expect(marketCss).toContain("bottom: var(--tdk-dock-bottom-wide");
  expect(marketCss).toContain("bottom: var(--tdk-dock-bottom-compact");
});
