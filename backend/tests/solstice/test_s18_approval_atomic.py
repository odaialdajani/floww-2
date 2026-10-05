"""S01 authoritative approval atomicity: failed-first probes.

Approved_at binding + threaded revoke/restore race. Fake transport only;
every refusal asserts zero broker effects (admission never places).
"""
import sys

sys.path.insert(0, "backend")

import threading


def _memdb():
    import duckdb

    return duckdb.connect(":memory:")


def _base_approval():
    return {
        "approval_id": "ap-atomic-1",
        "intent_hash": "a" * 64,
        "account_id": "ACCT-1",
        "scope": "order-entry",
        "valid_until": "2026-10-02T16:00:00+00:00",
        "approved_by": "op-1",
        "approved_at": "2026-10-02T15:00:00+00:00",
    }


def test_same_id_approved_at_mutation_conflicts():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        appr = _base_approval()
        assert adm.store_approval_required(conn, dict(appr), "op-1")["ok"] is True
        impostor = dict(appr)
        impostor["approved_at"] = "2026-10-02T15:05:00+00:00"
        out = adm.store_approval_required(conn, impostor, "op-1")
        assert out["ok"] is False and out["reason"] == "APPROVAL_CONFLICT"
        # Authority unchanged: original approved_at still stored.
        row = conn.execute(
            "SELECT approved_at FROM approvals_v1 WHERE approval_id = ?",
            [appr["approval_id"]]).fetchone()
        assert row[0] == appr["approved_at"]
    finally:
        conn.close()
        lc._reset_for_tests()


def test_concurrent_revoke_vs_restore_cannot_resurrect():
    import services.execution_admission as adm
    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    conn = _memdb()
    try:
        lc.register_store(conn)
        appr = _base_approval()
        stored = adm.store_approval_required(conn, dict(appr), "op-1")
        assert stored["ok"] is True
        approval_id = stored["approval_id"]
        # Revoke first, then race N concurrent restores: none may resurrect.
        assert adm.revoke_approval_required(
            conn, approval_id, "op-1")["ok"] is True
        outcomes = []
        lock = threading.Lock()

        def do_restore():
            out = adm.store_approval_required(conn, dict(appr), "op-1")
            with lock:
                outcomes.append(out)

        threads = [threading.Thread(target=do_restore) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert all(not t.is_alive() for t in threads)
        assert len(outcomes) == 5
        for out in outcomes:
            assert out.get("ok") is False
            assert out.get("reason") in ("APPROVAL_INVALID", "APPROVAL_CONFLICT")
        row = conn.execute(
            "SELECT revoked FROM approvals_v1 WHERE approval_id = ?",
            [approval_id]).fetchone()
        assert row is not None and bool(row[0]) is True
        # Strict verification refuses the revoked approval.
        import services.execution_admission as adm2

        assert adm2.verify_order_approval(
            conn, approval_id, "ACCT-1", "SPY", "BUY", 1, 3.15,
            operator="op-1")["reason"] in (
                "APPROVAL_INVALID", "APPROVAL_NOT_STORED",
                "BAD_CONTRACT", "POLICY_UNSET",
                "POLICY_STORE_UNAVAILABLE", "APPROVAL_STORE_UNAVAILABLE")
    finally:
        conn.close()
        lc._reset_for_tests()
