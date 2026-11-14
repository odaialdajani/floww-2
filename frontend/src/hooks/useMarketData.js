/**
 * useMarketData.js
 *
 * Offline-first data hook with IndexedDB caching.
 *
 * Strategy:
 *   1. Check IndexedDB cache first (instant).
 *   2. If cache miss or stale (>5 min), fetch from backend.
 *   3. On fetch error, fall back to cached data regardless of staleness.
 *   4. On success, update cache and serve fresh data.
 *   5. Display "Stale Data" badge when data is >15 min old.
 *
 * Returns: { data, loading, error, isStale, dataAge, refresh }
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { BACKEND_URL } from "../config/api";

// BACKEND_URL imported from config/api.js
const API = `${BACKEND_URL}/api`;

// IndexedDB configuration
const DB_NAME = "floww-market-data";
const DB_VERSION = 1;
const STORE = "cache";
const STALE_THRESHOLD_MS = 5 * 60 * 1000;       // 5 min — triggers background fetch
const BADGE_THRESHOLD_MS = 15 * 60 * 1000;       // 15 min — show "Stale Data" badge

// ── IndexedDB helpers ────────────────────────────────────────────────

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "key" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function cacheGet(key) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).get(key);
      req.onsuccess = () => {
        const entry = req.result;
        if (!entry) { resolve(null); return; }
        resolve({ data: entry.data, ts: entry.ts });
      };
      req.onerror = () => reject(req.error);
    });
  } catch {
    return null;  // IndexedDB unavailable — graceful degradation
  }
}

async function cachePut(key, data) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      const req = tx.objectStore(STORE).put({
        key,
        data,
        ts: Date.now(),
      });
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch {
    // silently fail — cache write is non-critical
  }
}

// ── Hook ─────────────────────────────────────────────────────────────

/**
 * @param {string} endpoint   API path after /api/, e.g. "data/SPY"
 * @param {Object} options
 * @param {number} [options.refreshMs=30000]  Polling interval (0 to disable)
 * @param {boolean} [options.skip=false]      If true, don't fetch
 * @param {Object} [options.query={}]         Extra query params
 */
export function useMarketData(endpoint, options = {}) {
  const { refreshMs = 30000, skip = false, query = {} } = options;

  const [dataEntry, setDataEntry] = useState(null);
  const [loadingEntry, setLoadingEntry] = useState(null);
  const [errorEntry, setErrorEntry] = useState(null);
  const [dataAgeEntry, setDataAgeEntry] = useState(null); // ms since data was cached

  const mountedRef = useRef(true);
  const abortRef = useRef(null);
  // Plain derived value — NOT useRef().current, whose initializer only runs on
  // the first render and froze cacheKey to the mount-time endpoint. When the
  // ticker changed (same hook instance, no key={ticker} on the chart), the
  // stale key made fetches read/write the wrong ticker's IndexedDB entry.
  const cacheKey = `${endpoint}?${JSON.stringify(query)}`;
  // Keep the last keyed entry available to the fetch error-fallback closure.
  // The callback intentionally does not depend on this state value.
  const dataRef = useRef(null);
  dataRef.current = dataEntry;
  // Data belongs to a specific endpoint/query. Never expose observations from
  // the previous ticker during the render before its next cache/network read.
  const data = dataEntry?.key === cacheKey ? dataEntry.value : null;
  const loading = !endpoint || skip
    ? false
    : loadingEntry?.key === cacheKey ? loadingEntry.value : data == null;
  const error = errorEntry?.key === cacheKey ? errorEntry.value : null;
  const dataAge = dataAgeEntry?.key === cacheKey ? dataAgeEntry.value : null;
  const isStale = dataAge != null && dataAge > STALE_THRESHOLD_MS;
  const showBadge = dataAge != null && dataAge > BADGE_THRESHOLD_MS;

  // ── Fetch from network ────────────────────────────────────────────

  const fetchFromNetwork = useCallback(async (opts = {}) => {
    if (!endpoint) return;
    const requestKey = cacheKey;

    // Cancel previous in-flight request
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch { /* noop */ }
    }
    const controller = new AbortController();
    abortRef.current = controller;

    if (!opts.silent) setLoadingEntry({ key: requestKey, value: true });

    try {
      const qs = new URLSearchParams();
      Object.entries(query).forEach(([k, v]) => {
        if (v != null && v !== "") qs.set(k, String(v));
      });
      const url = `${API}/${endpoint}${qs.toString() ? `?${qs}` : ""}`;

      const timeoutSignal = AbortSignal.timeout(30000);
      const combinedSignal = AbortSignal.any([controller.signal, timeoutSignal]);
      const res = await fetch(url, { signal: combinedSignal });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      const json = await res.json();

      if (!mountedRef.current || abortRef.current !== controller) return;

      // Update state
      setDataEntry({ key: requestKey, value: json });
      setDataAgeEntry({ key: requestKey, value: 0 });
      setErrorEntry({ key: requestKey, value: null });

      // Write to IndexedDB cache (async, non-blocking)
      cachePut(cacheKey, json).catch(() => {});

    } catch (e) {
      if (e.name === "AbortError") return;
      if (!mountedRef.current) return;

      // On network error: fall back to whatever cache we have
      const cached = await cacheGet(cacheKey);
      if (!mountedRef.current || abortRef.current !== controller) return;
      const currentDataBelongsToRequest = dataRef.current?.key === requestKey;
      if (cached && !currentDataBelongsToRequest) {
        // Only use cache if we don't already have data displayed
        setDataEntry({ key: requestKey, value: cached.data });
        const age = Date.now() - cached.ts;
        setDataAgeEntry({ key: requestKey, value: age });
        setErrorEntry({ key: requestKey, value: null });  // suppress error since we have cached data
      } else {
        setErrorEntry({ key: requestKey, value: e.message || "Fetch failed" });
      }
    } finally {
      if (mountedRef.current && abortRef.current === controller) {
        setLoadingEntry({ key: requestKey, value: false });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, cacheKey, JSON.stringify(query)]);

  // ── Initial load: cache-first ─────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;

    let cancelled = false;

    (async () => {
      if (skip || !endpoint) return;

      // 1. Serve from cache immediately (if available)
      const cached = await cacheGet(cacheKey);
      if (cancelled) return;

      if (cached) {
        const age = Date.now() - cached.ts;
        setDataEntry({ key: cacheKey, value: cached.data });
        setDataAgeEntry({ key: cacheKey, value: age });
        setErrorEntry({ key: cacheKey, value: null });

        // 2. If stale (>5 min), trigger background fetch
        if (age > STALE_THRESHOLD_MS) {
          fetchFromNetwork({ silent: true });
        }
      } else {
        // 3. No cache — show loading and fetch
        setLoadingEntry({ key: cacheKey, value: true });
        await fetchFromNetwork();
      }
    })();

    return () => {
      cancelled = true;
      mountedRef.current = false;
      if (abortRef.current) {
        try { abortRef.current.abort(); } catch { /* noop */ }
        abortRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, skip]);

  // ── Polling ───────────────────────────────────────────────────────

  useEffect(() => {
    if (skip || refreshMs <= 0) return;
    const id = setInterval(() => {
      fetchFromNetwork({ silent: true });
    }, refreshMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchFromNetwork, refreshMs, skip]);

  const refresh = useCallback(() => fetchFromNetwork(), [fetchFromNetwork]);

  return { data, loading, error, isStale, showBadge, dataAge, refresh };
}

export default useMarketData;
