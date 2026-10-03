import { act, fireEvent, render, screen } from "@testing-library/react";
import { NAV_ITEMS } from "./navConfig";
import useWorkspaceNavigation from "./useWorkspaceNavigation";

function Workspace() {
  const [page, navigate] = useWorkspaceNavigation();
  return <><output aria-label="Current workspace">{page}</output>{NAV_ITEMS.map(item =>
    <button key={item.id} aria-current={page === item.id ? "page" : undefined} onClick={() => navigate(item.id)}>{item.label}</button>
  )}<button onClick={() => navigate("unsupported-page")}>Unknown workspace</button></>;
}

beforeEach(() => window.history.replaceState(null, "", "/?keep=owned#selection"));

test.each(NAV_ITEMS.map(item => [item.id, item.label]))("loads and refreshes the existing deep link %s", (id, label) => {
  window.history.replaceState(null, "", `/?keep=owned&page=${id}#selection`);
  const view = render(<Workspace/>);
  expect(screen.getByLabelText("Current workspace")).toHaveTextContent(id);
  expect(screen.getByRole("button", { name: label, exact: true })).toHaveAttribute("aria-current", "page");
  view.unmount();
  render(<Workspace/>);
  expect(screen.getByLabelText("Current workspace")).toHaveTextContent(id);
});

test("workspace changes preserve unrelated URL state and do not add duplicate history entries", () => {
  render(<Workspace/>);
  const length = window.history.length;
  fireEvent.click(screen.getByRole("button", { name: "Triad", exact: true }));
  expect(window.location.search).toBe("?keep=owned&page=trinity");
  expect(window.location.hash).toBe("#selection");
  expect(window.history.length).toBe(length + 1);
  fireEvent.click(screen.getByRole("button", { name: "Triad", exact: true }));
  expect(window.history.length).toBe(length + 1);
  fireEvent.click(screen.getByRole("button", { name: "Unknown workspace" }));
  expect(screen.getByLabelText("Current workspace")).toHaveTextContent("trinity");
  expect(window.history.length).toBe(length + 1);
});

test("back/forward popstate uses the URL rather than untrusted history metadata", () => {
  render(<Workspace/>);
  fireEvent.click(screen.getByRole("button", { name: "Journal", exact: true }));
  act(() => {
    window.history.replaceState({ page: "public" }, "", "/?keep=owned&page=skylit#selection");
    window.dispatchEvent(new PopStateEvent("popstate", { state: { page: "public" } }));
  });
  expect(screen.getByLabelText("Current workspace")).toHaveTextContent("skylit");
  act(() => {
    window.history.replaceState(null, "", "/?page=journal");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  expect(screen.getByLabelText("Current workspace")).toHaveTextContent("journal");
});

test("unknown links fall back to Solstice and unmount releases the history listener", () => {
  window.history.replaceState(null, "", "/?page=not-a-workspace");
  const remove = jest.spyOn(window, "removeEventListener");
  const view = render(<Workspace/>);
  expect(screen.getByLabelText("Current workspace")).toHaveTextContent("heatseeker");
  view.unmount();
  expect(remove).toHaveBeenCalledWith("popstate", expect.any(Function));
  remove.mockRestore();
});
