"""Agent C (C5, C-side): earnings protocol routing in the desk pass.

Earnings-window alerts still fire (never-remove) but route to the event
protocol: earnings_protocol flag (drives C3 1% sizing cap), 1.5x wider
invalidation, event-day exit note in why. Eval-side GOLD cap + frontend
labels are A's side (ledger-proposed); this pins C's side.
"""
import pytest

from services.flow_desk import apply_earnings_protocol


def _alert(**kw):
    base = dict(
        ckey="SPY|call|700|2026-09-18", tier="SILVER", why="score 94",
        key_levels={"entry": 5.0, "invalidation": 3.0, "target": 9.0},
    )
    base.update(kw)
    return base


def test_earnings_tag_routes_to_protocol():
    alerts = [_alert()]
    tags = {"SPY|call|700|2026-09-18": {"earnings": {"days_to": 3}}}
    n = apply_earnings_protocol(alerts, tags)
    assert n == 1
    a = alerts[0]
    assert a["earnings_protocol"] is True
    assert a["key_levels"]["invalidation"] == pytest.approx(2.0)
    assert "event day" in a["why"].lower()


def test_no_tag_untouched():
    alerts = [_alert()]
    n = apply_earnings_protocol(alerts, {})
    assert n == 0
    assert "earnings_protocol" not in alerts[0]
    assert alerts[0]["key_levels"]["invalidation"] == 3.0


def test_missing_key_levels_flags_without_crash():
    alerts = [_alert(key_levels=None)]
    n = apply_earnings_protocol(alerts, {"SPY|call|700|2026-09-18": {"earnings": {"unknown": True}}})
    assert n == 1
    assert alerts[0]["earnings_protocol"] is True
    assert alerts[0]["key_levels"] is None
