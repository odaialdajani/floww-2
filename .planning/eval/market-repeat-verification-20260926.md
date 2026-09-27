# Full-market repeat history and daily-volume truth verification

Verified 2026-09-26. This cohort repairs observed defects in repeated scanner readings and the claims attached to cumulative daily volume. It does not activate paper/live execution or prove complete real-time options-flow coverage.

## Live provider pass before integration

The isolated read-only pass reached 8786/8786 catalog names.4350 returned usable snapshots;4436 did not. At completion only 27 names were within the 60-second freshness window. The pass took 8572.67 seconds of recorded active time. It resumed after one interruption at 1619 names, so it is not a continuous-pass proof and the 26186 HTTPrequest count is a lower bound. One 400 and one 429 response occurred; these do not establish the cause of every unavailable name. Zero order/model calls and zero blocked requests. All seven source identities remained unchanged through the pass and were checked again before applying the patch. The completed report is market-full-pass-20260926.json; its raw report hash is preserved there. This pass ran the old scanner. It cannot be used as live-provider proof of the new repeat-history implementation.

## Repairs and evidence

The previous global 20000-contract cache lost every prior reading across two 8786-name rotations with three contracts each. The replacement keeps an atomic, hashed per-name saved snapshot, up to 60 selected contracts/name and 20000 names, with 512 MiBlogical payload budget and explicit capacity/failure states. Two actual local-storage rotations now retain 26358/26358 eligible second-pass comparisons; fresh-process restart, ten-writer ordering, daily retirement, rewind, invalid volume, duplicate contract identity, source timing, corruption and failure checks pass. Disk work leaves asynchronous work responsive. Startup lock failures close temporary connections and use bounded retries; the two-second retry deadline is not a strict two-second wall-time guarantee.

Receipt-to-receipt volume changes remain distinct from trade arrival velocity. Velocity requires two coherent fresh source timestamps; absent timestamps stay unknown. Old quotes cannot sign newer or earlier trades incorrectly. Per-name contract caps and missing history are disclosed.

Daily cumulative volume times a quote remains an estimated dollar value. Public and alternate daily-volume rows cannot infer whole-day buying/selling, get a known-direction bonus, produce directional price levels, or count as directional wins. Provenance survives actual alert persistence/readback. An individual last-trade side stays separate from the day's total. Directional math tests now use explicitly synthetic signed-trade fixtures while negative daily-volume cases assert no direction.

Actual screen rendering shows~$200 k with an estimate tooltip and NO DIRECTION for a deliberately contaminated daily-volume fixture. Narrow screen selectors wrap;390 px and 1280 px pages have no horizontal page overflow. Tables retain their internal horizontal scrolling. Final screenshots were viewed; final browser proof is in the paired JSON. A temporary check-page text-encoding issue was corrected in that helper; product source text was already correct.

## Final checks

Python 3.11:246 related service checks,24 observation checks plus 6 subtests,40 direct consumer checks passed (310 checks total). Targeted Ruff and diff whitespace checks passed. Full frontend 98 suites 847 tests passed; subsequent text/CSS-only changes were checked by 100 focused tests, final successful production build and actual browser rendering. Existing deprecation/build-size notices remain. Full unrelated backend suite was not repeated.

An initial combined root/backend test invocation failed collection because both directories define a tests package. Separate normal invocations passed; no tests were removed. Independent review is market-repeat-history-review-20260926.md. Exact 17 source/test identities are in market-repeat-source-manifest-20260926.json. Original bytes and pre-integration hash proof remain under output/market-repeat-preparation.

## Remaining boundaries

No claim of every option/expiry, every trade, true executed premium, simultaneous freshness, or causal explanation for all 4436 unavailable names. No new patched live full-provider rotation was run. Existing app processes were not restarted. Broader research comparison, production paper admission, lifecycle and forward-validation gates remain owned by the main plan and are not completed by this cohort.
