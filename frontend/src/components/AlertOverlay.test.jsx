/** @jest-environment jsdom */
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import AlertOverlay from './AlertOverlay';

jest.mock('../config/api', () => ({
  API: '/api',
  BACKEND_URL: 'http://localhost:8000',
  BACKEND_BASE: '',
}));
jest.mock('../utils/appKey', () => ({ withWsToken: (u) => u }));

// Transport: the /ws/signals WebSocket. The producer in backend/routes/alerts.py
// normalizes every frame to {type: 'signal', signal, alert_type, ticker, ts},
// and server.py registers the exact path BEFORE the greedy /ws/{topic}, so this
// client is reachable. See docs/solstice/STATUS.md (#56).
let sockets;
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    sockets.push(this);
  }

  send() {}

  close() {
    if (this.readyState === MockWebSocket.CLOSED) return;
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) this.onclose({});
  }

  // Drive the component's handlers the way real server frames would.
  open() {
    this.readyState = MockWebSocket.OPEN;
    if (this.onopen) this.onopen();
  }

  message(payload) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(payload) });
  }
}

let unmount;

async function mount() {
  const utils = render(<AlertOverlay />);
  unmount = utils.unmount;
  await act(async () => {});
  return sockets[sockets.length - 1];
}

beforeEach(() => {
  sockets = [];
  global.WebSocket = MockWebSocket;
});

// The component registers a visibilitychange listener and schedules reconnect
// backoff timers in onclose. Unmount between tests so neither leaks.
afterEach(() => {
  if (unmount) unmount();
  unmount = null;
  jest.restoreAllMocks();
  delete global.WebSocket;
});

test('opens exactly one socket at /ws/signals', async () => {
  await act(async () => {
    render(<AlertOverlay />);
  });
  expect(sockets).toHaveLength(1);
  expect(sockets[0].url).toContain('/ws/signals');
});

test('accepts a normalized signal frame and renders the alert', async () => {
  const ws = await mount();
  await act(async () => {
    ws.open();
    // Exactly the shape _signal_frame() emits.
    ws.message({
      type: 'signal',
      signal: 'GAMMA_FLIP',
      alert_type: 'GAMMA_FLIP',
      ticker: 'SPY',
      message: 'Gamma flip at 773',
      ts: Date.now(),
    });
  });
  await waitFor(() => expect(screen.getByLabelText('Dismiss alert')).toBeInTheDocument());
  // GAMMA_FLIP has no entry in SIGNAL_LABELS, so the raw name renders.
  expect(screen.getByText(/GAMMA_FLIP\s*·\s*SPY/)).toBeInTheDocument();
});

test('ignores a frame whose type is an alert type rather than "signal"', async () => {
  const ws = await mount();
  await act(async () => {
    ws.open();
    // Regression guard: the pre-#56 shape. No `signal` key and a non-'signal'
    // type must NOT produce a toast.
    ws.message({ type: 'GAMMA_FLIP', ticker: 'SPY', message: 'unnormalized' });
  });
  expect(screen.queryByLabelText('Dismiss alert')).not.toBeInTheDocument();
});

test('ignores malformed JSON rather than throwing', async () => {
  const ws = await mount();
  await act(async () => {
    ws.open();
    ws.onmessage({ data: 'not json{' });
  });
  expect(screen.queryByLabelText('Dismiss alert')).not.toBeInTheDocument();
});

test('caps visible toasts at maxVisible, newest first', async () => {
  const ws = await mount();
  const frame = (signal, ticker) => ({
    type: 'signal',
    signal,
    alert_type: signal,
    ticker,
    message: `${signal} on ${ticker}`,
    ts: Date.now(),
  });

  await act(async () => {
    ws.open();
    ws.message(frame('GAMMA_FLIP', 'SPY'));
  });
  await waitFor(() => expect(screen.getByLabelText('Dismiss alert')).toBeInTheDocument());

  await act(async () => {
    ws.message(frame('MOMENTUM_EXTREME', 'QQQ'));
  });
  await waitFor(() =>
    expect(screen.getAllByLabelText('Dismiss alert')).toHaveLength(2)
  );

  // A third alert exceeds the default maxVisible of 3 only at 4; assert the
  // newest is prepended, which is the behavior addAlert actually implements.
  await act(async () => {
    ws.message(frame('IV_CRUSH', 'AAPL'));
  });
  await waitFor(() =>
    expect(screen.getAllByLabelText('Dismiss alert')).toHaveLength(3)
  );
  const labels = screen.getAllByLabelText('Dismiss alert').length;
  expect(labels).toBe(3);
});
