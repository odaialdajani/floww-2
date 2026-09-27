# PR50 wall integration verification

Verified 2026-09-27. This integrates the useful final PR50 styling commit (857e2067) into the existing reconciled branch; its earlier PR49 work had already been ported. The PR remains open, and no merge to remote main or deployment is claimed.

## Delivered behavior

The selected-wall comparison keeps basis and incomplete coverage visible beside its figures. Session volume distinguishes reported zero from missing/invalid input, independently of open interest and delta. Wall calculations reject boolean numeric stand-ins and retain unavailable values on overflow. VEX gross comes from absolute contract contributions before cancellation, while net remains signed. Its contract gross, coverage metadata and wall figures survive an actual saved-snapshot close/reopen. Old snapshots without those fields remain unavailable.

The mounted selected-wall component receives the current display VEX surface separately from the other metric grids. Duplicate member strikes cannot count twice; malformed counts/cells cannot prove measured zero. Partial member coverage is visible. Per-expiry text is grouped, review controls match the dark panel, and the candidate shortlist uses its own layout rather than five clipped comparison columns. Strongest-wall price remains on one line with its aggregate below.

## Evidence

- Root focused backend run: 40 passed; after import-only cleanup of the new test, its 23 cases passed again. Ruff passes all four changed backend/test files. Independent review includes fourteen boolean probes and actual DuckDB close/read-only reopen with gross 731.25 and net zero preserved.
- Full frontend run: 100 suites, 873 tests passed, exit0 before the final CSS/class adjustment. Independent final focused review runs 71 existing/focused plus18 adversarial checks, all89 passing. Existing asynchronous test warnings remain recorded; no failing assertion is hidden.
- Final isolated production build succeeds. Browser loads actual main.8c1a4ff0.js and main.0166caf6.css; no injected layout styles are used in final captures.
- Actual compiled app is driven through its polling response and real cell selection using labeled synthetic display values. At1600 and1280 desktop widths, document width equals viewport, the 199px candidate table has199px scroll width and all183px detail cells retain183px scroll width. The price changes from33px height to16.5px, and all candidate fields are visible. Root and independent reviewer viewed the final centered candidate and summary screenshots.
- Exact source/artifact hashes, raw result paths and limits are in pr50-wall-integration-proof-20260927.json. Independent reports: pr50-wall-backend-review-20260927.md and pr50-wall-frontend-review-20260927.md.

## Boundaries

Browser data is synthetic and ancillary requests intentionally return503; external Google Fonts is blocked. This verifies the wall layout and binding, not provider operation, every font, or frozen AI acceptance. The existing floating Ask button can cover lower content at some scroll positions; ordinary center scrolling exposes the full candidate. General placement improvement remains open. Mobile work stays paused. No existing app/server was restarted, no real model/provider/order request was sent, and paper activation remains unapproved/unconfigured.

The full AI/UI objective remains incomplete. The older comparison critical-source receipt is intentionally stale after these source changes; refresh it only against the intended stable source before an approved acceptance run. Broader research, proposals, paper composition, private briefs/watches, forward evidence, later-fill reconciliation and remaining production/test obligations are retained in REMAINING_WORK.md.
