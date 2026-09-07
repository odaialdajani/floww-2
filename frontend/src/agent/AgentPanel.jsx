import { Drawer } from "vaul";
import { useAgent } from "./AgentProvider";
import AgentPanelAnswer from "./AgentPanelAnswer";
import TradeCard from "./TradeCard";
import useAgentStream from "./useAgentStream";
import useScreenContext from "./useScreenContext";
import { useState } from "react";

/** Docked right panel (plan v3 L7). vaul drawer, fixed, sidebar-aware. Low-glare. */
export default function AgentPanel() {
  const agent = useAgent();
  const [ctx] = useScreenContext();
  const [q, setQ] = useState("");
  const [sentences, setSentences] = useState([]);
  const { state, ask } = useAgentStream({
    onEvent: (kind, payload) => {
      if (kind === "sentence") setSentences((s) => [...s, payload.text || ""]);
      if (kind === "done" && agent) agent.pushTurn({ text: sentences.join(" "), verdict: payload.verdict, flagged: payload.flagged || [], cost: payload.cost });
    },
  });
  if (!agent || !agent.open) return null;

  const submit = async () => {
    if (!q.trim()) return;
    setSentences([]);
    await ask({ question: q, ticker: ctx.ticker, horizon: ctx.dte, screen: ctx });
    setQ("");
  };

  return (
    <Drawer.Root open direction="right">
      <Drawer.Portal>
        <Drawer.Content
          style={{ position: "fixed", right: 0, top: 0, bottom: 0, width: 420, background: "#1e2126", color: "#a4a8ae", padding: 16, overflowY: "auto", zIndex: 60 }}
        >
          <div style={{ fontSize: 13, fontWeight: 600 }}>Lodestar — {ctx.ticker} · {ctx.dte}</div>
          <div style={{ fontSize: 11, opacity: 0.8 }}>Market-structure analysis, not financial advice. Levels are decision zones, not instructions. GEX/VEX nodes shift as price, open interest and dealer positioning change.</div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about structure, flow, levels…" style={{ flex: 1, background: "#16181c", color: "#a4a8ae", border: "1px solid #333942", borderRadius: 6, padding: 8 }} />
            <button onClick={submit} disabled={state === "streaming"} style={{ background: "#2a2f36", color: "#a4a8ae", borderRadius: 6, padding: "8px 12px" }}>Ask</button>
          </div>
          <div style={{ marginTop: 12, fontSize: 13, whiteSpace: "pre-wrap" }}>{sentences.join(" ")}</div>
          {agent.activeTurn && <AgentPanelAnswer turn={agent.activeTurn} />}
          <TradeCard turn={agent.activeTurn} />
          <button onClick={() => agent.setOpen(false)} style={{ marginTop: 12, fontSize: 12 }}>Close</button>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
