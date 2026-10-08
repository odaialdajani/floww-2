# C17 — explicit deferral with reason (OpenCode takeover, 2026-10-08)

C17 (optional P2) asks for a backend-admitted per-strike exposure series
or an explicit deferral. Recorded here as DEFERRED, for these exact reasons:

1. No qualified per-session share-volume store exists (U12 established:
   Related daily bars persist close-only; chain payloads carry per-contract
   option volume only). Any "measured" per-strike exposure built today
   would rest on unqualified inputs — the same invention the U12 repair
   removed.
2. The chain serves exactly one canonical gex + basis per row; no raw-vs-
   adjusted exposure pair exists server-side. Aggregating client-side is
   display derivation (T02 precedent: labeled not-a-metric), not an
   admitted metric.
3. Building a versioned envelope addition (schema + fixtures + producer +
   consumer + contract) without the owning producer role active would be
   invention under schedule pressure — precisely what the honesty rules
   forbid.

Revisit path: admit a per-session share-volume store (or multi-basis
exposure pair) producer-side then version the series with basis flags and
quarantine rules. Until then the overlay stays display-derived and labeled.
No code written for C17; nothing invented.
