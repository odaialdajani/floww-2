"""A deterministic saved draft never turns research into execution permission."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from services.agent.display_map import display_facts
from services.agent.grounding import grounding_hash
from services.agent.plan_draft import build_plan_draft
from tests.agent.test_display_map import NOW
from tests.agent.test_exact_contract_admission import by_metric, record, screen


def answer(mode="live"):
    context = screen(displayMode=mode)
    facts, gaps = display_facts(record(), context, "SPY", NOW)
    return {"context": context, "facts": facts, "gaps": gaps, "model_sections": []}


def test_typed_draft_owns_recorded_exact_contract_and_never_invents_order_fields():
    saved = answer()
    before = deepcopy(saved)
    draft = build_plan_draft(saved, "saved-turn", now=NOW)
    assert draft["version"] == "trade-plan-draft.v1"
    assert draft["status"] == "review_only" and draft["executable"] is False
    assert draft["contract"]["osi"] == by_metric(saved["facts"])["Exact contract OSI"]["value"]
    assert draft["contract"]["strike"] == "100.0000000000000000001"
    assert draft["contract"]["snapshot_id"] == "snap1"
    assert draft["selection"]["wall_bounds"] == {"id": "w1", "low": 99, "high": 101}
    assert draft["context_hash"] == grounding_hash(saved["context"], saved["facts"])
    assert draft["quantity"] is draft["limit_price"] is draft["approval"] is None
    assert draft["execution_owner"] is draft["account_id"] is None
    assert "PREFLIGHT_REQUIRED" in draft["blockers"]
    assert "COMMISSIONING_POLICY_UNSET" in draft["blockers"]
    assert saved == before


@pytest.mark.parametrize("change", [
    {"selectedWall": "other-wall"}, {"selectedExpiry": "2026-09-25"},
    {"overlayMetric": "delta"}, {"selectedContract": {"osi": "other"}},
    {"displayMode": "replay"}, {"snapshotId": "newer-record"},
])
def test_material_selection_changes_cannot_reuse_a_draft_identity(change):
    saved = answer()
    first = build_plan_draft(saved, "saved-turn", now=NOW)
    saved["context"].update(change)
    second = build_plan_draft(saved, "saved-turn", now=NOW)
    assert first["draft_id"] != second["draft_id"]
    assert first["context_hash"] != second["context_hash"]
    assert second["approval"] is None


def test_client_or_model_numeric_fields_are_not_contract_quote_or_order_evidence():
    saved = answer()
    saved["facts"] = []
    saved["context"]["selectedContract"] = {"osi": "FAKE", "bid": 999, "quantity": 20}
    saved["model_sections"] = [{"text": "buy 20 contracts at 999", "fact_ids": ["invented"]}]
    draft = build_plan_draft(saved, "saved-turn", now=datetime.now(UTC))
    assert draft["contract"] is None
    assert draft["rationale"] == []
    assert "EXACT_CONTRACT_REQUIRED" in draft["blockers"]
    assert draft["quantity"] is draft["limit_price"] is None


def test_replay_remains_research_and_requires_new_current_evidence():
    draft = build_plan_draft(answer("replay"), "saved-turn", now=NOW)
    assert "REPLAY_NOT_EXECUTABLE" in draft["blockers"]
    assert draft["executable"] is False
    assert draft["contract"]["bid"] == 0
    assert draft["contract"]["ask"] == 1
    assert draft["contract"]["quote_usage"] == "recorded_research_only"
