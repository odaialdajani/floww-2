"""Awaited storage; final answer and its recovery seed commit in one document."""

from __future__ import annotations

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
from services.agent.contracts import canonical

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

    async def initialize(self):
        await self.turns.create_index(
            [("owner", 1), ("request_id", 1)], unique=True, partialFilterExpression={"owner": {"$type": "string"}}
        )
        await self.turns.create_index("turn_id", unique=True)
        await self.turns.create_index([("owner", 1), ("created_at", -1)])
        await self.sessions.create_index("capability_hash", unique=True)
        await self.sessions.create_index("expires_at", expireAfterSeconds=0)
        await self.preferences.create_index("owner", unique=True)
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
        result = await self.turns.update_one(
            {"owner": owner, "turn_id": turn_id, "status": {"$in": ["queued", "running"]}, "version": doc["version"]},
            {
                "$set": {"status": "running", "updated_at": utcnow()},
                "$inc": {"version": 1},
                "$push": {"events": {"id": seq, "type": "progress", "message": message[:200]}},
            },
        )
        return result.modified_count == 1

    async def finish(self, owner, turn_id, status, *, answer=None, error=None, claim_seed=None):
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
        event = dict(id=len(doc["events"]) + 1, type="done" if status == "completed" else "error", status=status)
        result = await self.turns.update_one(
            {"owner": owner, "turn_id": turn_id, "status": {"$in": ["queued", "running"]}, "version": doc["version"]},
            {
                "$set": dict(
                    status=status,
                    answer=answer,
                    error=error,
                    claim_seed=claim_seed,
                    projection_pending=claim_seed is not None,
                    updated_at=utcnow(),
                ),
                "$inc": {"version": 1},
                "$push": {"events": event},
            },
        )
        if result.modified_count == 0:
            return await self.finish(owner, turn_id, status, answer=answer, error=error, claim_seed=claim_seed)
        return True

    async def history(self, owner):
        return await self.turns.find({"owner": owner}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(length=30)

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
