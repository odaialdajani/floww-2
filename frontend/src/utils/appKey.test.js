/**
 * @jest-environment jsdom
 *
 * appKey: local backend key prompt-once + header builder.
 */
import { getAppKey, clearAppKey, mutatingHeaders } from "./appKey";

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

test("mutatingHeaders carries the key or null when declined", () => {
  jest.spyOn(window, "prompt").mockReturnValueOnce("abc");
  expect(mutatingHeaders()).toEqual({ "X-API-Key": "abc" });
  expect(mutatingHeaders({ "X-Extra": "1" })).toEqual({ "X-API-Key": "abc", "X-Extra": "1" });
  clearAppKey();
  jest.spyOn(window, "prompt").mockReturnValueOnce("");
  expect(mutatingHeaders()).toBeNull();
});
