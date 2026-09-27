"""The quote symbol-match guard must never be weakened.

`_matching_quote` exists for one reason: the vendor can answer a request for
SPY with a quote for a different instrument. Taking `quotes[0]` in that case
labels the wrong price with our ticker — a verified failure mode on a sibling
stack where a QQQ price was served as SPY. The only safe behaviour is to
refuse and degrade to no-data.

These tests were added after mutation testing showed the guard had NO coverage:
removing the mismatch branch entirely left the whole suite green. That is the
specific hole this file closes.
"""

from __future__ import annotations

from services.public_api_adapter import _matching_quote


class Q:
    """Minimal quote double carrying a symbol, like the vendor's response."""

    def __init__(self, symbol, mid=1.0):
        self.symbol = symbol
        self.mid_price = mid


def test_refuses_quote_for_a_different_symbol() -> None:
    """THE regression: a QQQ quote must never be served for an SPY request."""
    assert _matching_quote([Q("QQQ", 500.0)], "SPY") is None


def test_matches_the_requested_symbol() -> None:
    q = Q("SPY", 450.0)
    assert _matching_quote([q], "SPY") is q


def test_picks_the_right_one_out_of_several() -> None:
    """Order in the vendor response must not decide the match."""
    quotes = [Q("QQQ", 500.0), Q("SPY", 450.0), Q("AAPL", 200.0)]
    got = _matching_quote(quotes, "SPY")
    assert got is not None
    assert got.mid_price == 450.0


def test_normalizes_caret_prefixed_symbols() -> None:
    """`^SPX` and `SPX` are the same instrument; the guard must see that."""
    assert _matching_quote([Q("SPX", 6000.0)], "^SPX") is not None


def test_no_quotes_is_no_data_not_an_error() -> None:
    assert _matching_quote([], "SPY") is None
    assert _matching_quote(None, "SPY") is None


def test_non_string_symbol_attribute_is_refused() -> None:
    """A malformed vendor object must not be treated as a match."""

    class Bad:
        symbol = object()  # not a str

    assert _matching_quote([Bad()], "SPY") is None
