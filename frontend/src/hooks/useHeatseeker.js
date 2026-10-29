import { useEffect, useState, useRef, useCallback } from "react";
import { BACKEND_URL } from "../config/api";

// BACKEND_URL imported from config/api.js
const API = `${BACKEND_URL}/api/heatseeker`;

/**
 * Fetch hook for `/api/heatseeker/<endpoint>` routes.
 *
 * Returns: { data, loading, error, refresh }
 *  - data: response JSON or null
 *  - loading: true while the first request is in flight (or any refresh)
 *  - error: string message or null
 *  - refresh: manual re-fetch trigger
 *
 * Behaviour:
 *  - Cancels in-flight fetches on unmount or param change via AbortController
 *  - Auto-refreshes every `params.refreshMs` ms (default 10000); pass 0 to disable
 *  - Skips fetch entirely when `params.skip` is true (lets caller pause polling)
 *  - `params.ticker` and other keys become query-string params
 */
export function useHeatseeker(endpoint, params = {}) {
  const { refreshMs = 10000, skip = false, ...query } = params;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);
  const mountedRef = useRef(true);

  // Stable key for query params so the effect doesn't re-fire on identical objects
  const queryKey = JSON.stringify(query);

  const fetcher = useCallback(async () => {
    if (skip || !endpoint) return;
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (e) { /* noop */ }
    }
    const controller = new AbortController();
    abortRef.current = controller;
    let timedOut = false;
    const deadline = setTimeout(() => { timedOut = true; controller.abort(); }, 45000);
    controller.signal.addEventListener("abort", () => clearTimeout(deadline), { once: true });
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      Object.entries(query).forEach(([k, v]) => {
        if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
      });
      const url = `${API}/${endpoint}${qs.toString() ? `?${qs}` : ""}`;
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      const json = await res.json();
      if (mountedRef.current && abortRef.current === controller) {
        setData(json);
        setError(null);
      }
    } catch (e) {
      if (e.name === "AbortError" && !timedOut) return;
      if (mountedRef.current && abortRef.current === controller) {
        setError(timedOut ? "Request timed out. The server may be busy." : e.message || "Fetch failed");
      }
    } finally {
      clearTimeout(deadline);
      if (mountedRef.current && abortRef.current === controller) {
        abortRef.current = null;
        setLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, queryKey, skip]);

  useEffect(() => {
    mountedRef.current = true;
    fetcher();
    let id = null;
    if (refreshMs > 0 && !skip) {
      // Timer ticks must let a slow read finish. A manual refresh or changed
      // scope still calls fetcher directly and replaces the old request.
      id = setInterval(() => { if (!abortRef.current) fetcher(); }, refreshMs);
    }
    return () => {
      mountedRef.current = false;
      if (id) clearInterval(id);
      if (abortRef.current) {
        try { abortRef.current.abort(); } catch (e) { /* noop */ }
        abortRef.current = null;
      }
    };
  }, [fetcher, refreshMs, skip]);

  return { data, loading, error, refresh: fetcher };
}

export default useHeatseeker;
