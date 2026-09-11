import React from "react";
import {render, screen} from "@testing-library/react";
import AgentPanelAnswer from "./AgentPanelAnswer";
test("answer heading uses the saved expiry scope instead of broad request alias",()=>{
 render(<AgentPanelAnswer turn={{ticker:"SPY",horizon:"all",status:"completed",answer:{snapshots:[{ticker:"SPY",window:{start:"2026-09-18",end:"2026-09-18"}}]}}}/>);
 expect(screen.getByRole("heading").textContent).toBe("SPY · 2026-09-18");
});
