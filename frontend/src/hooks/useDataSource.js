/**
 * useDataSource.js
 *
 * Polls /api/admin/data-source to surface the active data source
 * (Alpha Vantage, Databento, Schwab) and its delay to the UI.
 *
 * Returns: { source, delaySeconds, badgeStatus, loading, error, refresh }
 *
 * badgeStatus ∈ {"live", "delayed", "cached", "offline"}
 *   - "live":     real-time source (Schwab, Databento)
 *   - "delayed":   15-min delayed source (Alpha Vantage free tier)
 *   - "cached":    stale data being served from DuckDB/IndexedDB
 *   - "offline":   no data source reachable
 */

import { useEffect, useState, useRef, useCallback } from "react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

const POLL_INTERVAL_MS = 30000; // Poll every 30s

/**
 * @param {Object} [options]
 * @param {number} [options.pollIntervalMs=30000]  Polling interval
 * @param {boolean} [options.skip=false]           Skip fetching
 */
export function useDataSource(options = {}) {
  const { pollIntervalMs = POLL_INTERVAL_MS, skip = false } = options;

  const [sourceInfo, setSourceInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const mountedRef = useRef(true);
  const abortRef = useRef(null);

  // Derive badge status from source info
  const badgeStatus = _computeBadgeStatus(sourceInfo);

  const fetchSource = useCallback(async () => {
    if (skip) return;

    // Cancel previous in-flight request
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch { /* noop */ }
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);

    try {
      const res = await fetch(`${API}/admin/data-source`, {
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const json = await res.json();

      if (!mountedRef.current || abortRef.current !== controller) return;

      setSourceInfo(json);
      setError(null);
    } catch (e) {
      if (e.name === "AbortError") return;
      if (!mountedRef.current) return;
      setError(e.message || "Failed to fetch data source info");
    } finally {
      if (mountedRef.current && abortRef.current === controller) {
        setLoading(false);
      }
    }
  }, [skip]);

  // Initial fetch
  useEffect(() => {
    mountedRef.current = true;

    if (!skip) {
      fetchSource();
    }

    return () => {
      mountedRef.current = false;
      if (abortRef.current) {
        try { abortRef.current.abort(); } catch { /* noop */ }
        abortRef.current = null;
      }
    };
  }, [fetchSource, skip]);

  // Polling
  useEffect(() => {
    if (skip || pollIntervalMs <= 0) return;
    const id = setInterval(fetchSource, pollIntervalMs);
    return () => clearInterval(id);
  }, [fetchSource, pollIntervalMs, skip]);

  const refresh = useCallback(() => fetchSource(), [fetchSource]);

  return {
    source: sourceInfo?.active || null,
    delaySeconds: sourceInfo?.delay_seconds ?? null,
    configured: sourceInfo?.configured || null,
    keyPresent: sourceInfo?.key_present ?? false,
    badgeStatus,
    sourceInfo,
    loading,
    error,
    refresh,
  };
}

/**
 * Compute badge display status from source info.
 *
 * @param {Object|null} info
 * @returns {"live"|"delayed"|"cached"|"offline"}
 */
function _computeBadgeStatus(info) {
  if (!info || !info.active) {
    return "offline";
  }

  const { active, delay_seconds } = info;

  if (delay_seconds === 0) {
    return "live";
  }

  if (delay_seconds > 0 && delay_seconds <= 900) {
    return "delayed";
  }

  if (delay_seconds > 900) {
    // Very stale — likely cached/fallback data
    return "cached";
  }

  return "offline";
}

export default useDataSource;
