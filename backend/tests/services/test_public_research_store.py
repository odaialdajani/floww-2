"""Private raw research journal contracts; all evidence is synthetic."""
import copy
import hashlib
import importlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

MANIFEST = {
    "schema": "public-raw-research.v1",
    "parser_id": "public-option-contract+strict-research.v2",
    "symbols": ["SPY", "QQQ"],
    "expiries": ["2026-11-13"],
    "research_only": True, "trusted_for_admission": False, "executable": False,
    "limits": {"max_attempts": 8, "max_body_bytes": 1048576,
               "max_total_body_bytes": 8388608, "max_rows": 4000,
               "max_db_pages": 4096, "max_chunk_bytes": 65536,
               "max_total_read_bytes": 8912896,
               "request_timeout_s": 5.0, "cycle_timeout_s": 60.0},
}
AT = "2026-11-06T15:00:00+00:00"


def module():
    try:
        value = importlib.import_module("services.public_research_store")
    except ModuleNotFoundError as exc:
        if exc.name != "services.public_research_store":
            raise
        value = None
    assert value is not None, "private research journal is not implemented"
    return value


def manifest(**limits):
    value = copy.deepcopy(MANIFEST)
    value["limits"].update(limits)
    return value


def reserved(store, cycle="cycle-1"):
    assert store.begin_cycle(cycle, "XNYS:2026-11-06") is None
    value = store.reserve_attempt(cycle, {"kind": "chain", "symbol": "SPY", "expiry": "2026-11-13"})
    store.mark_dispatch(value["attempt_id"], AT)
    return value["attempt_id"]


def metadata(body):
    return {"http_status": 200, "source_delivery": "network",
            "media_type": "json", "content_encoding": "identity",
            "started_at": AT, "body_completed_at": AT,
            "response_closed_at": AT, "closure_gate_reason": None,
            "wall_clock_regressed": False, "body_complete": True,
            "bytes_observed": len(body), "source_body_sha256": hashlib.sha256(body).hexdigest(),
            "withholding_reason": None, "error_code": None}


def test_exact_entity_bytes_and_parse_link_survive_writer_exit_and_reopen(tmp_path):
    m = module()
    path = tmp_path / "research"
    body = b'{ "calls": [], "puts": [], "unknownVendorField": "kept" }\n'
    with m.ResearchStore(path, manifest()) as store:
        attempt = reserved(store)
        store.record_response(attempt, metadata(body), body)
        store.record_parsed(attempt, [{"kind": "chain", "symbol": "SPY", "row_index": 0,
                                      "bid_timestamp": None, "oi_effective_date": None}],
                            {"status": "parsed", "parsed_at": AT, "errors": 0, "truncated": False})
        receipt = {"status": "committed", "cycle_id": "cycle-1", "research_only": True}
        store.finish_cycle("cycle-1", receipt)
    with m.ResearchStore(path, manifest()) as reopened:
        rows = reopened.attempts("cycle-1")
        assert len(rows) == 1
        assert rows[0]["body"] == body
        assert rows[0]["response"]["source_body_sha256"] == hashlib.sha256(body).hexdigest()
        assert rows[0]["retained_body_sha256"] == hashlib.sha256(body).hexdigest()
        assert reopened.observations(attempt)[0]["oi_effective_date"] is None
        assert reopened.begin_cycle("cycle-1", "XNYS:2026-11-06") == receipt
        assert reopened.status()["reserved_attempts"] == 1


def test_dispatch_reservation_is_consumed_across_restart_and_existing_cycle_is_not_replayed(tmp_path):
    m = module()
    path = tmp_path / "research"
    with m.ResearchStore(path, manifest(max_attempts=2)) as store:
        first = reserved(store)
    with m.ResearchStore(path, manifest(max_attempts=2)) as store:
        interrupted = store.begin_cycle("cycle-1", "XNYS:2026-11-06")
        assert interrupted["status"] == "interrupted"
        assert interrupted["trusted_for_admission"] is False
        assert store.attempts("cycle-1")[0]["status"] == "interrupted"
        assert store.attempts("cycle-1")[0]["attempt_id"] == first
        assert store.begin_cycle("cycle-2", "XNYS:2026-11-06") is None
        store.reserve_attempt("cycle-2", {"kind": "quotes", "symbol": "QQQ", "expiry": None})
        with pytest.raises(m.ResearchRefusal, match="attempt_cap"):
            store.reserve_attempt("cycle-2", {"kind": "quotes", "symbol": "SPY", "expiry": None})
        assert store.status()["reserved_attempts"] == 2


def test_lifetime_guard_excludes_second_writer_and_is_not_unlinked(tmp_path):
    m = module()
    path = tmp_path / "research"
    with m.ResearchStore(path, manifest()) as store:
        inode = (path / "writer.lock").stat().st_ino
        with pytest.raises(m.ResearchRefusal, match="writer_held"):
            m.ResearchStore(path, manifest())
        assert store.status()["reserved_attempts"] == 0
    assert (path / "writer.lock").stat().st_ino == inode
    with m.ResearchStore(path, manifest()):
        assert (path / "writer.lock").stat().st_ino == inode


