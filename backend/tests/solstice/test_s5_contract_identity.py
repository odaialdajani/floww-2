"""S5 exact contract identity for review (Spark).

R10-13's backend half: contract detail must resolve an EXPLICIT identity,
never a wall midpoint plus the first expiry. These pin that, plus exact
decimal strike identity, per-leg quote age/spread with unknown preserved,
and the honest record of what the mounted Triad client actually requests.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.contract_identity import (  # noqa: E402
    REASON_AMBIGUOUS,
    REASON_IDENTITY_INCOMPLETE,
    REASON_NO_MATCH,
    REASON_NO_POPULATION,
    contract_identity,
    quote_state,
    resolve_contract,
    triad_request_scope,
)

NOW = datetime(2030, 1, 2, 15, 0, tzinfo=UTC)


def _c(osi, strike, expiry, otype="call", **kw):
    row = {"osi": osi, "strike": strike, "expiry": expiry, "type": otype,
           "bid": 1.00, "ask": 1.10, "last": 1.05,
           "bid_timestamp": "2030-01-02T14:59:00+00:00",
           "ask_timestamp": "2030-01-02T14:59:30+00:00",
           "last_timestamp": "2030-01-02T14:59:45+00:00",
           "data_source": "public_api"}
    row.update(kw)
    return row


POP = [
    _c("A-300-C", "300", "2030-02-21"),
    _c("A-300-P", "300", "2030-02-21", "put"),
    _c("A-300.25-C", "300.25", "2030-02-21"),
    _c("A-301-C", "301", "2030-02-21"),
    _c("A-300-C-MAR", "300", "2030-03-21"),
]


# ---- exact identity ----

def test_decimal_strike_identity_survives():
    ident = contract_identity(_c("A-300.25-C", 300.25, "2030-02-21"))
    assert ident["strike"] == "300.25"
    assert ident["strike"] == str(Decimal("300.25"))
    # A float that has already lost precision must NOT be silently accepted
    # as a different strike.
    assert contract_identity(_c("X", 300.2500001, "2030-02-21"))["strike"] == "300.2500001"


def test_identity_normalizes_string_and_numeric_strike():
    a = contract_identity(_c("A", "100.25", "2030-02-21"))
    b = contract_identity(_c("B", 100.25, "2030-02-21"))
    assert a["strike"] == b["strike"] == "100.25"


def test_type_is_normalized_and_series_is_derived_only_when_absent():
    assert contract_identity(_c("A", 100, "2030-02-21", "CALL"))["type"] == "call"
    derived = contract_identity(_c("A", 100, "2030-02-21"))
    assert derived["series"] == "2030-02-21"
    supplied = contract_identity(_c("A", 100, "2030-02-21", series="SPXW"))
    assert supplied["series"] == "SPXW"


def test_unusable_identity_is_none_not_a_guess():
    assert contract_identity(None) is None
    assert contract_identity({"expiry": "2030-02-21"}) is None  # no strike, no OSI
    assert contract_identity({"strike": "abc"}) is None
    assert contract_identity({"strike": True}) is None


# ---- resolution: exact or nothing ----

def test_resolves_by_osi_exactly():
    out = resolve_contract(POP, {"osi": "A-300.25-C"}, now=NOW)
    assert out["status"] == "ok"
    assert out["matched_identity"]["strike"] == "300.25"
    assert out["quote"]["spread_absolute"] == 0.09999999999999987 or round(
        out["quote"]["spread_absolute"], 6) == 0.1


def test_resolves_by_strike_expiry_type_without_osi():
    out = resolve_contract(POP, {"strike": 300, "expiry": "2030-02-21", "type": "put"}, now=NOW)
    assert out["status"] == "ok"
    assert out["matched_identity"]["osi"] == "A-300-P"


def test_a_wall_midpoint_is_never_substituted():
    """300.5 sits between 300 and 300.25. It must resolve to NOTHING."""
    out = resolve_contract(POP, {"strike": 300.5, "expiry": "2030-02-21", "type": "call"}, now=NOW)
    assert out["status"] == "unavailable"
    assert out["reason"] == REASON_NO_MATCH
    assert out["quote"] is None
    assert "midpoint" in out["note"]


def test_first_expiry_is_never_substituted():
    out = resolve_contract(POP, {"strike": 301, "expiry": "2030-04-18", "type": "call"}, now=NOW)
    assert out["status"] == "unavailable"
    assert out["reason"] == REASON_NO_MATCH


def test_ambiguous_identity_is_reported_not_resolved():
    dup = POP + [_c("A-300-C-DUP", "300", "2030-02-21")]
    out = resolve_contract(dup, {"strike": 300, "expiry": "2030-02-21", "type": "call"}, now=NOW)
    assert out["status"] == "unavailable"
    assert out["reason"] == REASON_AMBIGUOUS
    assert len(out["candidates"]) == 2


def test_incomplete_and_empty_inputs_are_unavailable():
    assert resolve_contract(POP, {}, now=NOW)["reason"] == REASON_IDENTITY_INCOMPLETE
    assert resolve_contract(POP, {"strike": 300}, now=NOW)["reason"] == REASON_IDENTITY_INCOMPLETE
    assert resolve_contract([], {"osi": "A-300-C"}, now=NOW)["reason"] == REASON_NO_POPULATION
    assert resolve_contract(None, {"osi": "A-300-C"}, now=NOW)["reason"] == REASON_NO_POPULATION


# ---- quote age and spread ----

def test_quote_age_and_spread_are_per_leg():
    out = quote_state(_c("A", 300, "2030-02-21"), now=NOW)
    assert out["ages_s"]["bid"] == 60.0
    assert out["ages_s"]["ask"] == 30.0
    assert out["ages_s"]["last"] == 15.0
    assert round(out["spread_absolute"], 6) == 0.1
    assert round(out["spread_percent"], 6) == round(0.1 / 1.05, 6)
    assert out["mid"] == 1.05
    assert out["side_has_aggressor_identity"] is False


def test_missing_timestamp_is_unknown_never_fresh():
    out = quote_state({"bid": 1.0, "ask": 1.1}, now=NOW)
    assert out["ages_s"] == {"bid": None, "ask": None, "last": None}
    assert out["age_reasons"]["bid"] == "NO_TIMESTAMP"
    # A quote with no timestamp is not stale and not fresh: it is unknown.
    assert out["stale"] is None


def test_unparseable_and_future_timestamps_are_labelled():
    bad = quote_state({"bid": 1.0, "ask": 1.1, "bid_timestamp": "nonsense"}, now=NOW)
    assert bad["age_reasons"]["bid"] == "UNPARSEABLE_TIMESTAMP"
    fut = quote_state({"bid": 1.0, "ask": 1.1,
                       "bid_timestamp": (NOW + timedelta(hours=1)).isoformat()}, now=NOW)
    assert fut["age_reasons"]["bid"] == "FUTURE"


def test_complete_prices_without_timestamps_are_not_fresh():
    out = quote_state({"bid": 1.0, "ask": 1.1, "last": 1.05}, now=NOW)
    assert out["stale"] is None
    assert out["age_reasons"]["last"] == "NO_TIMESTAMP"


def test_osi_does_not_override_a_conflicting_explicit_tuple():
    out = resolve_contract(POP, {"osi": "A-300-C", "strike": "300.25",
                                 "expiry": "2030-02-21", "type": "call"}, now=NOW)
    assert out["status"] == "unavailable"
    assert out["reason"] == REASON_NO_MATCH


def test_multiplier_is_not_inferred_from_the_symbol():
    out = resolve_contract(POP, {"osi": "A-300-C"}, now=NOW)
    assert out["multiplier"] == {"value": None, "source": None, "status": "unknown"}


def test_booleans_are_not_quotes():
    out = quote_state({"bid": True, "ask": True, "last": True}, now=NOW)
    assert (out["bid"], out["ask"], out["last"]) == (None, None, None)
    assert out["spread_absolute"] is None


# ---- the mounted Triad scope, recorded not inferred ----

def test_triad_scope_records_what_is_actually_requested():
    scope = triad_request_scope()
    assert scope["expiries_requested"] == 4
    assert scope["is_true_zero_dte"] is False
    assert "not 0DTE" in scope["zero_dte_note"]
    assert scope["refreshes_periodically"] is False
    assert scope["refresh_interval_s"] is None
    assert scope["window_basis_enabled"] is False
    assert scope["triggered_on"] == "ticker change"


def test_a_declared_refresh_is_reported_as_such():
    scope = triad_request_scope(refresh_interval_s=30.0)
    assert scope["refreshes_periodically"] is True
    assert scope["refresh_interval_s"] == 30.0
