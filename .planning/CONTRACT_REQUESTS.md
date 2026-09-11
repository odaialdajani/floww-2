# Contract Requests — Phase 9 frontend lane gaps (append-only)

> Source of truth for cross-agent contract requests that cannot be resolved by
> the requesting lane editing the target file (forbidden file, another agent's
> WIP, another agent's ownership). Each entry: gap → owner → request → status.
> Filed per AGENT_CONTRACT.md §2 (lane separation) and §3 (forbidden files).

---

## CR-001 (Agent 2 → App.js shell)

`FlowseekerProBlademap.jsx` monolith (2137 lines) needs a compose pass to mount
`PulseTape`, `OverviewBar`, `FilterBar`, `ChartModal`, `Tracker`, `DarkPoolPanel`,
`HistoryViews` and to migrate `PREFS_KEY` → `tabConfig` per-tab substrate.
**Request:** allow a single `App.js`-adjacent shell edit OR a new `FlowseekerShell.jsx`
that the router mounts. Until then, lane ships as standalone tested modules
(fixture-first, no regression).
**Status:** open — awaiting Agent 2 surface decision.
**Source:** `.planning/phases/phase-9-academy-flow/reports/agent2-frontend.md:135`.

---

## CR-002 (Agent 3 → App.js shell — static-import collision, dangling-file cluster)

**Filed:** 2026-09-04 by Agent 3 (tidehunter lane).
**Gap (exact file:line):**

- `frontend/src/App.js:50-52` — static imports of three files that exist ONLY as
  untracked files on the tidehunter worktree's disk and on NO branch:
  `import Wtipanel from "./components/Wtipanel"` (line 50),
  `import RussellPanel from "./components/RussellPanel"` (line 51),
  `import PublicPanel from "./components/PublicPanel"` (line 52).
- `frontend/src/App.js:1172` — `<PublicPanel />` rendered on `page === "public"`.
- The three panels share one untracked stylesheet
  `frontend/src/components/MarketPanels.css` (354 lines, imported at line 3 of each
  panel).

**What breaks:** on a clean checkout (any agent, any worktree), Jest module
resolution fails at `App.js:50` with `Cannot find module './components/Wtipanel'`
BEFORE any test runs — the whole suite collects 0 tests and `visual.test.jsx`
(which renders `<App />`) fails with 0 tests collected. The production build
(`npm run build`) ALSO fails because webpack resolves the same static imports at
build time. The break is at the module graph, not at runtime.

**What Agent 3 already did within its lane (evidence):** replaced
`FlowseekerProBlademap.jsx`'s own static imports of `../Wtipanel` +
`../RussellPanel` with `React.lazy` + `Suspense` + `.catch` fallbacks
(commits `bdbe0b8`, `33b5aaa`). Verified: files present → real modules render
(32/32 tests pass); files absent → empty cards, no crash (32/32 tests pass);
full suite 409/409 green; `craco build` clean. The lazy guard shields ONLY
`FlowseekerProBlademap.jsx` — it cannot reach `App.js` (forbidden file, line 50).

**Owner lane:** product shell (`App.js`) + the three panels — NOT Agent 3's lane.
`App.js` is architect-frozen (AGENT_CONTRACT.md §3). The three panels are not on
any branch (`git log --all -- frontend/src/components/PublicPanel.jsx` returns
nothing); Agent 3 has no authority to commit or delete them.

**Request (choose one, both acceptable):**

- **Option A (commit the panels):** the owning agent commits the four dangling files
  (`MarketPanels.css`, `PublicPanel.jsx`, `RussellPanel.jsx`, `Wtipanel.jsx`) to
  a branch, gets them onto `main` via PR. Resolves the static-import collision for
  everyone. CI `frontend-fs-integrity` step passes once the files are
  tracked.
- **Option B (remove the stale imports):** if the Public Brokerage / WTI / Russell
  panels are no longer wanted, the owning agent removes the three static imports
  (`App.js:50-52`) and the `<PublicPanel />` render (`App.js:1172`), and deletes
  or gitignores the four files. Resolves the collision; CI step passes.
- **Option C (lazy-import the App.js panels):** the owning agent replaces the three
  static imports in `App.js` with `React.lazy` + `Suspense` + `.catch` fallbacks
  (same pattern Agent 3 used for `FlowseekerProBlademap.jsx`). Keeps the panels
  importable but makes a missing file a runtime empty card, not a build/collect
  failure.

**Acceptance (same as the CI `frontend-fs-integrity` gate):** a fresh `actions/checkout@v4` + `npm ci`
must NOT fail at the module-resolution stage. Concretely: `git ls-files --others
--exclude-standard` must return EMPTY for the four files OR the four files must be
present and tracked. CI step `frontend-fs-integrity` (added in this session)
gates this.

---

## CR-003 (Agent 3 → Agent 2 / ChartModal — skew-levels RFC)

See `.planning/phases/phase-9-academy-flow/reports/tidehunter-rfc3-overview.md`
(RFC-3): overview-bar consolidation. Skewed tab substrate decision is Agent 2's to
make; engine, fixtures, and contracts are filed and tested by Agent 3.

---

## Convention

New entries append at the top under a new `CR-XXX` header. Status values:
`open`, `accepted`, `completed`, `closed-wontfix`. Each entry carries exact
file:line anchors and one unambiguous acceptance criterion so the owning agent can
act without asking clarifying questions.
