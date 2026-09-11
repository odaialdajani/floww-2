"""Agent C (C7): ex-post value per rule, net of slippage — feeds Sync-3 kill/keep.

rule_value_table consumes labeled ledger rows (flow_outcomes.label_alerts
shape: rule/hit/ret/censored) and scores each rule on realized edge net
of estimated cost. Thin rules stay THIN (unjudged), never CUT.
"""
import pytest

from services.flow_outcomes import rule_value_table


def _row(rule, ret=None, censored=False, slip=25.0):
    return {"rule": rule, "ret": ret, "hit": ret is not None and abs(ret) >= 0.01,
            "censored": censored, "slippage_bps_est": slip}


def test_value_table_hand_worked():
    rows = [
        _row("SCORE", 0.020), _row("SCORE", 0.015),
        _row("SCORE", -0.005), _row("SCORE", 0.010),
        _row("SCORE", 0.012), _row("SCORE", 0.008),
        _row("SCORE", -0.003), _row("SCORE", 0.020),
        _row("SCORE", 0.011), _row("SCORE", 0.005),
        _row("SCORE", None, censored=True),
        _row("WHALE", 0.030),
        _row("PRIME", -0.020), _row("PRIME", -0.015), _row("PRIME", -0.010),
        _row("PRIME", -0.025), _row("PRIME", -0.018), _row("PRIME", -0.012),
        _row("PRIME", -0.022), _row("PRIME", -0.008), _row("PRIME", -0.019),
        _row("PRIME", -0.011), _row("PRIME", -0.016),
    ]
    out = rule_value_table(rows)
    score = out["SCORE"]
    assert score["n_measured"] == 10
    assert score["hit_rate"] == pytest.approx(0.6)
    # avg ret 0.0093 minus 25bps cost → 0.0068 net
    assert score["avg_edge_net"] == pytest.approx(0.0068)
    assert score["verdict"] == "KEEP"
    assert out["WHALE"]["verdict"] == "THIN", "n=1 must stay unjudged"
    assert out["PRIME"]["verdict"] == "CUT"


def test_empty_is_empty():
    assert rule_value_table([]) == {}
    assert rule_value_table([_row("SCORE", None, censored=True)])["SCORE"]["verdict"] == "THIN"
