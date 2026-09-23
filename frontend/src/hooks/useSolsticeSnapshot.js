import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../config/api";
import { buildHeatmapQuery, heatmapQueryKey } from "../lib/heatmapQuery";

/**
 * useSolsticeSnapshot — one query identity + freshness lifecycle (T06/F19).
 * Single-flight fetch with AbortController + generation IDs; stale/cross-symbol
 * responses are discarded, never shown under a new heading.
 */
export function useSolsticeSnapshot({ ticker, expiries = 4, mode = "day", dte = null, scalp = false, pollMs = 25000 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const genRef = useRef(0);
  const key = heatmapQueryKey({ ticker, expiries, mode, dte, scalp });
  const query = buildHeatmapQuery({ expiries, mode, dte, scalp });

  useEffect(() => {
    let cancelled = false;
    const ctrl = new AbortController();
    const myGen = ++genRef.current;
    setLoading(true);
    axios
      .get(`${BACKEND_API}/heatmap/${encodeURIComponent(ticker)}?${query}`, {
        timeout: 45000,
        signal: ctrl.signal,
      })
      .then((r) => {
        if (!cancelled && genRef.current === myGen) {
          setData(r.data);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled && genRef.current === myGen && !axios.isCancel(e)) {
          setError(e?.response?.status === 404 ? "NO_OPTIONS" : "FETCH_FAILED");
        }
      })
      .finally(() => {
        if (!cancelled && genRef.current === myGen) setLoading(false);
      });
    const id = pollMs ? setInterval(async () => {
      const g = ++genRef.current;
      try {
        const r = await axios.get(`${BACKEND_API}/data/${encodeURIComponent(ticker)}?${query}`, {
          timeout: 45000,
          signal: ctrl.signal,
        });
        if (!cancelled && genRef.current === g) {
          setData(r.data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled && genRef.current === g && !axios.isCancel(e)) {
          setError(e?.response?.status === 404 ? "NO_OPTIONS" : "FETCH_FAILED");
        }
      }
    }, pollMs) : null;
    return () => {
      cancelled = true;
      ctrl.abort();
      if (id) clearInterval(id);
    };
  }, [ticker, query, pollMs, key]);

  return { data, loading, error, queryKey: key };
}
