# U09 — Selection, generation and assistant context continuity

Owner: OpenCode. Reviewer: Cline. Status: work recorded, pending Cline review.

## A. Parent Skylit fragment-brace correction (review)

Parent change (`frontend/src/components/heatseeker/SkylitDashboard.jsx`):
`</>}` → `</>` — removes a stray `}` that rendered as literal text after the
scroll-down study block.

Verification on current source:

- New pin in `SkylitDashboard.test.jsx`: `expect(screen.queryByText("}",
  {exact:true})).not.toBeInTheDocument()` inside the "default chart retains
  the accessible heatmap and study controls" test — proves no stray brace
  node renders while both studies stay visible (`price-node-history`,
  `mock-heatmap`, control bar, canvas-layout combobox all asserted visible in
  the same test).
- `SkylitDashboard` suite green in the 238/238 focused run. Both simultaneous
  Stock studies preserved; selection ownership untouched (no state/prop change
  in the patch — single-character markup fix).

## B. Context/generation continuity matrix (new)

New: `frontend/src/unified-tests/context-generation.test.jsx` (7 tests,
green). Synthetic records only; fetch injected; no model, network, or order
surface. Pinned:

1. Navigation-only phrases resolve to pages (`options map` → skylit,
   `market view for SPY` → trinity+SPY, `$NVDA screener` → flowseeker-pro+NVDA);
   research questions and >2000-char inputs stay null.
2. Bare "stock chart" binds literal pseudo-ticker STOCK via the `chart` key —
   documented quirk, fail-closed: `verifyNavigationTicker` refuses STOCK
   against a complete catalog ("not in the provider's available stock list").
   Overlong symbols (>12 chars) refuse at parse time.
3. `checkedChartAction` admits only exact grounded facts (ticker match,
   ≤30 fact_ids, heatseeker view); mismatched/foreign/oversized/unlisted
   facts → null. A page label never grants research grounding.
4. `verifyNavigationTicker`: confirms listed symbols; unknown symbol with a
   complete fresh catalog → explicit not-listed error; incomplete catalog →
   explicit incomplete error (never "confirmed"); malformed input refused.
5. `prepareScreenNavigation`: persists screener focusTicker; corrupt prefs →
   friendly error; non-screener pages untouched.
6. `useScopedReading`: cross-scope reads null; returning to the scope
   restores the retained value with its ORIGINAL observation payload
   (`event_time: 't0'` preserved — retention never re-times evidence).
7. Market-wide wording detected; "do not scan all" exclusions stay research.

Neighbor suites (`agent/chatNavigation`, `hooks/useScopedReading`,
`agent/useScreenContext`): 25/25 green — no existing navigation contract
altered.

## Files

- Modified (parent): `SkylitDashboard.jsx`, `SkylitDashboard.test.jsx`
  (hashes in U01 `EVIDENCE.json`).
- New (this task): `frontend/src/unified-tests/context-generation.test.jsx`.
- New (this dossier): `docs/unified/U09/REVIEW-NOTE.md` (+ evidence below).

## Next

Cline: review matrix + sealed snapshot. U09 acceptance needs your independent
verdict bound to baseline + snapshot.
