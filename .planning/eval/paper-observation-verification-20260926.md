# Prepared paper account valuation - September 26, 2026

Status: independently reviewed, offline/isolated-store preparation. **Not an enabled paper account, trading action or release.** No provider/model calls or broker orders were made by these checks.

## Implemented and bounded

- Exact derived cash can be valued without reapplying raw-input precision limits. The regression reproduced a refusal for initial cash 1e24 minus a purchase of 1e-24; marking at the same independent price now returns exactly 1e24. Inexact arithmetic still refuses.
- Valuation keeps structures/lots, cost basis, cash, reservations, realized result and unrealized result separate. Missing/stale/future/crossed/identity-mismatched prices or missing contract details yield unknown total equity; a known subtotal is separately labelled. A verified zero mark neither expires nor removes holdings.
- Source mark watermarks reject clock rewinds and changed source identities. Held lots are explicitly bounded positive whole quantities; unsupported short/malformed lots and negative reservations refuse instead of netting away gross exposure.
- Explicit account mark settings, verified session/opening-equity inputs and exact owner/account/venue/recovery binding are required. First request time never becomes the session open. Sampled loss/peak values retain their provenance through unknown inputs and restart. Sampled peaks do not claim an unobserved session maximum.
- Mark, session-close and option-event validity deadlines expire saved readings. An unchanged source frame can still save a newly unknown time-dependent state; a truly unchanged frame consumes no event and never refreshes its timestamp.
- The new unmounted service is default-denied without an independent trusted evidence checker. It freezes inputs, saves the observation with its event atomically, preserves prepaid exit space and refuses a stale account version. Twelve simultaneous identical requests return one committed observation; a receipt/read race is handled by retrieving the winner's durable receipt.

## Verification

Python 3.11: 47 focused paper checks pass (18 valuation, 15 arithmetic, 14 execution). Ruff passes for the new modules and verification script. The real-store report [paper-observations-20260926-2324b.json](paper-observation-store-proof-20260926.json) passes 13 checks in a new isolated synthetic database, including concurrent duplicates, changed requests, fresh-process reopen/projection, fill-versus-observation conflict, detached checker inputs, session-close transition, old epoch refusal, and a close at full observation capacity using reserved exit space. Earlier failed evidence and test databases are retained; none is production data.

Independent review [observation-review.md](paper-observation-independent-review-20260926.md) reproduced four defects, then independently cleared each fix. Raw recheck evidence is [observation-fix-recheck.json](paper-observation-independent-recheck-20260926.json). Source hashes are in [source-manifest.json](paper-observation-source-manifest-20260926.json).

## Still required

This does not configure an owned real paper account, source verified production contract/mark/session inputs, choose risk capital or limits, implement proposal confirmation, or activate the service. Per-trade entry risk and full account risk policy still need the actual production composition. Observed drawdown is sampled only. External cash movements, dividends, splits and corporate actions need their own verified event handling. Option expiration/exercise/assignment/settlement and adjusted deliverables remain unimplemented; due or uncertain events retain holdings and make dependent values unknown. Multi-leg/short product support is not established. Production restore/reconciliation remains separately gated. Research acceptance, paper activation and live approval are unchanged.

Root preservation check23:39UTC: all six source/test files match the author final hashes. Independent root rerun of arithmetic, valuation and execution tests passed47tests and28subtests underPython3.11. The store report is copied with only its isolated database identifier removed and the original raw report hash retained. No activation or source-truth claim was added.
