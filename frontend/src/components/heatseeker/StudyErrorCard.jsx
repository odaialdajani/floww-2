/**
 * StudyErrorCard.jsx — shared error card for heatseeker study tiles.
 *
 * Renders the three-state failure contract from studyFetch.js with the
 * exact wording WheelIncomeScreenerPanel established (the accepted
 * reference implementation):
 *
 *   study-unavailable → "<Title> · study unavailable" + the typed reason
 *     ("This backend reported <reason> — the study has no producer on
 *     this feed; no alternate source is substituted."). No start-hint:
 *     the backend is reachable and the refusal is deliberate.
 *   server-error → "<Title> · server error" + "backend @ <base> returned
 *     HTTP <status> → <message>".
 *   offline → "<Title> · offline" + "backend @ <base> unreachable →
 *     <message>" (+ optional start hint — only legitimate here).
 */
import React from "react";
import { classifyStudyError } from "./studyFetch";

function StudyErrorCard({ title, base, error, className, testId, hint, footer }) {
  const state = classifyStudyError(error);
  const headline =
    state.kind === "study-unavailable"
      ? `${title} · study unavailable`
      : state.kind === "server-error"
        ? `${title} · server error`
        : `${title} · offline`;
  return (
    <div className={className} data-testid={testId}>
      <div className="text-[10px] uppercase tracking-widest text-amber-300 font-bold mb-1">
        {headline}
      </div>
      <div className="text-[10px] text-amber-200/80">
        {state.kind === "study-unavailable" ? (
          <>This backend reported <span className="font-mono">{state.reason}</span> — the study has no producer on this feed; no alternate source is substituted.</>
        ) : state.kind === "server-error" ? (
          <>backend @ {base} returned HTTP {state.httpStatus} → {state.message}</>
        ) : (
          <>backend @ {base} unreachable → {state.message}</>
        )}
      </div>
      {hint && state.kind === "offline" && (
        <div className="text-[9px] text-amber-200/60 mt-1">{hint}</div>
      )}
      {footer}
    </div>
  );
}

export default StudyErrorCard;
