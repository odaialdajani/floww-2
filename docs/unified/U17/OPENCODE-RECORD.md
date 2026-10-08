# U17 — visual/interaction record (OpenCode takeover, 2026-10-08)

Dependencies satisfied for review purposes: U01, U02, U04, U05, U09
(Cline ACCEPTs) + U06, U07, U08 (OpenCode ACCEPTs recorded in
`U060708/U060708-VERDICTS.md` during Cline-halted takeover).

## Live-candidate battery (served composition: baseline + parent work)

Re-run this pass against the running preview pair (`:3000`/`:8002`):

- Flow battery (`verify_unified.cjs`): **11/11** — labels, chart/options
  coexistence, neutral surface `rgb(17,17,17)`, clean markup, real PNG
  download, desk focus, Related pane, assistant dock, portal palette,
  Triad view, Tidehunter + saved activity, 8 destinations, phone
  viewport, zero errors, zero order POSTs.
- Interaction battery (`verify_u17prep.cjs`): **6/6** — keyboard Enter,
  14-control focus sequence, accessible names, 200% zoom containment,
  reload restore, zero errors/orders. Zero-fetch by design.
- Related/saved/history frontend: 15 suites / 130 green (unit level).

Same known 429s on ordinary GETs (pre-fix backend serving; redeploy is a
human decision, not taken).

## Formal freeze: NOT claimed

U17 acceptance requires ONE frozen baseline-plus-patch snapshot through
these checks. The served composition does not include Cline's uncommitted
backend slices (U12/U13/U10/U11) or my uncommitted lane additions, and
H-PUBLICATION forbids me from composing/publishing the merge. Freezing
needs the human merge decision; this record is the complete prep package
for that moment — nothing visual remains unexercised.