def test_abrupt_process_exit_preserves_consumed_reservation_and_releases_only_os_lock(tmp_path):
    m = module()
    path = tmp_path / "research"
    backend = Path(__file__).resolve().parents[2]
    code = """
import json,os,sys
sys.path.insert(0,sys.argv[1])
from services.public_research_store import ResearchStore
s=ResearchStore(sys.argv[2],json.loads(sys.argv[3]))
s.begin_cycle('cycle-crash','XNYS:2026-11-06')
a=s.reserve_attempt('cycle-crash',{'kind':'quotes','symbol':'SPY','expiry':None})
s.mark_dispatch(a['attempt_id'],'2026-11-06T15:00:00+00:00')
os._exit(17)
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(backend), str(path), m.canonical(manifest())],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 17, result.stderr
    with m.ResearchStore(path, manifest()) as store:
        receipt = store.begin_cycle("cycle-crash", "XNYS:2026-11-06")
        assert receipt["status"] == "interrupted" and receipt["trusted_for_admission"] is False
        assert store.status()["reserved_attempts"] == 1
        assert store.attempts("cycle-crash")[0]["status"] == "interrupted"


def test_transport_hold_defers_close_and_keeps_writer_exclusion_until_settlement(tmp_path):
    m = module()
    path = tmp_path / "research"
    store = m.ResearchStore(path, manifest())
    store.retain_transport()
    assert store.close() is False
    with pytest.raises(m.ResearchRefusal, match="writer_held"):
        m.ResearchStore(path, manifest())
    store.release_transport()
    assert store.closed is True
    with m.ResearchStore(path, manifest()):
        pass


def test_store_refuses_dispatch_after_directory_privacy_changes(tmp_path):
    m = module()
    path = tmp_path / "research"
    with m.ResearchStore(path, manifest()) as store:
        path.chmod(0o755)
        try:
            with pytest.raises(m.ResearchRefusal, match="private_directory_invalid"):
                store.ensure_dispatch()
        finally:
            path.chmod(0o700)


@pytest.mark.parametrize("change", ["scope", "limits"])
def test_reopen_refuses_changed_manifest_instead_of_resetting_budget(tmp_path, change):
    m = module()
    path = tmp_path / "research"
    with m.ResearchStore(path, manifest()):
        pass
    changed = manifest()
    if change == "scope":
        changed["expiries"] = ["2026-11-20"]
    else:
        changed["limits"]["max_attempts"] = 7
    before = (path / "collector.sqlite3").read_bytes()
    with pytest.raises(m.ResearchRefusal, match="manifest_mismatch"):
        m.ResearchStore(path, changed)
    assert (path / "collector.sqlite3").read_bytes() == before


def test_replaced_guard_inode_is_refused_even_after_previous_writer_exits(tmp_path):
    m = module()
    path = tmp_path / "research"
    with m.ResearchStore(path, manifest()):
        pass
    guard = path / "writer.lock"
    with guard.open("rb"):
        guard.unlink()
        guard.write_bytes(b"")
        guard.chmod(0o600)
        with pytest.raises(m.ResearchRefusal, match="guard_identity_mismatch"):
            m.ResearchStore(path, manifest())


@pytest.mark.parametrize("case", ["symlink_directory", "symlink_db", "hardlink_db", "unexpected_file", "foreign_db"])
def test_foreign_or_unsafe_paths_are_refused_without_overwriting_evidence(tmp_path, case):
    m = module()
    path = tmp_path / "research"
    if case == "symlink_directory":
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        path.symlink_to(target, target_is_directory=True)
    elif case == "unexpected_file":
        path.mkdir(mode=0o700)
        (path / "private.env").write_text("synthetic-preserved")
    elif case == "foreign_db":
        path.mkdir(mode=0o700)
        with sqlite3.connect(path / "collector.sqlite3") as conn:
            conn.execute("CREATE TABLE foreign_history (value TEXT)")
            conn.execute("INSERT INTO foreign_history VALUES ('preserved')")
        (path / "collector.sqlite3").chmod(0o600)
    else:
        with m.ResearchStore(path, manifest()):
            pass
        db = path / "collector.sqlite3"
        if case == "hardlink_db":
            os.link(db, tmp_path / "other-name")
        else:
            db.rename(tmp_path / "original")
            db.symlink_to(tmp_path / "original")
    with pytest.raises(m.ResearchRefusal):
        m.ResearchStore(path, manifest())
    if case == "unexpected_file":
        assert (path / "private.env").read_text() == "synthetic-preserved"
    if case == "foreign_db":
        with sqlite3.connect(path / "collector.sqlite3") as conn:
            assert conn.execute("SELECT value FROM foreign_history").fetchone() == ("preserved",)


def test_parsed_row_cap_failure_preserves_already_committed_raw_evidence(tmp_path):
    m = module()
    body = b'{"calls":[]}'
    with m.ResearchStore(tmp_path / "research", manifest(max_rows=1)) as store:
        attempt = reserved(store)
        store.record_response(attempt, metadata(body), body)
        with pytest.raises(m.ResearchRefusal, match="row_cap"):
            store.record_parsed(attempt, [{"symbol": "SPY"}, {"symbol": "SPY"}],
                                {"status": "parsed", "parsed_at": AT, "errors": 0, "truncated": False})
        assert store.attempts("cycle-1")[0]["body"] == body
        assert store.attempts("cycle-1")[0]["status"] == "raw_committed"
        assert store.observations(attempt) == []


def test_sqlite_page_ceiling_commit_failure_never_acknowledges_raw_body(tmp_path):
    m = module()
    body = b"x" * 200000
    with m.ResearchStore(tmp_path / "research", manifest(max_db_pages=32)) as store:
        attempt = reserved(store)
        with pytest.raises(m.ResearchRefusal, match="store_commit_failed"):
            store.record_response(attempt, metadata(body), body)
        assert store.attempts("cycle-1")[0]["body"] is None
        assert store.attempts("cycle-1")[0]["status"] == "dispatching"
        assert store.status()["page_count"] <= 32


@pytest.mark.parametrize("payload", [b'{"accessToken":"synthetic-never-save"}', b"Bearer synthetic-never-save"])
def test_storage_rejects_sensitive_body_even_if_caller_mislabels_it(tmp_path, payload):
    m = module()
    with m.ResearchStore(tmp_path / "research", manifest()) as store:
        attempt = reserved(store)
        with pytest.raises(m.ResearchRefusal, match="sensitive_body"):
            store.record_response(attempt, metadata(payload), payload)
        assert b"synthetic-never-save" not in (tmp_path / "research" / "collector.sqlite3").read_bytes()


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), 9])
def test_invalid_or_expanded_attempt_limits_refuse_before_creating_directory(tmp_path, value):
    m = module()
    path = tmp_path / "research"
    with pytest.raises(m.ResearchRefusal, match="manifest_invalid"):
        m.ResearchStore(path, manifest(max_attempts=value))
    assert not path.exists()

def test_second_cycle_cannot_begin_while_another_cycle_is_collecting(tmp_path):
    m = module()
    with m.ResearchStore(tmp_path / "research", manifest()) as store:
        assert store.begin_cycle("first", "XNYS:2026-11-06") is None
        with pytest.raises(m.ResearchRefusal, match="cycle_in_progress"):
            store.begin_cycle("second", "XNYS:2026-11-06")


def test_incomplete_receipt_cannot_claim_a_full_body_hash(tmp_path):
    m = module()
    with m.ResearchStore(tmp_path / "research", manifest()) as store:
        attempt = reserved(store)
        value = metadata(b"prefix")
        value.update(body_complete=False, withholding_reason="incomplete_body")
        with pytest.raises(m.ResearchRefusal, match="metadata_invalid"):
            store.record_response(attempt, value, b"")


def test_parsed_observations_must_be_objects(tmp_path):
    m = module()
    with m.ResearchStore(tmp_path / "research", manifest()) as store:
        attempt = reserved(store)
        body = b"{}"
        store.record_response(attempt, metadata(body), body)
        with pytest.raises(m.ResearchRefusal, match="parsed_payload_invalid"):
            store.record_parsed(attempt, ["not-an-observation"],
                                {"status": "parsed", "parsed_at": AT, "errors": 0, "truncated": False})


def test_full_retained_capacity_refuses_next_reservation_without_spending_an_attempt(tmp_path):
    m = module()
    body = b"{}" + b" " * 510
    with m.ResearchStore(tmp_path / "research", manifest(max_body_bytes=512, max_total_body_bytes=512)) as store:
        attempt = reserved(store)
        store.record_response(attempt, metadata(body), body)
        with pytest.raises(m.ResearchRefusal, match="retained_byte_cap"):
            store.reserve_attempt("cycle-1", {"kind": "quotes", "symbol": "QQQ", "expiry": None})
        assert store.status()["reserved_attempts"] == 1
        assert store.status()["retained_body_bytes"] == 512
        assert store.attempts("cycle-1")[0]["body"] == body


def test_old_parser_manifest_cannot_silently_receive_corrected_identity_semantics(tmp_path):
    m = module()
    old = manifest()
    old["parser_id"] = "public-option-contract+strict-research.v1"
    with pytest.raises(m.ResearchRefusal, match="manifest_invalid"):
        m.ResearchStore(tmp_path / "research", old)
    assert not (tmp_path / "research").exists()
