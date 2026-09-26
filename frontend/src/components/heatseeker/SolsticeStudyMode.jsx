import React, { memo, useMemo, useRef, useState } from "react";
import SkylitHeatmapGrid from "./SkylitHeatmapGrid";

/**
 * SolsticeStudyMode — read-only frozen-grid study (R6-5/B12).
 *
 * Research-only: renders the ACTUAL grid component over a frozen synthetic
 * snapshot built from a fixture scenario (SYNTHETIC provenance — never live
 * data, never a trade surface). Five blinded tasks: wall location, metric
 * basis, observed interaction, confirmation/invalidation, data limits.
 * Answer keys are never rendered; grading is direction-aware and local.
 * Trade/selection callbacks are disabled: study clicks cannot leak into
 * live actions.
 */
export const STUDY_EXPIRY = "STUDY";

export function fixtureToSnapshot(sc) {
  const walls = [];
  for (const w of [sc.nearest_below, sc.nearest_above, sc.inside_wall]) {
    if (w) walls.push(w);
  }
  const strikes = [];
  const cells = {};
  for (const w of walls) {
    for (const s of [w.low, w.high]) {
      const gex = (w.gross || 0) / 2;
      strikes.push({ strike: s, gex, call_gex: gex, put_gex: 0 });
      cells[String(s)] = gex;
    }
  }
  return {
    ticker: sc.ticker || "STUDY",
    spot: sc.spot,
    asof: sc.asof || null,
    exposure_basis: "OI",
    formula_version: "gex.v2",
    provenance: "SYNTHETIC",
    strikes,
    grid: { expiries: [STUDY_EXPIRY], strikes: strikes.map((r) => r.strike), grid: { [STUDY_EXPIRY]: cells } },
    metrics: { walls: walls.map((w, i) => ({ ...w, wall_id: w.wall_id || `study-w${i}` })) },
    // R8-06: frozen displayed quality equals the fixture — a stale fixture
    // stays stale/setup-ineligible in the study grid, never laundered usable.
    quality: {
      state: sc.quality?.state || "usable",
      reasonCodes: sc.quality?.reasonCodes || [],
      setupEligible: sc.quality?.setupEligible ?? true,
    },
  };
}

export function gradeStudy(scenario, answers, latencyS = {}) {
  const b = scenario.nearest_below;
  const a = scenario.nearest_above;
  const inside = scenario.inside_wall;
  const nums = (t) => (String(t || "").match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
  const near = (g, e) => Math.abs(g - e) <= 0.51;
  const got = nums(answers.walls);
  const slots = [];
  if (b) slots.push([b.low, b.high]);
  if (a) slots.push([a.low, a.high]);
  if (inside) slots.push([inside.low, inside.high]);
  let wallOk;
  if (!slots.length) {
    wallOk = got.length === 0;
  } else {
    wallOk = true;
    let pos = 0;
    for (const exp of slots) {
      const pair = got.slice(pos, pos + 2);
      wallOk = wallOk && pair.length === 2 && exp.every((e) => pair.some((g) => near(g, e)));
      pos += 2;
    }
  }
  const txt = (k) => String(answers[k] || "").toLowerCase();
  // R8-06: negation-aware rubric. "not OI structure" / "never reclaim and
  // hold" must fail even though the keywords appear. Gibberish blockers
  // ("bananas") fail: a blocker needs a domain content word.
  const negated = (t, kw) =>
    new RegExp(`\\b(not|never|no|isn'?t|don't|dont|without)\\b[^.]{0,40}\\b${kw}`).test(t);
  const kindTxt = txt("kind");
  const kindOk = (kindTxt.includes("structure") || kindTxt.includes("oi"))
    && !kindTxt.includes("only activity")
    && !negated(kindTxt, "structure") && !negated(kindTxt, "oi");
  const side = b ? "above" : (a ? "below" : (inside ? "inside" : "above"));
  const confirmTxt = txt("confirm");
  const confirmOk = confirmTxt.includes("reclaim") && confirmTxt.includes("hold")
    && confirmTxt.includes(side)
    && !negated(confirmTxt, "reclaim") && !negated(confirmTxt, "hold");
  const antiSide = side === "above" ? "below" : side === "below" ? "above" : "beyond";
  const invTxt = txt("invalidate");
  const invalidateOk = invTxt.includes("acceptance") && invTxt.includes(antiSide)
    && !negated(invTxt, "acceptance");
  const blockerTxt = txt("blocker");
  const blockerOk = blockerTxt.length > 0
    && !/immediately|trade now|buy now|sell now/.test(blockerTxt)
    && /(unknown|stale|missing|wait|evidence|eligib|spread|quote|coverage|side|confirm|invalid|hold|accept|volume|data|quality|session|holiday|window|setup|block|reason|risk|time|expir|ask|bid|liquid)/.test(blockerTxt);
  const detail = { walls: wallOk, kind: kindOk, confirm: confirmOk, invalidate: invalidateOk, blocker: blockerOk };
  return { detail, total: Object.values(detail).filter(Boolean).length, latencyS };
}

const TASKS = [
  ["walls", "Q1 — bounds for each loaded zone, in order below, above, inside:"],
  ["kind", "Q2 — OI structure or recent activity?"],
  ["confirm", "Q3 — what price action confirms the watch?"],
  ["invalidate", "Q4 — what price action invalidates it?"],
  ["blocker", "Q5 — why is a setup withheld here?"],
];

function SolsticeStudyMode({ scenario, onDone = null }) {
  const snapshot = useMemo(() => fixtureToSnapshot(scenario), [scenario]);
  const t0 = useRef(null);
  if (t0.current == null) t0.current = Date.now();
  const [answers, setAnswers] = useState({});
  const [confidence, setConfidence] = useState("");
  const [result, setResult] = useState(null);
  if (!scenario) return null;
  const submit = () => {
    const latencyS = { total: Math.round((Date.now() - t0.current) / 100) / 10 };
    const graded = gradeStudy(scenario, answers, latencyS);
    graded.confidence = ["low", "medium", "high"].includes(confidence) ? confidence : null;
    setResult(graded);
    if (onDone) onDone(graded);
  };
  return (
    <div data-testid="solstice-study-mode" title="Frozen-grid study (research only, no live data)">
      <SkylitHeatmapGrid data={snapshot} spot={snapshot.spot} ticker={snapshot.ticker} />
      {TASKS.map(([key, prompt]) => (
        <label key={key} style={{ display: "block", marginTop: 6, fontSize: 12 }}>
          {prompt}
          <input
            data-testid={`study-answer-${key}`}
            value={answers[key] || ""}
            onChange={(e) => setAnswers((a) => ({ ...a, [key]: e.target.value }))}
            style={{ display: "block", width: "100%" }}
          />
        </label>
      ))}
      <label style={{ display: "block", marginTop: 6, fontSize: 12 }}>
        Confidence (recorded separately from accuracy):
        <select data-testid="study-confidence" value={confidence}
          onChange={(e) => setConfidence(e.target.value)}
          style={{ display: "block" }}>
          <option value="">—</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
      </label>
      <button className="skylit-trade-mode-btn" data-testid="study-submit" onClick={submit}>
        Submit (read-only)
      </button>
      {result && (
        <div data-testid="study-result">
          Score {result.total}/5 · {result.latencyS.total}s
          {result.confidence ? ` · confidence ${result.confidence}` : ""}
        </div>
      )}
    </div>
  );
}

export default memo(SolsticeStudyMode);
