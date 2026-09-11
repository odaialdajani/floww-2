import { render, screen, fireEvent } from "@testing-library/react";
import AgentPanel from "./AgentPanel";

let mockOpen = true;
const mockSetOpen = jest.fn();
jest.mock("./AgentProvider", () => ({ useAgent: () => ({ open: mockOpen, setOpen: mockSetOpen }) }));
jest.mock("./AgentConversation", () => () => <textarea aria-label="Question" />);

test("research sits outside the inactive page and restores access on close", () => {
  const root = document.createElement("div");
  root.id = "root";
  document.body.appendChild(root);
  document.body.style.overflow = "auto";
  const view = render(<AgentPanel />, { container: root });
  const panel = screen.getByRole("dialog");
  expect(root.contains(panel)).toBe(false);
  expect(root).toHaveAttribute("inert");
  expect(document.body.style.overflow).toBe("hidden");
  expect(screen.getByRole("textbox")).toHaveFocus();
  fireEvent.keyDown(panel, { key: "Escape" });
  expect(mockSetOpen).toHaveBeenCalledWith(false);
  mockOpen = false;
  view.rerender(<AgentPanel />);
  expect(root).not.toHaveAttribute("inert");
  expect(document.body.style.overflow).toBe("auto");
  view.unmount();
  root.remove();
  document.body.style.overflow = "";
});
