"""S02 authenticated principal and account authority: failed-first probes.

Cross-account mint, removed principal, and shared-key-only identity must
refuse with zero broker effects. Fake transport only.
"""
import sys

sys.path.insert(0, "backend")


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


def _policy(conn, adm, account="ACCT-1", operator="op-1"):
    assert adm.set_account_policy_required(
        conn, account, {"max_quantity": 5}, operator)["ok"] is True


def test_cross_account_mint_refuses():
    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        _policy(conn, adm)
        assert operators.register_operator(
            conn, "mallory", ["OTHER-ACCT"], "op-1")["ok"] is True
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "mallory")
        assert out.get("ok") is False
        assert out.get("reason") in ("OPERATOR_UNAUTHORIZED", "OPERATOR_UNKNOWN")
    finally:
        conn.close()
        lc._reset_for_tests()


def test_removed_principal_mint_and_verify_refuse():
    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        _policy(conn, adm)
        assert operators.register_operator(
            conn, "op-1", ["ACCT-1"], "op-1")["ok"] is True
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1")
        assert created.get("ok") is True
        assert operators.remove_operator(conn, "op-1")["ok"] is True
        # Minting as a removed principal refuses.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "op-1")
        assert out.get("ok") is False
        assert out.get("reason") == "OPERATOR_UNKNOWN"
        # Verifying as a removed principal refuses even with a valid approval.
        voir = adm.verify_order_approval(
            conn, created["approval_id"], "ACCT-1", "SPY", "BUY", 1, 3.15,
            operator="op-1")
        assert voir.get("ok") is False
        assert voir.get("reason") in ("OPERATOR_UNKNOWN", "APPROVAL_INVALID")
    finally:
        conn.close()
        lc._reset_for_tests()


def test_shared_key_only_identity_refuses():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        _policy(conn, adm)
        # "ghost" holds the shared master key but is in no registry.
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY", "BUY", 1, 3.15, "ghost")
        assert out.get("ok") is False
        assert out.get("reason") == "OPERATOR_UNKNOWN"
    finally:
        conn.close()
        lc._reset_for_tests()
