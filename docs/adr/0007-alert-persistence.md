# ADR-0007 — Alert persistence policy (MongoDB-backed rules + history)

**Status:** Accepted
**Date:** 2026-09-05
**Context:** Alert rules and trigger history lived in process memory
(`_alert_rules`, `_alert_history` in `backend/server.py`) — every restart
wiped rule configuration and erased the quality-audit trail that
`/api/alert-quality` and the outcome ledger read from. Phase 6.3 promoted
this to a build item; the build is now in place.

---

## Decision

Alert state persists in the MongoDB `alerts` collection (database
`confluence_decoder`, same store as the rest of the app):

1. **Rules sync both directions at startup.** `_init_alert_collection()`
   creates `alerts_ticker_idx` (sparse) and `alerts_created_at_idx`,
   upserts in-memory defaults, then loads all `{active: True}` docs back
   into `_alert_rules` (`backend/server.py`, `_load_rules_from_mongo`).
   Mongo is the source of truth after boot; memory is a read cache.
2. **Trigger history is write-through.** Every fired alert inserts a
   document (`_record_trigger` path); nothing alert-related lives only
   in memory past the request that created it.
3. **Degradation is explicit, not silent.** If Mongo is unreachable, the
   engine keeps serving from memory and logs a warning once
   (`_init_alert_collection` failure path) — availability over durability,
   with the gap visible in logs rather than a 500.
4. **No YAML-driven alert loading exists.** `backend/alerts/definitions/`
   ships a reference file nothing imports; alert configuration flows
   exclusively through the Mongo collection + `/api/alerts/*` routes.
   (If YAML-driven rules are ever introduced, they MUST go through
   schema validation at load — currently out of scope because there is
   no loader to validate against.)

---

## Consequences

- Restarts preserve rules and history; `/api/alert-quality` and outcome
  joins read complete data instead of session-truncated windows.
- Operators edit rules via API (persisted); hand-editing Mongo docs with
  `active: true` is honored on next boot.
- Tests use in-memory Mongo fakes or skip persistence assertions — no test
  may require a live Mongo for alert paths.
