"""Agent C (P1-7): whale tracker — bookmark → live state via Vol/ΔOI decay.

States: STILL_IN (OI held) / PARTIAL (OI decayed 10-50%) / EXITED (OI
collapsed >50%, or closer-shape: volume burst + OI decay) / EXPIRED
(past expiry). P&L is the side-signed UNDERLYING-leg move (proxy, not
premium P&L — labeled as such; premium needs chain mids at scan time).
"""
import pytest

from services.journal_store import (
    bookmark_whale,
    init_whale_tables,
    read_whales,
    update_whales,
    whale_state,
)


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe

    eng = dbe.DuckDBEngine(":memory:")
    init_whale_tables(eng)
    yield eng


def _alert(**kw):
    base = dict(key="whale|SPY|call|700|2026-09-18", ckey="SPY|call|700|2026-09-18",
                under="SPY", type="call", side="BUY", bias="BULLISH",
                strike=700.0, exp="2026-09-18", dte=10, tier="GOLD",
                asof="2026-09-05T10:00:00")
    base.update(kw)
    return base


def test_bookmark_is_idempotent(fresh_engine):
    assert bookmark_whale(fresh_engine, _alert(), spot=770.0, oi=5000, vol=30000) == 1
    assert bookmark_whale(fresh_engine, _alert(), spot=770.0, oi=5000, vol=30000) == 0
    assert len(read_whales(fresh_engine)) == 1


def test_still_in_while_oi_held(fresh_engine):
    bookmark_whale(fresh_engine, _alert(), spot=770.0, oi=5000, vol=30000)
    out = update_whales(fresh_engine, {"SPY|call|700|2026-09-18":
                                       {"spot": 775.0, "oi": 4900, "vol": 8000, "dte": 9}})
    assert out["SPY|call|700|2026-09-18"]["state"] == "STILL_IN"
    assert out["SPY|call|700|2026-09-18"]["pnl_underlying_pct"] == pytest.approx(
        round((775.0 - 770.0) / 770.0 * 100, 2))


def test_partial_on_oi_decay(fresh_engine):
    bookmark_whale(fresh_engine, _alert(), spot=770.0, oi=5000, vol=30000)
    out = update_whales(fresh_engine, {"SPY|call|700|2026-09-18":
                                       {"spot": 775.0, "oi": 3000, "vol": 8000, "dte": 9}})
    assert out["SPY|call|700|2026-09-18"]["state"] == "PARTIAL"


def test_exited_on_oi_collapse_and_on_closer_shape(fresh_engine):
    assert whale_state({"entry_spot": 770.0, "entry_oi": 5000, "entry_vol": 30000,
                        "side": "BUY", "type": "call"},
                       {"spot": 775.0, "oi": 1000, "vol": 8000, "dte": 9})["state"] == "EXITED"
    assert whale_state({"entry_spot": 770.0, "entry_oi": 5000, "entry_vol": 5000,
                        "side": "BUY", "type": "call"},
                       {"spot": 775.0, "oi": 3500, "vol": 20000, "dte": 9})["state"] == "EXITED"


def test_expired_past_expiry(fresh_engine):
    bookmark_whale(fresh_engine, _alert(), spot=770.0, oi=5000, vol=30000)
    out = update_whales(fresh_engine, {"SPY|call|700|2026-09-18":
                                       {"spot": 775.0, "oi": 4900, "vol": 8000, "dte": 0}})
    assert out["SPY|call|700|2026-09-18"]["state"] == "EXPIRED"


def test_no_oi_basis_holds_with_honest_reason():
    out = whale_state({"entry_spot": 770.0, "entry_oi": 0, "entry_vol": 0,
                       "side": "BUY", "type": "call"},
                      {"spot": 775.0, "oi": 4900, "vol": 8000, "dte": 9})
    assert out["state"] == "STILL_IN"
    assert "no OI basis" in out["reason"]
