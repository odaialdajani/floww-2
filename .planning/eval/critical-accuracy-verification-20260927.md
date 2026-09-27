# Critical accuracy corrections - 2026-09-27

## Delivered

- Modeled gamma regime requires the complete requested population's valid model inputs. A missing call IV/time cannot reverse the headline to the surviving put side. Incomplete inputs yield UNKNOWN, no modeled value and no zero-gamma roots; separate valid vendor exposure remains available. Vendor zero never overrides a positive modeled sign; true complete modeled cancellation stays zero. Status and wall context explain incomplete options data.
- Research selection is owned by its mounted supported view. Leaving the grid/Tidehunter clears its selection without allowing older cleanup to erase newer ownership. Unsupported Chain/Bars/etc. cannot submit an orphaned old ticker, expiry or map. Reentering a supported view restores asking; existing saved answers retain original context.
- Chain expiry, minimum OI, moneyness, maximum DTE and sorting operate on both public contract and merged row responses. Missing values stay unavailable; stale ticker rows and late replies are excluded. Changing ticker resets expiry, and near-spot shading uses the same response spot as filtering. ATM is explicitly within 1% of spot.

## Evidence

- Backend focused calculation suite: 44 passed; Ruff scoped check passed. Initial 14 regressions were failing before the fix. Independent eight-case arithmetic comparison and actual server display/quality helpers passed; no providers, orders or live stores were used. See critical-data-accuracy-review-20260927.md.
- Research context and missing-data presentation: 19 focused mounted checks passed, including actual AppShell/provider/grid -> chain -> grid behavior with mocked transports. Independent ownership/StrictMode/frozen-answer refutation passed. See screen-context-ownership-review-20260927.md. Original red reproduction is retained in critical-research-context-review-20260927.md.
- Chain: 34 mounted checks passed (24 new, 10 existing); original-source red proofs retained. Root separately reviewed filter/null/lifetime logic and identified two reproduced sibling failures (expiry retention and differing spot highlight), both corrected and tested. See critical-chain-selection-review-20260927.md and its proof JSON.
- Final full desktop suite: 104 suites / 901 tests passed, process exited 0. Final production build after the final chain source edit exited 0. No broad backend suite rerun: the isolated calculation path is the only backend production change in this set.
- Whitespace check passed. Private execution logs/receipts remain local under output. Independent browser rendering check is still in progress and is not claimed by this record.

## Remaining scope and limits

The user's current priority is substantive accuracy and existing behavior. No provider/model acceptance campaign, startup/shutdown work, backup experiment, live/paper activation or cosmetic work was added. Chain/Bars research is explicitly unavailable until it has its own supported context; saved grid/Tidehunter answers remain accessible. This set does not prove all incoming provider inputs or all research answers are correct.

Two older chart concerns still need a bounded decision-accuracy check: Bars substitutes GEX when the selected VEX/charm value is missing or zero; Profile may turn missing grid cells into zero-strength pockets. These are not claimed fixed in this commit. Current app processes were not restarted or deployed.
