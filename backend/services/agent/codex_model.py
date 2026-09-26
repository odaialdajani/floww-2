"""Owner-selected ChatGPT research with durable call accounting.

OAuth usage does not provide a dollar invoice or a hard token ceiling. The
application limits admission and wall time, and never labels unknown cost zero.
Codex owns its transport; one app dispatch does not claim one upstream attempt.
"""

import asyncio
import contextlib
import copy
import time
import uuid
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from services.agent.codex_bridge import CodexBridge
from services.agent.contracts import canonical, relationship_text
from services.agent.explanations import compact_explanation_menu
from services.agent.model import ANSWER_TOOL, MAX_BODY_BYTES

DEFAULT_SETTINGS = {"model": "gpt-5.6-terra", "effort": "medium", "speed": "default"}
POLICY_VERSION = "chatgpt-research-2026-09-26-compact-evidence"


def allowed_relationships(facts):
    """A bounded menu of relations that already satisfy the publication rules."""
    ledger = {fact["id"]: fact for fact in facts}
    result = []
    for fact in facts:
        candidates = [{"kind": kind, "fact_id": fact["id"]} for kind in ("fresh", "stale", "available", "event_date")]
        candidates.extend(
            {"kind": kind, "fact_id": fact["id"], "other_fact_id": other["id"]}
            for other in facts if other["id"] != fact["id"]
            for kind in ("above", "below", "rising", "falling")
        )
        for relation in candidates:
            try:
                relationship_text(relation, ledger)
            except (ValueError, TypeError, KeyError):
                continue
            result.append(relation)
            if len(result) == 64:
                return result
    return result


def answer_schema():
    schema = copy.deepcopy(ANSWER_TOOL["function"]["parameters"])
    schema["required"] = ["sections", "relationships", "explanations"]
    relation = schema["properties"]["relationships"]["items"]
    relation["required"] = ["kind", "fact_id", "other_fact_id"]
    relation["properties"]["other_fact_id"]["type"] = ["string", "null"]
    return schema


class OAuthUsage:
    def __init__(self, collection, daily_limit=40):
        self.collection, self.daily_limit = collection, daily_limit

    async def reserve(self, owner, turn_id, settings):
        day = datetime.now(UTC).date().isoformat()
        key = "day:" + day
        request_id = str(uuid.uuid4())
        # Global immutable turn identity, independent of day rollover. A crash
        # between this insert and dispatch cannot make the request replayable.
        try:
            await self.collection.insert_one(
                {
                    "_id": "turn:" + turn_id,
                    "owner": owner,
                    "request_id": request_id,
                    "day": day,
                    "reserved_at": datetime.now(UTC),
                }
            )
        except DuplicateKeyError:
            return None
        with contextlib.suppress(DuplicateKeyError):
            await self.collection.update_one({"_id": key}, {"$setOnInsert": {"calls": 0, "entries": {}}}, upsert=True)
        entry = dict(
            owner=owner,
            turn_id=turn_id,
            settings=settings,
            status="uncertain",
            reserved_at=datetime.now(UTC),
            actual_cost=None,
            accounting="subscription_usage",
        )
        result = await self.collection.find_one_and_update(
            {"_id": key, "calls": {"$lt": self.daily_limit}, f"turns.{turn_id}": {"$exists": False}},
            {"$inc": {"calls": 1}, "$set": {f"entries.{request_id}": entry, f"turns.{turn_id}": request_id}},
            return_document=ReturnDocument.AFTER,
        )
        return (key, request_id) if result else None

    async def finish(self, reservation, **result):
        key, request_id = reservation
        await self.collection.update_one(
            {"_id": key, f"entries.{request_id}": {"$exists": True}},
            {"$set": {f"entries.{request_id}.{k}": v for k, v in result.items()}},
        )

    async def state(self):
        row = await self.collection.find_one({"_id": "day:" + datetime.now(UTC).date().isoformat()})
        return dict(
            provider="ChatGPT login",
            calls=(row or {}).get("calls", 0),
            daily_limit=self.daily_limit,
            actual_cost=None,
            accounting="Subscription usage; dollar cost is not reported",
        )


