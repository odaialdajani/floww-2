/**
 * @jest-environment jsdom
 */

/**
 * Tests for useHeatseeker — the fetch hook backing every Solstice panel.
 *
 * Behaviour under test:
 *   1. Initial render returns {data: null, loading: true, error: null} while the
 *      first fetch is in flight.
 *   2. Successful fetch resolves with {data, loading: false, error: null}.
 *   3. Failed fetch resolves with {data: null, loading: false, error}.
 *   4. Unmounting aborts any in-flight AbortController.
 *   5. Param change triggers a refetch — data swaps from response 1 to response 2.
 */

import React from "react";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useHeatseeker } from "./useHeatseeker";

// Helper to build a fetch mock with a configurable JSON payload + ok flag.
function mockJsonResponse(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

describe("useHeatseeker", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = global.fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  test("returns loading=true with null data on initial render", async () => {
    // Fetch hangs forever — we never resolve so the hook stays in its initial loading state.
    let resolveFetch;
    global.fetch = jest.fn(
      () => new Promise((res) => { resolveFetch = res; })
    );

    const { result, unmount } = renderHook(() =>
      useHeatseeker("flip-zones", { ticker: "SPY", refreshMs: 0 })
    );

    // After mount the effect has fired setLoading(true) synchronously.
    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();

    // Cleanup — resolve so the dangling promise doesn't leak past the test.
    if (resolveFetch) resolveFetch(mockJsonResponse({}));
    unmount();
  });

  test("returns data, loading=false, error=null after fetch resolves", async () => {
    const payload = { flip_zones: [{ price: 500, from_sign: 1, to_sign: -1, strength: 1e9 }] };
    global.fetch = jest.fn(async () => mockJsonResponse(payload));

    const { result } = renderHook(() =>
      useHeatseeker("flip-zones", { ticker: "SPY", refreshMs: 0 })
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual(payload);
    expect(result.current.error).toBeNull();
  });

  test("returns error on fetch rejection", async () => {
    global.fetch = jest.fn(async () => {
      throw new Error("network down");
    });

    const { result } = renderHook(() =>
      useHeatseeker("flip-zones", { ticker: "SPY", refreshMs: 0 })
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("network down");
    expect(result.current.data).toBeNull();
  });

  test("returns error on non-ok HTTP response", async () => {
    global.fetch = jest.fn(async () =>
      mockJsonResponse({}, { ok: false, status: 500 })
    );

    const { result } = renderHook(() =>
      useHeatseeker("flip-zones", { ticker: "SPY", refreshMs: 0 })
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toMatch(/HTTP 500/);
  });

  test("aborts the in-flight AbortController on unmount", async () => {
    // Capture the AbortSignal handed to fetch so we can assert .aborted flipped to true.
    let capturedSignal = null;
    global.fetch = jest.fn(
      (_url, opts) => {
        capturedSignal = opts?.signal ?? null;
        // Never resolve — we need the request to remain pending until unmount.
        return new Promise(() => {});
      }
    );

    const { unmount } = renderHook(() =>
      useHeatseeker("flip-zones", { ticker: "SPY", refreshMs: 0 })
    );

    // Wait for fetch to have been called at least once.
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(capturedSignal).not.toBeNull();
    expect(capturedSignal.aborted).toBe(false);

    unmount();

    expect(capturedSignal.aborted).toBe(true);
  });

  test("param change triggers a refetch — data swaps from first response to second", async () => {
    const responses = {
      AAPL: { flip_zones: [{ price: 200 }] },
      MSFT: { flip_zones: [{ price: 400 }] },
    };
    global.fetch = jest.fn(async (url) => {
      const ticker = String(url).includes("ticker=AAPL") ? "AAPL" : "MSFT";
      return mockJsonResponse(responses[ticker]);
    });

    const { result, rerender } = renderHook(
      ({ ticker }) => useHeatseeker("flip-zones", { ticker, refreshMs: 0 }),
      { initialProps: { ticker: "AAPL" } }
    );

    await waitFor(() => expect(result.current.data).toEqual(responses.AAPL));

    // Param flip — hook should refetch and update.
    rerender({ ticker: "MSFT" });

    await waitFor(() => expect(result.current.data).toEqual(responses.MSFT));
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  test("a slow read survives polling ticks instead of being repeatedly aborted", async () => {
    jest.useFakeTimers();
    let resolveRead;
    let signal;
    global.fetch = jest.fn((_url, options) => {
      signal = options.signal;
      return new Promise(resolve => { resolveRead = resolve; });
    });
    const { result, unmount } = renderHook(() =>
      useHeatseeker("flip-zones", { ticker: "SPY", refreshMs: 10000 })
    );
    const firstSignal = signal;
    act(() => { jest.advanceTimersByTime(30000); });
    expect(firstSignal.aborted).toBe(false);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    await act(async () => { resolveRead(mockJsonResponse({ spot: 123 })); });
    expect(result.current.data).toEqual({ spot: 123 });
    expect(result.current.loading).toBe(false);
    act(() => { jest.advanceTimersByTime(10000); });
    expect(global.fetch).toHaveBeenCalledTimes(2);
    unmount();
  });

  test("a superseded request error cannot overwrite the new symbol reading", async () => {
    let rejectOld;
    global.fetch = jest.fn(url => String(url).includes("ticker=SPY")
      ? new Promise((_resolve, reject) => { rejectOld = reject; })
      : Promise.resolve(mockJsonResponse({ ticker: "QQQ", spot: 456 })));
    const { result, rerender } = renderHook(
      ({ ticker }) => useHeatseeker("flip-zones", { ticker, refreshMs: 0 }),
      { initialProps: { ticker: "SPY" } }
    );
    rerender({ ticker: "QQQ" });
    await waitFor(() => expect(result.current.data?.ticker).toBe("QQQ"));
    await act(async () => { rejectOld(new Error("old SPY read failed")); });
    expect(result.current.error).toBeNull();
    expect(result.current.data).toEqual({ ticker: "QQQ", spot: 456 });
    expect(result.current.loading).toBe(false);
  });

  test("a hung read times out and a later poll can retry", async () => {
    jest.useFakeTimers();
    const signals = [];
    global.fetch = jest.fn((_url, options) => {
      signals.push(options.signal);
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(
          Object.assign(new Error('aborted'), { name: 'AbortError' })
        ));
      });
    });
    const { result, unmount } = renderHook(() =>
      useHeatseeker('flip-zones', { ticker: 'SPY', refreshMs: 10000 })
    );
    await act(async () => { jest.advanceTimersByTime(45000); });
    expect(signals[0].aborted).toBe(true);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toMatch(/timed out/i);
    act(() => { jest.advanceTimersByTime(5000); });
    expect(global.fetch).toHaveBeenCalledTimes(2);
    unmount();
    expect(jest.getTimerCount()).toBe(0);
  });
});
