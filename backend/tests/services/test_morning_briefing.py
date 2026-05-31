"""
backend/tests/services/test_morning_briefing.py

Unit tests for the morning briefing engine:
  - regime classification (BULLISH / BEARISH / NEUTRAL / UNKNOWN)
  - narrative template generation
  - NaN guards on all metric thresholds

All tests are pure unit tests — no network, no DB, no file I/O.
Run with:
    cd backend && .venv/bin/python -m pytest tests/services/test_morning_briefing.py -v
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ────────────────────────────────────────────────────────────────────────
# Regime classification tests
# ────────────────────────────────────────────────────────────────────────

class TestRegimeClassification:
    """Test the BULLISH / BEARISH / NEUTRAL / UNKNOWN regime classifier."""

    def _make_classifier(self):
        """Import and return the classifier function/class."""
        from services.morning_briefing import classify_regime
        return classify_regime

    def test_bullish_positive_gex_call_oi_surge(self):
        """Positive GEX + call OI surge above threshold → BULLISH."""
        classify = self._make_classifier()
        result = classify(
            net_gex=1.5e9,
            call_oi=500000,
            put_oi=300000,
            iv_skew=0.005,
            flip_level=450.0,
            spot=452.0,
        )
        assert result == "BULLISH", f"Expected BULLISH, got {result}"

    def test_bearish_negative_gex_put_oi_surge(self):
        """Negative GEX + put OI surge above threshold → BEARISH."""
        classify = self._make_classifier()
        result = classify(
            net_gex=-1.5e9,
            call_oi=300000,
            put_oi=500000,
            iv_skew=0.04,
            flip_level=450.0,
            spot=445.0,
        )
        assert result == "BEARISH", f"Expected BEARISH, got {result}"

    def test_neutral_mixed_signals(self):
        """Mixed signals / below thresholds → NEUTRAL."""
        classify = self._make_classifier()
        result = classify(
            net_gex=1.0e8,
            call_oi=300000,
            put_oi=300000,
            iv_skew=0.01,
            flip_level=450.0,
            spot=449.0,
        )
        assert result == "NEUTRAL", f"Expected NEUTRAL, got {result}"

    def test_unknown_when_all_metrics_nan(self):
        """All NaN inputs → UNKNOWN."""
        classify = self._make_classifier()
        result = classify(
            net_gex=math.nan,
            call_oi=math.nan,
            put_oi=math.nan,
            iv_skew=math.nan,
            flip_level=math.nan,
            spot=math.nan,
        )
        assert result == "UNKNOWN", f"Expected UNKNOWN, got {result}"

    def test_unknown_when_all_zero(self):
        """All-zero inputs (no data) → UNKNOWN."""
        classify = self._make_classifier()
        result = classify(
            net_gex=0.0,
            call_oi=0.0,
            put_oi=0.0,
            iv_skew=0.0,
            flip_level=0.0,
            spot=0.0,
        )
        assert result == "UNKNOWN", f"Expected UNKNOWN, got {result}"

    def test_bullish_spot_above_flip_positive_gex(self):
        """Spot above flip level + positive GEX → BULLISH."""
        classify = self._make_classifier()
        result = classify(
            net_gex=5.0e8,
            call_oi=400000,
            put_oi=350000,
            iv_skew=0.01,
            flip_level=448.0,
            spot=455.0,
        )
        assert result == "BULLISH", f"Expected BULLISH, got {result}"

    def test_bearish_spot_below_flip_negative_gex(self):
        """Spot below flip level + negative GEX → BEARISH."""
        classify = self._make_classifier()
        result = classify(
            net_gex=-5.0e8,
            call_oi=350000,
            put_oi=400000,
            iv_skew=0.03,
            flip_level=455.0,
            spot=448.0,
        )
        assert result == "BEARISH", f"Expected BEARISH, got {result}"

    def test_nan_gex_still_classifies_from_other_signals(self):
        """NaN GEX but strong put/fear signals → BEARISH."""
        classify = self._make_classifier()
        result = classify(
            net_gex=math.nan,
            call_oi=100000,
            put_oi=600000,
            iv_skew=0.06,
            flip_level=450.0,
            spot=440.0,
        )
        assert result == "BEARISH", f"Expected BEARISH, got {result}"

    def test_nan_iv_skew_still_classifies(self):
        """NaN IV skew but strong GEX + OI signals → BULLISH."""
        classify = self._make_classifier()
        result = classify(
            net_gex=2.0e9,
            call_oi=700000,
            put_oi=200000,
            iv_skew=math.nan,
            flip_level=450.0,
            spot=460.0,
        )
        assert result == "BULLISH", f"Expected BULLISH, got {result}"

    def test_return_type_is_string(self):
        """Regime is always a plain str."""
        classify = self._make_classifier()
        result = classify(
            net_gex=1.0e8,
            call_oi=200000,
            put_oi=200000,
            iv_skew=0.01,
            flip_level=450.0,
            spot=451.0,
        )
        assert isinstance(result, str)


# ────────────────────────────────────────────────────────────────────────
# Narrative template tests
# ────────────────────────────────────────────────────────────────────────

class TestNarrativeTemplate:
    """Test the template-driven narrative engine."""

    def _make_generator(self):
        from services.morning_briefing import generate_narrative
        return generate_narrative

    def test_bullish_narrative_contains_regime(self):
        gen = self._make_generator()
        result = gen(
            regime="BULLISH",
            ticker="SPY",
            spot=452.0,
            flip_level=448.0,
            net_gex=1.5e9,
            iv_skew=0.005,
            top_movers=[
                {"ticker": "AAPL", "pct": 2.5},
                {"ticker": "MSFT", "pct": 1.8},
            ],
            call_oi=500000,
            put_oi=300000,
        )
        assert "BULLISH" in result
        assert isinstance(result, str)
        assert len(result) > 0

    def test_bearish_narrative_contains_regime(self):
        gen = self._make_generator()
        result = gen(
            regime="BEARISH",
            ticker="SPY",
            spot=445.0,
            flip_level=450.0,
            net_gex=-1.5e9,
            iv_skew=0.04,
            top_movers=[
                {"ticker": "TSLA", "pct": -3.2},
            ],
            call_oi=300000,
            put_oi=500000,
        )
        assert "BEARISH" in result
        assert isinstance(result, str)

    def test_neutral_narrative(self):
        gen = self._make_generator()
        result = gen(
            regime="NEUTRAL",
            ticker="SPY",
            spot=449.0,
            flip_level=450.0,
            net_gex=1.0e8,
            iv_skew=0.01,
            top_movers=[],
            call_oi=300000,
            put_oi=300000,
        )
        assert "NEUTRAL" in result

    def test_unknown_narrative(self):
        gen = self._make_generator()
        result = gen(
            regime="UNKNOWN",
            ticker="SPY",
            spot=0.0,
            flip_level=0.0,
            net_gex=0.0,
            iv_skew=0.0,
            top_movers=[],
            call_oi=0,
            put_oi=0,
        )
        assert "UNKNOWN" in result

    def test_narrative_under_500_chars(self):
        gen = self._make_generator()
        result = gen(
            regime="BULLISH",
            ticker="SPY",
            spot=452.0,
            flip_level=448.0,
            net_gex=1.5e9,
            iv_skew=0.005,
            top_movers=[
                {"ticker": "AAPL", "pct": 2.5},
                {"ticker": "MSFT", "pct": 1.8},
                {"ticker": "GOOG", "pct": 1.2},
                {"ticker": "AMZN", "pct": 0.9},
                {"ticker": "NVDA", "pct": 3.1},
            ],
            call_oi=500000,
            put_oi=300000,
        )
        assert len(result) <= 500, f"Narrative {len(result)} chars > 500 limit"

    def test_narrative_contains_ticker(self):
        gen = self._make_generator()
        result = gen(
            regime="BULLISH",
            ticker="SPY",
            spot=452.0,
            flip_level=448.0,
            net_gex=1.5e9,
            iv_skew=0.005,
            top_movers=[],
            call_oi=500000,
            put_oi=300000,
        )
        assert "SPY" in result

    def test_narrative_mentions_iv_skew_direction(self):
        gen = self._make_generator()
        fear_result = gen(
            regime="BEARISH",
            ticker="SPY",
            spot=445.0,
            flip_level=450.0,
            net_gex=-1.5e9,
            iv_skew=0.05,
            top_movers=[],
            call_oi=300000,
            put_oi=500000,
        )
        # Should mention fear or put-skew for high positive skew
        assert "fear" in fear_result.lower() or "put" in fear_result.lower()

    def test_narrative_generation_under_50ms(self):
        """Performance: narrative generation must be < 50ms."""
        gen = self._make_generator()
        start = time.monotonic()
        for _ in range(100):
            gen(
                regime="BULLISH",
                ticker="SPY",
                spot=452.0,
                flip_level=448.0,
                net_gex=1.5e9,
                iv_skew=0.005,
                top_movers=[
                    {"ticker": "AAPL", "pct": 2.5},
                    {"ticker": "MSFT", "pct": 1.8},
                ],
                call_oi=500000,
                put_oi=300000,
            )
        elapsed_ms = (time.monotonic() - start) / 100 * 1000
        assert elapsed_ms < 50, f"Avg {elapsed_ms:.1f}ms > 50ms budget"

    def test_empty_movers_still_generates(self):
        gen = self._make_generator()
        result = gen(
            regime="NEUTRAL",
            ticker="QQQ",
            spot=390.0,
            flip_level=392.0,
            net_gex=5.0e7,
            iv_skew=0.015,
            top_movers=[],
            call_oi=200000,
            put_oi=200000,
        )
        assert isinstance(result, str)
        assert len(result) > 0


# ────────────────────────────────────────────────────────────────────────
# NaN guard tests (I-8)
# ────────────────────────────────────────────────────────────────────────

class TestNaNGuards:
    """Verify NaN inputs never cause exceptions."""

    def _make_classifier(self):
        from services.morning_briefing import classify_regime
        return classify_regime

    def _make_generator(self):
        from services.morning_briefing import generate_narrative
        return generate_narrative

    def test_classifier_nan_net_gex(self):
        classify = self._make_classifier()
        result = classify(
            net_gex=math.nan,
            call_oi=500000,
            put_oi=300000,
            iv_skew=0.005,
            flip_level=450.0,
            spot=452.0,
        )
        assert result in ("BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN")

    def test_classifier_nan_flip_level(self):
        classify = self._make_classifier()
        result = classify(
            net_gex=1.5e9,
            call_oi=500000,
            put_oi=300000,
            iv_skew=0.005,
            flip_level=math.nan,
            spot=452.0,
        )
        assert result in ("BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN")

    def test_classifier_nan_call_oi(self):
        classify = self._make_classifier()
        result = classify(
            net_gex=1.5e9,
            call_oi=math.nan,
            put_oi=300000,
            iv_skew=0.005,
            flip_level=450.0,
            spot=452.0,
        )
        assert result in ("BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN")

    def test_narrative_nan_metrics_no_crash(self):
        gen = self._make_generator()
        result = gen(
            regime="UNKNOWN",
            ticker="SPY",
            spot=math.nan,
            flip_level=math.nan,
            net_gex=math.nan,
            iv_skew=math.nan,
            top_movers=[],
            call_oi=math.nan,
            put_oi=math.nan,
        )
        assert isinstance(result, str)
