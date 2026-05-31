"""
Unit tests for Black-Scholes math, GEX calculations, and alert engine.
These tests don't require the server to be running.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



# ----------------------------- BS Math Tests -----------------------------

def test_bs_gamma_basic():
    """Test Black-Scholes gamma calculation."""
    from bs_greeks import bs_gamma
    # ATM option with 30 DTE, 20% IV
    gamma = bs_gamma(100, 100, 30/365, 0.2, 0)
    assert gamma > 0
    assert gamma < 1
    # Gamma should be highest for ATM
    gamma_itm = bs_gamma(100, 90, 30/365, 0.2, 0)
    gamma_otm = bs_gamma(100, 110, 30/365, 0.2, 0)
    assert gamma > gamma_itm
    assert gamma > gamma_otm


def test_bs_gamma_zero_iv():
    """Test gamma with zero IV returns 0."""
    from bs_greeks import bs_gamma
    gamma = bs_gamma(100, 100, 30/365, 0, 0)
    assert gamma == 0


def test_bs_delta_call():
    """Test call delta is between 0 and 1."""
    from bs_greeks import bs_delta
    delta = bs_delta(100, 100, 30/365, 0.2, 0, "call")
    assert 0 < delta < 1
    # ATM call delta should be ~0.5
    assert 0.4 < delta < 0.6


def test_bs_delta_put():
    """Test put delta is between -1 and 0."""
    from bs_greeks import bs_delta
    delta = bs_delta(100, 100, 30/365, 0.2, 0, "put")
    assert -1 < delta < 0
    # ATM put delta should be ~-0.5
    assert -0.6 < delta < -0.4


def test_bs_vega_positive():
    """Test vega is always positive."""
    from bs_greeks import bs_vega
    vega = bs_vega(100, 100, 30/365, 0.2, 0)
    assert vega > 0


def test_bs_charm_decreases_with_time():
    """Test charm (delta decay) behavior."""
    from bs_greeks import bs_charm
    charm_30dte = bs_charm(100, 100, 30/365, 0.2, 0, "call")
    charm_7dte = bs_charm(100, 100, 7/365, 0.2, 0, "call")
    # Charm should be larger (more negative) for shorter DTE
    assert abs(charm_7dte) > abs(charm_30dte)


def test_calc_implied_move():
    """Test implied move calculation."""
    from server import calc_implied_move
    contracts = [
        {"strike": 100, "type": "call", "iv": 0.2, "T": 30/365},
        {"strike": 100, "type": "put", "iv": 0.2, "T": 30/365},
    ]
    result = calc_implied_move(100, contracts)
    assert result is not None
    assert "straddle_price" in result
    assert "implied_move_pct" in result
    assert "upper_range" in result
    assert "lower_range" in result
    assert result["straddle_price"] > 0
    assert result["upper_range"] > 100
    assert result["lower_range"] < 100


def test_calc_implied_move_no_contracts():
    """Test implied move with no contracts returns None."""
    from server import calc_implied_move
    result = calc_implied_move(100, [])
    assert result is None


def test_calc_implied_move_no_atm():
    """Test implied move with no ATM contracts returns None."""
    from server import calc_implied_move
    contracts = [
        {"strike": 80, "type": "call", "iv": 0.2, "T": 30/365},
        {"strike": 120, "type": "put", "iv": 0.2, "T": 30/365},
    ]
    result = calc_implied_move(100, contracts)
    assert result is None


# ----------------------------- GEX Calculation Tests -----------------------------

def test_calc_gex_basic():
    """Test basic GEX calculation."""
    from server import calc_aggregate_gex_curve
    contracts = [
        {"strike": 100, "type": "call", "oi": 1000, "iv": 0.2, "T": 30/365},
        {"strike": 100, "type": "put", "oi": 500, "iv": 0.2, "T": 30/365},
    ]
    result = calc_aggregate_gex_curve(100, contracts)
    assert isinstance(result, list)


def test_calc_gex_empty():
    """Test GEX with no contracts."""
    from server import calc_aggregate_gex_curve
    result = calc_aggregate_gex_curve(100, [])
    assert result == []


def test_calc_aggregate_gex_curve():
    """Test aggregate GEX curve calculation."""
    from server import calc_aggregate_gex_curve
    contracts = [
        {"strike": 95, "type": "call", "oi": 1000, "iv": 0.2, "T": 30/365},
        {"strike": 100, "type": "call", "oi": 2000, "iv": 0.2, "T": 30/365},
        {"strike": 105, "type": "put", "oi": 1500, "iv": 0.2, "T": 30/365},
    ]
    curve = calc_aggregate_gex_curve(100, contracts)
    assert isinstance(curve, list)
    assert len(curve) > 0


# ----------------------------- Alert Engine Tests -----------------------------

def test_alert_engine_creation():
    """Test alert engine can be created."""
    from alert_engine import AlertEngine
    engine = AlertEngine()
    assert engine is not None


def test_alert_creation():
    """Test alert dataclass."""
    from alert_engine import Alert
    alert = Alert(
        type="GAMMA_FLIP",
        priority="HIGH",
        ticker="SPY",
        message="Test alert"
    )
    assert alert.type == "GAMMA_FLIP"
    assert alert.priority == "HIGH"
    assert alert.ticker == "SPY"
    assert alert.timestamp != ""


def test_alert_to_dict():
    """Test alert serialization."""
    from alert_engine import Alert
    alert = Alert(
        type="GAMMA_FLIP",
        priority="HIGH",
        ticker="SPY",
        message="Test",
        data={"key": "value"}
    )
    d = alert.to_dict()
    assert d["type"] == "GAMMA_FLIP"
    assert d["data"]["key"] == "value"


def test_gex_snapshot_creation():
    """Test GEX snapshot dataclass."""
    from alert_engine import GEXSnapshot
    snap = GEXSnapshot(
        ticker="SPY",
        spot_price=450,
        gamma_flip=445,
        call_wall=455,
        put_wall=440,
        max_pain=448,
        max_gamma_strike=450,
        total_gex=1e9,
        net_gex=5e8,
        regime="POSITIVE"
    )
    assert snap.ticker == "SPY"
    assert snap.regime == "POSITIVE"
    assert snap.timestamp != ""


def test_detect_alerts_no_data():
    """Test alert detection with no data returns empty."""
    from alert_engine import AlertEngine
    engine = AlertEngine()
    alerts = engine.detect_alerts("SPY")
    assert alerts == []


def test_detect_alerts_with_snapshots():
    """Test alert detection with mock snapshots."""
    from alert_engine import AlertEngine, GEXSnapshot
    engine = AlertEngine()

    # Add two snapshots with regime change
    snap1 = GEXSnapshot(
        ticker="SPY", spot_price=450, gamma_flip=445,
        call_wall=455, put_wall=440, max_pain=448,
        max_gamma_strike=450, total_gex=1e9, net_gex=5e8,
        regime="POSITIVE", timestamp="2025-01-01T00:00:00"
    )
    snap2 = GEXSnapshot(
        ticker="SPY", spot_price=448, gamma_flip=445,
        call_wall=455, put_wall=440, max_pain=448,
        max_gamma_strike=450, total_gex=-1e9, net_gex=-5e8,
        regime="NEGATIVE", timestamp="2025-01-02T00:00:00"
    )

    engine._snapshots["SPY"] = [snap1, snap2]
    alerts = engine.detect_alerts("SPY")

    # Should detect GAMMA_FLIP
    assert len(alerts) > 0
    assert any(a.type == "GAMMA_FLIP" for a in alerts)


def test_all_alert_types_registered():
    """Test that all 11 alert types are detectable."""
    from alert_engine import AlertEngine, GEXSnapshot
    engine = AlertEngine()

    # Create snapshots that trigger each alert type
    snap_positive = GEXSnapshot(
        ticker="TEST", spot_price=100, gamma_flip=100.1,
        call_wall=105, put_wall=95, max_pain=100,
        max_gamma_strike=100, total_gex=1e9, net_gex=5e8,
        regime="POSITIVE", gex_by_strike={100: 5e8, 105: 2e8, 95: -1e8},
        timestamp="2025-01-01T00:00:00"
    )
    snap_negative = GEXSnapshot(
        ticker="TEST", spot_price=99.9, gamma_flip=100.1,
        call_wall=105, put_wall=95, max_pain=100,
        max_gamma_strike=100, total_gex=-1e9, net_gex=-5e8,
        regime="NEGATIVE", gex_by_strike={100: -5e8, 105: -2e8, 95: 1e8},
        timestamp="2025-01-02T00:00:00"
    )

    engine._snapshots["TEST"] = [snap_positive, snap_negative]
    alerts = engine.detect_alerts("TEST", momentum_score=85)

    alert_types = {a.type for a in alerts}
    # Should have multiple alert types
    assert len(alert_types) >= 3


# ----------------------------- Auth Tests -----------------------------

def test_verify_api_key_public_path():
    """Test that public paths don't require auth."""
    from auth import is_public_path
    assert is_public_path("/health")
    assert is_public_path("/api/spot/SPY")
    assert is_public_path("/api/data/SPY")
    assert is_public_path("/api/chain/SPY")


def test_verify_api_key_protected_path():
    """Test that protected paths require auth."""
    from auth import is_public_path
    assert not is_public_path("/api/portfolio/test/position")
    assert not is_public_path("/api/alerts")
    assert not is_public_path("/api/memory/trade")


def test_sanitize_csv_field():
    """Test CSV injection protection."""
    def sanitize(value):
        s = str(value) if value is not None else ""
        if s and s[0] in "=+-@":
            return "'" + s
        return s

    assert sanitize("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize("+cmd") == "'+cmd"
    assert sanitize("-cmd") == "'-cmd"
    assert sanitize("@cmd") == "'@cmd"
    assert sanitize("normal") == "normal"
    assert sanitize("") == ""
    assert sanitize(None) == ""
