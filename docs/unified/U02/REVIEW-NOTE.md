# U02 — Review: parent range null-date compatibility patch

Owner: OpenCode (review of parent implementation). Reviewer: Cline.
Baseline `8194eca4`. Parent files reviewed at candidate hashes in `EVIDENCE.json`.
No reimplementation; this dossier is the review record.

## Patch under review

`frontend/src/lib/rangeAnalytics.js` (`admitRangeEnvelope` clocks guard):

- Before: `!Array.isArray(clocks.oi_effective_dates) || ...some(!date)` —
  explicit producer `null` refused `RANGE_CLOCKS_UNAVAILABLE`.
- After: `(clocks.oi_effective_dates !== null && (!Array.isArray(...) || ...))` —
  explicit `null` admitted; `undefined`/missing still refuses (fails `!== null`
  then `!Array.isArray(undefined)` → refuse); non-array non-null (string,
  object, number) refuses; arrays containing a non-date refuse.
- `[]` (empty array) admits and renders `unknown`; classified as explicit
  empty, not malformed. No measured cell, coverage flag, digest, identity or
  synthetic label is touched by this guard.

`frontend/src/components/heatseeker/RangeAnalyticsWorkspace.jsx`:
`(envelope.clocks.oi_effective_dates || []).join(', ') || 'unknown'` —
null-safe display, unknown stays unknown, never zero-filled.

## Counterexample verification (current source, not borrowed)

New regression pins (parent-authored, independently executed here):

- `explicitly unknown vendor OI dates remain unknown without rejecting a valid
  range`: null admitted, `reason` null, envelope identity preserved, field
  stays null (not normalized away).
- `missing OI dates declaration` (key deleted) → `RANGE_CLOCKS_UNAVAILABLE`.
- `malformed OI date` (`['unknown']`) → `RANGE_CLOCKS_UNAVAILABLE`.
- Workspace: null-date payload loads the `Raw OI GEX` grid intact and shows
  `OI effective dates: unknown`.

Guard read confirms string/object/non-null primitives refuse by the same
`!== null && !Array.isArray` clause. Producer shape, measured cells and
`reference-only trade refusal` unchanged (full suite green, no other
rangeAnalytics test altered).

## Receipts

Focused suites: `rangeAnalytics` + `RangeAnalyticsWorkspace` green within the
238/238 run (`craco test --testPathPattern="(rangeAnalytics|
RangeAnalyticsWorkspace|RecordedPriceChart|SkylitDashboard)"`, exit 0).
Command, hashes and file SHAs in `EVIDENCE.json`.

## Verdict (OpenCode → Cline)

REVIEW_ACCEPT_SUBJECT_TO_PEER: patch is narrow, null-safe, refusal-preserving,
and pinned. Cline: confirm against the sealed snapshot; U02 acceptance needs
your independent verdict bound to baseline + snapshot.
