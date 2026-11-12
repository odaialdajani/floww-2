/**
 * @jest-environment jsdom
 */

import React from "react";
import { act, render, screen } from "@testing-library/react";
import { PositionSizing } from "./PositionSizing";

const originalFetch = global.fetch;
beforeEach(() => { global.fetch = jest.fn().mockRejectedValue(new Error("test")); });
afterEach(() => { global.fetch = originalFetch; });

describe("PositionSizing", () => {
  test("renders without crashing on null/undefined props", async () => {
    let container;
    await act(async () => { ({ container } = render(<PositionSizing ticker="SPY" spot={null} />)); });
    expect(screen.getByText("Position Sizing Calculator")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(expect.stringMatching(/\/daily-checklist\/SPY\?expiries=4$/));
    expect(container).toBeTruthy();
  });
});
