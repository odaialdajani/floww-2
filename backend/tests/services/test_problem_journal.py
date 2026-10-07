import json
import logging

from services.problem_journal import ProblemHandler, ProblemJournal, redact


def test_durable_repeat_counts_and_observed_recovery(tmp_path):
    store = ProblemJournal(tmp_path)
    event = {"kind": "read_error", "route": "/api/agent/models?token=private", "method": "GET", "status": 503}
    store.record(event)
    store.record(event)
    store.record({"kind": "recovery", "route": "/api/agent/models", "method": "GET", "result": "attempted"})
    store.record({"kind": "recovery", "route": "/api/agent/models", "method": "GET", "result": "succeeded"})
    store.close()
    reopened = ProblemJournal(tmp_path)
    summary = reopened.summary()
    assert summary["recurring"] == 1
    assert summary["issues"][0]["count"] == 2
    assert summary["issues"][0]["route"] == "/api/agent/models"
    assert summary["recoveries"][0]["attempted"] == 1
    assert summary["recoveries"][0]["succeeded"] == 1
    assert "private" not in (tmp_path / "events.jsonl").read_text()
    reopened.close()


def test_log_excludes_bodies_keys_and_cookies(tmp_path):
    store = ProblemJournal(tmp_path)
    store.record({"kind": "browser_error", "name": "TypeError", "question": "private question",
                  "body": "secret body", "cookie": "private cookie"})
    text = (tmp_path / "events.jsonl").read_text()
    assert "private" not in text and "secret body" not in text
    assert "TypeError" in text
    store.close()
    cleaned = redact("Authorization=secret-value Bearer abc123 https://example.com?q=private api_key=hidden-value")
    assert "secret-value" not in cleaned and "abc123" not in cleaned and "private" not in cleaned and "hidden-value" not in cleaned


def test_journal_rotates_and_caps_issue_groups(tmp_path):
    store = ProblemJournal(tmp_path)
    store.events.maxBytes = 300
    for number in range(305):
        store.record({"kind": "read_error", "route": f"/api/example/{number}", "status": 503})
    assert len(store.state["issues"]) == 300
    assert store.summary()["total_events"] == 305
    assert len(list(tmp_path.glob("events.jsonl*"))) <= 4
    json.loads((tmp_path / "summary.json").read_text())
    store.close()


def test_logging_failure_never_raises(monkeypatch):
    import services.problem_journal as module
    monkeypatch.setattr(module, "journal", lambda: (_ for _ in ()).throw(OSError("disk full")))
    assert module.record_problem({"kind": "browser_error"}) is False
    ProblemHandler().emit(logging.makeLogRecord({"msg": "failure", "levelno": logging.ERROR, "name": "test"}))


def test_arbitrary_server_log_text_never_reaches_issue_files(tmp_path):
    store = ProblemJournal(tmp_path)
    store.record({"kind": "server_log", "source": "server.startup", "message":
                  '{"password": "plain-password", "api_key": "short-secret", "question": "private-question"} https://user:plain-password@example.com/path'})
    saved = (tmp_path / "events.jsonl").read_text() + (tmp_path / "summary.json").read_text()
    for secret in ("plain-password", "short-secret", "private-question", "example.com"):
        assert secret not in saved
    store.close()


def test_replayed_browser_report_is_counted_once(tmp_path):
    store = ProblemJournal(tmp_path)
    event = {"kind":"browser_error", "name":"TypeError", "event_id":"11111111-1111-4111-8111-111111111111"}
    store.record(event)
    store.record(event)
    assert store.summary()["total_events"] == 1
    store.close()
    store=ProblemJournal(tmp_path)
    store.record(event)
    assert store.summary()["total_events"] == 1
    store.close()


def test_failed_disk_save_does_not_mark_report_saved(monkeypatch, tmp_path):
    from pathlib import Path

    import pytest
    store = ProblemJournal(tmp_path)
    event = {"kind":"browser_error", "event_id":"22222222-2222-4222-8222-222222222222"}
    original = Path.write_text
    failed = False
    def fail_once(path, *args, **kwargs):
        nonlocal failed
        if path.name == "summary.pending" and not failed:
            failed = True
            raise OSError("disk temporarily unavailable")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", fail_once)
    with pytest.raises(OSError):
        store.record(event)
    assert store.summary()["total_events"] == 0
    assert event["event_id"] not in store.state["processed_events"]
    store.record(event)
    assert store.summary()["total_events"] == 1
    assert (tmp_path / "summary.json").exists()
    store.close()


def test_default_journal_cannot_touch_app_files_during_tests(monkeypatch):
    import pytest

    import services.problem_journal as module
    monkeypatch.delenv("FLOWW_PROBLEM_LOG_DIR", raising=False)
    with pytest.raises(RuntimeError, match="isolated"):
        module.journal()
