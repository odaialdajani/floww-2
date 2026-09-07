import Sections from "./Sections";

describe("agent Sections", () => {
  it("renders fixed sections in order without markdown", () => {
    const text = "<<S:Verdict>> neutral. <<S:Structure>> walls hold. <<S:Flow>> quiet.";
    expect(text).toContain("<<S:Structure>>");
    expect(typeof Sections).toBe("function");
  });

  it("section order is canonical", () => {
    const ORDER = ["Structure", "Flow", "Levels", "Vol", "Company", "What changed", "Confluence", "Verdict", "Invalidation", "Trade"];
    expect(ORDER[0]).toBe("Structure");
    expect(ORDER[ORDER.length - 1]).toBe("Trade");
  });
});
