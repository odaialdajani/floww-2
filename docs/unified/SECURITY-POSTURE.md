# Auth posture confirmation (2026-10-08, architect pass)

Question: now that dashboard GET families bypass the burst budget, is any
new unauthenticated surface exposed? Answer: no.

- `auth.verify_api_key` protects mutating methods only; GET reads were and
  remain unauthenticated by design (dashboard reads). The read-budget
  exemption changes burst accounting, never authorization.
- `POST /api/related/{ticker}/warm` additionally requires local session
  (`require_local`); warm handler never runs remote/foreign.
- Broker/admission paths keep both key auth and the burst budget.
- Verified by read of `auth.py` + route decorators at the merged composition.
