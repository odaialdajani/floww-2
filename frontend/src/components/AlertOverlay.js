import React, { useEffect, useRef, useState, useCallback, memo } from 'react';
import { BACKEND_URL } from "../config/api";
import { withWsToken } from "../utils/appKey";

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
 * Connects to WebSocket for real-time signal delivery.
 *
 * Props:
 *   onSignalClick: (alert) => void - called when user clicks a toast
 *   maxVisible: max number of toasts (default 3)
 */
export default function AlertOverlay({ onSignalClick, maxVisible = 3 }) {
  const [alerts, setAlerts] = useState([]);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const mountedRef = useRef(true);
  const alertIdRef = useRef(0);

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

  // Lifted to component scope: both useEffects below reference connect.
  const connect = useCallback(() => {
    // Don't open a second socket if one is already connecting/open — the
    // visibilitychange handler and the backoff timer can both re-enter here.
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;
    try {
      // BACKEND_URL imported from config/api.js
      const WS_URL = BACKEND_URL.replace('http', 'ws');
      const ws = new WebSocket(withWsToken(`${WS_URL}/ws/signals`));
      wsRef.current = ws;   // track immediately (CONNECTING) so re-entrant connect() bails

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return; }
        reconnectRef.current = null;   // successful open — reset backoff attempts
      };

      ws.onmessage = (e) => {
        if (!mountedRef.current) return;
        try {
          const data = JSON.parse(e.data);
          if (data.type === 'signal' || data.signal) {
            addAlert(data);
          }
        } catch { /* skip malformed */ }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        wsRef.current = null;
        // Exponential backoff reconnect (mobile-friendly)
        const delay = Math.min(1000 * Math.pow(2, (reconnectRef.current?.attempts || 0)), 30000);
        reconnectRef.current = {
          attempts: (reconnectRef.current?.attempts || 0) + 1,
          timer: setTimeout(connect, delay),
        };
      };

      ws.onerror = () => {
        try { ws.close(); } catch { /* noop */ }
      };
    } catch { /* noop */ }
  }, [addAlert]);

  // WebSocket connection for real-time signals
  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectRef.current?.timer);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  // Handle visibility change - reconnect when tab becomes visible
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible' && mountedRef.current && !wsRef.current) {
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
