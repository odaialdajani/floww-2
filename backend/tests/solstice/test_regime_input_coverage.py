"""A missing side of the chain must not manufacture the opposite market regime."""
import math

import pytest

from services.solstice_regime import regime_at_spot


def pair():
    common = {"strike": 100, "gamma": .01, "iv": .2, "T": .1, "multiplier": 100}
    return [{**common, "type": "call", "oi": 200},
            {**common, "type": "put", "oi": 100}]


@pytest.mark.parametrize("field", ["iv", "T", "oi", "strike", "type"])
def test_missing_active_contract_input_never_flips_to_surviving_side(field):
    rows = pair()
    complete = regime_at_spot(100, rows)
    assert complete["sign"] == "POSITIVE"
    rows[0][field] = None
    result = regime_at_spot(100, rows)
    assert result["sign"] == "UNKNOWN"
    assert result["modeled_at_spot"] is None
    assert result["roots"] == []
    assert result["model_coverage"]["status"] == "partial"
    assert result["model_coverage"]["usable"] == 1
    assert result["model_coverage"]["requested"] == 2


def test_all_missing_model_inputs_are_not_zero_or_a_hundred_roots():
    rows = [dict(row, iv=None) for row in pair()]
    result = regime_at_spot(100, rows)
    assert result["sign"] == "UNKNOWN"
    assert result["roots"] == []
    assert result["vendor_at_spot"] == 10000
    assert result["model_coverage"]["status"] == "unavailable"


def test_zero_vendor_gamma_does_not_replace_the_modeled_sign():
    row = dict(pair()[0], gamma=0)
    result = regime_at_spot(100, [row])
    assert result["modeled_at_spot"] > 0
    assert result["sign"] == "POSITIVE"
    assert result["vendor_at_spot"] == 0
    assert result["model_vendor_residual"] == result["modeled_at_spot"]
    assert result["sign_basis"] == "frozen_oi_iv_model"


def test_missing_vendor_gamma_does_not_block_complete_modeled_inputs():
    rows = [dict(row, gamma=None) for row in pair()]
    result = regime_at_spot(100, rows)
    assert result["sign"] == "POSITIVE"
    assert result["vendor_at_spot"] is None
    assert result["model_vendor_residual"] is None


def test_known_zero_interest_needs_no_volatility_and_does_not_hide_the_other_side():
    rows = pair()
    rows[0].update(oi=0, iv=None, T=None)
    result = regime_at_spot(100, rows)
    assert result["sign"] == "NEGATIVE"
    assert result["model_coverage"]["status"] == "complete"


def test_true_complete_zero_curve_has_no_isolated_roots():
    rows = pair()
    rows[0]["oi"] = rows[1]["oi"]
    result = regime_at_spot(100, rows)
    assert result["sign"] == "ZERO"
    assert result["modeled_at_spot"] == 0
    assert result["roots"] == []
    assert result["reason"] == "ZERO_CURVE"


@pytest.mark.parametrize("value", [True, math.nan, math.inf, -1])
def test_invalid_positive_interest_input_cannot_publish_a_regime(value):
    rows = pair()
    rows[0]["iv"] = value
    result = regime_at_spot(100, rows)
    assert result["sign"] == "UNKNOWN"
    assert result["roots"] == []
