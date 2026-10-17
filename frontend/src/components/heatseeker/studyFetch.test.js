/**
 * @jest-environment jsdom
 *
 * Unit coverage for the shared study fetch + classification contract.
 * The component-level contract is pinned by studyCardsPublicOnlyErrors.test.jsx
 * and WheelIncomeScreenerPanel.test.jsx; these tests pin the parser itself.
 */
import { fetchStudyJSON, classifyStudyError, PUBLIC_ONLY_STUDY_UNAVAILABLE } from "./studyFetch";

const typedRefusalBody = {
  error: {
    status: "unavailable",
    reason: "PUBLIC_ONLY_STUDY_UNAVAILABLE",
    message: "This study has no Public-only producer; alternate sources are disabled",
  },
  status_code: 503,
  path: "/api/dual_gex/SPY",
};

function respondWith(status, body) {
  return { ok: false, status, json: () => Promise.resolve(body) };
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("fetchStudyJSON", () => {
  test("passes a 2xx JSON body straight through", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ spot: 500 }) })
    );
    await expect(fetchStudyJSON("http://x/api/study")).resolves.toEqual({ spot: 500 });
  });

  test("keeps the typed refusal reason and HTTP status from a 503 body", async () => {
    global.fetch = jest.fn(() => Promise.resolve(respondWith(503, typedRefusalBody)));
    let thrown;
    try {
      await fetchStudyJSON("http://x/api/study");
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(Error);
    expect(thrown.reason).toBe(PUBLIC_ONLY_STUDY_UNAVAILABLE);
    expect(thrown.httpStatus).toBe(503);
    expect(thrown.message).toBe("This study has no Public-only producer; alternate sources are disabled");
  });

  test("recognizes the older stringified refusal body", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve(respondWith(503, {
        error: "{'status': 'unavailable', 'reason': 'PUBLIC_ONLY_STUDY_UNAVAILABLE'}",
      }))
    );
    let thrown;
    try {
      await fetchStudyJSON("http://x/api/study");
    } catch (e) {
      thrown = e;
    }
    expect(thrown.reason).toBe(PUBLIC_ONLY_STUDY_UNAVAILABLE);
    expect(thrown.httpStatus).toBe(503);
  });

  test("an untyped FastAPI detail is a server error, not a refusal", async () => {
    global.fetch = jest.fn(() => Promise.resolve(respondWith(422, { detail: "Invalid filter" })));
    let thrown;
    try {
      await fetchStudyJSON("http://x/api/study");
    } catch (e) {
      thrown = e;
    }
    expect(thrown.reason).toBeNull();
    expect(thrown.httpStatus).toBe(422);
    expect(thrown.message).toBe("Invalid filter");
  });

  test("a non-JSON error body keeps the bare HTTP status", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.reject(new SyntaxError("Unexpected token")) })
    );
    let thrown;
    try {
      await fetchStudyJSON("http://x/api/study");
    } catch (e) {
      thrown = e;
    }
    expect(thrown.reason).toBeNull();
    expect(thrown.httpStatus).toBe(500);
    expect(thrown.message).toBe("HTTP 500");
  });

  test("a rejected fetch propagates untouched (no fake status)", async () => {
    global.fetch = jest.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(fetchStudyJSON("http://x/api/study")).rejects.toThrow("Failed to fetch");
  });
});

describe("classifyStudyError", () => {
  test("a typed reason means the study is unavailable on this feed", () => {
    const state = classifyStudyError({ reason: PUBLIC_ONLY_STUDY_UNAVAILABLE, httpStatus: 503, message: "no producer" });
    expect(state.kind).toBe("study-unavailable");
    expect(state.reason).toBe(PUBLIC_ONLY_STUDY_UNAVAILABLE);
    expect(state.httpStatus).toBe(503);
  });

  test("an HTTP status without a reason is a server error", () => {
    const state = classifyStudyError({ httpStatus: 500, message: "HTTP 500" });
    expect(state.kind).toBe("server-error");
  });

  test("a plain network error is offline", () => {
    const state = classifyStudyError(new TypeError("Failed to fetch"));
    expect(state.kind).toBe("offline");
    expect(state.httpStatus).toBeNull();
    expect(state.reason).toBeNull();
    expect(state.message).toBe("Failed to fetch");
  });
});
