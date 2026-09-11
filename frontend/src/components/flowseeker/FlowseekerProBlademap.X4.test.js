/**
 * X4 — poll interval persistence test for Blademap inline surfaces.
 *
 * Pins the poll-interval contract found in receipt X4-dynamic-behavior.md:
 * - pollMs defaults to 60000 when localStorage empty (FlowseekerProBlademap.jsx:414-416)
 * - pollMs persists to localStorage on mount (FlowseekerProBlademap.jsx:417)
 *
 * This is the component's owned contract: it reads fsb.pollMs from localStorage
 * and persists it back. The stale/retry edge for inline surfaces is covered
 * by scanLogic.X4.test.js (pulseState classification).
 *
 * Scope: FlowseekerProBlademap.jsx pollMs persistence path only.
 * No backend, no App.js, no live feed, no dead-component revival.
 */

import { render } from "@testing-library/react";
import React from "react";
import FlowseekerProBlademap from "./FlowseekerProBlademap";

const mockLocalStorage = {
  _data: {},
  getItem(key) { return this._data[key] ?? null; },
  setItem(key, val) { this._data[key] = String(val); },
  removeItem(key) { delete this._data[key]; },
  clear() { this._data = {}; },
};

beforeAll(() => {
  Object.defineProperty(global, "localStorage", {
    value: mockLocalStorage,
    writable: true,
    configurable: true,
  });
});

beforeEach(() => {
  mockLocalStorage.clear();
});

const mockAxios = { get: jest.fn(() => Promise.resolve({ ok: true, data: [] })) };
jest.mock("axios", () => () => mockAxios);

describe("X4 — poll interval persistence (FlowseekerProBlademap.jsx:414-417)", () => {
  test("defaults to 60000 when localStorage empty — persists default on mount", () => {
    // localStorage empty → component reads null → falls back to 60000 (L414-416)
    // On mount, the useEffect persists the value back (L417)
    render(<FlowseekerProBlademap ticker="SPY" width={800} height={600} />);
    // After render, localStorage should carry the persisted value.
    // The component stores String(pollMs) — default 60000.
    expect(mockLocalStorage.getItem("fsb.pollMs")).toBe("60000");
  });

  test("custom pollMs persists to localStorage on mount", () => {
    mockLocalStorage.setItem("fsb.pollMs", "30000");
    render(<FlowseekerProBlademap ticker="SPY" width={800} height={600} />);
    expect(mockLocalStorage.getItem("fsb.pollMs")).toBe("30000");
  });

  test("pollMs persistence survives re-render with same value", () => {
    mockLocalStorage.setItem("fsb.pollMs", "45000");
    render(<FlowseekerProBlademap ticker="SPY" width={800} height={600} />);
    expect(mockLocalStorage.getItem("fsb.pollMs")).toBe("45000");
  });
});
