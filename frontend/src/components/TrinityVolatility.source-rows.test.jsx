/* G3 pin (Hermes-2, M2 freeze 4): the long exact-source review rows on the
   Volatility tab live behind NAMED details controls — closed by default so
   the tab stays an uncluttered read, with the full exact rows (nearest
   strike, actual delta, distance from target, per expiry) disclosed on
   demand. Pinned RED before the wrap; the real-browser receipt proves the
   actual open/close toggle (jsdom does not implement details activation). */
import React from 'react';
import { render, screen, act } from '@testing-library/react';
import axios from 'axios';
import TrinityVolatility from './TrinityVolatility';

jest.mock("../config/api", () => ({ API: "/api", BACKEND_URL: "", BACKEND_BASE: "" }));
jest.mock("axios", () => ({ get: jest.fn() }));

const chain = {
  ticker: "SPY", spot: 767.94,
  expiries: ["2026-10-19", "2026-10-21"],
  data_source: "public_api", event_time: null,
  fetched_at: "2026-10-19T13:32:51Z",
  rows: [
    { expiry: "2026-10-19", type: "call", strike: 765, iv: 3.60, delta: 0.47, oi: 1200 },
    { expiry: "2026-10-19", type: "put", strike: 765, iv: 3.55, delta: -0.47, oi: 700 },
    { expiry: "2026-10-21", type: "call", strike: 770, iv: 2.90, delta: 0.46, oi: 900 },
    { expiry: "2026-10-21", type: "put", strike: 770, iv: 2.80, delta: -0.46, oi: 800 },
  ],
};

const plotlyStub = { react: jest.fn().mockImplementation(async () => {}), purge: jest.fn() };

async function mount() {
  axios.get.mockImplementation(() => Promise.resolve({ data: chain }));
  Object.defineProperty(window, "Plotly", { value: plotlyStub, configurable: true });
  await act(async () => { render(<TrinityVolatility ticker="SPY" expiries={2} loaderDeadlineMs={10000} />); });
  await screen.findByText(/SPY \u00b7 spot /);
}

test("ATM term-structure exact rows sit behind a named closed details", async () => {
  await mount();
  const details = document.querySelector('[data-testid="tv-source-details-term"]');
  expect(details).not.toBeNull();
  expect(details.tagName).toBe("DETAILS");
  expect(details.open).toBe(false);
  // The summary NAMES the content (not a bare chevron).
  expect(details.querySelector("summary").textContent).toMatch(/exact/i);
  expect(details.querySelector("summary").textContent).toMatch(/expir/i);
  // Full exact rows preserved inside: per-expiry nearest strike + delta.
  const body = details.textContent;
  expect(body).toContain("2026-10-19");
  expect(body).toContain("2026-10-21");
  expect(body).toMatch(/call 76[58] IV/);
  expect(body).toMatch(/distance/);
});

test("25\u0394 RR exact rows sit behind their own named closed details", async () => {
  await mount();
  const details = document.querySelector('[data-testid="tv-source-details-rr"]');
  expect(details).not.toBeNull();
  expect(details.open).toBe(false);
  expect(details.querySelector("summary").textContent).toMatch(/exact/i);
  const body = details.textContent;
  expect(body).toContain("from +0.25");
  expect(body).toContain("from \u22120.25");
});

test("the short lens captions stay visible outside the details", async () => {
  await mount();
  // The one-line approximation captions are NOT inside the details.
  const termDetails = document.querySelector('[data-testid="tv-source-details-term"]');
  const caption = screen.getByText(/vol vs expiry \u00b7 nearest-observation approximation/);
  expect(termDetails.contains(caption)).toBe(false);
});
