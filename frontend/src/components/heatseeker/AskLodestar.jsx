import React, { memo, useState } from "react";
import { useAgent } from "../../agent/AgentProvider";

/**
 * AskLodestar — compact entry point next to a selected wall / active pane.
 *
 * Uses the EXISTING assistant (AgentProvider → useAgentStream); this is not
 * a second chatbot. Lodestar stays closed until the user asks.
 *
 * Admission is honest about the current server guard
 * (backend services/agent/contracts.py request_spec): research answers are
 * only admitted for the LIVE RAW map. Adjusted overlays, replay and the
 * price-history view are refused server-side until exact-surface/snapshot
 * resolution exists, so this control explains that instead of sending a
 * request that will 422. The published screen context (not these props)
 * is what the server validates; client values are never numeric evidence.
 */
export const STARTERS = [
  "Why this wall?",
  "What changed?",
  "What confirms or invalidates?",
];

export function admissionBlock({ context, overlayMetric, displayMode }) {
  if (displayMode === "replay") return "Replay answers need recorded-snapshot resolution, which is not enabled yet — return to Live to ask.";
  if (displayMode === "price-history") return "Close the price-history chart to ask about the live map.";
  if (overlayMetric && overlayMetric !== "raw") return "Lodestar reads the live Raw OI map today — switch the GEX basis to Raw OI to ask. Adjusted answers need server-side surface resolution first.";
  if (context && !context.ticker) return "No published selection for this screen.";
  return null;
}

function AskLodestar({ subject = "", overlayMetric = "raw", displayMode = "live", compact = false, testId = "ask-lodestar" }) {
  const agent = useAgent();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState(null);
  if (!agent) {
    return (
      <span className="lodestar-ask lodestar-ask-off" data-testid={`${testId}-unavailable`}
        title="Lodestar is not mounted on this screen">
        Lodestar unavailable
      </span>
    );
  }
  const block = admissionBlock({ context: agent.context, overlayMetric, displayMode });
  const busy = ["asking", "running", "reconnecting", "cancelling"].includes(agent.state);
  const ask = (q) => {
    setOpen(false);
    if (block) { setNote(block); return; }
    setNote(null);
    agent.setOpen(true);
    agent.askQuestion(subject ? `${q} (${subject})` : q);
  };
  return (
    <span className={`lodestar-ask${compact ? " compact" : ""}`} data-testid={testId}>
      <button type="button" className="skylit-trade-mode-btn lodestar-ask-btn"
        aria-haspopup="menu" aria-expanded={open} disabled={busy}
        title={block || "Ask Lodestar about this selection — uses the same published evidence, no new data"}
        data-testid={`${testId}-btn`}
        onClick={() => setOpen((o) => !o)}>
        ✦ Ask Lodestar
      </button>
      {open && (
        <span className="lodestar-ask-menu" role="menu" data-testid={`${testId}-menu`}>
          {STARTERS.map((q) => (
            <button key={q} type="button" role="menuitem" className="lodestar-ask-item"
              data-testid={`${testId}-q-${STARTERS.indexOf(q)}`} onClick={() => ask(q)}>
              {q}
            </button>
          ))}
        </span>
      )}
      {note && (
        <span className="lodestar-ask-note" role="status" data-testid={`${testId}-note`}>{note}</span>
      )}
    </span>
  );
}

export default memo(AskLodestar);
