import { useCallback, useLayoutEffect, useRef } from "react";

/** Stable research handoff callbacks. No provider, contract guess, or order call. */
export default function useSolsticeReviewCallbacks({ ticker, data, spot, setMode, refresh, clearError, onReview }) {
  const current = useRef(null);
  useLayoutEffect(() => { current.current = { ticker, data, spot, setMode, refresh, clearError, onReview }; });
  const timeframe = useCallback(tf => current.current.setMode(tf === "1m" ? "scalp" : tf === "1h" ? "swing" : "day"), []);
  const reload = useCallback(() => { current.current.clearError(null); current.current.refresh(); }, []);
  const cell = useCallback((strike, expiry, value, selection = null) => {
    const c = current.current;
    const row = c.data?.strikes?.find(r => r.strike === strike);
    c.onReview({ ticker: c.ticker, strike, expiry, spot: c.spot, snapshotId: c.data?.snapshotId || null,
      selectedMetric: selection?.metric || "raw", selectedView: selection?.view || "gex", selectedValue: value,
      gex: c.data?.grid?.grid?.[expiry]?.[String(strike)] ?? null,
      iv: row?.iv ?? null, delta: null, oi: row?.total_oi ?? row?.oi ?? null,
      call_gex: row?.call_gex ?? null, put_gex: row?.put_gex ?? null, vex: row?.vex ?? null, charm: row?.charm ?? null,
      oi_symbol: null, call_bid: null, call_ask: null, call_last: null, put_bid: null, put_ask: null, put_last: null,
    });
  }, []);
  const strike = useCallback(s => { const c = current.current; c.onReview({ ticker: c.ticker, strike: s, spot: c.spot, expiry: null, oi_symbol: null }); }, []);
  return { timeframe, reload, cell, strike };
}
