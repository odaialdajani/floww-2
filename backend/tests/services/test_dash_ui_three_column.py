"""TDD test for Heatseeker three-column layout compute helpers.
These tests are RED at the start of Phase 1.
They go GREEN after Phase 2 implements the helpers.
"""
import math
import pytest

SAMPLE_CONTRACTS = [
    {"strike": 740, "gex":  3e8, "oi": 5000, "type": "call", "expiry": "2026-06-20"},
    {"strike": 745, "gex":  5e8, "oi": 8000, "type": "call", "expiry": "2026-06-20"},
    {"strike": 750, "gex":  1e8, "oi": 9000, "type": "call", "expiry": "2026-06-20"},
    {"strike": 755, "gex": -2e8, "oi": 4000, "type": "put",  "expiry": "2026-06-20"},
    {"strike": 760, "gex": -4e8, "oi": 6000, "type": "put",  "expiry": "2026-06-20"},
]
SPOT = 748.0


def test_gamma_regime_returns_valid_label():
    from services.dash_ui import _compute_gamma_regime
    regime, color, ratio = _compute_gamma_regime(SAMPLE_CONTRACTS)
    assert regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNKNOWN")
    assert color in ("#00ff88", "#ff4444", "#ffaa00", "#666666")
    assert isinstance(ratio, (int, float)) and math.isfinite(ratio)


def test_key_levels_returns_all_keys():
    from services.dash_ui import _compute_key_levels
    klv = _compute_key_levels(SPOT, SAMPLE_CONTRACTS)
    assert set(klv.keys()) == {"gamma_flip", "call_wall", "put_wall", "max_pain", "spot"}
    assert klv["spot"] == SPOT


def test_risk_levels_returns_4_levels():
    from services.dash_ui import _compute_risk_levels
    risk = _compute_risk_levels(SPOT, SAMPLE_CONTRACTS)
    assert set(risk.keys()) == {"R1", "R2", "S1", "S2"}


def test_stacked_nodes_top_n_limit():
    from services.dash_ui import _compute_stacked_nodes
    nodes = _compute_stacked_nodes(SAMPLE_CONTRACTS, top_n=3)
    assert len(nodes) <= 3
    for n in nodes:
        assert {"strike", "call_pct", "put_pct", "total_oi"} == set(n.keys())


def test_cell_tags_assigns_king():
    from services.dash_ui import _compute_cell_tags
    tags = _compute_cell_tags(SPOT, SAMPLE_CONTRACTS)
    assert any("KING" in t for t in tags.values()), "KING tag missing"


def test_handles_empty_contracts():
    from services.dash_ui import (_compute_gamma_regime, _compute_key_levels,
                                  _compute_stacked_nodes, _compute_cell_tags)
    assert _compute_gamma_regime([])[0] == "UNKNOWN"
    assert _compute_key_levels(SPOT, [])["spot"] == SPOT
    assert _compute_stacked_nodes([]) == []
    assert _compute_cell_tags(SPOT, []) == {}


def test_handles_nan_gex_safely():
    from services.dash_ui import _compute_gamma_regime
    contracts = [{"strike": 745, "gex": float("nan"), "oi": 1000, "type": "call"}]
    regime, _, _ = _compute_gamma_regime(contracts)
    assert regime == "UNKNOWN"   # NaN must be filtered


def test_fmt_money_handles_edge_cases():
    from services.dash_ui import _fmt_money
    assert _fmt_money(1_500_000_000) == "$1.50B"
    assert _fmt_money(473_200_000) == "$473.2M"
    assert _fmt_money(float("nan")) == "—"
    assert _fmt_money(None) == "—"
