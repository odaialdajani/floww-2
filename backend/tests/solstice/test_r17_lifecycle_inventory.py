"""R17-4 lifecycle inventory: authenticated, default-deny, read-only.

The route under test performs no broker calls, no recovery, no activation and
no live path; lifecycle state is isolated per test like the existing R15
lifecycle tests. Auth is exercised exactly as the other Public routes do it.
"""

import sys

sys.path.insert(0, "backend")

_KEY = "test-secret-key"  # matches backend/tests/conftest.py


def _client():
    from fastapi.testclient import TestClient

    from server import app

    return TestClient(app, raise_server_exceptions=False)


def test_inventory_is_default_deny_when_unconfigured(monkeypatch):
    from services import public_execution_lifecycle as lc

    lc._reset_for_tests()
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    r = _client().get("/api/public/execution-lifecycle/inventory")
    assert r.status_code == 503, r.text  # unconfigured → disabled, not open


def test_inventory_refuses_wrong_key(monkeypatch):
    from services import public_execution_lifecycle as lc

    lc._reset_for_tests()
    monkeypatch.setenv("API_SECRET_KEY", _KEY)
    r = _client().get("/api/public/execution-lifecycle/inventory",
                      headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401, r.text


def test_inventory_reports_storeless_boundary_honestly(monkeypatch):
    from services import public_execution_lifecycle as lc

    lc._reset_for_tests()
    monkeypatch.setenv("API_SECRET_KEY", _KEY)
    r = _client().get("/api/public/execution-lifecycle/inventory",
                      headers={"X-API-Key": _KEY})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == "lifecycle-inventory.v1"
    assert body["storeless"] is True and body["durable"] is False
    assert body["intents"]["n_known"] == 0 and body["intents"]["open"] == []
    # Storeless is never claimed as proof that no orders are open.
    assert body["recovery"]["durable_nonterminal_rows"] is None
    assert body["live_submission_armed"] is False
    assert body["policy"]["account_wide_limits"] == "UNSET"
    assert body["protection"]["cancel_allowed_during_pause"] is True


def test_inventory_reports_open_unknown_and_native_without_broker(monkeypatch):
    from services import public_execution_lifecycle as lc

    lc._reset_for_tests()
    monkeypatch.setenv("API_SECRET_KEY", _KEY)
    lc.register_native_workflow("swing-entry", "public", "REVIEW_PENDING", "corr-1")
    # Seed the in-memory registry the way the submit path does (no broker).
    lc._INTENTS["in_testopen1"] = {
        "intent": {"ticker": "SPY", "execution_owner": "FLOWW_BACKEND"},
        "intent_hash": "abc", "order_id": "ord-1", "state": "OPEN",
        "approval": {"intent_hash": "abc"},
    }
    lc._INTENTS["in_testunk1"] = {
        "intent": {"ticker": "SPY", "execution_owner": "FLOWW_BACKEND"},
        "intent_hash": "def", "order_id": "ord-2", "state": "UNKNOWN",
        "error": "TimeoutError: ambiguous",
    }
    r = _client().get("/api/public/execution-lifecycle/inventory",
                      headers={"X-API-Key": _KEY})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intents"]["n_open"] == 1 and body["intents"]["n_unknown"] == 1
    assert body["intents"]["open"][0]["order_id"] == "ord-1"
    assert body["intents"]["open"][0]["has_approval"] is True
    assert body["intents"]["open"][0]["protection"]["protected"] is False
    assert body["intents"]["unknown"][0]["error"] == "TimeoutError: ambiguous"
    assert body["native_workflows"] == [
        {"strategy": "swing-entry", "venue": "public", "status": "REVIEW_PENDING",
         "correlation": "corr-1"}]
    assert body["live_submission_armed"] is False


def test_inventory_counts_durable_nonterminal_rows_readonly(monkeypatch):
    import tempfile

    import duckdb

    from services import public_execution_lifecycle as lc

    lc._reset_for_tests()
    monkeypatch.setenv("API_SECRET_KEY", _KEY)
    with tempfile.TemporaryDirectory() as tmp:
        conn = duckdb.connect(f"{tmp}/inv.db")
        try:
            assert lc.register_store(conn) is True
            conn.execute(
                "INSERT INTO execution_intents_v1 "
                "(intent_id, intent_hash, ticker, owner, state, order_id, "
                "record_json, updated_at) VALUES "
                "('in_dur1', 'h', 'SPY', 'FLOWW_BACKEND', 'OPEN', 'ord-9', '{}', 'now'), "
                "('in_dur2', 'h', 'SPY', 'FLOWW_BACKEND', 'FILLED', 'ord-8', '{}', 'now')")
            body = lc.lifecycle_inventory()
            # Read-only count: the OPEN row is durable and not yet rehydrated;
            # the FILLED row stays history. In-memory known stays 0 — the
            # inventory discloses both sides of the boundary honestly.
            assert body["durable"] is True and body["storeless"] is False
            assert body["recovery"]["durable_nonterminal_rows"] == 1
            assert body["intents"]["n_known"] == 0
        finally:
            conn.close()
