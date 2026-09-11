"""
backend/tests/services/test_blademap_conviction.py

RED-first tests for the Blademap-style conviction upgrade:

1. WEIGHTED conviction score (0-100) — Blademap weights dimensions, it
   doesn't count booleans. score_conviction() replaces the factor-count
   tier_of() as the alert-quality signal while keeping tier_of() for
   backward compatibility (existing feed consumers).

2. KEY LEVELS — every GOLD alert carries Blademap's alert contract:
   entry / invalidation / target derived from the underlying price,
   the contract's delta, and the GEX regime. A signal without a
   falsifiable invalidation is an opinion, not a trade.

3. CONTEXT BLOCK — institutional_indicators list + dealer_positioning
   + market_regime, so the feed explains the WHY the way Blademap does.

All pure logic — no I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import math
from datetime import date, timedelta

from services.flow_alerts import norm_rows  # noqa: E402


def _future_exp(biz_days: int) -> str:
    d = date.today()
    added = 0
    while added < biz_days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.isoformat()


def _raw(under="PLTR", occ="O:PLTR260918C00138000", typ="call", strike=138.0,
         exp=None, vol=18000, oi=1200, iv=0.62, delta=0.38, spot=133.0):
    """One cvforge screen row in list form, ordered per SCAN_COLUMNS."""
    return [under, occ, typ, strike, exp or _future_exp(4), vol, oi, iv, delta, spot]


def _row(**over):
    defaults = dict(under="PLTR", occ="O:PLTR260918C00138000", typ="call",
                    strike=138.0, exp=None, vol=18000, oi=1200, iv=0.62,
                    delta=0.38, spot=133.0)
    defaults.update(over)
    return norm_rows([_raw(**defaults)])[0]


# ── 1. weighted conviction ───────────────────────────────────────────

class TestWeightedConviction:
    def test_score_conviction_exists_and_clamped(self):
        from services.flow_alerts import score_conviction
        s = score_conviction(_row())
        assert 0 <= s <= 100

    def test_strong_flow_outscores_weak_flow(self):
        from services.flow_alerts import score_conviction
        strong = score_conviction(_row(vol=60000, oi=1500, delta=0.25))
        weak = score_conviction(_row(vol=1200, oi=40000, delta=0.9))
        assert strong > weak + 15

    def test_confluences_add_points(self):
        from services.flow_alerts import score_conviction
        base = _row(vol=60000, oi=1500, delta=0.25)
        plain = score_conviction(base)
        # same row but with every confluence lit
        confluent = score_conviction(base, factors={
            "score90": True, "whale": True, "sigma_ticker": True,
            "informed_band": True, "regime_confluent": True, "prime": True,
            "cluster": True, "cw_confirm": True, "gex_confluent": True,
        })
        assert confluent > plain + 20

    def test_factors_argument_optional(self):
        from services.flow_alerts import score_conviction
        assert isinstance(score_conviction(_row()), int)


# ── 2. key levels ────────────────────────────────────────────────────

class TestKeyLevels:
    def test_gold_alert_has_entry_invalidation_target(self):
        from services.flow_alerts import build_key_levels
        r = _row(delta=0.38, spot=133.0)
        kl = build_key_levels(r, bias="BULLISH", gex_regime="negative")
        assert kl["entry"] == pytest.approx(133.0)
        assert kl["invalidation"] < kl["entry"] < kl["target"]

    def test_bearish_invalidation_above_entry(self):
        from services.flow_alerts import build_key_levels
        r = _row(typ="put", delta=-0.35, spot=133.0)
        kl = build_key_levels(r, bias="BEARISH", gex_regime="positive")
        assert kl["target"] < kl["entry"] < kl["invalidation"]

    def test_negative_gamma_widens_target(self):
        from services.flow_alerts import build_key_levels
        r = _row(spot=133.0)
        neg = build_key_levels(r, bias="BULLISH", gex_regime="negative")
        pos = build_key_levels(r, bias="BULLISH", gex_regime="positive")
        # short-gamma regimes move harder — target is further out
        assert neg["target"] > pos["target"]

    def test_no_bias_no_levels(self):
        from services.flow_alerts import build_key_levels
        r = _row()
        assert build_key_levels(r, bias=None, gex_regime=None) is None


# ── 3. context block ─────────────────────────────────────────────────

class TestContextBlock:
    def test_summary_uses_actual_open_interest_not_volume_ratio(self):
        from services.flow_alerts import build_context
        text = build_context(_row(vol=60000,oi=1500),{})["activity_summary"]
        assert "1,500" in text and "4,000 resting" not in text
        assert "session volume" in text

    def test_build_context_lists_indicators(self):
        from services.flow_alerts import build_context
        r = _row(vol=60000, oi=1500)
        factors = {"score90": True, "whale": False, "sigma_ticker": True,
                   "informed_band": True, "regime_confluent": True,
                   "prime": True, "cluster": True, "cw_confirm": True,
                   "gex_confluent": False, "gex_regime": "negative"}
        ctx = build_context(r, factors)
        assert ctx["market_regime"] == "NEGATIVE_GAMMA"
        assert "dealer_positioning" in ctx
        assert isinstance(ctx["institutional_indicators"], list)
        assert len(ctx["institutional_indicators"]) >= 2
        assert "activity_summary" in ctx

    def test_activity_summary_mentions_premium(self):
        from services.flow_alerts import build_context
        r = _row(vol=18000)
        ctx = build_context(r, {"gex_regime": "positive"})
        assert "18,000" in ctx["activity_summary"] or "18k" in ctx["activity_summary"].lower()


# ── 4. alerts carry the full Blademap contract ──────────────────────

class TestAlertContract:
    def test_gold_alert_carries_conviction_levels_context(self):
        from services.flow_alerts import eval_institutional
        alerts = eval_institutional(
            [_row(vol=60000, oi=1500, delta=0.25)],
            regimes={"PLTR": "negative"},
        )
        gold = [a for a in alerts if a.get("tier") == "GOLD"]
        assert gold, "expected at least one GOLD alert"
        a = gold[0]
        assert isinstance(a["conviction"], int) and 0 <= a["conviction"] <= 100
        assert a["key_levels"] is not None
        assert "invalidation" in a["key_levels"]
        assert "context" in a and "institutional_indicators" in a["context"]
