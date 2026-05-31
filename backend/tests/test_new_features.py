"""Tests for ML pipeline, data layer, and trading execution."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_gex_snapshot_schema():
    from data.repositories import GexSnapshot
    snap = GexSnapshot(ticker="SPY", ts="2025-01-01T00:00:00Z", spot=450.0)
    assert snap.ticker == "SPY"
    assert snap.regime == "unknown"


def test_alert_history_schema():
    from data.repositories import AlertHistory
    alert = AlertHistory(ticker="SPY", ts="2025-01-01T00:00:00Z", alert_type="GAMMA_FLIP", priority="HIGH", message="Test")
    assert alert.priority == "HIGH"


def test_data_quality_valid():
    from data.repositories import DataQualityChecker, GexSnapshot
    valid = GexSnapshot(ticker="SPY", ts="2025-01-01T00:00:00Z", spot=450.0, regime="POSITIVE",
                        total_gex=1e9, net_gex=5e8,
                        strikes_compact=[{"strike": 450.0, "gex": 1e8}])
    issues = DataQualityChecker.validate_snapshot(valid)
    assert len(issues) == 0


def test_data_quality_invalid():
    from data.repositories import DataQualityChecker, GexSnapshot
    invalid = GexSnapshot(ticker="", ts="2025-01-01T00:00:00Z", spot=-1, regime="INVALID")
    issues = DataQualityChecker.validate_snapshot(invalid)
    assert len(issues) >= 3


def test_iron_condor_strategy():
    from paper_trading import IronCondor
    ic = IronCondor(call_strike_high=460, call_strike_low=455, put_strike_high=440, put_strike_low=435, expiry="2025-01-17")
    assert ic.type == "iron_condor"


def test_strategy_typo_fixed():
    from paper_trading import DEFAULT_STRATEGY
    assert DEFAULT_STRATEGY == "iron_condor"
    assert "iron_condible" not in dir()


def test_client_order_id():
    from paper_trading import generate_client_order_id
    intent = {"ticker": "SPY", "side": "buy", "qty": 1}
    id1 = generate_client_order_id(intent, "s1")
    id2 = generate_client_order_id(intent, "s1")
    id3 = generate_client_order_id(intent, "s2")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 16


def test_gex_surface():
    from services.analytics import GexSurfaceComputer
    contracts = [
        {"strike": 450, "expiry": "2025-01-17", "type": "call", "gamma": 0.05, "oi": 1000},
        {"strike": 450, "expiry": "2025-01-17", "type": "put", "gamma": 0.05, "oi": 500},
    ]
    surface = GexSurfaceComputer.compute_surface(450.0, contracts)
    assert "strikes" in surface
    assert surface["spot"] == 450.0


def test_regime_statistics():
    from services.analytics import HistoricalGexAnalyzer
    snaps = [
        {"regime": "POSITIVE", "spot": 450.0, "total_gex": 1e9, "net_gex": 5e8},
        {"regime": "POSITIVE", "spot": 451.0, "total_gex": 1.1e9, "net_gex": 6e8},
        {"regime": "NEGATIVE", "spot": 449.0, "total_gex": -1e9, "net_gex": -5e8},
    ]
    stats = HistoricalGexAnalyzer.compute_regime_statistics(snaps)
    assert stats["total_snapshots"] == 3
    assert stats["regime_changes"] == 1


def test_multi_ticker_compare():
    from services.analytics import MultiTickerComparator
    snaps = {
        "SPY": [{"regime": "POSITIVE", "spot": 450.0, "net_gex": 5e8, "total_gex": 1e9, "king_strike": 450.0}],
        "QQQ": [{"regime": "NEGATIVE", "spot": 400.0, "net_gex": -5e8, "total_gex": -1e9, "king_strike": 400.0}],
    }
    comp = MultiTickerComparator.compare_regimes(snaps)
    assert "tickers" in comp
