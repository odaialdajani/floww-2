"""Owner-selected ChatGPT research with durable call accounting.

OAuth usage does not provide a dollar invoice or a hard token ceiling. The
application limits admission and wall time, and never labels unknown cost zero.
Codex owns its transport; one app dispatch does not claim one upstream attempt.
"""

import asyncio
import contextlib
import copy
import hashlib
import re
import time
import uuid
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from services.agent.codex_bridge import CodexBridge
from services.agent.contracts import canonical, finite, relationship_text
from services.agent.explanations import compact_explanation_menu, explanation_menu
from services.agent.grounding import grounding_hash
from services.agent.model import ANSWER_TOOL, MAX_BODY_BYTES

DEFAULT_SETTINGS = {"model": "gpt-5.6-terra", "effort": "medium", "speed": "default"}
POLICY_VERSION = "chatgpt-research-2026-10-06-grounded-choices"


def allowed_relationships(facts):
    """A bounded menu of relations that already satisfy the publication rules."""
    ledger = {fact["id"]: fact for fact in facts}
    result = []
    comparable = [fact for fact in facts if fact.get("status") == "ok" and finite(fact.get("value"))]
    for fact in facts:
        candidates = [{"kind": kind, "fact_id": fact["id"]} for kind in ("fresh", "stale", "available", "event_date")]
        if fact.get("status") == "ok" and finite(fact.get("value")):
            candidates.extend(
                {"kind": kind, "fact_id": fact["id"], "other_fact_id": other["id"]}
                for other in comparable if other["id"] != fact["id"]
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


def relationship_choices(facts):
    return {f"r{index:02d}": relation for index, relation in enumerate(allowed_relationships(facts))}


def decode_relationship_choices(data, choices):
    if not isinstance(data, dict) or not isinstance(data.get("relationships", []), list):
        raise ValueError("Invalid relationship choices")
    decoded = []
    for item in data.get("relationships", []):
        if isinstance(item, str) and item in choices:
            decoded.append(dict(choices[item]))
        elif isinstance(item, dict):
            # Retain checked compatibility for existing adapter integrations.
            normalized = {key: value for key, value in item.items() if not (key == "other_fact_id" and value is None)}
            if normalized not in choices.values():
                raise ValueError("Unknown relationship choice")
            decoded.append(dict(normalized))
        else:
            raise ValueError("Unknown relationship choice")
    result = dict(data)
    result["relationships"] = decoded
    return result


def answer_schema(facts=None, relationships=None):
    """Restrict each request to supplied evidence and already checked relations.

    Keep the no-argument form for existing integrations. The publisher still
    validates every result; provider output restrictions never replace it.
    """
    schema = copy.deepcopy(ANSWER_TOOL["function"]["parameters"])
    schema["required"] = ["sections", "relationships", "explanations"]
    relation = schema["properties"]["relationships"]["items"]
    relation["required"] = ["kind", "fact_id", "other_fact_id"]
    relation["properties"]["other_fact_id"]["type"] = ["string", "null"]
    if facts is None:
        return schema
    ids = list(dict.fromkeys(f["id"] for f in facts))
    healthy = [f["id"] for f in facts if f.get("status") == "ok"]
    section = schema["properties"]["sections"]["items"]
    limited = copy.deepcopy(section)
    limited["properties"]["interpretation"]["enum"] = ["limited"]
    if ids:
        limited["properties"]["fact_ids"]["items"]["enum"] = ids
    choices = [limited]
    if healthy:
        full = copy.deepcopy(section)
        full["properties"]["fact_ids"]["items"]["enum"] = healthy
        full["properties"]["interpretation"]["enum"] = ["descriptive", "mixed"]
        choices.append(full)
    schema["properties"]["sections"]["items"] = {"anyOf": choices}
    relations = relationship_choices(facts) if relationships is None else relationships
    if relations:
        schema["properties"]["relationships"]["items"] = {"type": "string", "enum": list(relations)}
    else:
        schema["properties"]["relationships"]["maxItems"] = 0
    explanations = [item["id"] for item in explanation_menu(facts)]
    if explanations:
        schema["properties"]["explanations"]["items"]["enum"] = explanations
    else:
        schema["properties"]["explanations"]["maxItems"] = 0
    return schema


SOURCE_GAP_CHOICES = (
    (("unknown", "time"), "Source observation time is unknown."),
    (("stale",), "Some saved readings are out of date."),
    (("out of date",), "Some saved readings are out of date."),
    (("implied", "unavailable"), "A verified implied move needs a current price, matched option volatility readings and exact expiry time."),
    (("implied", "missing"), "Verified implied volatility readings are missing."),
    (("realized",), "Verified realized volatility needs coherent completed daily price history."),
    (("daily", "bar"), "Completed daily price history is missing or invalid."),
    (("chain",), "Saved option-chain coverage is missing or limited."),
    (("contract", "coverage"), "Saved contract coverage cannot establish a compatible comparison."),
    (("expiry",), "Exact expiry coverage or time could not be verified."),
    (("flow",), "A verified directional flow reading is unavailable."),
    (("alert",), "A verified directional alert reading is unavailable."),
    (("history",), "A compatible earlier saved observation is unavailable."),
    (("earlier",), "A compatible earlier saved observation is unavailable."),
    (("display",), "The exact displayed selection could not be fully verified."),
    (("map",), "Verified map readings for this selection are unavailable."),

)


def selection_context(facts, selection=None, source_gaps=None):
    """Send fixed gap descriptions and server-owned scope, never client values."""
    selection = selection if isinstance(selection, dict) else {}
    tickers = list(dict.fromkeys(f.get("ticker") for f in facts
                   if isinstance(f.get("ticker"), str) and re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", f["ticker"])))[:3]
    scopes = list(dict.fromkeys(f.get("horizon") for f in facts
                  if isinstance(f.get("horizon"), str) and re.fullmatch(r"[A-Za-z0-9:_-]{1,100}", f["horizon"])))[:12]
    safe = {"tickers": tickers, "scopes": scopes}
    names = {"Structure", "Flow", "Levels", "Vol", "Company", "What changed", "Confluence", "Verdict", "Invalidation", "Trade"}
    requested = selection.get("requested_sections", [])
    requested = requested if isinstance(requested, (list, tuple)) else []
    safe["requested_sections"] = [name for name in requested if isinstance(name, str) and name in names][:10]
    safe["recorded_selection"] = selection.get("recorded_selection") is True
    gaps = []
    source_gaps = source_gaps if isinstance(source_gaps, (list, tuple)) else []
    for gap in source_gaps[:32]:
        if not isinstance(gap, str):
            continue
        if gap in {"The question names a different ticker from the selected screen; screen contract was not reused",
                   "Expiry scope follows the question; the original chart selection is retained as context only"}:
            continue
        text = gap[:2000].lower()
        matched = [label for terms, label in SOURCE_GAP_CHOICES if all(term in text for term in terms)]
        if "quote" in text:
            if "do not establish" in text or "do not prove" in text or "aggressor" in text or "dealer intent" in text:
                matched.append("Recorded option quotes do not establish aggressor side, dealer intent or trade direction.")
            elif "stale" in text or "out of date" in text:
                matched.append("Recorded option quotes are out of date and do not establish current prices.")
            elif "unknown" in text and "time" in text:
                matched.append("The recorded option quote observation time is unknown.")
            elif re.search(r"\b(?:unavailable|missing|absent|failed)\b|not found|could not (?:load|read|fetch)", text):
                matched.append("Verified quotes for the exact option contract are unavailable.")
            else:
                matched.append("Recorded option quote completeness or timing needs checking.")
        gaps.extend(matched or ["Some required source data could not be verified."])
    return safe, list(dict.fromkeys(gaps))[:12]


class OAuthUsage:
    def __init__(self, collection, daily_limit=40):
        self.collection, self.daily_limit = collection, daily_limit

    async def reserve(self, owner, turn_id, settings, *, trace=None):
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
            trace=copy.deepcopy(trace),
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
    supports_selection_context = True

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
        self, question, facts, turn_id, *, owner, settings, allow_inspect=True, history_note=None, repair=False,
                context=None, source_gaps=None, selection=None
    ):
        started = time.monotonic()
        trace = dict(
            version="lodestar-trace.v1", correlation_id=turn_id, policy_version=POLICY_VERSION,
            requested=dict(settings), effective=None,
            context_hash=grounding_hash(context or {}, facts),
            evidence_ids=sorted({f["id"] for f in facts}),
            observation_ids=sorted({f["snapshot_id"] for f in facts if f.get("snapshot_id")}),
            status="not_dispatched", latency_ms=0, tokens=None, actual_cost=None,
        )
        info = dict(
            trace=trace,
            provider="ChatGPT login",
            accounting="subscription_usage",
            actual_cost=None,
            policy_version=POLICY_VERSION,
        )
        if not facts:
            trace.update(status="input_refused", latency_ms=round((time.monotonic() - started) * 1000))
            return dict(status="unavailable", reason="No recorded evidence is available for model interpretation", **info)
        safe_selection, safe_gaps = selection_context(facts, selection, source_gaps)
        relations = relationship_choices(facts)
        content = canonical(dict(
            question=question, facts=facts, history=history_note,
            selection=safe_selection, source_gaps=safe_gaps,
            allowed_relationships=relations,
            **compact_explanation_menu(facts),
        ))
        trace["input_hash"] = hashlib.sha256(content.encode()).hexdigest()
        output_schema = answer_schema(facts, relations)
        input_size = len(content.encode()) + len(canonical(output_schema).encode())
        if input_size > MAX_BODY_BYTES:
            trace.update(status="input_refused", latency_ms=round((time.monotonic() - started) * 1000))
            return dict(status="unavailable", reason="Evidence exceeds the bounded model input", **info)
        reservation = None
        try:
            await self.validate_settings(settings)
            async with asyncio.timeout(100):
                async with self.bridge_factory() as bridge:
                    # Verify the managed login before recording a possible dispatch.
                    available = await bridge.catalog()
                    if not any(
                        m["id"] == settings["model"]
                        and settings["effort"] in m["efforts"]
                        and settings["speed"] in m["speeds"]
                        for m in available
                    ):
                        raise ValueError("Selected AI settings are no longer available")
                    trace["status"] = "reserved_dispatch_unknown"
                    reservation = await self.spend.reserve(owner, turn_id, settings, trace=trace)
                    if not reservation:
                        trace["status"] = "admission_refused"
                        return dict(
                            status="cost_limited", reason="Daily AI call limit reached or request already used", **info
                        )
                    info["reservation_id"] = reservation[1]
                    data, usage, thread_id, model_turn_id = await bridge.answer(content, settings, output_schema)
                    data = decode_relationship_choices(data, relations)
                    if isinstance(data, dict) and isinstance(data.get("relationships"), list):
                        for relation in data["relationships"]:
                            if isinstance(relation, dict) and relation.get("other_fact_id", 1) is None:
                                del relation["other_fact_id"]
                    # answer() only returns after checking the provider's model,
                    # effort/speed and no-reroute/tool policy; failed work is not proof.
                    trace.update(effective=dict(settings), status="completed", tokens=usage,
                                 latency_ms=round((time.monotonic() - started) * 1000))
                    info.update(**settings, tokens=usage, generation_id=model_turn_id)
                    await self.spend.finish(
                        reservation,
                        status="completed",
                        tokens=usage,
                        thread_id=thread_id,
                        generation_id=model_turn_id,
                        completed_at=datetime.now(UTC),
                        trace=trace,
                    )
                    return dict(status="ok", name="research_answer", data=data, **info)
        except asyncio.CancelledError:
            # Admission remains counted; cancellation does not prove unused quota.
            trace["status"] = "cancelled_dispatch_unknown"
            raise
        except Exception:
            trace["status"] = "unavailable"
            return dict(status="unavailable", reason="ChatGPT interpretation unavailable; no automatic retry", **info)
        finally:
            trace["latency_ms"] = round((time.monotonic() - started) * 1000)
            if reservation:
                # The reservation already retains grounded/requested identity if
                # shutdown or storage failure prevents this terminal trace write.
                with contextlib.suppress(Exception):
                    await self.spend.finish(reservation, status=trace["status"], trace=trace)

    async def reconcile(self):
        # ChatGPT subscription usage has no dollar-cost lookup. Unknown work
        # remains durably counted; never repeat it or invent zero cost.
        return None
