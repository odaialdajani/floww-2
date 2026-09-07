import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { useAgent } from "./AgentProvider";
import useAgentStream from "./useAgentStream";
import useScreenContext from "./useScreenContext";

/** Centered overlay on Ctrl/Cmd+K only — / is taken by the blademap (plan v3 L7). */
export default function AgentCommandBar() {
  const agent = useAgent();
  const [ctx] = useScreenContext();
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const { ask } = useAgentStream({
    onEvent: (kind, payload) => {
      if (kind === "sentence") setAnswer((a) => `${a} ${payload.text || ""}`);
      if (kind === "done" && agent) agent.pushTurn({ text: answer, verdict: payload.verdict, flagged: [] });
    },
  });

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (agent) agent.setBarOpen(!agent.barOpen);
      }
      if (e.key === "Escape" && agent) agent.setBarOpen(false);
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [agent]);

  if (!agent || !agent.barOpen) return null;
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 70, display: "flex", justifyContent: "center", paddingTop: 120 }} onClick={() => agent.setBarOpen(false)}>
      <div style={{ width: 560, height: "fit-content", background: "#1e2126", color: "#a4a8ae", borderRadius: 10, padding: 12 }} onClick={(e) => e.stopPropagation()}>
        <Command>
          <Command.Input value={q} onValueChange={setQ} placeholder={`${ctx.ticker} · ${ctx.dte} — ask one thing…`} style={{ width: "100%", background: "#16181c", color: "#a4a8ae", border: "1px solid #333942", borderRadius: 6, padding: 10 }} />
          <Command.List>
            <Command.Item onSelect={() => ask({ question: q, ticker: ctx.ticker, horizon: ctx.dte, screen: ctx, question_class: "quick-read" })}>Answer: {q || "…"}</Command.Item>
          </Command.List>
        </Command>
        {answer && <div style={{ marginTop: 8, fontSize: 13 }}>{answer}</div>}
      </div>
    </div>
  );
}
