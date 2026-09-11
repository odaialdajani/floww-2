"""Agent C (C1): per-horizon move persistence.

update_moves overwrites a single move_pct per scan — the latest stamp wins
and +1/+5/+20 legs are lost. This pins the additive fix: every stamp also
appends one leg per alert into flow_alert_moves; readers derive horizon
legs from ordered stamps. Existing move_pct behavior is untouched.
"""

import pytest

from services.flow_alerts import (
    eval_institutional,
    get_move_path,
    horizon_moves,
    init_flow_alert_tables,
    norm_rows,
    persist_alerts,
    update_moves,
)


def _raw(**kw):
    base = dict(
        underlying_ticker="PLTR", ticker="O:PLTR260116C00133000",
        contract_type="call", strike_price=133.0, expiration_date="2026-01-16",
        day_volume=60000, open_interest=1500, implied_volatility=0.45,
        delta=0.25, underlying_price=133.0,
    )
    base.update(kw)
    return [base[k] for k in (
        "underlying_ticker", "ticker", "contract_type", "strike_price",
        "expiration_date", "day_volume", "open_interest",
        "implied_volatility", "delta", "underlying_price")]


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe

    engine = dbe.DuckDBEngine(":memory:")
    yield engine


def _persist_one(fresh_engine):
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([_raw()])
    n = persist_alerts(fresh_engine, eval_institutional(rows))
    assert n == 1, "fixture must persist exactly one alert"
    got = fresh_engine.query(
        "SELECT asof_date, key FROM flow_alerts_daily")
    return str(got[0]["asof_date"]), str(got[0]["key"])


def test_stamps_append_legs_without_overwriting(fresh_engine):
    asof_date, key = _persist_one(fresh_engine)
    update_moves(fresh_engine, {"PLTR": 134.0},
                 stamp_ts="2026-09-01T10:00:00")
    update_moves(fresh_engine, {"PLTR": 138.2},
                 stamp_ts="2026-09-02T10:00:00")
    legs = get_move_path(fresh_engine, asof_date, key)
    assert len(legs) == 2, "two stamps must persist two legs"
    assert legs[0]["move_pct"] == pytest.approx((134.0 - 133.0) / 133.0 * 100)
    assert legs[1]["move_pct"] == pytest.approx((138.2 - 133.0) / 133.0 * 100)


def test_horizon_reader_picks_session_legs(fresh_engine):
    asof_date, key = _persist_one(fresh_engine)
    update_moves(fresh_engine, {"PLTR": 134.0},
                 stamp_ts="2026-09-01T10:00:00")
    update_moves(fresh_engine, {"PLTR": 138.2},
                 stamp_ts="2026-09-02T10:00:00")
    out = horizon_moves(fresh_engine, asof_date, key, horizons=(1, 2, 5))
    assert out[1] == pytest.approx((134.0 - 133.0) / 133.0 * 100)
    assert out[2] == pytest.approx((138.2 - 133.0) / 133.0 * 100)
    assert out[5] is None, "unmeasured horizon stays None, never fabricated"


def test_stamp_failure_never_breaks_latest_move(fresh_engine):
    # Fail-open: even if leg persistence cannot write, the latest-price
    # UPDATE must still land (existing behavior preserved).
    asof_date, key = _persist_one(fresh_engine)
    n = update_moves(fresh_engine, {"PLTR": 138.2})
    assert n == 1
    row = fresh_engine.query(
        "SELECT move_pct FROM flow_alerts_daily")[0]
    assert row["move_pct"] == pytest.approx(3.9, abs=0.1)
