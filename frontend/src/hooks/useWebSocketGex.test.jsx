import { act, renderHook } from "@testing-library/react";
import { useWebSocketGex } from "./useWebSocketGex";

class FakeSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances = [];
  constructor(url) {
    this.url = url;
    this.readyState = FakeSocket.CONNECTING;
    this.close = jest.fn(() => { this.readyState = FakeSocket.CLOSED; });
    FakeSocket.instances.push(this);
  }
  open() { this.readyState = FakeSocket.OPEN; this.onopen?.(); }
  message(payload) { this.onmessage?.({ data: JSON.stringify(payload) }); }
  disconnect() { this.readyState = FakeSocket.CLOSED; this.onclose?.(); }
}

const reading = (ticker = "SPY", more = {}) => ({
  ticker, spot: 764.25, total_gex: 0, king: null, floors: [], ceilings: [], regime: null,
  asof: "2026-09-11T20:37:27+00:00", ...more,
});

describe("useWebSocketGex behavior", () => {
  let originalSocket;
  beforeEach(() => {
    jest.useFakeTimers();
    originalSocket = global.WebSocket;
    global.WebSocket = FakeSocket;
    FakeSocket.instances = [];
  });
  afterEach(() => {
    global.WebSocket = originalSocket;
    jest.useRealTimers();
  });

  test("accepts the real server shape, including a zero reading and absent king", () => {
    const { result } = renderHook(() => useWebSocketGex("SPY"));
    const socket = FakeSocket.instances[0];
    act(() => { socket.open(); socket.message(reading()); });
    expect(result.current).toEqual({ data: reading(), connected: true, reconnectAttempt: 0 });
  });

  test("recognizes the server's SPX to ^SPX ticker alias", () => {
    const { result } = renderHook(() => useWebSocketGex("SPX"));
    act(() => FakeSocket.instances[0].message(reading("^SPX", { total_gex: -1000 })));
    expect(result.current.data?.ticker).toBe("^SPX");
  });

  test("ticker changes clear the previous ticker reading and connection state", () => {
    const { result, rerender } = renderHook(({ ticker }) => useWebSocketGex(ticker), { initialProps: { ticker: "SPY" } });
    const old = FakeSocket.instances[0];
    act(() => { old.open(); old.message(reading()); });
    rerender({ ticker: "QQQ" });
    expect(old.close).toHaveBeenCalledTimes(1);
    expect(result.current).toEqual({ data: null, connected: false, reconnectAttempt: 0 });
    act(() => { FakeSocket.instances[1].open(); FakeSocket.instances[1].message(reading("QQQ")); });
    expect(result.current.data.ticker).toBe("QQQ");
  });

  test("queued callbacks from a previous ticker cannot write into the new ticker", () => {
    const { result, rerender } = renderHook(({ ticker }) => useWebSocketGex(ticker), { initialProps: { ticker: "SPY" } });
    const old = FakeSocket.instances[0];
    const callbacks = { open: old.onopen, close: old.onclose, message: old.onmessage, error: old.onerror };
    rerender({ ticker: "QQQ" });
    const current = FakeSocket.instances[1];
    act(() => { current.open(); current.message(reading("QQQ")); });
    act(() => {
      callbacks.close();
      callbacks.message({ data: JSON.stringify(reading("SPY")) });
      callbacks.error();
    });
    expect(result.current).toEqual({ data: reading("QQQ"), connected: true, reconnectAttempt: 0 });
    expect(old.close).toHaveBeenCalledTimes(1);
    act(() => current.disconnect());
    expect(result.current.connected).toBe(false);
    act(() => callbacks.open());
    expect(result.current.connected).toBe(false);
  });

  test("disabling a ticker clears values and cancels pending reconnects", () => {
    const { result, rerender } = renderHook(({ ticker }) => useWebSocketGex(ticker), { initialProps: { ticker: "SPY" } });
    const socket = FakeSocket.instances[0];
    act(() => { socket.open(); socket.message(reading()); socket.disconnect(); });
    expect(result.current.reconnectAttempt).toBe(1);
    rerender({ ticker: null });
    act(() => jest.advanceTimersByTime(60000));
    expect(FakeSocket.instances).toHaveLength(1);
    expect(result.current).toEqual({ data: null, connected: false, reconnectAttempt: 0 });
  });

  test.each([
    ["error", { ticker: "SPY", error: "No data" }],
    ["status", { ticker: "SPY", status: "connected" }],
    ["heartbeat", { ticker: "SPY", heartbeat: true, ts: "2026-09-11T20:37:27Z" }],
    ["wrong ticker", reading("QQQ")],
    ["null spot", reading("SPY", { spot: null })],
    ["numeric string", reading("SPY", { spot: "764.25" })],
    ["zero spot", reading("SPY", { spot: 0 })],
    ["null exposure", reading("SPY", { total_gex: null })],
    ["bad date", reading("SPY", { asof: "not a time" })],
    ["missing date", reading("SPY", { asof: null })],
    ["timezone-free date", reading("SPY", { asof: "2026-09-11T20:37:27" })],
    ["empty object", {}],
    ["null", null],
    ["array", []],
  ])("ignores %s packets and retains the last valid reading", (_, packet) => {
    const { result } = renderHook(() => useWebSocketGex("SPY"));
    const socket = FakeSocket.instances[0];
    act(() => { socket.open(); socket.message(reading()); socket.message(packet); });
    expect(result.current.data).toEqual(reading());
  });

  test("malformed JSON does not erase valid values", () => {
    const { result } = renderHook(() => useWebSocketGex("SPY"));
    const socket = FakeSocket.instances[0];
    act(() => { socket.message(reading()); socket.onmessage({ data: "{" }); });
    expect(result.current.data).toEqual(reading());
  });

  test("reconnects once, resets backoff on open and rejects replaced-socket callbacks", () => {
    const { result } = renderHook(() => useWebSocketGex("SPY"));
    const old = FakeSocket.instances[0];
    const staleMessage = old.onmessage;
    act(() => old.disconnect());
    expect(result.current.reconnectAttempt).toBe(1);
    act(() => jest.advanceTimersByTime(1000));
    expect(FakeSocket.instances).toHaveLength(2);
    const current = FakeSocket.instances[1];
    act(() => { current.open(); current.message(reading("SPY", { spot: 765 })); });
    act(() => staleMessage({ data: JSON.stringify(reading()) }));
    expect(result.current.data.spot).toBe(765);
    expect(result.current.reconnectAttempt).toBe(0);
  });

  test("unmount blocks saved callbacks and pending reconnect work", () => {
    const { unmount } = renderHook(() => useWebSocketGex("SPY"));
    const socket = FakeSocket.instances[0];
    const close = socket.onclose;
    act(() => socket.disconnect());
    unmount();
    act(() => { close(); jest.advanceTimersByTime(60000); });
    expect(FakeSocket.instances).toHaveLength(1);
  });

  test("accepts the server's fractional-second timestamp", () => {
    const { result } = renderHook(() => useWebSocketGex("SPY"));
    const payload = reading("SPY", { asof: "2026-09-11T20:37:27.123456+00:00" });
    act(() => FakeSocket.instances[0].message(payload));
    expect(result.current.data).toEqual(payload);
  });

  test("reconnect delay grows to its cap without duplicate timers", () => {
    const { result } = renderHook(() => useWebSocketGex("SPY"));
    for (const delay of [1000, 2000, 4000, 8000, 16000, 30000, 30000]) {
      const socket = FakeSocket.instances[FakeSocket.instances.length - 1];
      const count = FakeSocket.instances.length;
      act(() => { socket.disconnect(); socket.disconnect(); });
      expect(result.current.reconnectAttempt).toBe(count);
      act(() => jest.advanceTimersByTime(delay - 1));
      expect(FakeSocket.instances).toHaveLength(count);
      act(() => jest.advanceTimersByTime(1));
      expect(FakeSocket.instances).toHaveLength(count + 1);
    }
  });
});