class CodexModel:
    single_attempt = True

    def __init__(self, repository, collection, *, bridge_factory=CodexBridge):
        self.repository, self.spend = repository, OAuthUsage(collection)
        self.bridge_factory = bridge_factory
        self._catalog = None
        self._catalog_at = 0
        self._catalog_lock = asyncio.Lock()

    async def catalog(self):
        async with self._catalog_lock:
            if self._catalog is None or time.monotonic() - self._catalog_at > 300:
                async with asyncio.timeout(25):
                    async with self.bridge_factory() as bridge:
                        self._catalog = await bridge.catalog()
                        self._catalog_at = time.monotonic()
            return [dict(item) for item in self._catalog]

    async def validate_settings(self, value):
        if not isinstance(value, dict) or set(value) != {"model", "effort", "speed"}:
            raise ValueError("Choose a model, thinking depth, and speed")
        for model in await self.catalog():
            if (
                value["model"] == model["id"]
                and value["effort"] in model["efforts"]
                and value["speed"] in model["speeds"]
            ):
                return dict(value)
        raise ValueError("The selected AI settings are unavailable for this login")

    async def settings_for(self, owner):
        prefs = await self.repository.get_preferences(owner)
        # Saved choices were validated on write; recheck current availability
        # immediately before model work, without blocking factual research.
        return dict(prefs.get("ai_settings", DEFAULT_SETTINGS))

    async def once(
        self, question, facts, turn_id, *, owner, settings, allow_inspect=True, history_note=None, repair=False
    ):
        info = dict(
            model=settings["model"],
            effort=settings["effort"],
            speed=settings["speed"],
            provider="ChatGPT login",
            accounting="subscription_usage",
            actual_cost=None,
            policy_version=POLICY_VERSION,
        )
        content = canonical(dict(
            question=question, facts=facts, history=history_note,
            allowed_relationships=allowed_relationships(facts),
            **compact_explanation_menu(facts),
        ))
        if len(content.encode()) > MAX_BODY_BYTES:
            return dict(status="unavailable", reason="Evidence exceeds the bounded model input", **info)
        reservation = None
        try:
            await self.validate_settings(settings)
            async with asyncio.timeout(100):
                async with self.bridge_factory() as bridge:
                    # Verify the managed login before recording a possible dispatch.
                    available = await bridge.catalog()
                    if not any(m["id"] == settings["model"] for m in available):
                        raise ValueError("Model is no longer available")
                    reservation = await self.spend.reserve(owner, turn_id, settings)
                    if not reservation:
                        return dict(
                            status="cost_limited", reason="Daily AI call limit reached or request already used", **info
                        )
                    info["reservation_id"] = reservation[1]
                    data, usage, thread_id, model_turn_id = await bridge.answer(content, settings, answer_schema())
                    if isinstance(data, dict) and isinstance(data.get("relationships"), list):
                        for relation in data["relationships"]:
                            if isinstance(relation, dict) and relation.get("other_fact_id", 1) is None:
                                del relation["other_fact_id"]
                    info.update(tokens=usage, generation_id=model_turn_id)
                    await self.spend.finish(
                        reservation,
                        status="completed",
                        tokens=usage,
                        thread_id=thread_id,
                        generation_id=model_turn_id,
                        completed_at=datetime.now(UTC),
                    )
                    return dict(status="ok", name="research_answer", data=data, **info)
        except asyncio.CancelledError:
            # Admission remains counted; cancellation does not prove unused quota.
            raise
        except Exception:
            return dict(status="unavailable", reason="ChatGPT interpretation unavailable; no automatic retry", **info)

    async def reconcile(self):
        # ChatGPT subscription usage has no dollar-cost lookup. Unknown work
        # remains durably counted; never repeat it or invent zero cost.
        return None
