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
 * admitted for live raw, verified adjusted v2 selections and recorded GEX
 * replay with complete identity, plus resolved listed-contract selectors.
 * Window/price-history remain unavailable. Only the server resolves facts.
 * The published screen context (not these props)
 * is what the server validates; client values are never numeric evidence.
 */
export const STARTERS = [
  "Why this wall?",
  "What changed?",
  "What confirms or invalidates?",
];

export function admissionBlock({ context, overlayMetric, displayMode }) {
  if (displayMode === "price-history") return "Close the price-history chart to ask about the live map.";
  if (context && !context.ticker) return "No published selection for this screen.";
  if (context?.selectedContract) {
    const c = context.selectedContract;
    const exact = context.contextVersion === 2 && context.snapshotId && context.mapQuery && context.mapVersion && context.provider && context.formula
      && context.contractResolution === "resolved" && c.osi && c.strike && c.expiry && c.type
      && Number(c.strike) === context.selectedStrike && c.expiry === context.selectedExpiry
      && context.mapStrikes?.includes(Number(c.strike)) && context.mapExpiries?.includes(c.expiry);
    if (!exact) return "Exact contract selection is incomplete, changed or unresolved — use the authoritative read-only contract drawer.";
  }
  if (!["raw", "delta", "session_delta_volume", "activity"].includes(overlayMetric || "raw")) return "This adjusted basis remains explicitly unavailable to Lodestar.";
  if ((context?.overlayMetric && context.overlayMetric !== overlayMetric) || (context?.displayMode && context.displayMode !== displayMode)) return "Published selection changed — wait for the current pane and basis.";
  const advanced = displayMode === "replay" || (overlayMetric && overlayMetric !== "raw");
  const bound = context?.contextVersion === 2 && context.snapshotId && context.mapQuery && context.mapVersion && context.provider && context.formula;
  if (advanced && !bound) return displayMode === "replay"
    ? "Replay answers need a complete recorded-snapshot resolution identity; older records remain unavailable — return to Live."
    : "Adjusted answers need a complete server-side surface identity — use Raw OI until this observation resolves.";
  if (displayMode === "replay" && context?.metric && !["gex", "skylit"].includes(context.metric)) return "Recorded replay answers for this metric remain unavailable.";
  if (displayMode && !["live", "replay"].includes(displayMode)) return "This display is unavailable to Lodestar.";
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
