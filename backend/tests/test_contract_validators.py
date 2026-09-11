"""
backend/tests/test_contract_validators.py — Agent D (D3 data-contract
enforcement). Provider-boundary validators: malformed payloads are
quarantined with counters, never raised into callers.
"""
from __future__ import annotations

import random
import sys


def _ensure_imports():
    if "services.contract_validators" not in sys.modules:
        sys.path.insert(0, "/Users/nav/Documents/GitHub/floww/backend")


_ensure_imports()

GOOD_BAR = {"t": "2026-09-05T10:00:00-04:00", "o": 100.0, "h": 101.5,
            "l": 99.5, "c": 101.0, "v": 12000}
GOOD_ROW = ["SPY", "O:SPY261218C00760000", "call", 760.0, "2026-12-18",
            200000, 2000, 0.5, 0.3, 758.0]
GOOD_QUOTE = {"bid": 1.2, "ask": 1.4, "last": 1.3}


def test_valid_payloads_pass():
    from services.contract_validators import (
        validate_bar,
        validate_chain_row,
        validate_quote,
    )

    assert validate_bar(GOOD_BAR)[0] is True
    assert validate_chain_row(GOOD_ROW)[0] is True
    assert validate_quote(GOOD_QUOTE)[0] is True


def test_malformed_bars_quarantined_with_reason():
    from services.contract_validators import validate_bar

    cases = [
        dict(GOOD_BAR, h=98.0),          # high < low
        dict(GOOD_BAR, o=102.0),         # open above high
        dict(GOOD_BAR, c=99.0),          # close below low
        dict(GOOD_BAR, v=-5),            # negative volume
        {k: v for k, v in GOOD_BAR.items() if k != "h"},  # missing key
        dict(GOOD_BAR, h=float("nan")),  # NaN poisons aggregates
        dict(GOOD_BAR, c=float("inf")),  # Inf poisons aggregates
        dict(GOOD_BAR, o="bad"),         # non-numeric
        "not-a-dict",
        None,
    ]
    for bad in cases:
        ok, reason = validate_bar(bad)
        assert ok is False and isinstance(reason, str) and reason, bad


def test_malformed_rows_and_quotes_quarantined():
    from services.contract_validators import validate_chain_row, validate_quote

    assert validate_chain_row(GOOD_ROW[:9])[0] is False      # wrong length
    assert validate_chain_row(list(GOOD_ROW[:4]) + [-1.0] + list(GOOD_ROW[5:]))[0] is False  # bad strike
    assert validate_chain_row(list(GOOD_ROW[:4]) + ["not-a-date"] + list(GOOD_ROW[5:]))[0] is False
    assert validate_chain_row(list(GOOD_ROW[:5]) + [-3] + list(GOOD_ROW[6:]))[0] is False  # neg vol
    ok, reason = validate_quote({"bid": 1.5, "ask": 1.4, "last": 1.45})
    assert ok is False and "crossed" in reason
    ok, _ = validate_quote({"bid": None, "ask": 1.4, "last": 1.3})
    assert ok is True  # one-sided quote = unknown, not malformed


def test_batch_and_quarantine_store():
    from services.contract_validators import Quarantine, validate_bar, validate_batch

    q = Quarantine(max_items=10)
    valid, n = validate_batch("public_1min", [GOOD_BAR, dict(GOOD_BAR, h=1.0),
                                              dict(GOOD_BAR, v=-2)], validate_bar, q)
    assert len(valid) == 1 and n == 2
    assert q.counts()["public_1min"] == 2
    assert all("reason" in item for item in q.items())


def test_quarantine_bounded_and_never_raises():
    from services.contract_validators import Quarantine

    q = Quarantine(max_items=5)
    for i in range(20):
        q.submit("src", {"i": i}, f"reason-{i}")
    assert len(q.items()) == 5
    assert q.counts()["src"] == 20
    q.submit("src", object(), "odd-object")  # unserializable payload must not raise


def test_fuzz_malformed_bars_never_raise():
    from services.contract_validators import validate_bar

    rng = random.Random(20260905)
    keys = ["t", "o", "h", "l", "c", "v"]
    weird = [None, "x", -1.0, float("nan"), float("inf"), 1e18, {}, [], True]
    for _ in range(500):
        bar = {k: rng.choice(weird) for k in keys}
        if rng.random() < 0.1:
            bar = dict(GOOD_BAR)  # canary: valid bars must always pass
            ok, _ = validate_bar(bar)
            assert ok is True
        else:
            ok, reason = validate_bar(bar)
            assert isinstance(ok, bool) and (ok or isinstance(reason, str))
