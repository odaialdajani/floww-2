"""Position direction tests (audit V2 math-heap fix).

Quantity is signed (negative for short) AND is_long flags direction;
current_greeks multiplied by both, double-flipping shorts. It now uses
abs(quantity) * sign — the same convention as pnl(), add_position(),
and the server aggregations.
"""
from __future__ import annotations

from portfolio import Position


def _pos(**kw):
    base = dict(symbol="SPY", option_type="call", strike=500.0, expiry="2030-01-15",
                quantity=1, entry_price=5.0, entry_iv=0.2, underlying_price=500.0)
    base.update(kw)
    return Position(**base)


def test_short_greeks_negate_long_greeks():
    long = _pos(quantity=1, is_long=True)
    short = _pos(quantity=-1, is_long=False)
    gl = long.current_greeks(spot=500.0, iv=0.2)
    gs = short.current_greeks(spot=500.0, iv=0.2)
    for k in ("delta", "gamma", "vega", "theta", "vanna", "charm"):
        assert gl[k] != 0, k
        assert gs[k] == -gl[k], k


def test_unsigned_short_style_agrees():
    # Unsigned quantity + is_long=False (the other plausible input style)
    # must agree with the signed convention.
    a = _pos(quantity=-2, is_long=False)
    b = _pos(quantity=2, is_long=False)
    ga = a.current_greeks(spot=500.0, iv=0.2)
    gb = b.current_greeks(spot=500.0, iv=0.2)
    assert ga["delta"] == gb["delta"] != 0


def test_greeks_agree_with_pnl_direction():
    short = _pos(quantity=-1, is_long=False)
    g = short.current_greeks(spot=500.0, iv=0.2)
    p = short.pnl(current_price=4.0)  # price fell 1.00: short gains
    assert p["total"] > 0
    assert g["delta"] < 0  # short call is short delta
