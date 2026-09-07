import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

const AgentContext = createContext(null);

export function useAgent() {
  return useContext(AgentContext);
}

/** One conversation state shared by the panel and the command bar (plan v3 L7). */
export default function AgentProvider({ children }) {
  const [turns, setTurns] = useState([]);
  const [activeTurn, setActiveTurn] = useState(null);
  const [open, setOpen] = useState(false);
  const [barOpen, setBarOpen] = useState(false);
  const abortRef = useRef(null);

  const pushTurn = useCallback((turn) => {
    setTurns((t) => [...t.slice(-19), turn]);
    setActiveTurn(turn);
  }, []);

  const value = useMemo(
    () => ({ turns, activeTurn, setActiveTurn, pushTurn, open, setOpen, barOpen, setBarOpen, abortRef }),
    [turns, activeTurn, pushTurn, open, barOpen]
  );
  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}
