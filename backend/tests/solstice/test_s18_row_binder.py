"""S08 raw row and executable payload binder: column/payload probe.

Stored columns and the stored JSON payload must agree: a same-ID row
whose columns were altered out from under its payload refuses instead
of verifying. Fake store only; no broker, no live calls.
"""
import sys

sys.path.insert(0, "backend")


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


def _mint(conn, adm, operators):
    assert operators.register_operator(
        conn, "op-1", ["ACCT-1"], "root")["ok"] is True
    assert adm.set_account_policy_required(
        conn, "ACCT-1", {"max_quantity": 5}, "op-1")["ok"] is True
    created = adm.create_order_approval(
        conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1",
        order_type="LIMIT", instrument_type="EQUITY")
    assert created["ok"] is True, created
    return created["approval_id"]


def test_altered_columns_refuse():
    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        approval_id = _mint(conn, adm, operators)
        # Direct raw-row alteration: columns now disagree with the payload.
        conn.execute(
            "UPDATE approvals_v1 SET account_id = 'OTHER-ACCT' "
            "WHERE approval_id = ?", [approval_id])
        out = adm.verify_order_approval(
            conn, approval_id, "ACCT-1", "SPY", "BUY", 1, 3.15,
            order_type="LIMIT", instrument_type="EQUITY", operator="op-1")
        assert out.get("ok") is False, out
        assert out.get("reason") in ("APPROVAL_INVALID",
                                     "APPROVAL_STORE_UNAVAILABLE"), out
    finally:
        conn.close()
        lc._reset_for_tests()


def test_altered_payload_hash_refuses():
    import json

    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        approval_id = _mint(conn, adm, operators)
        row = conn.execute(
            "SELECT approval_json FROM approvals_v1 WHERE approval_id = ?",
            [approval_id]).fetchone()
        payload = json.loads(row[0])
        payload["intent_hash"] = "0" * 64
        conn.execute(
            "UPDATE approvals_v1 SET approval_json = ? WHERE approval_id = ?",
            [json.dumps(payload), approval_id])
        out = adm.verify_order_approval(
            conn, approval_id, "ACCT-1", "SPY", "BUY", 1, 3.15,
            order_type="LIMIT", instrument_type="EQUITY", operator="op-1")
        assert out.get("ok") is False, out
        assert out.get("reason") == "APPROVAL_INVALID", out
    finally:
        conn.close()
        lc._reset_for_tests()
