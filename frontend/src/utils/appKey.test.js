/**
 * @jest-environment jsdom
 *
 * appKey: local backend key prompt-once + header builder.
 */
import { getAppKey, clearAppKey, mutatingHeaders, storedAppKey, storedAppKeyHeaders, withWsToken } from "./appKey";

const LS_KEY = "floww_app_key";

beforeEach(() => {
  window.localStorage.clear();
  jest.restoreAllMocks();
});

test("prompts once, then reuses the stored key", () => {
  const prompt = jest.spyOn(window, "prompt").mockReturnValueOnce("  k1  ");
  expect(getAppKey()).toBe("k1");
  expect(window.localStorage.getItem(LS_KEY)).toBe("k1");
  expect(getAppKey()).toBe("k1");
  expect(prompt).toHaveBeenCalledTimes(1);
});

test("declined prompt yields empty key (callers must abort)", () => {
  jest.spyOn(window, "prompt").mockReturnValueOnce(null);
  expect(getAppKey()).toBe("");
  expect(window.localStorage.getItem(LS_KEY)).toBeNull();
});

test("storedAppKey returns the raw stored key without prompting", () => {
  const prompt = jest.spyOn(window, "prompt").mockReturnValue("nope");
  expect(storedAppKey()).toBe("");
  window.localStorage.setItem(LS_KEY, "  k9  ");
  expect(storedAppKey()).toBe("k9");
  expect(prompt).not.toHaveBeenCalled();
});

test("storedAppKeyHeaders never prompts (polling-safe)", () => {
  const prompt = jest.spyOn(window, "prompt").mockReturnValue("nope");
  expect(storedAppKeyHeaders()).toBeNull();
  expect(prompt).not.toHaveBeenCalled();
  window.localStorage.setItem(LS_KEY, "stored-1");
  expect(storedAppKeyHeaders()).toEqual({ "X-API-Key": "stored-1" });
  expect(prompt).not.toHaveBeenCalled();
});

test("mutatingHeaders carries the key or null when declined", () => {
  jest.spyOn(window, "prompt").mockReturnValueOnce("abc");
  expect(mutatingHeaders()).toEqual({ "X-API-Key": "abc" });
  expect(mutatingHeaders({ "X-Extra": "1" })).toEqual({ "X-API-Key": "abc", "X-Extra": "1" });
  clearAppKey();
  jest.spyOn(window, "prompt").mockReturnValueOnce("");
  expect(mutatingHeaders()).toBeNull();
});

test("withWsToken appends the stored key or leaves the URL alone", () => {
  const prompt = jest.spyOn(window, "prompt").mockReturnValue("nope");
  expect(withWsToken("ws://h/ws/gex/SPY")).toBe("ws://h/ws/gex/SPY");
  window.localStorage.setItem(LS_KEY, "k 1&2");
  expect(withWsToken("ws://h/ws/gex/SPY")).toBe("ws://h/ws/gex/SPY?token=k%201%262");
  expect(withWsToken("ws://h/x?a=b")).toBe("ws://h/x?a=b&token=k%201%262");
  expect(prompt).not.toHaveBeenCalled();
});
