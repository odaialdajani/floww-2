"""P2 scope_echo: server cache_key echoed onto heatmap payloads.

Lets the chart request the screener's exact recorded scope instead of
guessing it. Missing/foreign keys never fabricate an echo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from services.solstice_scope import attach_scope_echo  # noqa: E402


def test_attaches_exact_key():
    payload = {"ticker": "SPY"}
    out = attach_scope_echo(payload, "SPY:4:day:None:False:True:200")
    assert out["scope_echo"] == "SPY:4:day:None:False:True:200"
    assert out["ticker"] == "SPY"


def test_refuses_missing_or_foreign_keys():
    assert attach_scope_echo({"ticker": "SPY"}, "") == {"ticker": "SPY"}
    assert attach_scope_echo({"ticker": "SPY"}, None) == {"ticker": "SPY"}
    assert attach_scope_echo(None, "K") is None
    assert attach_scope_echo({"ticker": "SPY"}, 123) == {"ticker": "SPY"}
