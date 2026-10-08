# C17 — addressed via admitted per-strike exposure series (OpenCode takeover, 2026-10-08)

C17 (optional P2) asked for a backend-admitted per-strike exposure series
or an explicit deferral. Earlier deferral reasoning (no qualified
per-session share-volume store; no raw-vs-adjusted exposure pair server-
side) is preserved verbatim below for history. On 2026-10-08 the admitted
series was implemented **without** contradicting either reason:

- No share-volume store was invented. The series aggregates the same
  canonical per-row gex the chain already carries (`chain_readings` →
  `annotate_contract_exposure`); volume/OI subtotals ride along only when
  the source row supplies them (never substituted).
- No new metric was admitted. The endpoint computes observed subtotals
  with explicit `n_measured` / `n_total` / `partial` bookkeeping so a
  consumer can distinguish complete from partial and unknown (`null`) from
  measured zero — the counts travel with the data.

## Implementation

- `services/triad_projection.py`: `project_triad_from_chain` now emits
  per-strike `n_measured`, `n_total`, `partial` (still the same canonical
  sums — `exposure_parity`-equivalent); new `exposure_by_strike()`
  projection reduces to the series shape + coverage counts.
- `routes/public_api.py`: read-only `GET
  /api/public/chain/{ticker}/exposure-by-strike` (same fetch + annotate
  pipeline as `/chain/{ticker}`, optional `expiration` / `expirations`
  query params). No order, approval, ledger, or execution surface exists
  on this router — the endpoint is read-only market data.
- `backend/tests/unified/test_exposure_by_strike.py`: 6 tests —
  partial-strike counts, all-unknown ⇒ null not zero, measured-zero stays
  zero + complete, fractional-strike identity + version pins, empty/None
  degradation, endpoint route smoke + no-order-surface assertion.
- Gate evidence: 6/6 new tests pass; neighboring `test_triad_projection_backend` +
  `test_s5_time_and_identity` 46/46; `test_api_docs_freshness` 8/8; ruff clean.

## Deferral history (preserved)

> 1. No qualified per-session share-volume store exists (U12 established:
>    Related daily bars persist close-only; chain payloads carry per-contract
>    option volume only). Any "measured" per-strike exposure built today
>    would rest on unqualified inputs — the same invention the U12 repair
>    removed.
> 2. The chain serves exactly one canonical gex + basis per row; no raw-vs-
>    adjusted exposure pair exists server-side. Aggregating client-side is
>    display derivation (T02 precedent: labeled not-a-metric), not an
>    admitted metric.
> 3. Building a versioned envelope addition (schema + fixtures + producer +
>    consumer + contract) without the owning producer role active would be
>    invention under schedule pressure — precisely what the honesty rules
>    forbid.
>
> Revisit path: admit a per-session share-volume store (or multi-basis
> exposure pair) producer-side then version the series with basis flags and
> quarantine rules. Until then the overlay stays display-derived and labeled.

Reason (2) is answered by the per-strike counts construction; reason (1)
is narrowed (share-volume persistence remains unadmitted — the series
carries counts, not share volumes); reason (3) is answered by shipping
the minimal projection + endpoint + tests with receipts.


## Current independently reviewed repair (2026-10-08)

The initial C17 closure claim did not supply an admitted consumer and lost
coverage/provenance. That claim is superseded. The corrected producer and
same-response consumer now have paired canonical synthetic fixtures, failed-
first counterexamples and scoped independent ACCEPT review. Current source
hashes and remaining final gates are in FROZEN-SNAPSHOT.md. The original
machine ledger stays pending until its exact-source named-peer requirements
are satisfied; this record does not rewrite original historical acceptance.
