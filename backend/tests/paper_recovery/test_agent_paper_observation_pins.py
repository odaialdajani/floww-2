"""Offline CI pins for PreparedObservationService (paper-recovery B22).

services/agent/paper/observation_service.py is the default-denied persistence
seam for verified paper account observations. Like recovery.py before B18, it
has NO CI-visible coverage — only the opt-in real-Mongo verify script. These
pins run the REAL PaperRepository + PreparedObservationService over fake
in-memory collections (no Mongo, no network, no admission path):

  - default deny: no configured evidence check -> PaperConflict, nothing saved
  - failed independent evidence check -> PaperConflict
  - a fresh verified frame commits one paper_account_observed event and binds
    the snapshot to account version + 1
  - replaying the SAME operation returns the original receipt (idempotent)
  - an unchanged frame under a NEW operation commits NOTHING and returns
    (None, False) — stale input cannot masquerade as a fresh observation
  - an operation bound to a stale account version refuses honestly
"""
from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.agent.paper.execution import new_book  # noqa: E402
from services.agent.paper.observation_service import PreparedObservationService  # noqa: E402
from services.agent.paper.repository import PaperConflict, PaperRepository, operation_id  # noqa: E402

NOW = datetime(2026, 10, 27, 14, tzinfo=UTC)


def _frame(sequence=0):
    opened = NOW - timedelta(minutes=30)
    return {
        "marks": [],
        "metadata": [],
        "policy": {"policy_id": "explicit-synthetic", "mark_method": "midpoint",
                   "max_mark_age_seconds": 60, "max_spread": "2",
                   "daily_loss_limit": "50", "drawdown_limit": "40",
                   "max_gross_exposure": "1000"},
        "session": {"session_id": "synthetic-session", "calendar_version": "synthetic-calendar",
                    "source_id": "session-source", "opened_at": opened.isoformat(),
                    "closed_at": (NOW + timedelta(hours=6)).isoformat()},
        "session_open": {"session_id": "synthetic-session", "source_id": "opening-equity",
                         "observed_at": opened.isoformat(), "equity": "1000"},
    }


class _FakeCursor:
    def __init__(self, docs):
        self._rows = list(docs)

    def sort(self, *_a):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def find(self, _query, **_kwargs):
        return _FakeCursor([])

    async def insert_one(self, doc):
        self.docs.append(doc)

    async def update_one(self, query, update):
        target = await self.find_one(query)
        if target is None:
            return SimpleNamespace(modified_count=0)
        for key, value in update.get("$set", {}).items():
            target[key] = value
        for key, value in update.get("$push", {}).items():
            target.setdefault(key, []).append(value)
        return SimpleNamespace(modified_count=1)

    async def create_index(self, *a, **k):  # pragma: no cover
        return None


class _FakeDatabase:
    def get_collection(self, name, write_concern=None):
        col = _FakeCollection()
        col.write_concern = write_concern
        return col


async def _fresh_account():
    repo = PaperRepository(_FakeDatabase())
    owner, account = str(uuid.uuid4()), str(uuid.uuid4())
    await repo.create(owner, account, new_book("1000", currency="USD"))
    return repo, owner, account


async def _pass(*_args):
    return True


async def _fail(*_args):
    return False


def _op(repo, owner, account, version=0):
    return operation_id(version, epoch=repo.accounts.docs[0]["epoch"])


class TestObservationServicePins:
    @pytest.mark.asyncio
    async def test_default_deny_without_evidence_check(self):
        repo, owner, account = await _fresh_account()
        service = PreparedObservationService(repo, clock=lambda: NOW)
        with pytest.raises(PaperConflict, match="admission is not configured"):
            await service.record(owner, account, _op(repo, owner, account), _frame())
        assert repo.accounts.docs[0]["version"] == 0, "nothing may be saved on refusal"

    @pytest.mark.asyncio
    async def test_failed_evidence_check_refuses(self):
        repo, owner, account = await _fresh_account()
        service = PreparedObservationService(repo, evidence_check=_fail,
                                             clock=lambda: NOW)
        with pytest.raises(PaperConflict, match="did not independently pass"):
            await service.record(owner, account, _op(repo, owner, account), _frame())
        assert repo.accounts.docs[0]["version"] == 0

    @pytest.mark.asyncio
    async def test_fresh_verified_frame_commits_once(self):
        repo, owner, account = await _fresh_account()
        service = PreparedObservationService(repo, evidence_check=_pass,
                                             clock=lambda: NOW)
        operation = _op(repo, owner, account)
        event, created = await service.record(owner, account, operation, _frame())
        assert created is True
        assert event["body"]["kind"] == "paper_account_observed"
        doc = repo.accounts.docs[0]
        assert doc["version"] == 1
        assert doc["state"]["valuation"]["saved_version"] == 1, \
            "the snapshot must be bound to the version it was saved at"

    @pytest.mark.asyncio
    async def test_same_operation_replays_the_original_receipt(self):
        repo, owner, account = await _fresh_account()
        service = PreparedObservationService(repo, evidence_check=_pass,
                                             clock=lambda: NOW)
        operation = _op(repo, owner, account)
        first, created = await service.record(owner, account, operation, _frame())
        assert created is True
        replay, created2 = await service.record(owner, account, operation, _frame())
        assert created2 is False
        assert replay == first, "a replayed operation must return the original receipt"
        assert repo.accounts.docs[0]["version"] == 1, "no second commit on replay"

    @pytest.mark.asyncio
    async def test_unchanged_frame_under_new_operation_saves_nothing(self):
        repo, owner, account = await _fresh_account()
        service = PreparedObservationService(repo, evidence_check=_pass,
                                             clock=lambda: NOW)
        frame = _frame()
        _, created = await service.record(owner, account, _op(repo, owner, account), frame)
        assert created is True
        second_op = _op(repo, owner, account, version=1)
        result, created2 = await service.record(owner, account, second_op, frame)
        assert result is None and created2 is False, \
            "unchanged input must not pretend to be a fresh saved observation"
        assert repo.accounts.docs[0]["version"] == 1, "no commit for unchanged input"

    @pytest.mark.asyncio
    async def test_stale_operation_version_refuses(self):
        repo, owner, account = await _fresh_account()
        service = PreparedObservationService(repo, evidence_check=_pass,
                                             clock=lambda: NOW)
        await service.record(owner, account, _op(repo, owner, account), _frame())
        stale = _op(repo, owner, account, version=0)  # account is now at version 1
        with pytest.raises(PaperConflict, match="Account changed before observation"):
            await service.record(owner, account, stale, _frame())
