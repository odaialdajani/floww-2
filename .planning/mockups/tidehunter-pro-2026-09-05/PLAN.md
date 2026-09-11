# Tidehunter Pro UI redesign v3 - implementation plan

Updated: 2026-09-11

**User priority update,2026-09-11 22:22 UTC:** Stop mobile optimization work.
Desktop behavior and remaining AI/data features take priority. Do not schedule
further mobile layout, polish or dedicated validation. Previously completed
mobile fixes and recorded checks remain historical; this instruction does not
request their rollback.

**Status (2026-09-11 implementation update):** The production redesign, dealer
detail and shared research context are implemented. Actual Public-backed wide,
narrow and colour-blind views were inspected against the included reference.
All 676 frontend checks pass and the final production build succeeds. The
companion AI release still has open acceptance gates; UI completion does not
close them. See the dated [full UI sweep](../../eval/ui-plan-sweep-20260911.md)
for retained limitations and [delivery evidence](../../INTEGRATION_AI_UI_GOAL.md).

There are two implementation plans for this work:

- [AI implementation plan](../../unknowns/lodestar-plan-v4-review-draft.md): the
  assistant, evidence, saved conversations, research, proposals and later
  separately gated trading capabilities.
- This UI redesign plan: the complete Tidehunter Pro dashboard, its controls,
  layout, settings, dealer map and drill-down. All UI build notes are contained
  here. The preview below is a visual asset belonging to this plan, not a third
  plan or a separate implementation brief.

## 1. Included design reference and scope

**Open the included design:** [UI redesign v3 preview](tidehunter-pro-blademap-v3.html).
It is the latest Blademap-inspired, low-glare visual reference, including the
owner-requested [dealer drill-down](ref/drilldown-reference.png).

Keep one page with section navigation. Build from the latest preview rather
than reviving the earlier three-look design or the superseded second mockup's
right rail. The dealer drill-down is directly below the Lattice map. Preserve
the latest preview's section order, table-based density, typography, colours,
spacing and control placement; do not replace it with a fresh design direction.

The earlier Claude Code redesign brief supplies retained behaviour and control
requirements, incorporated below. Where its presentation differs, v3 wins:
sidebar section links, Vector/Pulse/Lattice layout, conviction bars and tier
words, and the below-map drill-down replace the older right rail and ring-led
presentation. Older mockups and briefs are historical references only.

This is UI work, independent of the gated paid Tidehunter Pro data-provider
integration. Preserve existing services and trading protections. This plan
does not authorize new broker execution, scoring changes, a framework migration,
or an unrelated app-wide redesign.

## 2. Complete page and information order

| Area | Required live behaviour |
| --- | --- |
| Sidebar and top bar | Navigate Board, Vector, Pulse, Lattice, Trust and Settings within one page. Show the selected ticker, active screen, market state, refresh and settings access. Do not restore separate scanner/flow/gamma page tabs. |
| Board | Keep the v3 title, freshness/source line and expiry, score and layout controls. Show the active universe and actual available contract/signal counts. |
| Four answer cells | Trade now, Money building, Changed since you looked, and Dealers for the printed focused ticker. Give one short verdict plus supporting facts, freshness and a useful destination. |
| Screens and filters | All flow, Whale blocks, OI-confirmed, 0DTE lottos, Hedges, Fresh positioning and My universe. Apply the same active scope to cards, Vector, Pulse and sample-based summaries. |
| Vector | A ranked decision table with ticker/contract, direction, evidence stage, conviction bar and tier, short reason, labelled levels and movement. Retain Drill, Watch, Plan and Ack actions where valid. |
| Pulse | Screened contracts with type, expiry, score, activity, volume, open-interest change and other selectable columns. Preserve sorting, focused selection, refresh and export. |
| Lattice | Focused-ticker dealer map, displayed strikes/expiries, spot, flip, walls, max pain and labelled gamma scope. An unavailable measure must not masquerade as the selected one. |
| Dealer drill-down | Required panel immediately below the map; complete details and calculations are in section 5. |
| Trust | Real available performance bands and sample counts, plus journal results by setup. Small samples must remain visibly uncertain. |
| Settings | Editable copies of screens, rule conditions, universe, section order, columns, layout mode and supported display preferences, using the existing settings store. |

The preview contains invented sample values and some illustrative controls.
Its presence proves neither live wiring nor that every control works. The live
build must implement each retained control or display a clear unavailable state;
do not ship decorative buttons that silently do nothing.

