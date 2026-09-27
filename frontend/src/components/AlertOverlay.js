import React, { useEffect, useRef, useState, useCallback, memo } from 'react';
import { API } from "../config/api";

const SIGNAL_STYLES = {
  BUY: 'toast-buy',
  SELL: 'toast-sell',
  HOLD: '',
};

const SIGNAL_LABELS = {
  BUY: '🟢 BUY',
  SELL: '🔴 SELL',
  HOLD: '🟡 HOLD',
};

function Toast({ alert, onDismiss, onClick }) {
  const [exiting, setExiting] = useState(false);
  const timerRef = useRef(null);
  // Keep the latest onDismiss without making it a timer dependency — the parent
  // passes a fresh arrow each render, which would otherwise reset the 8s timer
  // on every re-render (so toasts never auto-dismissed under signal flow).
  const onDismissRef = useRef(onDismiss);
  useEffect(() => { onDismissRef.current = onDismiss; });

  useEffect(() => {
    timerRef.current = setTimeout(() => {
      setExiting(true);
      setTimeout(() => onDismissRef.current?.(), 300);
    }, 8000);
    return () => clearTimeout(timerRef.current);
  }, []);   // start once on mount; never reset

  const handleClick = () => {
    clearTimeout(timerRef.current);
    onClick?.(alert);
  };

  const handleDismiss = (e) => {
    e.stopPropagation();
    clearTimeout(timerRef.current);
    setExiting(true);
    setTimeout(onDismiss, 300);
  };

  return (
    <div
      className={`toast ${SIGNAL_STYLES[alert.signal] || ''} ${exiting ? 'toast-exit' : ''}`}
      onClick={handleClick}
      role="alert"
      aria-live="polite"
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.08em',
          }}>
            {SIGNAL_LABELS[alert.signal] || alert.signal} · {alert.ticker}
          </span>
          <span style={{ fontSize: 9, color: '#64748b', marginLeft: 8 }}>
            {alert.time || new Date().toLocaleTimeString()}
          </span>
        </div>
        {alert.message && (
          <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.4 }}>
            {alert.message}
          </div>
        )}
        {alert.details && (
          <div style={{
            display: 'flex',
            gap: 12,
            marginTop: 4,
            fontSize: 10,
            color: '#64748b',
            flexWrap: 'wrap',
          }}>
            {Object.entries(alert.details).map(([k, v]) => (
              <span key={k}>{k}: <strong style={{ color: '#94a3b8' }}>{v}</strong></span>
            ))}
          </div>
        )}
      </div>
      <button
        onClick={handleDismiss}
        style={{
          background: 'none',
          border: 'none',
          color: '#64748b',
          cursor: 'pointer',
          fontSize: 14,
          padding: '0 0 0 4px',
          flexShrink: 0,
        }}
        aria-label="Dismiss alert"
      >
        ✕
      </button>
    </div>
  );
}

const ToastMemo = memo(Toast);

/**
 * AlertOverlay - Non-intrusive toast notification overlay for trading signals.
 * Consumes the conviction-alert SSE stream (same source as the Blademap
 * feed), toasting each unseen high-conviction alert once.
 *
 * Props:
 *   onSignalClick: (alert) => void - called when user clicks a toast
 *   maxVisible: max number of toasts (default 3)
 */
export default function AlertOverlay({ onSignalClick, maxVisible = 3 }) {
  const [alerts, setAlerts] = useState([]);
  const esRef = useRef(null);
  const reconnectRef = useRef(null);
  const mountedRef = useRef(true);
  const alertIdRef = useRef(0);
  const seenKeysRef = useRef(new Set());

  const dismissAlert = useCallback((id) => {
    setAlerts(prev => prev.filter(a => a._id !== id));
  }, []);

  const addAlert = useCallback((signal) => {
    const id = ++alertIdRef.current;
    const alert = {
      _id: id,
      signal: signal.signal || signal.type || 'HOLD',
      ticker: signal.ticker || 'SPY',
      message: signal.message || '',
      details: signal.details || signal.data || {},
      time: new Date().toLocaleTimeString(),
      ts: Date.now(),
    };
    setAlerts(prev => {
      const next = [alert, ...prev];
      return next.slice(0, maxVisible);
    });
  }, [maxVisible]);

  // Lifted to component scope: visibility handler and backoff timer re-enter here.
  // Transport is the conviction-alert SSE stream (same source as the Blademap
  // feed: GET /api/flowseeker/alerts/stream). The legacy /ws/signals socket
  // had no server producer; SSE auto-reconnects and the stream re-issues.
  const connect = useCallback(() => {
    if (esRef.current) return;
    try {
      const es = new EventSource(
        `${API}/flowseeker/alerts/stream?min_conviction=75&max_seconds=300`
      );
      esRef.current = es;   // track immediately so re-entrant connect() bails

      const scheduleReconnect = () => {
        if (!mountedRef.current) return;
        try { es.close(); } catch { /* noop */ }
        if (esRef.current === es) esRef.current = null;
        const attempts = (reconnectRef.current?.attempts || 0) + 1;
        const delay = Math.min(1000 * Math.pow(2, attempts - 1), 30000);
        reconnectRef.current = {
          attempts,
          timer: setTimeout(connect, delay),
        };
      };

      es.addEventListener("alerts", (e) => {
        if (!mountedRef.current) return;
        try {
          const body = JSON.parse(e.data);
          for (const row of body.alerts || []) {
            const key = row.key || `${row.under}|${row.asof_ts}|${row.tier}`;
            if (seenKeysRef.current.has(key)) continue;
            seenKeysRef.current.add(key);
            if (seenKeysRef.current.size > 500) {
              const first = seenKeysRef.current.values().next().value;
              seenKeysRef.current.delete(first);
            }
            addAlert({
              signal: row.bias || row.side || row.tier || "HOLD",
              ticker: row.under || row.ticker || "SPY",
              message: row.headline || row.summary ||
                `${row.tier || ""} ${row.under || ""} conviction ${row.conviction ?? ""}`.trim(),
              details: { tier: row.tier, conviction: row.conviction, ...(row.details || {}) },
            });
          }
          reconnectRef.current = null;   // live data — reset backoff
        } catch { /* skip malformed */ }
      });
      es.addEventListener("error", scheduleReconnect);
      es.addEventListener("end", scheduleReconnect);
      es.onerror = scheduleReconnect;
    } catch { /* noop */ }
  }, [addAlert]);

  // Alert-stream connection for real-time toasts
  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectRef.current?.timer);
      if (esRef.current) {
        try { esRef.current.close(); } catch { /* noop */ }
        esRef.current = null;
      }
    };
  }, [connect]);

  // Handle visibility change - reconnect when tab becomes visible
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible' && mountedRef.current && !esRef.current) {
        try { connect(); } catch { /* noop */ }
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [connect]);

  if (alerts.length === 0) return null;

  return (
    <div className="alert-overlay-container" aria-label="Trading alerts">
      {alerts.map(alert => (
        <ToastMemo
          key={alert._id}
          alert={alert}
          onDismiss={() => dismissAlert(alert._id)}
          onClick={onSignalClick}
        />
      ))}
    </div>
  );
}
