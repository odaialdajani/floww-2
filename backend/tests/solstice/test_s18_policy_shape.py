"""S07 mandatory versioned complete policy: typo-ceiling probe.

A misspelled ceiling must refuse at install (BAD_CONTRACT) instead of
installing a policy that silently enforces nothing. Missing real operator
values stay UNSET; this test invents no production numbers.
"""
import sys

sys.path.insert(0, "backend")


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


def test_typo_ceiling_refuses_at_install():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        out = adm.set_account_policy_required(
            conn, "ACCT-1", {"max_quantitiy": 1}, "op-1")
        assert out["ok"] is False
        assert out["reason"].startswith("BAD_CONTRACT"), out
        # No policy was installed by the refused write.
        assert adm.get_account_policy_required(
            conn, "ACCT-1")["reason"] == "POLICY_UNSET"
    finally:
        conn.close()
        lc._reset_for_tests()


def test_known_fields_still_install():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        policy = {"max_quantity": 5, "max_notional": "100000",
                  "max_positions": 10, "max_daily_loss": "10000",
                  "today": "2026-10-02", "min_entry_dte": 5,
                  "allow_unprotected_entry": True,
                  "same_day_cutoff_et": "13:00",
                  "allowed_products": ["OPTION", "EQUITY"]}
        assert adm.set_account_policy_required(
            conn, "ACCT-1", policy, "op-1")["ok"] is True
    finally:
        conn.close()
        lc._reset_for_tests()


def test_disallowed_product_refuses_at_creation_and_verify():
    import services.execution_admission as adm
    import services.operator_registry as operators
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        assert operators.register_operator(
            conn, "op-1", ["ACCT-1"], "root")["ok"] is True
        assert adm.set_account_policy_required(
            conn, "ACCT-1",
            {"max_quantity": 5, "min_entry_dte": 5,
             "allow_unprotected_entry": True,
             "allowed_products": ["EQUITY"]}, "op-1")["ok"] is True
        out = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="OPTION")
        assert out["reason"] == "UNSUPPORTED_PRODUCT", out
        # Narrowing the allowlist after mint refuses at verify.
        assert adm.set_account_policy_required(
            conn, "ACCT-1",
            {"max_quantity": 5, "min_entry_dte": 5,
             "allow_unprotected_entry": True,
             "allowed_products": ["OPTION", "EQUITY"]},
            "op-1")["ok"] is True
        created = adm.create_order_approval(
            conn, "ACCT-1", "SPY271217C00760000", "BUY", 1, 3.15, "op-1",
            order_type="LIMIT", instrument_type="OPTION")
        assert created["ok"] is True, created
        assert adm.set_account_policy_required(
            conn, "ACCT-1",
            {"max_quantity": 5, "min_entry_dte": 5,
             "allow_unprotected_entry": True,
             "allowed_products": ["EQUITY"]}, "op-1")["ok"] is True
        out = adm.verify_order_approval(
            conn, created["approval_id"], "ACCT-1",
            "SPY271217C00760000", "BUY", 1, 3.15, order_type="LIMIT",
            instrument_type="OPTION", operator="op-1")
        assert out["reason"] == "UNSUPPORTED_PRODUCT", out
    finally:
        conn.close()
        lc._reset_for_tests()
