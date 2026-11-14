/** @jest-environment jsdom */

import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useMarketData } from "./useMarketData";

describe("useMarketData request scope", () => {
  let originalIndexedDB;
  let originalFetch;
  let originalAbortSignalAny;
  let originalAbortSignalTimeout;

  beforeEach(() => {
    originalIndexedDB = window.indexedDB;
    originalFetch = global.fetch;
    originalAbortSignalAny = AbortSignal.any;
    originalAbortSignalTimeout = AbortSignal.timeout;
    AbortSignal.timeout = jest.fn(() => new AbortController().signal);
    AbortSignal.any = jest.fn((signals) => signals[0]);
    // Make cache reads/writes unavailable so this test isolates request scope.
    const fakeIndexedDB = {
      open: jest.fn(() => { throw new Error("IndexedDB unavailable in test"); }),
    };
    Object.defineProperty(window, "indexedDB", { configurable: true, value: fakeIndexedDB });
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: fakeIndexedDB });
  });

  afterEach(() => {
    Object.defineProperty(window, "indexedDB", { configurable: true, value: originalIndexedDB });
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: originalIndexedDB });
    global.fetch = originalFetch;
    AbortSignal.any = originalAbortSignalAny;
    AbortSignal.timeout = originalAbortSignalTimeout;
    jest.restoreAllMocks();
  });

  test("does not expose the previous endpoint while the next endpoint is loading", async () => {
    let resolveQqq;
    global.fetch = jest.fn((url) => String(url).includes("data/SPY")
      ? Promise.resolve({ ok: true, json: async () => ({ ticker: "SPY", spot: 500 }) })
      : new Promise((resolve) => { resolveQqq = resolve; }));

    const { result, rerender } = renderHook(
      ({ endpoint }) => useMarketData(endpoint, { refreshMs: 0 }),
      { initialProps: { endpoint: "data/SPY" } }
    );
    await waitFor(() => expect(window.indexedDB.open).toHaveBeenCalled());
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await waitFor(() => expect(result.current.data).toEqual({ ticker: "SPY", spot: 500 }));

    act(() => rerender({ endpoint: "data/QQQ" }));
    expect(result.current.data).toBeNull();
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));

    await act(async () => {
      resolveQqq({ ok: true, json: async () => ({ ticker: "QQQ", spot: 450 }) });
    });
    await waitFor(() => expect(result.current.data).toEqual({ ticker: "QQQ", spot: 450 }));
  });

  test("keeps cached data out of loading state during a silent stale refresh", async () => {
    const cachedPayload = { ticker: "QQQ", spot: 450 };
    const db = {
      transaction: () => ({
        objectStore: () => ({
          get: (key) => {
            const request = {};
            Promise.resolve().then(() => {
              request.result = {
                key,
                data: cachedPayload,
                ts: Date.now() - 6 * 60 * 1000,
              };
              request.onsuccess?.();
            });
            return request;
          },
        }),
      }),
    };
    const fakeIndexedDB = {
      open: jest.fn(() => {
        const request = {};
        Promise.resolve().then(() => {
          request.result = db;
          request.onsuccess?.();
        });
        return request;
      }),
    };
    Object.defineProperty(window, "indexedDB", { configurable: true, value: fakeIndexedDB });
    Object.defineProperty(globalThis, "indexedDB", { configurable: true, value: fakeIndexedDB });
    global.fetch = jest.fn(() => new Promise(() => {}));

    const { result } = renderHook(() =>
      useMarketData("data/QQQ", { refreshMs: 0 })
    );

    await waitFor(() => expect(result.current.data).toEqual(cachedPayload));
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(result.current.loading).toBe(false);
  });
});
