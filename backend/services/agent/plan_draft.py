"""A versioned, evidence-bound research draft. Never a broker intent or approval."""

import copy
import hashlib
from datetime import UTC, datetime
from typing import Literal, TypedDict

from services.agent.contracts import INTERPRETATIONS, canonical, instant
from services.agent.grounding import grounding_hash


class TradePlanDraft(TypedDict):
    version: Literal["trade-plan-draft.v1"]
    draft_id: str
    correlation_id: str
    created_at: str
    context_hash: str
    status: Literal["review_only"]
    executable: Literal[False]
    selection: dict
    contract: dict | None
    evidence_ids: list[str]
    observation_ids: list[str]
    rationale: list[dict]
    blockers: list[str]
    quantity: None
    limit_price: None
    execution_owner: None
    account_id: None
    approval: None
    confirmation_evidence: None


def build_plan_draft(answer, turn_id, *, now=None) -> TradePlanDraft:
    context, facts = answer.get("context") or {}, answer.get("facts") or []
    snapshot_id, ticker = context.get("snapshotId"), context.get("ticker")
    recorded = [f for f in facts if f.get("snapshot_id") == snapshot_id and f.get("ticker") == ticker
                and f.get("metric", "").startswith("Exact contract ")]
    ledger = {f["metric"].removeprefix("Exact contract "): f for f in recorded}
    required = ("OSI", "strike", "expiry", "type", "owning snapshot")
    complete = (snapshot_id and all(ledger.get(k, {}).get("value") is not None for k in required)
                and len(ledger) == len(recorded)
                and ledger["owning snapshot"]["value"] == snapshot_id
                and ledger["expiry"]["value"] == context.get("selectedExpiry"))
    selector = context.get("selectedContract")
    if isinstance(selector, dict) and selector.get("osi") and complete:
        complete = selector["osi"] == ledger["OSI"]["value"]
    contract = None
    range_replay = context.get("displayMode") == "range-replay"
    if complete and not range_replay:
        contract = {k: ledger.get(label, {}).get("value") for k, label in (
            ("osi", "OSI"), ("strike", "strike"), ("expiry", "expiry"), ("type", "type"),
            ("snapshot_id", "owning snapshot"), ("multiplier", "multiplier"),
            ("multiplier_source", "multiplier source"), ("bid", "bid"), ("ask", "ask"),
        )}
        contract["quote_usage"] = "recorded_research_only"
        contract["quote_clocks"] = {side: ledger.get(side, {}).get("event_time") for side in ("bid", "ask")}
    evidence_ids = sorted({f["id"] for f in facts})
    rationale = [{"text": s["text"], "fact_ids": list(s["fact_ids"])}
                 for s in answer.get("model_sections", [])
                 if s.get("text") in INTERPRETATIONS.values() and s.get("fact_ids")
                 and set(s["fact_ids"]).issubset(evidence_ids)]
    blockers = ["PREFLIGHT_REQUIRED", "COMMISSIONING_POLICY_UNSET", "CONFIRMATION_EVIDENCE_REQUIRED",
                "EXECUTION_OWNER_UNSET", "ACCOUNT_UNSET", "AUTHENTICATED_INTENT_APPROVAL_REQUIRED"]
    if contract is None:
        blockers.insert(0, "EXACT_CONTRACT_REQUIRED")
    if range_replay:
        blockers.insert(0, "RANGE_CONTRACT_UNAVAILABLE")
    if context.get("displayMode") in {"replay", "range-replay"}:
        blockers.insert(0, "REPLAY_NOT_EXECUTABLE")
    draft: TradePlanDraft = dict(
        version="trade-plan-draft.v1", correlation_id=turn_id,
        created_at=instant(now or datetime.now(UTC)), context_hash=grounding_hash(context, facts),
        status="review_only", executable=False,
        selection=copy.deepcopy({k: context.get(k) for k in (
            "page", "ticker", "snapshotId", "selectedWall", "selectedStrike", "selectedExpiry",
            "metric", "overlayMetric", "activePane", "displayMode", "mapVersion",
            "observedAt", "sourceWorkspace", "sourceObservedAt",
            "rangeVersion", "rangeRecordId", "rangeDigest", "rangeMetric", "rangeBasis", "rangeStatus",
            "provider", "formula", "mapQuery", "mapStrikes", "mapExpiries",
        )}),
        contract=contract, evidence_ids=evidence_ids,
        observation_ids=sorted({f["snapshot_id"] for f in facts if f.get("snapshot_id")}),
        rationale=rationale, blockers=blockers, quantity=None, limit_price=None,
        execution_owner=None, account_id=None, approval=None, confirmation_evidence=None,
        draft_id="",
    )
    wall_id = ledger.get("selected wall id", {}).get("value")
    draft["selection"]["wall_bounds"] = (
        {"id": wall_id, "low": ledger["selected wall low"]["value"], "high": ledger["selected wall high"]["value"]}
        if wall_id and wall_id == context.get("selectedWall")
        and "selected wall low" in ledger and "selected wall high" in ledger else None
    )
    if context.get("selectedWall") and draft["selection"]["wall_bounds"] is None:
        draft["blockers"].append("WALL_BOUNDS_UNAVAILABLE")
    draft["draft_id"] = "draft_" + hashlib.sha256(canonical(draft).encode()).hexdigest()
    return draft
