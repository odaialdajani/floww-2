"""
backend/tests/services/test_gex_aggregator_oracle.py

Golden-oracle correctness tests for the GEX aggregation seam.

Hand-derived ground truth (no fixtures, no mocks) for a fixed 4-contract chain.
Asserts BOTH GEX scale conventions that coexist in this codebase and pins the
exact relationship between them so neither can drift silently.

Two INTENTIONAL conventions (see docs/superpowers/specs/2026-06-13-gex-gamma-
correctness-audit-design.md):

  * DISPLAY scale (S^2): services/gex_aggregator.py
        gex = sign * gamma * OI * 100 * spot^2 * 0.01
        Standard dealer dollar-GEX (SqueezeMetrics convention). Human-facing.

  * FEATURE scale (S^1): services/gex_history.py + scripts/compute_gex_features.py
        gex = sign * gamma * OI * 100 * spot * 0.01
        The ML-feature convention: gex_history collection -> add_gex_features ->
        the trained GBM models. This series is a FROZEN model-input contract.

They differ by EXACTLY a factor of `spot` and are NOT interchangeable. This file
locks both and their ratio. Sign convention (calls +, puts -) is pinned too.

Canonical chain (spot = 100):
    | type | strike | gamma | OI   |
    | call | 100    | 0.10  | 2000 |
    | put  | 100    | 0.04  | 2000 |
    | call | 105    | 0.03  | 500  |
    | put  | 105    | 0.05  | 3000 |

DISPLAY (S^2): per-contract = sign * gamma * OI * (spot^2 * 0.01 * 100)
                            = sign * gamma * OI * 10_000
    +2_000_000, -800_000, +150_000, -1_500_000
    per-strike:  K100 = +1_200_000 ;  K105 = -1_350_000
    net_gex           = -150_000
    total_gex (pos)   = +1_200_000
    total_negative    = -1_350_000
    King Node (max)   = 100 ; min = 105
    zero-gamma flip   = 100 + (1_200_000 / 2_550_000) * 5 = 102.35294117647
    gex_ratio         = 1_200_000 / 1_350_000 = 0.88888888889

FEATURE (S^1): per-contract = sign * gamma * OI * (spot * 0.01 * 100)
                            = sign * gamma * OI * 100
    call_gex = 0.10*2000*100 + 0.03*500*100 = 20_000 + 1_500 = 21_500
    put_gex  = -(0.04*2000*100) - (0.05*3000*100) = -8_000 - 15_000 = -23_000
    net_gex  = -1_500

Relationship: DISPLAY.net_gex == spot * FEATURE.net_gex  ->  -150_000 == 100 * -1_500
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.gex_aggregator import GexAggregator  # noqa: E402
from services.gex_history import calc_gex_timeframes  # noqa: E402

SPOT = 100.0

# Economic contracts shared by both engines (engine-specific key shaping below).
_CHAIN = [
    {"type": "call", "strike": 100.0, "gamma": 0.10, "oi": 2000},
    {"type": "put", "strike": 100.0, "gamma": 0.04, "oi": 2000},
    {"type": "call", "strike": 105.0, "gamma": 0.03, "oi": 500},
    {"type": "put", "strike": 105.0, "gamma": 0.05, "oi": 3000},
]


def _aggregator_contracts():
    # GexAggregator needs an expiry/T; one shared expiry -> single surface column.
    return [{**c, "T": 0.05} for c in _CHAIN]


def _history_contracts():
    # calc_gex_timeframes uses the precomputed gamma (>0) as-is; iv/T unused here.
    # expiry is only for DTE bucketing -- we assert the date-independent 'all' bucket.
    return [{**c, "iv": 0.20, "T": 0.05, "expiry": "2026-09-18"} for c in _CHAIN]


class TestDisplayScaleOracleS2:
    """services/gex_aggregator.py -- standard dealer dollar-GEX (S^2)."""

    def setup_method(self):
        self.out = GexAggregator().compute(SPOT, _aggregator_contracts())

    def test_net_gex(self):
        assert self.out["net_gex"] == pytest.approx(-150_000.0, rel=1e-9)

    def test_total_and_negative_gex(self):
        assert self.out["total_gex"] == pytest.approx(1_200_000.0, rel=1e-9)
        assert self.out["total_negative_gex"] == pytest.approx(-1_350_000.0, rel=1e-9)

    def test_per_strike_gex_1d(self):
        assert self.out["strikes"] == [100.0, 105.0]
        assert self.out["gex_1d"] == pytest.approx([1_200_000.0, -1_350_000.0], rel=1e-9)

    def test_king_node_and_min(self):
        assert self.out["max_gex_strike"] == 100.0
        assert self.out["min_gex_strike"] == 105.0

    def test_zero_gamma_flip_level(self):
        assert self.out["zero_gamma_levels"] == pytest.approx([102.35294117647], rel=1e-9)

    def test_gex_ratio(self):
        assert self.out["gex_ratio"] == pytest.approx(0.88888888889, rel=1e-9)


class TestFeatureScaleOracleS1:
    """services/gex_history.py -- ML-feature GEX (S^1). Frozen model-input contract."""

    def setup_method(self):
        self.all = calc_gex_timeframes(SPOT, _history_contracts(), "TEST")["timeframes"]["all"]

    def test_net_gex(self):
        assert self.all["net_gex"] == pytest.approx(-1_500.0, rel=1e-9)

    def test_call_and_put_gex(self):
        assert self.all["call_gex"] == pytest.approx(21_500.0, rel=1e-9)
        assert self.all["put_gex"] == pytest.approx(-23_000.0, rel=1e-9)

    def test_contract_count(self):
        assert self.all["contract_count"] == 4


class TestCrossEngineScaleRelationship:
    """The two conventions must differ by EXACTLY a factor of spot -- pin it so an
    accidental edit to either engine's scale is caught immediately."""

    def test_display_equals_spot_times_feature(self):
        disp = GexAggregator().compute(SPOT, _aggregator_contracts())["net_gex"]
        feat = calc_gex_timeframes(SPOT, _history_contracts(), "TEST")["timeframes"]["all"][
            "net_gex"
        ]
        assert disp == pytest.approx(SPOT * feat, rel=1e-9)


class TestFeaturePathConstantsAreModelLocked:
    """The S^1 feature path feeds FROZEN trained GBM models, so its scale and
    its fixed (iv, r) are a model-input contract. Locked here so an accidental
    'cleanup' edit fails loudly. Genuinely changing them requires re-backfilling
    the gex_history collection and retraining -- out of correctness-audit scope.
    """

    def test_feature_risk_free_rate_locked(self):
        from services import gex_history

        assert gex_history._RISK_FREE == 0.045, (
            "Feature-path risk-free rate changed -- this shifts every trained "
            "model's gex_total feature. Retrain before changing."
        )

    def test_feature_iv_fallback_locked(self):
        from services import gex_history

        assert gex_history._IV_FALLBACK == 0.20, (
            "Feature-path IV fallback changed -- this shifts every trained "
            "model's gex_total feature. Retrain before changing."
        )
