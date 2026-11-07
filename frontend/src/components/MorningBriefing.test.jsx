/**
 * @jest-environment jsdom
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { MorningBriefing } from "./MorningBriefing";

const originalFetch = global.fetch;
beforeEach(() => { global.fetch = jest.fn().mockRejectedValue(new Error("test")); });
afterEach(() => { global.fetch = originalFetch; });

describe("MorningBriefing", () => {
  test("renders without crashing on null/undefined props", async () => {
    const { container } = render(<MorningBriefing ticker="SPY" spot={null} />);
    await screen.findByText("No briefing data available");
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(expect.stringMatching(/\/daily-checklist\/SPY\?expiries=4$/));
    expect(container).toBeTruthy();
  });
});
