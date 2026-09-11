import { useEffect, useState } from "react";
import { BACKEND_URL } from "../config/api";

const WS_URL = BACKEND_URL.replace(/^http/, "ws");
const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;
const BACKOFF_MULTIPLIER = 2;
const EMPTY = { data: null, connected: false, reconnectAttempt: 0 };

function streamTicker(value) {
  const symbol = typeof value === "string" ? value.trim().toUpperCase() : "";
  return symbol === "SPX" ? "^SPX" : symbol;
}

function isReading(payload, ticker) {
  // The server also sends {error, ticker}. Those packets describe the
  // connection, not a market reading, and must not replace saved values.
  return payload && typeof payload === "object" && !Array.isArray(payload)
    && streamTicker(payload.ticker) === ticker
    && typeof payload.spot === "number" && Number.isFinite(payload.spot) && payload.spot > 0
    && typeof payload.total_gex === "number" && Number.isFinite(payload.total_gex)
    && typeof payload.asof === "string"
    && /^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(payload.asof)
    && Number.isFinite(Date.parse(payload.asof));
}

export function useWebSocketGex(ticker) {
  const symbol = streamTicker(ticker);
  const [state, setState] = useState({ ticker: null, ...EMPTY });

  useEffect(() => {
    let active = true;
    let socket = null;
    let reconnectTimer = null;
    let attempts = 0;
    setState({ ticker: symbol, ...EMPTY });

    const current = (ws) => active && socket === ws;
    const update = (patch) => setState((previous) => (
      active && previous.ticker === symbol ? { ...previous, ...patch } : previous
    ));

    function reconnect() {
      if (!active || reconnectTimer !== null) return;
      attempts += 1;
      update({ connected: false, reconnectAttempt: attempts });
      const delay = Math.min(
        INITIAL_RECONNECT_DELAY * Math.pow(BACKOFF_MULTIPLIER, attempts - 1),
        MAX_RECONNECT_DELAY
      );
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (active) connect();
      }, delay);
    }

    function connect() {
      if (!active || !symbol) return;
      if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
      let ws;
      try {
        ws = new WebSocket(`${WS_URL}/ws/gex/${encodeURIComponent(symbol)}`);
      } catch (error) {
        reconnect();
        return;
      }
      socket = ws;
      ws.onopen = () => {
        if (!current(ws)) return;
        attempts = 0;
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
        update({ connected: true, reconnectAttempt: 0 });
      };
      ws.onclose = () => {
        if (!current(ws)) return;
        reconnect();
      };
      ws.onerror = () => {
        if (!current(ws)) return;
        update({ connected: false });
        try { ws.close(); } catch (error) { reconnect(); }
      };
      ws.onmessage = (event) => {
        if (!current(ws)) return;
        try {
          const payload = JSON.parse(event.data);
          if (isReading(payload, symbol)) update({ data: payload });
        } catch (error) {
          // Keep the last valid reading when a packet cannot be decoded.
        }
      };
    }

    connect();
    return () => {
      active = false;
      clearTimeout(reconnectTimer);
      if (socket) {
        socket.onopen = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        try { socket.close(); } catch (error) { /* already closed */ }
        socket = null;
      }
    };
  }, [symbol]);

  // Do not expose the previous ticker even during the render before cleanup.
  if (state.ticker !== symbol) return EMPTY;
  return { data: state.data, connected: state.connected, reconnectAttempt: state.reconnectAttempt };
}