## 3. Answers, screening and actions

### Answer rules

- Trade now uses the leading eligible directional alert in the active screen.
  A missing contract, missing direction, inadequate conviction or stale source
  must produce an explicit withheld/empty state, not a fabricated trade.
  Label model-derived entry/invalidation/target levels; they are not guaranteed
  fills or independently validated trade economics.
- Money building carries the ticker rollup, premium concentration, repeated
  activity, call/put skew and the available evidence source. Do not present an
  unadjusted client comparison as a market-adjusted server reading.
- Changed since you looked re-arms per return visit and reports the last check.
  An empty update is a valid result, not a reason to recycle an old alert as new.
- Dealers prints the focused ticker and uses its available regime and map.
  The card, map and drill-down share one fetch/state path; it must work without
  first visiting a now-removed page tab.
- Every card carries appropriate source age, market-closed, fallback, limited
  coverage, stale, loading or missing-data wording. Do not retain the mockup's
  LIVE label over stale or unavailable observations.

### Screens, filters and settings

- Preserve the named screens and existing supported rule types. The builder
  supports conditions and AND/OR groups plus save, rename, duplicate and delete.
  Built-ins are copied before edits; this UI work does not add new scoring rules.
- Preserve type, minimum volume/score, ticker search, expiry range, universe
  membership, alert score, existing sort presets, poll interval and force refresh.
  Show active filters as removable chips and clear reset behaviour.
- Preserve notifications and their existing scope, tape order, copy, clear,
  acknowledged history and data export behind the v3 controls. Respect existing
  permissions and never increase market-data quotas through a UI convenience.
- Store screens, section order, per-mode columns and mode through the existing
  settings conventions. Guard failed storage writes and keep the displayed
  saved state honest. Do not require a frozen parent-file change merely to add
  an in-page settings entry.

### Vector and Pulse interaction

- A pinned trade is one record, not a duplicated table row. Context-only alerts
  carry their reason and Drill action without invented direction or levels.
- Keep row order stable while the pointer or keyboard selection is active;
  expose incoming changes without moving the action target under the user.
- Drill selects the actual row ticker/contract. Watch uses the existing universe
  behaviour. Ack hides acknowledged items with a history view. Plan creates an
  editable local planning/journal entry only; it cannot call an execution route.
- Implement the shown keyboard actions with visible focus, including ticker
  search, row navigation, activation, refresh and escape. Skip page shortcuts
  while the user is typing in a field. Every action must work without hover.
- Keep displayed percentages in their original units. Safely decode structured
  alert context, and use consistent filtering/time scope for polling and pushed
  updates. Verify these against current code before deciding an old issue is
  still present; repair only confirmed defects that block this redesign.

## 4. Layout, accessibility and data honesty

- Trade prioritizes answers and decisions; Monitor is denser and reveals the
  drill-down on request; Research gives more room to evidence and dealer detail.
  Switching mode changes emphasis without cloning the whole page or losing
  selection, screen settings or queued edits.
- Use the latest preview's dark surfaces, muted text, accent and table treatment.
  Colours are secondary to direction words, signs and patterns. Maintain
  readable button text, chart labels, focus outlines and filter states.
- At narrow widths, wrap controls and facts, collapse navigation sensibly and
  allow deliberate table/chart scrolling. Do not hide the selected ticker or
  force the entire page to overflow to preserve a desktop composition.
- Reuse the current allowed data sources and polling/coordinator paths. No
  invented live coverage, duplicate scans triggered by selection, or hidden
  placeholder calculations. Confirm route availability before wiring a view.
- Preserve dealer display-scale units, actual expiry scope and observation time.
  A chart setting for a measure with no validated source stays unavailable.
  Missing observations are not zeros; keep gaps and errors visible.
- Trust values use the backend's actual bands and denominator. Show sample size
  and grey out inadequate samples rather than implying proven performance.
- Retain existing useful facts when moving controls: refresh/source/counts in
  Board, rollups in answer cells, alert history in Vector, contract facts in
  Pulse, dealer context in Lattice and drill-down, calibration in Trust, and
  preferences in Settings. Unreachable Academy and volatility-surface mock pages
  remain outside this redesign; unavailable order-flow measures stay honest.

## 5. Required dealer drill-down

