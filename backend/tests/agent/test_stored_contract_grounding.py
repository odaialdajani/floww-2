"""I05: stored contract grounding on the Lodestar plan draft.

The draft must bind the EXACT stored record (id + digest + query identity)
via the owning resolver — a claimed record that is absent, foreign, or whose
digest disagrees with the stored content fails closed; a resolver that
refuses remains contractNone/review_only/executable=False by policy.
"""
import sys

sys.path.insert(0, "backend")

import json
from pathlib import Path

from services.agent.plan_draft import build_plan_draft
from services.agent.stored_contract_resolver import bind_stored_range_contract

_FIXTURES = Path(__file__).resolve().parents[3] / "docs/solstice/r18/fixtures"

def _env(name="complete_v1.json"):
    return json.loads((_FIXTURES / name).read_text())

def _answer(extra_ctx=None, facts=None):
    ctx = {"ticker": "SPY", "snapshotId": "snap1", "displayMode": "range-replay",
           "rangeRecordId": _env()["record_id"],
           "rangeDigest": _env()["content_digest"],
           "rangeMetric": "raw_oi"}
    ctx.update(extra_ctx or {})
    return {"context": ctx, "facts": facts or [],
            "model_sections": []}

class TestStoredContractGrounding:
    def test_stored_record_binds_to_the_draft_verified(self):
        env = _env()
        out = build_plan_draft(_answer({"stored_envelope": env}), "t1")
        binding = out.get("range_record")
        assert binding is not None
        assert binding["verified"] is True
        assert binding["record_id"] == env["record_id"]
        assert binding["content_digest"] == env["content_digest"]
        assert binding["query_identity"]["symbol"] == "SPY"
        # Policy grounding stays non-executable
        assert out["status"] == "review_only"
        assert out["executable"] is False
        assert out["contract"] is None

    def test_tampered_digest_fails_closed_and_keeps_the_policy_blocker(self):
        env = _env()
        out = build_plan_draft(_answer({"stored_envelope": env,
                                        "rangeDigest": "0" * 64}), "t1")
        assert out["range_record"]["verified"] is False
        assert out["range_record"]["reason"] == "RANGE_DIGEST_TAMPER"
        assert out["contract"] is None

    def test_foreign_record_id_fails_closed(self):
        env = _env()
        out = build_plan_draft(_answer({"stored_envelope": env,
                                        "rangeRecordId": "rga1-foreign-record"}), "t1")
        assert out["range_record"]["verified"] is False
        assert out["range_record"]["reason"] == "RANGE_IDENTITY_MISMATCH"

    def test_missing_stored_store_refuses(self):
        out = build_plan_draft(_answer(), "t1")
        assert out["range_record"]["verified"] is False
        assert out["range_record"]["reason"] == "RANGE_STORE_UNAVAILABLE"
        assert out["contract"] is None
