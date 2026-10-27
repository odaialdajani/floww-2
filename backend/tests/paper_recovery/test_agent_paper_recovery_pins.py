"""Restart-recovery invariants of the agent-paper checkpoint system (B18).

services/agent/paper/recovery.py (export_checkpoint / restore_frozen_copy) is
the ledger's restart-recovery core: it must stream a CONSISTENT version
boundary, fill projection gaps from pending seeds, refuse gaps with no seed,
never roll a funded account backwards in place, and refuse tampered or
incomplete checkpoints. No repo-root suite covers it — only the opt-in
real-Mongo verify scripts do — so these invariants run NOWHERE in CI.

This file pins them OFFLINE with an in-memory repository that reuses the REAL
PaperRepository (its _size/BSON limits) over fake collections: no Mongo, no
network, no admission path. These are invariant pins — they must pass on the
current tree; any failure is a real defect, not a fixture problem.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pymongo.errors import DuplicateKeyError  # noqa: E402

from services.agent.paper.recovery import export_checkpoint, restore_frozen_copy  # noqa: E402
from services.agent.paper.repository import (  # noqa: E402
    MAX_EVENT_BYTES,
    PaperConflict,
    PaperRepository,
    digest,
    scope,
)

OWNER = str(uuid.uuid4())
ACCOUNT = str(uuid.uuid4())
VENUE = "internal"
EPOCH = str(uuid.uuid4())


class _FakeCursor:
    def __init__(self, docs, query):
        self._rows = [d for d in docs
                      if d["scope_id"] == query["scope_id"]
                      and d["epoch"] == query["epoch"]
                      and d["version"] <= query["version"].get("$lte", 0)]
        self._rows.sort(key=lambda d: d["version"])
        self._i = 0

    def sort(self, _key, _direction):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._i]
        self._i += 1
        return row


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []
        self.raise_duplicate = False

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def find(self, query, **_kwargs):
        return _FakeCursor(self.docs, query)

    async def insert_one(self, doc):
        if self.raise_duplicate:
            raise DuplicateKeyError("E11000 duplicate")
        self.docs.append(doc)

    async def create_index(self, *args, **kwargs):  # pragma: no cover - unused here
        return None


class _FakeDatabase:
    def __init__(self):
        self.collections: dict[str, _FakeCollection] = {}

    def get_collection(self, name, write_concern=None):
        col = self.collections.setdefault(name, _FakeCollection())
        col.write_concern = write_concern
        return col


def _event(version, body="x"):
    return dict(_id=digest([OWNER, ACCOUNT, f"op{version}"]), scope_id=digest(scope(OWNER, ACCOUNT, VENUE)),
                owner=OWNER, account_id=ACCOUNT, venue=VENUE, epoch=EPOCH,
                operation_id=f"{EPOCH}:{version}:nonce{version}", command_digest=digest({"v": version}),
                version=version, recorded_at="2026-10-27T00:00:00+00:00", body={"kind": body})


def _account(version=3, pending=(), epoch_initial_version=0):
    return dict(_id=digest(scope(OWNER, ACCOUNT, VENUE)), owner=OWNER, account_id=ACCOUNT,
                venue=VENUE, version=version, state={"cash": "1000"}, epoch=EPOCH,
                initial_digest="irrelevant", storage_version=1, reserve_events=0,
                epoch_initial_version=epoch_initial_version, pending_events=list(pending))


def _repo():
    return PaperRepository(_FakeDatabase())


class TestExportCheckpoint:
    async def test_continuous_history_exports_complete_manifest(self, tmp_path):
        repo = _repo()
        repo.events.docs = [_event(v) for v in (1, 2, 3)]
        repo.accounts.docs = [_account()]
        directory = tmp_path / "ckpt"
        manifest = await export_checkpoint(repo, OWNER, ACCOUNT, directory)
        assert manifest["format"] == "paper-checkpoint-1"
        assert manifest["events"] == 3
        assert manifest["version"] == 3
        lines = (directory / "events.jsonl").read_text().strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["version"] == 1
        assert (directory / "manifest.json").exists()

    async def test_pending_seed_fills_projection_gap(self, tmp_path):
        repo = _repo()
        seed = _event(2, body="pending-seed")
        repo.events.docs = [_event(1), _event(3)]  # v2 missing from history
        repo.accounts.docs = [_account(pending=[seed])]
        manifest = await export_checkpoint(repo, OWNER, ACCOUNT, tmp_path / "ckpt")
        assert manifest["events"] == 3
        lines = (tmp_path / "ckpt" / "events.jsonl").read_text().strip().splitlines()
        assert [json.loads(line)["version"] for line in lines] == [1, 2, 3]
        assert json.loads(lines[1])["body"] == {"kind": "pending-seed"}

    async def test_gap_without_seed_refuses_and_writes_no_manifest(self, tmp_path):
        repo = _repo()
        repo.events.docs = [_event(1), _event(3)]
        repo.accounts.docs = [_account()]  # no pending seed for v2
        directory = tmp_path / "ckpt"
        with pytest.raises(PaperConflict, match="gap"):
            await export_checkpoint(repo, OWNER, ACCOUNT, directory)
        assert not (directory / "manifest.json").exists(), \
            "a failed export must leave no restorable manifest"

    async def test_pending_seed_conflicting_with_history_refuses(self, tmp_path):
        repo = _repo()
        seed = _event(2, body="different-content")
        repo.events.docs = [_event(1), _event(2), _event(3)]
        repo.accounts.docs = [_account(pending=[seed])]
        with pytest.raises(PaperConflict, match="pending"):
            await export_checkpoint(repo, OWNER, ACCOUNT, tmp_path / "ckpt")


class TestRestoreFrozenCopy:
    async def _export(self, tmp_path, name="ckpt"):
        repo = _repo()
        repo.events.docs = [_event(v) for v in (1, 2)]
        repo.accounts.docs = [_account(version=2)]
        directory = tmp_path / name
        manifest = await export_checkpoint(repo, OWNER, ACCOUNT, directory)
        return repo, directory, manifest

    async def test_restore_fresh_identity_requires_reconciliation(self, tmp_path):
        repo, directory, manifest = await self._export(tmp_path)
        new_account = str(uuid.uuid4())
        restored = await restore_frozen_copy(repo, OWNER, new_account, directory)
        assert restored["account_id"] == new_account
        assert restored["recovery_pending"] is True, \
            "a restored copy must land frozen until reconciliation clears it"
        assert restored["version"] == 0
        assert restored["epoch"] != EPOCH, "old confirmations must die with the old epoch"
        assert restored["state"] == {"cash": "1000"}
        assert restored["recovery"]["source_account"] == ACCOUNT
        assert restored["recovery"]["manifest_digest"] == digest(manifest)

    async def test_in_place_rollback_refused(self, tmp_path):
        repo, directory, _ = await self._export(tmp_path)
        with pytest.raises(PaperConflict, match="new account identity"):
            await restore_frozen_copy(repo, OWNER, ACCOUNT, directory)

    async def test_tampered_manifest_refused(self, tmp_path):
        repo, directory, manifest = await self._export(tmp_path)
        manifest["events"] = 99  # tamper after export
        (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True,
                                                            separators=(",", ":")))
        with pytest.raises(PaperConflict):
            await restore_frozen_copy(repo, OWNER, str(uuid.uuid4()), directory)

    async def test_existing_target_not_replaced(self, tmp_path):
        repo, directory, _ = await self._export(tmp_path)
        repo.accounts.raise_duplicate = True
        with pytest.raises(PaperConflict, match="not replaced"):
            await restore_frozen_copy(repo, OWNER, str(uuid.uuid4()), directory)

    async def test_tampered_history_line_refused(self, tmp_path):
        repo, directory, _ = await self._export(tmp_path)
        # Tamper one exported event's version: event_valid must refuse the
        # sequence mismatch before anything is restored.
        path = directory / "events.jsonl"
        lines = path.read_text().strip().splitlines()
        first = json.loads(lines[0])
        first["version"] = 5  # out of sequence
        lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n")
        with pytest.raises(PaperConflict):
            await restore_frozen_copy(repo, OWNER, str(uuid.uuid4()), directory)