- Heading: `Drill-down` and the selected ticker, visibly updated together.
- Three facts: market regime (including warming state), gamma flip with its
  distance from spot, and volatility environment.
- Upper chart: net dealer gamma per strike, with red short-gamma bars and green
  long-gamma bars. Heights show absolute magnitude; signs and labels retain
  direction even without colour. Add stripes to short bars in colour-blind mode.
- Lower chart: cumulative signed gamma over the same ascending strike sequence.
  Bars, curve points and strike labels must share one numeric horizontal scale.
- Gamma-flip marker at the actual flip price on that scale. Interpolate between
  strikes when necessary; do not use a fixed percentage or put the marker at
  the cumulative zero crossing. If the flip is outside the plotted range,
  state that in text instead of drawing it at an unrelated strike.
- A zero guide for the cumulative curve and concise short/long-gamma explanation.
- Match the latest mockup's dark panel, rounded border, spacing and muted text.
  Keep labels readable, wrap the facts on narrow screens, and allow the chart
  itself to scroll horizontally if its labels would otherwise become unreadable.

### 5.1 Selection and navigation

- Ticker buttons in both Vector and Pulse, plus Vector's Drill actions, open
  the panel for that row's ticker. The Dealers card opens the current dealer
  focus. Other card destinations retain their existing purpose.
- On the live app, reuse the existing `focusTicker` / `doDrill` selection path.
  The header, dealer map, facts and chart must refer to the same ticker, expiry
  selection and refresh result. Clear or visibly mark old data while changing
  tickers; an old request must never overwrite a later selection.
- The mockup has one dealer dataset: NVDA. Other tickers must show their own
  heading and an explicit unavailable preview state, with a way back to NVDA.
  Never relabel the NVDA chart as another ticker's data.
- Drill actions in Monitor mode reveal the panel by switching to Trade mode.
  Research mode retains it. Keyboard activation must work without hover, and
  opening the panel moves focus to its heading container.
- Keep layout, screen and colour-blind buttons working. Their handlers must
  match the actual buttons, not the root element's matching data attributes.

### 5.2 Data and calculation contract for the live build

| Display | Existing source / rule |
| --- | --- |
| Ticker | Current `focusTicker`; selected row passes its own ticker through `doDrill` |
| Regime and warming | Existing dealer regime result: `current_state`, `is_warming`, `confidence` where supplied |
| Flip and distance | `gamma_flip`, `dist_to_flip_pct`, with spot used to make above/below wording explicit |
| Volatility environment | `vol_env`; unavailable text when missing |
| Strike bars | Existing dealer heatmap `grid.grid`, `grid.expiries`, `grid.strikes`; sum the displayed expiry cells for each displayed strike |
| Cumulative line | Running signed sum of those same bar values, ordered by ascending numeric strike |
| Chart units | Same display-scale gamma as the dealer map; never combine it with model-feature gamma history |

Use the existing dealer fetch/state paths in
`frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` and scoped styles in
`frontend/src/components/flowseeker/FlowseekerProBlademap.css`. The current component
already derives `lattice.net` / `lattice.cumArr` and renders horizontal gamma rows.
Adapt that area to the requested vertical bars and cumulative line without
duplicating the fetch or adding a second, inconsistent set of totals.

Scale bar heights using the largest absolute per-strike sum, not the largest
individual expiry cell. Preserve zero values, support mixed/all-positive/all-negative
series, and handle one strike or all-zero data without invalid coordinates.
Missing data is not a zero measurement. Show loading, empty, error and stale
states explicitly; validate finite strike/value inputs before plotting.

