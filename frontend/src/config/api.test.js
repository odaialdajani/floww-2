import { backendBaseFor } from "./api";

describe("managed backend origin derivation", () => {
  test("loopback pages use the managed loopback backend", () => {
    expect(backendBaseFor("http://127.0.0.1:3000")).toBe("http://127.0.0.1:8213");
    expect(backendBaseFor("http://localhost:3000")).toBe("http://127.0.0.1:8213");
    expect(backendBaseFor("http://[::1]:3000")).toBe("http://127.0.0.1:8213");
  });

  test("LAN pages use the same host on the managed backend port", () => {
    expect(backendBaseFor("http://192.168.0.18:3000")).toBe("http://192.168.0.18:8213");
    expect(backendBaseFor("http://navs-macbook-air-2.local:3000")).toBe("http://navs-macbook-air-2.local:8213");
  });

  test("a missing or non-http origin keeps the documented fallback", () => {
    expect(backendBaseFor("")).toBe("http://localhost:8000");
    expect(backendBaseFor(null)).toBe("http://localhost:8000");
    expect(backendBaseFor("file:///tmp/index.html")).toBe("http://localhost:8000");
  });
});
