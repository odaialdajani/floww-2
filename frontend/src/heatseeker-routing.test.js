/**
 * The `skylit` page is reachable ONLY through the URL query param.
 *
 * App.js gates `HeatseekerDashboard` (and 18 sibling panels) behind
 * `page === "skylit"`, but no `setPage(...)` call ever passes "skylit" --
 * the nav only sets trinity/heatseeker/portfolio/journal. The one entry path
 * that reaches it is the lazy state initializer:
 *
 *   const [page, setPage] = useState(() => {
 *     const q = new URLSearchParams(window.location.search).get("page");
 *     if (q && [..., "skylit", ...].includes(q)) return q;
 *     return "heatseeker";
 *   });
 *
 * So `?page=skylit` works but there is no link to it. That makes the allowlist
 * load-bearing in a way a `setPage` grep cannot see -- during this work the
 * branch was briefly believed to be dead code because only `setPage` call
 * sites were searched.
 *
 * This reads App.js as source (App.js is architect-frozen and cannot be
 * imported here without mounting the whole app) and pins:
 *   1. the initializer honors ?page=
 *   2. "skylit" is in its allowlist
 *   3. the branch the panel lives in is still gated on page === "skylit"
 *
 * A future edit that drops "skylit" from the allowlist makes the whole
 * dashboard subtree unreachable with no other signal.
 */

const fs = require("fs");
const path = require("path");

const APP = path.join(__dirname, "App.js");

const readApp = () => fs.readFileSync(APP, "utf8");

describe("skylit page routing", () => {
  test("page state is initialized from the ?page= query param", () => {
    const src = readApp();
    expect(src).toMatch(/const\s*\[page,\s*setPage\]\s*=\s*useState\(\s*\(\)\s*=>/);
    expect(src).toMatch(/new URLSearchParams\(window\.location\.search\)\.get\(["']page["']\)/);
  });

  test('"skylit" is in the initializer allowlist', () => {
    const src = readApp();
    // Isolate the initializer body and its allowlist array.
    const start = src.indexOf("const [page, setPage] = useState(");
    expect(start).toBeGreaterThan(-1);

    const body = src.slice(start, start + 700);
    const allowlist = body.match(/\[([^\]]*)\]\.includes\(q\)/);
    expect(allowlist).not.toBeNull();

    const values = allowlist[1]
      .split(",")
      .map((s) => s.trim().replace(/^["']|["']$/g, ""))
      .filter(Boolean);

    expect(values).toContain("skylit");
    // Guard the other reachable pages so the list is not silently emptied.
    expect(values).toEqual(expect.arrayContaining(["heatseeker", "trinity"]));
  });

  test("the panel's dashboard branch is still gated on page === 'skylit'", () => {
    const src = readApp();
    // HeatseekerDashboard must remain inside a page === "skylit" block.
    const dashIdx = src.indexOf("<HeatseekerDashboard");
    expect(dashIdx).toBeGreaterThan(-1);

    const preceding = src.slice(Math.max(0, dashIdx - 3000), dashIdx);
    const lastGuard = preceding.lastIndexOf('page === "skylit"');
    expect(lastGuard).toBeGreaterThan(-1);
  });

  test("no setPage call passes 'skylit' (query param is the only entry path)", () => {
    // Documents WHY the allowlist above matters. If this ever changes, the
    // nav has a real link and the query param is a convenience, not the
    // sole route.
    const src = readApp();
    const setPageValues = [...src.matchAll(/setPage\(\s*["']([^"']+)["']\s*\)/g)].map(
      (m) => m[1]
    );
    expect(new Set(setPageValues)).not.toContain("skylit");
  });
});
