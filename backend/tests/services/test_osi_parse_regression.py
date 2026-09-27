"""The Databento OI overlay was wired but could never return a symbol.

`OSI_RE` captures six groups (underlying, YY, MM, DD, C/P, 8-digit strike),
but `parse_osi` unpacked them into four names. Every call raised
`ValueError: too many values to unpack (expected 4, got 6)`, the provider
failed closed, and the circuit breaker kept the OI path disabled — so
`fetch_oi_for_ticker` was live code that could only ever fail.
"""

from __future__ import annotations

import pytest

from databento_provider import OSI_RE, parse_osi


def test_regex_group_count_matches_unpacking():
    """The invariant that was violated: N groups must unpack into N names."""
    m = OSI_RE.match("SPY   260612C00500000")
    assert m is not None
    assert len(m.groups()) == 6, "changing this must update parse_osi's unpack"


@pytest.mark.parametrize(
    ("raw", "underlying", "expiry", "typ", "strike"),
    [
        ("SPY   260612C00500000", "SPY", "2026-06-12", "call", 500.0),
        ("SPY   260612P00495000", "SPY", "2026-06-12", "put", 495.0),
        ("AAPL  260918C00250000", "AAPL", "2026-09-18", "call", 250.0),
        ("QQQ   261218P00600000", "QQQ", "2026-12-18", "put", 600.0),
    ],
)
def test_parse_osi_round_trips(raw, underlying, expiry, typ, strike):
    got = parse_osi(raw)
    assert got is not None, f"failed to parse {raw!r}"
    assert got["underlying"] == underlying
    assert got["expiry"] == expiry
    assert got["type"] == typ
    assert got["strike"] == pytest.approx(strike)


def test_parse_osi_never_raises_on_a_matching_symbol():
    """The regression itself: this used to raise on EVERY match."""
    try:
        parse_osi("SPY   260612C00500000")
    except ValueError as exc:  # pragma: no cover - the bug we are pinning
        pytest.fail(f"parse_osi raised on a valid symbol: {exc}")


def test_parse_osi_returns_none_on_garbage():
    assert parse_osi("not-a-symbol") is None
    assert parse_osi("") is None


def test_strike_is_thousandths():
    """OSI encodes strike x1000; 00500000 -> 500.0, not 500000.0."""
    assert parse_osi("SPY   260612C00500000")["strike"] == pytest.approx(500.0)
