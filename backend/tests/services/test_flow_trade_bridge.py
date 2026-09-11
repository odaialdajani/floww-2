"""
backend/tests/services/test_flow_trade_bridge.py

Signal-to-trade bridge: converts qualifying institutional flow alerts into
paper-trading orders + journal seed entries. Filters: tier >= SILVER,
side == BUY (directional claims only — FLOW/STRATEGY never auto-trade),
DTE >= min_dte (default 2 — skip same-day 0DTE per architect mandate),
dedup per contract key so one alert = one trade.

Families:
  ELIGIBILITY   — tier/side/DTE gates
  CONVERSION    — alert → order + journal entry field mapping
  DEDUP         — one trade per ckey; re-fire suppressed within TTL
"""
import pytest

from services.flow_trade_bridge import (
    alert_to_journal_entry,
    alert_to_order,
    dedupe_alerts,
    eligible_for_auto_trade,
)


def _alert(**kw):
    base = {
        "key": "score|O:SPY260918C00750000", "ckey": "SPY260918C00750000",
        "rule": "SCORE", "tier": "GOLD", "side": "BUY", "bias": "BULLISH",
        "under": "SPY", "type": "call", "strike": 750.0,
        "exp": "2026-09-18", "dte": 27, "score": 92,
        "est_entry": 4.25, "premium": 3_200_000, "notional": 1.1e6,
        "vol_oi": 5.1, "under_price": 744.5,
        "why": "score 92 — vol 5.1x OI, ~$3.20M premium, 27 DTE",
        "asof": "2026-08-22T12:00:00",
    }
    base.update(kw)
    return base


# ── ELIGIBILITY ──────────────────────────────────────────────────────

def test_gold_buy_30dte_eligible():
    assert eligible_for_auto_trade(_alert()) is True


def test_bronze_never_eligible():
    assert eligible_for_auto_trade(_alert(tier="BRONZE")) is False


def test_flow_side_not_directional_enough():
    a = _alert(side="FLOW", bias=None)
    assert eligible_for_auto_trade(a) is False


def test_strategy_legs_demoted_by_finalize_are_excluded():
    a = _alert(side="STRATEGY", tier="BRONZE")
    assert eligible_for_auto_trade(a) is False


def test_zero_dte_excluded_by_default():
    assert eligible_for_auto_trade(_alert(dte=0)) is False
    assert eligible_for_auto_trade(_alert(dte=1)) is False


def test_min_dte_override_allows_1dte():
    assert eligible_for_auto_trade(_alert(dte=1), min_dte=1) is True


def test_missing_entry_price_not_tradable():
    assert eligible_for_auto_trade(_alert(est_entry=None)) is False


def test_min_tier_filter_silver_floor():
    assert eligible_for_auto_trade(_alert(tier="SILVER")) is True
    assert eligible_for_auto_trade(_alert(tier="SILVER"), min_tier="GOLD") is False


# ── CONVERSION ───────────────────────────────────────────────────────

def test_order_fields_match_paper_engine():
    o = alert_to_order(_alert(), account_equity=100_000)
    assert o["symbol"] == "SPY"
    assert o["side"] == "BUY"
    assert o["quantity"] >= 1
    # risk-sized: contracts*100*entry must not exceed 2% of equity
    assert o["quantity"] * 100 * 4.25 <= 0.02 * 100_000 * 1.05
    assert o["metadata"]["ckey"] == "SPY260918C00750000"
    assert o["metadata"]["source"] == "flowseeker"


def test_journal_entry_matches_floww_trades_v2_schema():
    j = alert_to_journal_entry(_alert())
    assert j["ticker"] == "SPY"
    assert j["type"] == "call"
    assert j["action"] == "buy"
    assert j["strike"] == 750.0
    assert j["expiry"] == "2026-09-18"
    assert j["entry_price"] == 4.25
    assert j["gex_regime"] == "" or isinstance(j["gex_regime"], str)
    assert "flowseeker" in (j["tags"] or "")
    assert "score" in (j["setup"] or "").lower()
    assert j["notes"]


def test_put_alert_maps_to_buy_put():
    j = alert_to_journal_entry(_alert(type="put", bias="BEARISH"))
    assert j["type"] == "put" and j["action"] == "buy"


# ── DEDUP ────────────────────────────────────────────────────────────

def test_dedupe_one_trade_per_ckey():
    alerts = [_alert(), _alert()]  # identical ckey twice
    out = dedupe_alerts(alerts)
    assert len(out) == 1


def test_dedupe_different_ckey_passes():
    out = dedupe_alerts([_alert(), _alert(ckey="QQQ261218P00480000",
                                         under="QQQ", key="score|x")])
    assert len(out) == 2


# ── DETERMINISM (C8, Agent C) ────────────────────────────────────────
# Paper fills must replay byte-identical: same alert in → same order out
# (qty, size_basis, execution, timestamps all derived from the alert, no
# wall-clock, no randomness). Timestamps are audited: entry_date comes
# from the alert's asof (fire time), never now.

def test_build_auto_trades_deterministic():
    from services.flow_trade_bridge import build_auto_trades
    alerts = [_alert(), _alert()]
    first = build_auto_trades(alerts)
    second = build_auto_trades(alerts)
    assert first == second
    assert len(first) == 1, "same ckey twice → one trade (idempotent)"


def test_order_timestamps_come_from_alert_not_clock():
    o = alert_to_order(_alert())
    assert o["metadata"]["size_basis"]["method"] == "flat"  # uncalibrated fixture
    j = alert_to_journal_entry(_alert())
    assert j["entry_date"] == "2026-08-22", "journal entry dated at fire time"
