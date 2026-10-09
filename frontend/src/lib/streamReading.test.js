import { snapshotStreamNote, streamScopeLabel } from "./streamReading";

describe("streamScopeLabel", () => {
  test("labels a full-identity stream reading", () => {
    expect(streamScopeLabel({
      reading: "stream", formula_version: "gex.v2", units: "USD",
      expiries: ["2026-10-09", "2026-10-10"],
    })).toBe("Stream · separate reading · 2 exp · USD · gex.v2");
  });

  test("unknown stays unknown and never crashes", () => {
    expect(streamScopeLabel(null)).toMatch(/unavailable/);
    expect(streamScopeLabel(undefined)).toMatch(/unavailable/);
    expect(streamScopeLabel({})).toBe(
      "Stream · separate reading · expiry scope unknown · units unknown · version unknown"
    );
  });
});

describe("snapshotStreamNote", () => {
  test("null when both readings agree", () => {
    expect(snapshotStreamNote(
      { regime: "negative", king: { strike: 767 } },
      { regime: "negative", king: { strike: 767 } },
    )).toBeNull();
  });

  test("names separation when regimes disagree (the 767/790 contradiction)", () => {
    expect(snapshotStreamNote(
      { regime: "negative", king: { strike: 767 } },
      { regime: "positive", king: { strike: 790 } },
    )).toBe("Snapshot and stream are separate readings — different scope and clocks. Not one signal.");
  });

  test("names separation when only the king differs", () => {
    expect(snapshotStreamNote(
      { regime: "negative", king: { strike: 767 } },
      { regime: "negative", king: { strike: 790 } },
    )).not.toBeNull();
  });

  test("null while either side is missing", () => {
    expect(snapshotStreamNote(null, { regime: "positive" })).toBeNull();
    expect(snapshotStreamNote({ regime: "negative" }, null)).toBeNull();
    expect(snapshotStreamNote(undefined, undefined)).toBeNull();
  });

  const known = { regime: "positive", king: { strike: 790 } };

  test.each([
    ["missing reading", null],
    ["undefined reading", undefined],
    ["missing king", { regime: "positive" }],
    ["null king", { regime: "positive", king: null }],
    ["missing strike", { regime: "positive", king: {} }],
    ...[
      null, undefined, "", " ", "\t", true, false, [], [791], {},
      NaN, Infinity, -Infinity, "Infinity", "not-a-strike",
    ].map((strike, index) => [
      `unknown or invalid strike ${index}`,
      { regime: "positive", king: { strike } },
    ]),
  ])("does not invent a king disagreement for %s on either side", (_, unknown) => {
    expect(snapshotStreamNote(unknown, known)).toBeNull();
    expect(snapshotStreamNote(known, unknown)).toBeNull();
  });

  test("numeric strings and measured zero remain comparable", () => {
    expect(snapshotStreamNote(
      { regime: "positive", king: { strike: "790" } }, known,
    )).toBeNull();
    expect(snapshotStreamNote(
      { regime: "positive", king: { strike: 0 } },
      { regime: "positive", king: { strike: "0" } },
    )).toBeNull();
    expect(snapshotStreamNote(
      { regime: "positive", king: { strike: 0 } }, known,
    )).not.toBeNull();
  });

  test("a known regime disagreement still warns with unknown kings", () => {
    expect(snapshotStreamNote(
      { regime: "negative", king: null },
      { regime: "positive", king: null },
    )).not.toBeNull();
  });
});
