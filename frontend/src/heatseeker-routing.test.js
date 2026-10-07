/** Options map must remain reachable by deep link and the shared navigation registry. */
import {NAV_ITEMS} from "./shell/navConfig";
import {readWorkspace} from "./shell/useWorkspaceNavigation";

const fs = require("fs");
const path = require("path");
const readApp = () => fs.readFileSync(path.join(__dirname, "App.js"), "utf8");
afterEach(() => window.history.replaceState({}, "", "/"));

describe("skylit page routing", () => {
  test("page state is initialized from the URL-authoritative navigation hook", () => {
    window.history.replaceState({}, "", "/?page=skylit&review=retained");
    expect(readWorkspace()).toBe("skylit");
    expect(readApp()).toMatch(/const\s*\[page,\s*setPage\]\s*=\s*useWorkspaceNavigation\(\)/);
  });

  test('"skylit" and the other workspaces are admitted by the registry', () => {
    expect(NAV_ITEMS.map(item => item.id)).toEqual(expect.arrayContaining(["skylit", "heatseeker", "trinity"]));
    for (const item of NAV_ITEMS) {
      window.history.replaceState({}, "", `/?page=${item.id}`);
      expect(readWorkspace()).toBe(item.id);
    }
  });

  test("the panel's dashboard branch is still gated on page === 'skylit'", () => {
    const src = readApp();
    const dashIdx = src.indexOf("<HeatseekerDashboard");
    expect(dashIdx).toBeGreaterThan(-1);
    expect(src.slice(Math.max(0, dashIdx - 3000), dashIdx).lastIndexOf('page === "skylit"')).toBeGreaterThan(-1);
  });

  test("Options map has a real navigation entry, not only an undocumented deep link", () => {
    expect(NAV_ITEMS.find(item => item.id === "skylit")).toMatchObject({label: "Options map"});
    window.history.replaceState({}, "", "/?page=not-a-workspace");
    expect(readWorkspace()).toBe("flowseeker-pro");
  });
});
