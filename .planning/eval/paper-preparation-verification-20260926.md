# Paper preparation verification - 2026-09-26 22:39 UTC

## Current status

Prepared, unmounted, admission disabled by default. No provider/model calls or external paper/live orders in these checks. Local settings drafts do not create an account. User's configurable slippage decision is accepted; historical backtest economics remain unchanged.

## Proven bounded behavior

Python3.11.15:28 focused arithmetic/execution tests passed. Exact financial arithmetic refuses inexact derived results. Slippage off/price/cash is explicit, fees remain separate and cost is not doubled. Cash, fills and pending history commit atomically under account version and recovery epoch. Original request retries return the saved event; new request identities cannot apply an already-used source quote. Unfilled/no-op attempts do not constitute accepted operation receipts.

Real isolated Mongo:30 storage checks passed in paper-storage-20260926-2231-py311.json. Fresh-process read/reprojection, owner isolation, duplicate and competing commands, restore/version/epoch fences, reserved bytes/events, checkpoint races, frozen-copy restore, maximum-size records and escaped JSON checked. No Mongo process crash/power-loss test was performed.

Final-source real controller run:17 checks passed in paper-execution-20260926-2239.json. Human-confirmation fields were synthetic and the independent admission callback was explicitly test-only. Twelve identical fill requests produce one cash debit and one saved receipt. Two partial entries and two partial exits produce independently calculated final cash1067.40 and realized result67.40 from1000.00. Restart retains partial order/reservation/cash; immutable journal sums match balances. Frozen quotes survive input mutation during await. Competing entries cannot reserve the last cash twice. Saved monotonic time prevents consuming retired quote size again after a clock reversal.

## Reserved exit contract

Entry protects one retained close attempt per structure, at most8new quote rows and12event credits. Existing source quote rows retain consumed size until their maximum eligible age expires. No new entry/quote write may consume reserved exit slots. A close stage/fill uses already reserved events even at the valid pending+reserved cap. Working or terminal closes must be projected and archived before another attempt or replenishment. Remaining positions survive exhausted attempt budgets; new attempts require successful durable projection, safe archival, actual row/slot room and explicit replenishment. Unlimited exits during permanent storage failure are not claimed. Final holding removal retains terminal bookkeeping capacity until archive. No new risk/lifecycle source path is mounted.

## UI corrections

Independent review reproduced invalid slippage values and empty-account selection. Four failing mounted checks became green; current PaperSettings9checks pass. Hydration filters every stored draft, removes unknown fields/types and invalid enum choices without selecting defaults; save validates again. Empty/whitespace account identities cannot satisfy selection. Independent recheck closed both findings: six mounted probes and twelve existing settings tests pass. The complete frontend passes98suites/844tests and the production build succeeds at the final three UI hashes. Build still reports its existing large-bundle advisory; this is not a browser or paper-activation proof.

## Remaining scope and dependencies

Research acceptance and concrete proposals are not complete. Production owner-account creation/listing/settings, real human confirmation, verified contract semantics/eligibility, session risk/marks, expiry/exercise/assignment/deliverables/dividends/corporate actions, multi-leg/short shapes and linked claim outcome acceptance remain unfinished. No unsupported product is admitted by these new modules. Default admission denial remains essential. Existing research and live boundaries unchanged; separate live approval and future forward evidence still required.

## Evidence locations

Source hash manifest: paper-preparation-source-hashes-20260926.json. Independent foundation review: paper-foundation-review-20260926.md. Independent execution review: paper-execution-review-20260926.md. Settings review: paper-settings-review-20260926.md; latest corrections independently rerun and closed. Raw synthetic databases and restart capabilities remain local, not required source artifacts.
