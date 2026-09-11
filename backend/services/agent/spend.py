"""Integer-dollar-micro-unit reservations in one conditional billing document."""

from __future__ import annotations

import contextlib
import copy
import inspect
import re
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError


def money_units(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError("Invalid monetary amount")
        return int((amount * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    except InvalidOperation:
        raise ValueError("Invalid monetary amount") from None


class SpendLedger:
    def __init__(self, collection, *, cap_units=20_000_000, clock=None, maximum_entries=5000, audit_collection=None):
        self.collection = collection
        self.cap_units = cap_units
        self.clock = clock or (lambda: datetime.now(UTC))
        self.maximum_entries = maximum_entries
        self.audit_collection = audit_collection

    def day(self):
        return self.clock().astimezone(ZoneInfo("America/New_York")).date().isoformat()

    async def initialize(self):
        with contextlib.suppress(DuplicateKeyError):
            await self.collection.insert_one(
                {"_id": "openrouter", "version": 1, "days": {}, "requests": {}, "frozen": False}
            )

    def state_of(self, doc):
        pending = sum(r["reserved"] for r in doc["requests"].values() if r["state"] in {"reserved", "dispatched"})
        spent = doc["days"].get(self.day(), 0)
        return dict(
            cap_units=self.cap_units,
            spent_units=spent,
            reserved_units=pending,
            remaining_units=max(0, self.cap_units - spent - pending),
            day=self.day(),
            frozen=doc["frozen"],
        )

    async def state(self):
        doc = await self.collection.find_one({"_id": "openrouter"})
        if doc is None:
            raise RuntimeError("Budget storage is not initialized")
        return self.state_of(doc)

    async def recover_undispatched(self):
        """Only at startup before admitting work; never release uncertain dispatches."""

        def mutate(doc):
            released = 0
            for entry in doc["requests"].values():
                if entry["state"] == "reserved":
                    entry["state"] = "released"
                    entry["release_reason"] = "Restart before dispatch"
                    released += 1
            return released, bool(released)

        return await self._change(mutate)

    async def _change(self, mutate):
        for _ in range(20):
            doc = await self.collection.find_one({"_id": "openrouter"})
            if doc is None:
                raise RuntimeError("Budget storage is not initialized")
            updated = copy.deepcopy(doc)
            mutation = mutate(updated)
            result, changed = await mutation if inspect.isawaitable(mutation) else mutation
            if not changed:
                return result
            updated["version"] = doc["version"] + 1
            saved = await self.collection.replace_one({"_id": "openrouter", "version": doc["version"]}, updated)
            if saved.modified_count:
                return result
        raise RuntimeError("Budget is busy; request not admitted")

    async def reserve(self, request_id, amount, turn_id):
        if (
            not re.fullmatch(r"[a-f0-9-]{36}", request_id)
            or not isinstance(amount, int)
            or isinstance(amount, bool)
            or amount <= 0
        ):
            raise ValueError("Invalid reservation")

        async def mutate(doc):
            if self.audit_collection is not None:
                archived = await self.audit_collection.find_one({"_id": request_id})
                if archived:
                    if archived["entry"]["reserved"] != amount or archived["entry"]["turn_id"] != turn_id:
                        raise ValueError("Archived reservation identity conflict")
                    return False, False
            old = doc["requests"].get(request_id)
            if old:
                if old["reserved"] != amount or old["turn_id"] != turn_id:
                    raise ValueError("Reservation identity conflict")
                return old["state"] == "reserved", False
            state = self.state_of(doc)
            if doc["frozen"] or len(doc["requests"]) >= self.maximum_entries or amount > state["remaining_units"]:
                return False, False
            doc["requests"][request_id] = dict(
                day=self.day(), reserved=amount, state="reserved", turn_id=turn_id, created_at=self.clock()
            )
            return True, True

        return await self._change(mutate)

    async def dispatch(self, request_id):
        def mutate(doc):
            entry = doc["requests"].get(request_id)
            if not entry or entry["state"] != "reserved":
                return False, False
            entry["state"] = "dispatched"
            entry["dispatched_at"] = self.clock()
            # Usage belongs to the day work is sent. An unresolved reservation
            # still reduces every later day's allowance until actual cost arrives.
            entry["day"] = self.day()
            return True, True

        return await self._change(mutate)

    async def settle(self, request_id, actual_units, generation_id):
        if not isinstance(actual_units, int) or isinstance(actual_units, bool) or actual_units < 0 or not generation_id:
            raise ValueError("Invalid provider usage")
        if self.audit_collection is not None:
            archived = await self.audit_collection.find_one({"_id": request_id})
            if archived:
                if (
                    archived["entry"].get("actual") != actual_units
                    or archived["entry"].get("generation_id") != generation_id
                ):
                    raise ValueError("Conflicting archived settlement")
                return False

        async def mutate(doc):
            entry = doc["requests"].get(request_id)
            if self.audit_collection is not None:
                archived_generation = await self.audit_collection.find_one({"entry.generation_id": generation_id})
                if archived_generation:
                    if (
                        archived_generation["_id"] == request_id
                        and archived_generation["entry"].get("actual") == actual_units
                    ):
                        return False, False
                    raise ValueError("Generation already settled in archived detail")
            if not entry:
                raise ValueError("Unknown or archived reservation; reconciliation required")
            if entry["state"] == "settled":
                if entry["actual"] != actual_units or entry["generation_id"] != generation_id:
                    raise ValueError("Conflicting settlement")
                return False, False
            if entry["state"] != "dispatched":
                raise ValueError("Only dispatched requests may settle")
            if any(key != request_id and r.get("generation_id") == generation_id for key, r in doc["requests"].items()):
                raise ValueError("Generation already settled")
            doc["days"][entry["day"]] = doc["days"].get(entry["day"], 0) + actual_units
            entry.update(state="settled", actual=actual_units, generation_id=generation_id, settled_at=self.clock())
            if actual_units > entry["reserved"]:
                doc["frozen"] = True  # Provider exceeded the admitted bound; require investigation.
            return True, True

        return await self._change(mutate)

    async def note_generation(self, request_id, generation_id):
        def mutate(doc):
            entry = doc["requests"].get(request_id)
            if not entry or entry["state"] != "dispatched":
                return False, False
            if entry.get("generation_id"):
                if entry["generation_id"] != generation_id:
                    raise ValueError("Conflicting generation identity")
                return True, False
            entry["generation_id"] = generation_id
            return True, True

        return await self._change(mutate)

    async def release_undispatched(self, request_id):
        def mutate(doc):
            entry = doc["requests"].get(request_id)
            if not entry or entry["state"] != "reserved":
                return False, False
            entry["state"] = "released"
            return True, True

        return await self._change(mutate)

    async def project_terminal(self, maximum=100):
        """Project immutable detail before removing terminal aggregate entries."""
        if self.audit_collection is None:
            return 0
        doc = await self.collection.find_one({"_id": "openrouter"})
        if doc is None:
            raise RuntimeError("Budget storage is unavailable")
        count = 0
        for key, entry in list(doc["requests"].items()):
            if count >= maximum:
                break
            if entry["state"] not in {"settled", "released"}:
                continue
            try:
                await self.audit_collection.insert_one({"_id": key, "entry": entry, "projected_at": self.clock()})
            except DuplicateKeyError:
                old = await self.audit_collection.find_one({"_id": key})
                if old is None or old["entry"] != entry:
                    raise ValueError("Budget audit projection conflict") from None

            def remove(current, identity=key, expected=entry):
                existing = current["requests"].get(identity)
                if existing != expected:
                    return False, False
                del current["requests"][identity]
                return True, True

            count += bool(await self._change(remove))
        return count

    async def claim_lookup(self, maximum=4):
        now = self.clock()

        def mutate(doc):
            pending = []
            for key, entry in doc["requests"].items():
                last = entry.get("lookup_at")
                if last and last.tzinfo is None:
                    last = last.replace(tzinfo=UTC)
                if (
                    entry["state"] == "dispatched"
                    and entry.get("generation_id")
                    and (last is None or (now - last).total_seconds() >= 300)
                ):
                    entry["lookup_at"] = now
                    pending.append((key, entry["generation_id"]))
                    if len(pending) >= maximum:
                        break
            return pending, bool(pending)

        return await self._change(mutate)
