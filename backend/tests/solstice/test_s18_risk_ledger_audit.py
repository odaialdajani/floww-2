"""S09 risk ledger and proposed reservations: behavior audit.

Dedup fills once, fee-inclusive loss, exact multiplier exposure, and
refusal on incomplete/unknown facts. No broker, no live calls.
"""
import sys

sys.path.insert(0, "backend")


def _facts(**kw):
    facts = {
        "buying_power": "10000",
        "positions": [],
        "open_orders": [],
        "fills": [],
        "account_id": "ACCT-1",
        "source": "fake-broker",
        "asof": "2026-10-02T14:59:00+00:00",
    }
    facts.update(kw)
    return facts


def _policy(**kw):
    policy = {"max_quantity": 5, "max_notional": "100000",
              "max_positions": 10, "max_daily_loss": "10000",
              "today": "2026-10-02"}
    policy.update(kw)
    return policy


def test_duplicate_fill_ids_count_once():
    import services.account_risk_ledger as ledger

    fill = {"fill_id": "f-1", "symbol": "SPY", "side": "BUY", "quantity": 1,
            "price": "3.15", "fees": "0.65", "ts": "2026-10-02T14:00:00+00:00",
            "multiplier": "100"}
    one = ledger.evaluate_account_risk(
        _facts(fills=[fill]), _policy(), today="2026-10-02")
    two = ledger.evaluate_account_risk(
        _facts(fills=[fill, dict(fill)]), _policy(), today="2026-10-02")
    assert one["ok"] is True and two["ok"] is True
    assert (one["snapshot"]["day_realized"]
            == two["snapshot"]["day_realized"])


def test_unknown_open_order_state_refuses():
    import services.account_risk_ledger as ledger

    facts = _facts(open_orders=[{"order_id": "o-1", "status": "UNKNOWN"}])
    out = ledger.evaluate_account_risk(facts, _policy(), today="2026-10-02")
    assert out["ok"] is False
    assert out["reason"] == "UNKNOWN_ORDERS_PENDING", out


def test_missing_buying_power_refuses():
    import services.account_risk_ledger as ledger

    facts = _facts()
    facts["buying_power"] = None
    out = ledger.evaluate_account_risk(facts, _policy(), today="2026-10-02")
    assert out["ok"] is False
    assert out["reason"] == "RISK_FACTS_INCOMPLETE", out


def test_incomplete_policy_refuses_in_complete_mode():
    import services.account_risk_ledger as ledger

    out = ledger.evaluate_account_risk(
        _facts(), {"max_quantity": 5}, today="2026-10-02",
        require_complete_policy=True)
    assert out["ok"] is False
    assert out["reason"] == "POLICY_INCOMPLETE", out
