"""Awaited storage; final answer and its recovery seed commit in one document."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from services.agent.claims import claim_seed as rebuild_claim
from services.agent.claims import resolve_claim
from services.agent.contracts import canonical, instant

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def utcnow():
    return datetime.now(UTC)


def request_time(request_id, now=None):
    """A pruned expired identity can never create new paid work."""
    if not isinstance(request_id, str) or not re.fullmatch(r"\d{13}-[a-f0-9-]{36}", request_id):
        raise ValueError("A timestamped request identity is required")
    created = datetime.fromtimestamp(int(request_id[:13]) / 1000, UTC)
    age = ((now or utcnow()) - created).total_seconds()
    if age < -300 or age > 7 * 86400:
        raise ValueError("Request identity expired or has an invalid clock")
    return created


HISTORY_PAGE_FIELDS = ("turn_id", "ticker", "question", "horizon", "status", "created_at", "updated_at", "saved")
HISTORY_SEARCH_LIMIT = 64
HISTORY_DB_TIME_MS = 2000
MARKET_TIME_PATTERN = (r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T"
                       r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$")


def storage_utc(value):
    """Mongo's trusted BSON clocks are UTC, including its naive read form.

    This helper never interprets market observation timestamps.
    """
    if not isinstance(value, datetime):
        raise ValueError("Invalid saved-answer clock")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def history_cursor(created_at, turn_id):
    payload = {"v": 1, "created_at": storage_utc(created_at).isoformat(), "turn_id": turn_id}
    return base64.urlsafe_b64encode(canonical(payload).encode()).decode().rstrip("=")


def parse_history_cursor(value):
    error = "Invalid saved-answer cursor"
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(error)
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        payload = json.loads(decoded)
        if (not isinstance(payload, dict) or set(payload) != {"v", "created_at", "turn_id"}
                or type(payload["v"]) is not int or payload["v"] != 1
                or not isinstance(payload["turn_id"], str)
                or not re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", payload["turn_id"])
                or not isinstance(payload["created_at"], str)
                or instant(payload["created_at"]) != payload["created_at"]):
            raise ValueError(error)
        observed = datetime.fromisoformat(payload["created_at"])
        if history_cursor(observed, payload["turn_id"]) != value:
            raise ValueError(error)
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error):
        raise ValueError(error) from None
    return observed, payload["turn_id"]



def market_time_key(value):
    """Exact UTC seconds and microseconds; never BSON millisecond precision."""
    observed = instant(value)
    if observed is None:
        raise ValueError("Market source time is unknown")
    parsed = datetime.fromisoformat(observed)
    seconds = (parsed.toordinal() - 1) * 86400 + parsed.hour * 3600 + parsed.minute * 60 + parsed.second
    return seconds, parsed.microsecond


def market_time_stages(field, prefix):
    """Calendar-validated, timezone-aware comparison keys before sort and cap.

    All integer keys remain below 2**53, including year 9999. Keeping the
    fractional part separate retains every supported source microsecond.
    These temporary fields never alter the source fact or its identity.
    """
    def ref(name):
        return "$" + prefix + name

    def substring(start, length):
        return {"$substr": [field, start, length]}

    def number(start, length):
        return {"$toInt": substring(start, length)}

    leap = {"$and": [{"$eq": [{"$mod": [ref("year"), 4]}, 0]},
                     {"$or": [{"$ne": [{"$mod": [ref("year"), 100]}, 0]},
                              {"$eq": [{"$mod": [ref("year"), 400]}, 0]}]}]}
    maximum_day = {"$switch": {"branches": [
        {"case": {"$in": [ref("month"), [1, 3, 5, 7, 8, 10, 12]]}, "then": 31},
        {"case": {"$in": [ref("month"), [4, 6, 9, 11]]}, "then": 30}],
        "default": {"$cond": [leap, 29, 28]}}}
    year_days = {"$add": [{"$multiply": [ref("past_year"), 365]},
                           {"$floor": {"$divide": [ref("past_year"), 4]}},
                           {"$multiply": [-1, {"$floor": {"$divide": [ref("past_year"), 100]}}]},
                           {"$floor": {"$divide": [ref("past_year"), 400]}}]}
    day_count = {"$add": [year_days,
                          {"$arrayElemAt": [[0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334],
                                             {"$subtract": [ref("month"), 1]}]},
                          {"$subtract": [ref("day"), 1]},
                          {"$cond": [{"$and": [{"$gt": [ref("month"), 2]}, ref("leap")]}, 1, 0]}]}
    offset = {"$cond": [{"$eq": [ref("zone"), "Z"]}, 0,
                         {"$multiply": [{"$cond": [{"$eq": [{"$substr": [ref("zone"), 0, 1]}, "-"]}, -1, 1]},
                                        {"$add": [{"$multiply": [{"$toInt": {"$substr": [ref("zone"), 1, 2]}}, 60]},
                                                  {"$toInt": {"$substr": [ref("zone"), 4, 2]}}]}]}]}
    return [
        {"$addFields": {prefix + "year": number(0, 4), prefix + "month": number(5, 2), prefix + "day": number(8, 2),
                        prefix + "hour": number(11, 2), prefix + "minute": number(14, 2), prefix + "second": number(17, 2),
                        prefix + "clock": {"$arrayElemAt": [{"$split": [field, "T"]}, 1]}}},
        {"$addFields": {prefix + "plus": {"$split": [ref("clock"), "+"]},
                        prefix + "minus": {"$split": [ref("clock"), "-"]}, prefix + "leap": leap,
                        prefix + "past_year": {"$subtract": [ref("year"), 1]},
                        prefix + "calendar_ok": {"$and": [{"$gte": [ref("year"), 1]}, {"$lte": [ref("year"), 9999]},
                            {"$gte": [ref("month"), 1]}, {"$lte": [ref("month"), 12]},
                            {"$gte": [ref("day"), 1]}, {"$lte": [ref("day"), maximum_day]}]}}},
        {"$match": {prefix + "calendar_ok": True}},
        {"$addFields": {prefix + "zone": {"$cond": [{"$gt": [{"$size": ref("plus")}, 1]},
            {"$concat": ["+", {"$arrayElemAt": [ref("plus"), 1]}]},
            {"$cond": [{"$gt": [{"$size": ref("minus")}, 1]},
                {"$concat": ["-", {"$arrayElemAt": [ref("minus"), 1]}]}, "Z"]}]},
            prefix + "clean_clock": {"$arrayElemAt": [{"$split": [
                {"$arrayElemAt": [{"$split": [{"$arrayElemAt": [ref("plus"), 0]}, "-"]}, 0]}, "Z"]}, 0]}}},
        {"$addFields": {prefix + "offset": offset,
                        prefix + "microsecond": {"$toInt": {"$substr": [{"$concat": [
                            {"$ifNull": [{"$arrayElemAt": [{"$split": [ref("clean_clock"), "."]}, 1]}, ""]},
                            "000000"]}, 0, 6]}}}},
        {"$addFields": {prefix + "seconds": {"$subtract": [
            {"$add": [{"$multiply": [day_count, 86400]}, {"$multiply": [ref("hour"), 3600]},
                      {"$multiply": [ref("minute"), 60]}, ref("second")]}, {"$multiply": [ref("offset"), 60]}]}}},
        {"$match": {prefix + "seconds": {"$gte": 0, "$lte": 315537897599}}},
    ]


def market_bound(prefix, value, *, lower=False):
    seconds, microseconds = market_time_key(value)
    return {"$or": [{prefix + "seconds": {"$gt" if lower else "$lt": seconds}},
                    {prefix + "seconds": seconds, prefix + "microsecond": {"$gte" if lower else "$lt": microseconds}}]}


class AgentRepository:
    def __init__(self, database):
        self.turns = database["agent_turns"]
        self.sessions = database["agent_sessions"]
        self.preferences = database["agent_preferences"]
        self.claims = database["agent_claims"]
        self.claim_paths = database["agent_claim_paths"]
        self.snapshots = database["agent_structure_snapshots"]
        self.budgets = database["agent_budget_accounts"]
        self.collection_jobs = database["agent_collection_jobs"]
        self.handoffs = database["agent_native_handoffs"]

    async def initialize(self):
        await self.turns.create_index(
            [("owner", 1), ("request_id", 1)], unique=True, partialFilterExpression={"owner": {"$type": "string"}}
        )
        await self.turns.create_index("turn_id", unique=True)
        await self.turns.create_index([("owner", 1), ("created_at", -1)])
        await self.turns.create_index([("owner", 1), ("created_at", -1), ("turn_id", -1)])
        await self.sessions.create_index("capability_hash", unique=True)
        await self.sessions.create_index("expires_at", expireAfterSeconds=0)
        await self.preferences.create_index("owner", unique=True)
        await self.handoffs.create_index([("owner", 1), ("created_at", -1)])
        await self.claims.create_index("claim_id", unique=True)
        await self.claim_paths.create_index([("owner", 1), ("claim_id", 1), ("recorded_at", -1)])
        await self.snapshots.create_index([("owner", 1), ("ticker", 1), ("created_at", -1)])
        await self.snapshots.create_index("expires_at", expireAfterSeconds=0)
        await self.collection_jobs.create_index("expires_at", expireAfterSeconds=0)
        async for doc in self.turns.find({"status": {"$in": ["queued", "running"]}, "owner": {"$type": "string"}}):
            await self.finish(
                doc["owner"], doc["turn_id"], "interrupted", error="Server restarted; work was not repeated"
            )
        await self.project_claims()

    async def save_native_handoff(self, owner, record):
        digest = hashlib.sha256(canonical({"owner": owner, **record}).encode()).hexdigest()
        await self.handoffs.update_one(
            {"_id": digest, "owner": owner},
            {"$setOnInsert": {**record, "owner": owner, "handoff_id": "handoff_" + digest,
                              "created_at": utcnow()}},
            upsert=True,
        )
        return await self.handoffs.find_one({"_id": digest, "owner": owner})

    async def native_handoff_history(self, owner):
        return await self.handoffs.find({"owner": owner}).sort("created_at", -1).limit(20).to_list(length=20)

    async def session(self, capability=None):
        now = utcnow()
        if capability and isinstance(capability, str) and len(capability) <= 128:
            digest = hashlib.sha256(capability.encode()).hexdigest()
            doc = await self.sessions.find_one_and_update(
                {"capability_hash": digest, "expires_at": {"$gt": now}},
                {"$set": {"expires_at": now + timedelta(days=30)}},
                return_document=ReturnDocument.AFTER,
            )
            if doc:
                return doc["owner"], capability
        token = secrets.token_urlsafe(32)
        owner = str(uuid.uuid4())
        await self.sessions.insert_one(
            dict(
                owner=owner,
                capability_hash=hashlib.sha256(token.encode()).hexdigest(),
                created_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
        return owner, token

    async def owner(self, capability):
        if not capability or not isinstance(capability, str) or len(capability) > 128:
            return None
        doc = await self.sessions.find_one(
            {"capability_hash": hashlib.sha256(capability.encode()).hexdigest(), "expires_at": {"$gt": utcnow()}}
        )
        return doc["owner"] if doc else None

    async def rotate_session(self, capability):
        token = secrets.token_urlsafe(32)
        now = utcnow()
        doc = await self.sessions.find_one_and_update(
            {"capability_hash": hashlib.sha256(capability.encode()).hexdigest(), "expires_at": {"$gt": now}},
            {
                "$set": {
                    "capability_hash": hashlib.sha256(token.encode()).hexdigest(),
                    "expires_at": now + timedelta(days=30),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise ValueError("Session expired")
        return doc["owner"], token

    async def revoke_session(self, capability):
        if capability:
            await self.sessions.update_one(
                {"capability_hash": hashlib.sha256(capability.encode()).hexdigest()}, {"$set": {"expires_at": utcnow()}}
            )

    async def recover_session(self, owner):
        """Caller must enforce the server-key recovery boundary before this method."""
        if not isinstance(owner, str) or not re.fullmatch(r"[a-f0-9-]{36}", owner):
            raise ValueError("Invalid owner")
        known = (
            await self.sessions.find_one({"owner": owner})
            or await self.turns.find_one({"owner": owner})
            or await self.claims.find_one({"owner": owner})
        )
        if known is None:
            raise ValueError("Owner history not found")
        token = secrets.token_urlsafe(32)
        now = utcnow()
        await self.sessions.update_many({"owner": owner}, {"$set": {"expires_at": now}})
        await self.sessions.insert_one(
            {
                "owner": owner,
                "capability_hash": hashlib.sha256(token.encode()).hexdigest(),
                "created_at": now,
                "expires_at": now + timedelta(days=30),
            }
        )
        return token

    async def admit(self, owner, request_id, spec):
        request_time(request_id)
        digest = hashlib.sha256(canonical(spec).encode()).hexdigest()
        existing = await self.turns.find_one({"owner": owner, "request_id": request_id})
        if existing:
            if existing["digest"] != digest:
                raise ValueError("Request identity already belongs to a different question")
            return existing, False
        now = utcnow()
        doc = dict(
            turn_id=str(uuid.uuid4()),
            owner=owner,
            request_id=request_id,
            digest=digest,
            spec=spec,
            ticker=spec["ticker"],
            question=spec["question"],
            horizon=spec["horizon"],
            status="queued",
            created_at=now,
            updated_at=now,
            version=1,
            events=[],
            saved=True,
        )
        try:
            await self.turns.insert_one(doc)
            return doc, True
        except DuplicateKeyError:
            return await self.admit(owner, request_id, spec)

    async def read(self, owner, turn_id):
        return await self.turns.find_one({"owner": owner, "turn_id": turn_id}, {"_id": 0})

    async def progress(self, owner, turn_id, message):
        # Single service worker per turn owns event numbering. Completion/cancel
        # competes on state and cannot be overwritten by a delayed progress update.
        doc = await self.read(owner, turn_id)
        if not doc or doc["status"] in TERMINAL or len(doc["events"]) >= 60:
            return False
        seq = len(doc["events"]) + 1
        recorded_at = utcnow()
        result = await self.turns.update_one(
            {"owner": owner, "turn_id": turn_id, "status": {"$in": ["queued", "running"]}, "version": doc["version"]},
            {
                "$set": {"status": "running", "updated_at": recorded_at},
                "$inc": {"version": 1},
                "$push": {"events": {"id": seq, "type": "progress", "message": message[:200],
                                     "recorded_at": recorded_at.isoformat()}},
            },
        )
        return result.modified_count == 1

    async def save_read_activity(self, owner, turn_id, activity):
        result = await self.turns.update_one(
            {"owner": owner, "turn_id": turn_id, "status": {"$in": ["queued", "running"]}},
            {"$set": {"read_activity": activity}, "$inc": {"version": 1}},
        )
        return result.matched_count == 1

    async def finish(self, owner, turn_id, status, *, answer=None, error=None, claim_seed=None, read_activity=None):
        if status not in TERMINAL:
            raise ValueError("Invalid terminal state")
        if len(canonical(answer)) > 500000:
            raise ValueError("Answer exceeds storage limit")
        if claim_seed is not None:
            validated = rebuild_claim(
                **{
                    key: value
                    for key, value in claim_seed.items()
                    if key not in {"claim_id", "version", "confidence_meaning"}
                }
            )
            if status != "completed" or validated != claim_seed or validated["turn_id"] != turn_id:
                raise ValueError("Invalid claim for this final answer")
        doc = await self.read(owner, turn_id)
        if not doc or doc["status"] in TERMINAL:
            return False
        if claim_seed is not None and claim_seed["ticker"] != doc["ticker"]:
            raise ValueError("Claim ticker differs from saved question")
        if claim_seed is not None:
            if not isinstance(answer, dict) or not isinstance(answer.get("facts"), list):
                raise ValueError("Predictive answer needs its evidence ledger")
            ledger = {item["id"]: item for item in answer["facts"]}
            if any(canonical(ledger.get(item["id"])) != canonical(item) for item in claim_seed["evidence"]):
                raise ValueError("Claim evidence is absent from its saved answer")
            # The trusted issuance point is this finalization attempt, never a
            # caller-selected past time. A delayed CAS retry issues a new seed.
            parameters = {
                key: value
                for key, value in claim_seed.items()
                if key not in {"claim_id", "version", "confidence_meaning"}
            }
            parameters["issued_at"] = utcnow()
            claim_seed = rebuild_claim(**parameters)
            answer = {**answer, "claim_id": claim_seed["claim_id"], "claim_issued_at": claim_seed["issued_at"]}
        activity = copy.deepcopy(read_activity if read_activity is not None else doc.get("read_activity"))
        if activity is not None and not activity.get("closed"):
            activity["closed"] = True
            activity["entry_count_complete"] = False
            for attempt in activity.get("attempts", []):
                if attempt["outcome"] in {"reserved", "running"}:
                    attempt["outcome"] = "interrupted_unknown"
                    attempt["worker_unresolved"] = True
        recorded_at = utcnow()
        event = dict(id=len(doc["events"]) + 1, type="done" if status == "completed" else "error",
                     status=status, recorded_at=recorded_at.isoformat())
        result = await self.turns.update_one(
            {"owner": owner, "turn_id": turn_id, "status": {"$in": ["queued", "running"]}, "version": doc["version"]},
            {
                "$set": dict(
                    status=status,
                    answer=answer,
                    error=error,
                    claim_seed=claim_seed,
                    projection_pending=claim_seed is not None,
                    updated_at=recorded_at,
                    **({"read_activity": activity} if activity is not None else {}),
                ),
                "$inc": {"version": 1},
                "$push": {"events": event},
            },
        )
        if result.modified_count == 0:
            return await self.finish(owner, turn_id, status, answer=answer, error=error, claim_seed=claim_seed, read_activity=read_activity)
        return True

    async def history(self, owner):
        return await self.turns.find({"owner": owner}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(length=30)

    async def history_page(self, owner, *, limit=30, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("Choose between one and thirty saved answers")
        query = {"owner": owner}
        if cursor is not None:
            observed, turn_id = parse_history_cursor(cursor)
            anchor = await self.turns.find_one({"owner": owner, "turn_id": turn_id}, {"created_at": 1, "_id": 0})
            if anchor is None or storage_utc(anchor.get("created_at")) != observed:
                raise ValueError("Invalid saved-answer cursor")
            query["$or"] = [{"created_at": {"$lt": observed}},
                            {"created_at": observed, "turn_id": {"$lt": turn_id}}]
        projection = {key: 1 for key in HISTORY_PAGE_FIELDS}
        projection["_id"] = 0
        page_query = self.turns.find(query, projection).sort([("created_at", -1), ("turn_id", -1)]).limit(limit + 1)
        if hasattr(page_query, "max_time_ms"):
            page_query = page_query.max_time_ms(HISTORY_DB_TIME_MS)
        rows = await page_query.to_list(length=limit + 1)
        more = len(rows) > limit
        turns = rows[:limit]
        for row in turns:
            for field in ("created_at", "updated_at"):
                if isinstance(row.get(field), datetime):
                    row[field] = storage_utc(row[field])
        next_cursor = history_cursor(turns[-1]["created_at"], turns[-1]["turn_id"]) if more else None
        return {"turns": turns, "next_cursor": next_cursor, "has_more": more}

    async def history_candidates(self, owner, *, ticker, horizon, before, start=None, end=None,
                                 coverage_id=None, source=None, unit=None, close_time=None, compatible=True):
        """Filter stored source observations before loading a bounded price-only set.

        A compatible observation buried beneath recent questions remains visible.
        No created-at clock selects market evidence and no provider is called.
        """
        upper = min((before, end), key=market_time_key) if end is not None else before
        price = {"metric": "Underlying price", "ticker": ticker, "horizon": horizon,
                 "event_time": {"$regex": MARKET_TIME_PATTERN},
                 "value": {"$type": "number", "$gte": -1.7976931348623157e308, "$lte": 1.7976931348623157e308}}
        scope = {"ticker": ticker, "horizon": horizon}
        if compatible:
            scope["coverage_id"] = coverage_id
            price.update(source=source, unit=unit, status={"$in": ["ok", "degraded", "stale"]})
        if close_time is not None:
            scope["anchor_kind"] = "close"
            scope["window.session_close"] = {"$regex": MARKET_TIME_PATTERN}
        scope["facts"] = {"$elemMatch": price}
        minimal = ("ticker", "horizon", "snapshot_id", "coverage_id", "coverage", "anchor_kind", "window.session_close", "facts")
        snapshots, truncated = [], False
        stores = (
            (self.turns, "answer.snapshots", {"owner": owner, "status": "completed",
                                             "answer.snapshots": {"$elemMatch": scope}}),
            (self.snapshots, "snapshot", {"owner": owner, "ticker": ticker, "expires_at": {"$gt": utcnow()},
                                         **{"snapshot." + key: value for key, value in scope.items()}}),
        )
        for collection, path, query in stores:
            stages = [{"$match": query}]
            if path == "answer.snapshots":
                stages.append({"$unwind": "$" + path})
            stages.extend([
                {"$project": {"_id": 0, "snapshot": "$" + path}},
                {"$match": {"snapshot." + key: value for key, value in scope.items()}},
                {"$unwind": "$snapshot.facts"},
                {"$match": {"snapshot.facts." + key: value for key, value in price.items()}},
            ])
            stages.extend(market_time_stages("$snapshot.facts.event_time", "_price_"))
            bounds = [market_bound("_price_", upper)]
            if start is not None:
                bounds.append(market_bound("_price_", start, lower=True))
            if close_time is not None:
                seconds, micros = market_time_key(close_time)
                bounds.append({"_price_seconds": seconds, "_price_microsecond": micros})
                stages.extend(market_time_stages("$snapshot.window.session_close", "_close_"))
                bounds.append({"_close_seconds": seconds, "_close_microsecond": micros})
            stages.extend([
                {"$match": {"$and": bounds}},
                {"$sort": {"_price_seconds": -1, "_price_microsecond": -1, "snapshot.snapshot_id": -1}},
                {"$limit": HISTORY_SEARCH_LIMIT + 1},
                {"$project": {"_id": 0, **{"snapshot." + key: 1 for key in minimal}}},
            ])
            rows = await collection.aggregate(stages, maxTimeMS=HISTORY_DB_TIME_MS,
                                              allowDiskUse=False).to_list(length=HISTORY_SEARCH_LIMIT + 1)
            truncated = truncated or len(rows) > HISTORY_SEARCH_LIMIT
            for row in rows[:HISTORY_SEARCH_LIMIT]:
                item = copy.deepcopy(row["snapshot"])
                item["facts"] = [item["facts"]]
                snapshots.append(item)
        snapshots.sort(key=lambda item: (instant(item["facts"][0].get("event_time")) or "", item.get("snapshot_id", "")), reverse=True)
        return {"snapshots": snapshots, "truncated": truncated, "limit_per_store": HISTORY_SEARCH_LIMIT}

    async def project_claims(self):
        """Replay only canonical committed answers, bounded per maintenance tick."""
        cursor = self.turns.find({"status": "completed", "projection_pending": True}).sort("created_at", 1).limit(20)
        async for turn in cursor:
            seed = turn["claim_seed"]
            validated = rebuild_claim(
                **{
                    key: value
                    for key, value in seed.items()
                    if key not in {"claim_id", "version", "confidence_meaning"}
                }
            )
            if validated != seed or seed["turn_id"] != turn["turn_id"] or seed["ticker"] != turn["ticker"]:
                raise ValueError("Saved claim cannot be projected")
            await self.claims.update_one(
                {"claim_id": seed["claim_id"], "owner": turn["owner"]},
                {
                    "$setOnInsert": {
                        "owner": turn["owner"],
                        "claim_id": seed["claim_id"],
                        "seed": seed,
                        "status": "open",
                        "created_at": turn["created_at"],
                        "version": 0,
                        "next_due": utcnow(),
                    }
                },
                upsert=True,
            )
            await self.turns.update_one(
                {"turn_id": turn["turn_id"], "owner": turn["owner"], "status": "completed"},
                {"$set": {"projection_pending": False}},
            )

    async def record_claim_path(self, owner, claim_id, bars, *, now, source_available=True):
        """Immutable source revisions; current result advances by checked receipt time."""
        doc = await self.claims.find_one({"owner": owner, "claim_id": claim_id})
        if doc is None:
            raise ValueError("Claim not found")
        # Persist exactly the canonical values used by the digest. BSON datetime
        # roundtrips otherwise lose timezone and sub-millisecond information.
        bars = json.loads(canonical(bars))
        resolution = resolve_claim(doc["seed"], bars, now=now, source_available=source_available)
        if resolution["status"] == "malformed" or len(canonical(bars)) > 500000:
            raise ValueError("Invalid or oversized outcome path")
        checked_at = datetime.fromisoformat(resolution["resolved_at"])
        key = hashlib.sha256(
            canonical(
                [
                    owner,
                    claim_id,
                    resolution["resolver_version"],
                    resolution["path_digest"],
                    resolution["status"],
                    source_available,
                ]
            ).encode()
        ).hexdigest()
        await self.claim_paths.update_one(
            {"_id": key},
            {
                "$setOnInsert": {
                    "owner": owner,
                    "claim_id": claim_id,
                    "recorded_at": checked_at,
                    "bars": bars,
                    "source_available": source_available,
                    "resolution": resolution,
                }
            },
            upsert=True,
        )
        # A late older worker cannot replace a newer correction. A duplicate
        # observation retains the first immutable resolution rather than aging it.
        stored = await self.claim_paths.find_one({"_id": key})
        first_seen = stored["recorded_at"]
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=UTC)
        await self.claims.update_one(
            {
                "owner": owner,
                "claim_id": claim_id,
                "resolution_id": {"$ne": key},
                "$or": [{"revision_seen_at": {"$exists": False}}, {"revision_seen_at": {"$lt": first_seen}}],
            },
            {
                "$set": {
                    "resolution_id": key,
                    "resolution": stored["resolution"],
                    "status": resolution["status"],
                    "revision_seen_at": first_seen,
                    "next_due": checked_at + timedelta(minutes=15) if resolution["status"] == "open" else None,
                },
                "$inc": {"version": 1},
                "$max": {"checked_at": checked_at},
            },
        )
        await self.claims.update_one(
            {"owner": owner, "claim_id": claim_id, "resolution_id": key, "checked_at": {"$lt": checked_at}},
            {
                "$set": {
                    "checked_at": checked_at,
                    "next_due": checked_at + timedelta(minutes=15) if resolution["status"] == "open" else None,
                }
            },
        )
        return stored["resolution"]

    async def collect_claim_paths(self, now):
        # No verified historical-range adapter is available. Persist that gap;
        # never substitute the latest recent bars for the missing interval.
        docs = (
            await self.claims.find({"status": "open", "next_due": {"$lte": now}})
            .sort("next_due", 1)
            .limit(4)
            .to_list(length=4)
        )
        for doc in docs:
            await self.record_claim_path(doc["owner"], doc["claim_id"], [], now=now, source_available=False)

    async def get_preferences(self, owner):
        doc = await self.preferences.find_one({"owner": owner}, {"_id": 0, "owner": 0})
        return doc or {}

    async def save_preferences(self, owner, value):
        await self.preferences.update_one({"owner": owner}, {"$set": value}, upsert=True)

    async def save_anchor(self, owner, snapshot):
        now = utcnow()
        key = hashlib.sha256(f"{owner}|{snapshot['snapshot_id']}".encode()).hexdigest()
        await self.snapshots.update_one(
            {"_id": key},
            {
                "$setOnInsert": {
                    "owner": owner,
                    "ticker": snapshot["ticker"],
                    "created_at": now,
                    "expires_at": now + timedelta(days=30),
                    "snapshot": snapshot,
                }
            },
            upsert=True,
        )

    async def watch_observations(self, owner, ticker, horizon, selected_expiry=None):
        now = utcnow()
        key = hashlib.sha256(canonical([owner, ticker, horizon, selected_expiry]).encode()).hexdigest()
        await self.collection_jobs.update_one(
            {"_id": key},
            {
                "$setOnInsert": {
                    "owner": owner,
                    "ticker": ticker,
                    "horizon": horizon,
                    "selected_expiry": selected_expiry,
                    "next_due": now + timedelta(minutes=15),
                },
                "$set": {"expires_at": now + timedelta(days=30)},
            },
            upsert=True,
        )

    async def due_jobs(self, now):
        return (
            await self.collection_jobs.find(
                {
                    "next_due": {"$lte": now},
                    "expires_at": {"$gt": now},
                    "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": now}}],
                }
            )
            .sort("next_due", 1)
            .limit(4)
            .to_list(length=4)
        )

    async def claim_job(self, job_id, now):
        return await self.collection_jobs.find_one_and_update(
            {
                "_id": job_id,
                "next_due": {"$lte": now},
                "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": now}}],
            },
            {"$set": {"lease_until": now + timedelta(minutes=2)}},
            return_document=ReturnDocument.AFTER,
        )

    async def finish_job(self, job_id, now, error=None):
        await self.collection_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {"next_due": now + timedelta(minutes=15), "last_checked": now, "error": error},
                "$unset": {"lease_until": ""},
            },
        )