The mockup uses invented numbers already present in its visible dealer map.
Its curve is calculated from that map rather than copied from the screenshot.
For its example, the $176 flip is below the $178.40 spot; label the reference
point explicitly so the wording cannot imply that spot is below the flip.
The displayed distance is phrased as `Spot 1.4% above flip`. The map's `Shown
gamma` chip uses the same visible-strike/expiry sum as the curve's final value,
which is distinct from a full-universe dealer regime reading.
The screenshot is a visual reference, not a source of live market values.

## 6. Connection to the AI implementation plan

The UI owns the dashboard and drill-down rendering, calculations, controls and
acceptance above. The AI plan owns research, conversation state and answer
handling. Share selection; do not build a second assistant or duplicate its
market-data acquisition in this redesign.

Publish the exact ticker, selected row/contract, expiry scope, view and displayed
observation time through the agreed screen-context path. The AI freezes that
context when Ask is pressed. A later ticker change updates the UI selection
without relabelling an in-flight or saved answer. Coordinate ownership of the
dashboard publisher and shared shell changes before implementation.

The AI plan retains the dealer drill-down as a required integration dependency,
with this document as the single source for its detailed UI requirements.

## 7. Implementation sequence and completion evidence

| Step | Work | Evidence required to close |
| --- | --- | --- |
| Confirm the working baseline | Read the current component, styles, settings, screen state, tests and provider contracts; respect concurrent edits and frozen files. Identify what already exists and what is only in the preview. | A current control/source inventory and confirmed baseline failures, without speculative fixes. |
| Build the v3 page structure | Implement sidebar anchors, Board, four answers, Vector, Pulse, Lattice, Trust and Settings using the existing component boundaries. | The real page matches the v3 ordering and density, with no lost reachable controls or restored page tabs. |
| Connect answers and controls | Wire active screens, filters/rules, sorting, row actions, saved preferences, source states and supported keyboard flows. | One screen change updates all relevant content consistently; save/reload and action results work; planning cannot submit orders. |
| Deliver dealer detail | Retain the map, add the section 5 drill-down, connect selection and derive plots from the same displayed data. | Fixed expected chart values, correct flip position, honest missing states and no stale ticker overwrite. |
| Connect shared screen context | Integrate the existing AI selection/conversation entry without duplicating it. | A question uses the visible ticker/contract/expiry/time, and changing the chart cannot relabel the answer. |
| Verify the live redesign | Exercise layouts, keyboard, colour-blind mode, narrow screens, data degradation and existing frontend behaviour. | Focused checks plus required frontend tests/build pass, followed by rendered comparison with the included preview. Record existing unrelated failures accurately. |

Implementation should use the existing
`frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` and its scoped CSS,
the existing screen/selection helpers and the existing settings entry where
appropriate. Keep new helpers small and responsibility-based. Do not copy the
entire standalone HTML into the production component or add a new chart package
without first establishing that existing capabilities cannot meet the need.

## 8. Delivery checklist

- [x] Add the panel to the latest standalone mockup below the dealer map.
- [x] Include regime, flip, volatility, strike bars, cumulative line and legend.
- [x] Connect ticker/Drill buttons and provide an honest unavailable-ticker state.
- [x] Record this required panel in the redesign build plan.
- [x] Consolidate the complete v3 UI scope, build notes and preview reference
  into this one UI implementation plan.
- [x] Verify the current app baseline and retained-control inventory.
- [x] Implement the full v3 page structure and four answer cells.
- [x] Complete active screens, filters/rules, Vector/Pulse actions and settings.
- [x] Implement the panel in the live component, reusing existing dealer state.
- [x] Cover live loading/error/stale/empty states and rapid ticker changes.
- [x] Verify chart maths with fixed expected values, including the displayed
  expiry scope, negative sums, single strike, all-zero data and out-of-range flip.
- [x] Verify keyboard selection, focus, Monitor/Trade/Research, colour-blind
  mode and narrow-screen readability in the live app.
- [x] Verify the shared AI screen-context handoff without stale answer relabelling.
- [x] Run the focused frontend checks and build; visually compare the live panel
  and full dashboard with the supplied reference and updated mockup before
  marking the redesign complete.

Checks above combine mounted behavior tests and actual rendered browser inspection;
they do not claim every possible permission response or market state was observed
live. Current Public data with unknown observation times remains visibly limited.

## 9. Historical mockup verification and limits

- 2026-09-11: Node syntax check and a JSDOM execution of the complete HTML passed
  with no script errors or duplicate element IDs.
- Fixed expected values checked all 12 per-strike sums and running totals; the
  final visible-scope cumulative value is +$56,000. The $176 marker is correctly
  40% of the distance between the $175 and $177.5 positions.
- Checked row-ticker and Drill actions, unavailable SPY preview and return to
  NVDA, focus movement, Monitor-to-Trade reveal, Research mode, screen reranking,
  Dealers-card navigation, and colour-blind pattern on/off.
- A browser-rendered visual check was not performed: browser control rejected
  this local-file URL earlier in the session. These checks establish document
  structure, calculations and interaction state, not screenshot equivalence.
- At the original mockup-only review, live implementation remained unchecked
  and production source was unchanged. The later implementation update above
  supersedes that historical status without changing these mockup-only claims.
