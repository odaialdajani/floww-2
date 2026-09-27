import { useEffect, useState, useRef, useCallback } from "react";
import { BACKEND_URL } from "../config/api";
import { withWsToken } from "../utils/appKey";

const WS_URL = BACKEND_URL.replace("http", "ws");
const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;
const BACKOFF_MULTIPLIER = 2;

export function useWebSocketGex(ticker) {
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const mountedRef = useRef(true);
  const attemptRef = useRef(0);

  const connect = useCallback(() => {
    if (!ticker) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(withWsToken(`${WS_URL}/ws/gex/${ticker}`));
    wsRef.current = ws;

    ws.onopen = () => {
      if (mountedRef.current) {
        setConnected(true);
        attemptRef.current = 0;
        setReconnectAttempt(0);
      }
    };

    ws.onclose = () => {
      if (mountedRef.current) setConnected(false);
      if (wsRef.current === ws && mountedRef.current) {
        attemptRef.current += 1;
        setReconnectAttempt(attemptRef.current);
        const delay = Math.min(
          INITIAL_RECONNECT_DELAY * Math.pow(BACKOFF_MULTIPLIER, attemptRef.current - 1),
          MAX_RECONNECT_DELAY
        );
        reconnectRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      try { ws.close(); } catch (e) { /* noop */ }
    };

    ws.onmessage = (e) => {
      if (!mountedRef.current) return;
      try {
        setData(JSON.parse(e.data));
      } catch (err) {
        /* noop */
      }
    };
  }, [ticker]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { data, connected, reconnectAttempt };
}