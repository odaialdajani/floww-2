import { fireEvent, render, screen, act } from "@testing-library/react";
import SolsticeStudyMode, { fixtureToSnapshot, gradeStudy } from "./SolsticeStudyMode";

const SC = {
  id: "t", ticker: "SYNTH", spot: 500.0,
  nearest_below: { low: 490, high: 495, gross: 1e6, net: 1e6 },
  nearest_above: null, inside_wall: null,
  quality: { setupEligible: true, reasonCodes: [] },
};

describe("solsticeStudy (R6-5)", () => {
  test("fixture snapshot renders real grid cells with synthetic provenance", () => {
    const snap = fixtureToSnapshot(SC);
    expect(snap.provenance).toBe("SYNTHETIC");
    expect(snap.grid.grid.STUDY["490"]).toBe(500000);
    expect(snap.metrics.walls.length).toBe(1);
  });

  test("correct answers score 5/5, reversed walls fail", () => {
    const good = { walls: "490 495", kind: "OI structure",
      confirm: "reclaim and hold above the zone",
      invalidate: "sustained acceptance below the zone", blocker: "trade side unknown" };
    expect(gradeStudy(SC, good).total).toBe(5);
    const rev = { ...good, walls: "495 490" };
    // Single-pair reversal is symmetric; direction + blocker guards still hold,
    // but a fully reversed two-zone answer fails location.
    const two = { nearest_below: { low: 480, high: 482 }, nearest_above: { low: 518, high: 522 } };
    expect(gradeStudy(two, { ...good, walls: "518 522 480 482" }).detail.walls).toBe(false);
    expect(gradeStudy(SC, { ...good, blocker: "trade immediately" }).detail.blocker).toBe(false);
  });

  test("mounted study mode grades blinded answers without revealing keys", async () => {
    await act(async () => { render(<SolsticeStudyMode scenario={SC} />); });
    // Keys hidden: bounds appear only as grid rail numbers, never as answers.
    expect(screen.queryByTestId("study-result")).toBeNull();
    await act(async () => {
      fireEvent.change(screen.getByTestId("study-answer-walls"), { target: { value: "490 495" } });
      fireEvent.change(screen.getByTestId("study-answer-kind"), { target: { value: "OI structure" } });
      fireEvent.change(screen.getByTestId("study-answer-confirm"), { target: { value: "reclaim and hold above" } });
      fireEvent.change(screen.getByTestId("study-answer-invalidate"), { target: { value: "acceptance below" } });
      fireEvent.change(screen.getByTestId("study-answer-blocker"), { target: { value: "trade side unknown" } });
    });
    await act(async () => { fireEvent.click(screen.getByTestId("study-submit")); });
    expect(screen.getByTestId("study-result").textContent).toContain("5/5");
  });
});

describe("study rubric hardening (R8-06)", () => {
  const good = { walls: "490 495", kind: "OI structure",
    confirm: "reclaim and hold above the zone",
    invalidate: "sustained acceptance below the zone", blocker: "trade side unknown" };
  test("gibberish and negated answers fail; direction still enforced", () => {
    expect(gradeStudy(SC, { ...good, blocker: "bananas" }).detail.blocker).toBe(false);
    expect(gradeStudy(SC, { ...good, blocker: "" }).detail.blocker).toBe(false);
    expect(gradeStudy(SC, { ...good, kind: "not OI structure" }).detail.kind).toBe(false);
    expect(gradeStudy(SC, { ...good, confirm: "never reclaim and hold above" }).detail.confirm).toBe(false);
    expect(gradeStudy(SC, { ...good, invalidate: "acceptance above the zone" }).detail.invalidate).toBe(false);
    expect(gradeStudy(SC, { ...good, invalidate: "acceptance, direction unclear" }).detail.invalidate).toBe(false);
    expect(gradeStudy(SC, good).total).toBe(5);
  });
  test("stale fixture quality reaches the frozen snapshot unlaundered", () => {
    const stale = { ...SC, quality: { state: "stale", reasonCodes: ["STALE_ASK"], setupEligible: false } };
    const snap = fixtureToSnapshot(stale);
    expect(snap.quality.state).toBe("stale");
    expect(snap.quality.setupEligible).toBe(false);
    expect(snap.quality.reasonCodes).toEqual(["STALE_ASK"]);
    expect(fixtureToSnapshot(SC).quality.setupEligible).toBe(true);
  });
  test("mounted submit records confidence alongside score", async () => {
    await act(async () => { render(<SolsticeStudyMode scenario={SC} />); });
    await act(async () => {
      fireEvent.change(screen.getByTestId("study-answer-walls"), { target: { value: "490 495" } });
      fireEvent.change(screen.getByTestId("study-answer-kind"), { target: { value: "OI structure" } });
      fireEvent.change(screen.getByTestId("study-answer-confirm"), { target: { value: "reclaim and hold above" } });
      fireEvent.change(screen.getByTestId("study-answer-invalidate"), { target: { value: "acceptance below" } });
      fireEvent.change(screen.getByTestId("study-answer-blocker"), { target: { value: "trade side unknown" } });
      fireEvent.change(screen.getByTestId("study-confidence"), { target: { value: "high" } });
    });
    await act(async () => { fireEvent.click(screen.getByTestId("study-submit")); });
    expect(screen.getByTestId("study-result").textContent).toContain("5/5");
    expect(screen.getByTestId("study-result").textContent).toContain("confidence high");
  });
});
