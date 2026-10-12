import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import BriefingStrip from "../../BriefingStrip";

const payload = { ticker: "SPY", asof: "2026-10-11T12:00:00+00:00",
  regime: "BULL", metrics: { net_gex: 1e9 } };

function mockFetch(data) {
  global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(data) }));
}

beforeEach(() => { jest.restoreAllMocks(); });
afterEach(() => { delete global.fetch; });

test("export button copies a draft agent brief, never an order", async () => {
  mockFetch(payload);
  const writeText = jest.fn(() => Promise.resolve());
  Object.assign(navigator, { clipboard: { writeText } });
  render(<BriefingStrip ticker="SPY" />);
  const btn = await screen.findByTestId("export-brief");
  fireEvent.click(btn);
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const brief = JSON.parse(writeText.mock.calls[0][0]);
  expect(brief.ticker).toBe("SPY");
  expect(brief.brief).toBe("floww-agent-brief.v1");
  expect(brief.executes_nothing).toBe(true);
  expect(brief.asof).toBe("2026-10-11T12:00:00+00:00");
  expect(await screen.findByTestId("export-brief-status")).toHaveTextContent(/copied|paste/i);
  delete navigator.clipboard;
});

test("copy failure falls back to selectable text, never silence", async () => {
  mockFetch(payload);
  Object.assign(navigator, { clipboard: { writeText: () => Promise.reject(new Error("denied")) } });
  render(<BriefingStrip ticker="SPY" />);
  fireEvent.click(await screen.findByTestId("export-brief"));
  const box = await screen.findByTestId("export-brief-text");
  expect(JSON.parse(box.value).ticker).toBe("SPY");
  delete navigator.clipboard;
});

test("no export button without briefing data", async () => {
  global.fetch = jest.fn(() => Promise.reject(new Error("down")));
  render(<BriefingStrip ticker="SPY" />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  expect(screen.queryByTestId("export-brief")).not.toBeInTheDocument();
});
