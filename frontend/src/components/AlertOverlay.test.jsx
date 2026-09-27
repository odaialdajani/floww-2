/** @jest-environment jsdom */
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import AlertOverlay from './AlertOverlay';

jest.mock('../config/api', () => ({ API: '/api', BACKEND_URL: '', BACKEND_BASE: '' }));

let listeners;
class MockEventSource {
  constructor(url) {
    this.url = url;
    this.closed = false;
    listeners = {};
    MockEventSource.instances.push(this);
  }
  addEventListener(name, fn) {
    (listeners[name] = listeners[name] || []).push(fn);
  }
  removeEventListener() {}
  close() {
    this.closed = true;
  }
}
MockEventSource.instances = [];

function emit(es, name, data) {
  for (const fn of listeners[name] || []) fn({ data: JSON.stringify(data) });
}

beforeEach(() => {
  MockEventSource.instances = [];
  global.EventSource = MockEventSource;
});

afterEach(() => {
  jest.restoreAllMocks();
  delete global.EventSource;
});

test('connects to the conviction-alert SSE stream, not a socket', async () => {
  await act(async () => {
    render(<AlertOverlay />);
  });
  expect(MockEventSource.instances).toHaveLength(1);
  expect(MockEventSource.instances[0].url).toBe(
    '/api/flowseeker/alerts/stream?min_conviction=75&max_seconds=300'
  );
});

test('toasts each unseen alert once; repeats are swallowed', async () => {
  await act(async () => {
    render(<AlertOverlay />);
  });
  const es = MockEventSource.instances[0];
  const row = { key: 'k1', under: 'SPY', tier: 'GOLD', conviction: 92, bias: 'BULLISH' };
  await act(async () => {
    emit(es, 'alerts', { count: 1, alerts: [row] });
  });
  await waitFor(() => expect(screen.getByLabelText('Dismiss alert')).toBeInTheDocument());
  expect(screen.getByText('GOLD SPY conviction 92')).toBeInTheDocument();
  await act(async () => {
    emit(es, 'alerts', { count: 1, alerts: [row] });
  });
  expect(screen.getAllByLabelText('Dismiss alert')).toHaveLength(1);
  await act(async () => {
    emit(es, 'alerts', {
      count: 2,
      alerts: [row, { key: 'k2', under: 'QQQ', tier: 'SILVER', conviction: 81 }],
    });
  });
  await waitFor(() =>
    expect(screen.getAllByLabelText('Dismiss alert')).toHaveLength(2)
  );
});
