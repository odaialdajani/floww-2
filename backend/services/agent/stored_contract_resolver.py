"""I05 (C10 deliverable): stored range-record binding for the Lodestar draft.

A plan draft on a range-replay selection must name the EXACT stored record it
is grounded in — verified via the owning resolver, never by trusting the
client echo. This module binds store::identity::digest::query::metric::status
to the draft's context and returns the refusal-first binding result; the draft
builder does NOT become executable (RANGE_CONTRACT_UNAVAILABLE stands by
commissioning policy).

Producer fixtures only; no live chain queries (never replay history).
"""
from __future__ import annotations

from services.agent.range_replay import compute_content_digest, record_id_for_digest

# I05 refusal reasons (draft binding only; the record itself was already
# admitted by the owning replay resolver upstream of this seam).
_BIND_REFUSALS = (
    "RANGE_RECORD_REFUSAL",
    "RANGE_IDENTITY_MISMATCH",
    "RANGE_DIGEST_TAMPER",
    "RANGE_CONTRACT_UNSUPPORTED",
)


def bind_stored_range_contract(ctx: dict) -> dict:
    """Bind ctx's claimed range selection to a stored range record.

    Contract: ctx carries ``rangeRecordId`` (the claiming record), the
    claimed ``rangeMetric``, and ``stored_envelope`` — the actual stored
    payload the UI fetched. Returns a binding dict even when record/digest
    are absent (unresolved observation is a valid answer), but the binding
    only VALIDATES the draft's claimed identity against the stored record
    when evidence is present; conflicting claims falsify the binding.

    The draft remains review_only/executable=False regardless: this seam
    supplies grounded EVIDENCE, never trading authority.
    """
    rid = ctx.get("rangeRecordId")
    metric = ctx.get("rangeMetric")
    claimed_digest = ctx.get("rangeDigest")
    env = ctx.get("stored_envelope")

    base = {
        "record_id": None,
        "content_digest": None,
        "metric": metric,
        "query_identity": None,
        "verified": False,
        "grounded": False,
        "blocker": "RANGE_CONTRACT_UNAVAILABLE",
    }

    # A claiming ID with no stored envelope is an unresolved reference;
    # a claiming ID whose stored envelope's identity/digest disagrees is
    # tamper evidence — both fail closed, never admit.
    if rid and env is None:
        return {**base, "reason": "RANGE_STORE_UNAVAILABLE"}
    if rid and env is not None:
        env_rid = env.get("record_id") if isinstance(env, dict) else None
        env_digest = env.get("content_digest") if isinstance(env, dict) else None
        genuine = (isinstance(env, dict)
                   and isinstance(env_digest, str) and env_digest
                   and compute_content_digest(env) == env_digest
                   and isinstance(rid, str) and rid and env_rid == rid
                   and (claimed_digest is None or claimed_digest == env_digest))
        if not isinstance(env, dict) or env.get("status") == "refused":
            return {**base, "reason": ctx.get("refusal_reason") or "RANGE_RECORD_REFUSAL"}
        if isinstance(env, dict) and env.get("grounding", {}).get("resolver") != "range-resolver.v1":
            return {**base, "reason": "RANGE_CONTRACT_UNSUPPORTED"}
        if isinstance(env, dict) and env.get("grounding", {}).get("contract_drafting", {}).get("admitted") is False:
            # Producer says reference-only: the binding is valid AS EVIDENCE
            # but the drafting capability is explicitly REFUSED at producer
            # level — surface that blocker, never admit.
            base["blocker"] = "RANGE_RECORD_REFERENCE_ONLY"
        if genuine:
            # Bind the OWNING query identity (symbol + window + asof) from the
            # producer's grounding block, not the bare query — identity completeness
            # is its whole point (RANGE_IDENTITY_MISMATCH on any divergence).
            qid = (env.get("grounding") or {}).get("record_query_identity")
            return {
                **base,
                "record_id": rid,
                "content_digest": env_digest,
                "query_identity": dict(qid) if isinstance(qid, dict) else None,
                "verified": True,
                "grounded": True,
            }
        digest_mismatch = bool(env_digest and claimed_digest
                                and claimed_digest != env_digest)
        id_mismatch = bool(env_rid and rid and env_rid != rid)
        return {**base,
                "reason": "RANGE_DIGEST_TAMPER" if digest_mismatch
                          else ("RANGE_IDENTITY_MISMATCH" if id_mismatch
                                else "RANGE_RECORD_REFUSAL"),
                "expected_digest": env_digest, "claimed_digest": claimed_digest,
                "expected_record_id": env_rid, "claimed_record_id": rid}

    # No stored reference at all — unresolved observation; the draft's
    # RANGE_CONTRACT_UNAVAILABLE blocker stays by policy.
    return {**base, "reason": "RANGE_RECORD_REQUIRED"}
