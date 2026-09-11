"""
backend/tests/services/test_flow_desk.py

The desk pass — post-eval hardening that runs AFTER eval_institutional and
BEFORE dedup/persist (collision-safe sibling of flow_alerts/flow_quality):

  VOL DELTAS  — per-contract cumulative-volume marks → NEW interest since
                the last scan (cvforge day_volume is cumulative; without
                this, a 10am print keeps re-qualifying all day on stale
                volume once its dedup TTL lapses)
  FRESH GATE  — intraday rules re-fire only on fresh interest
  CAMPAIGN    — same contract alerting on multiple prior sessions =
                institutional campaign → one-notch tier promotion
  IV CONTEXT  — per-ticker daily median-IV store → demote directional
                alerts fired into rich vol (>=80th own-history percentile)
"""

from datetime import date, datetime, timedelta

import pytest

from services.flow_alerts import eval_institutional, init_flow_alert_tables, norm_rows, persist_alerts
from services.flow_desk import (
    apply_campaign,
    desk_pass,
    fresh_gate,
    init_desk_tables,
    iv_context,
    mark_vol_deltas,
    read_prior_alert_days,
    record_iv_daily,
)
from tests.services.test_flow_alerts import _future_exp, _raw


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe

    engine = dbe.DuckDBEngine(":memory:")
    init_desk_tables(engine)
    yield engine


def _alert(ckey="PLTR|call|138|2026-08-01", rule="SCORE", tier="SILVER",
           bias="BULLISH", notional=1e7, strike=138.0, why="w"):
    return {"key": f"{rule.lower()}|{ckey}", "ckey": ckey, "rule": rule,
            "tier": tier, "bias": bias, "under": ckey.split("|")[0],
            "notional": notional, "strike": strike, "why": why}


# ── VOL DELTAS ──────────────────────────────────────────────────────

def test_first_sight_has_no_delta_but_writes_mark(fresh_engine):
    rows = norm_rows([_raw(vol=10000)])
    d1 = mark_vol_deltas(fresh_engine, rows)
    assert d1[rows[0]["ckey"]] is None
    d2 = mark_vol_deltas(fresh_engine, rows)          # same cumulative vol
    assert d2[rows[0]["ckey"]] == 0


def test_delta_is_new_volume_since_last_mark(fresh_engine):
    rows = norm_rows([_raw(vol=10000)])
    mark_vol_deltas(fresh_engine, rows)
    rows2 = norm_rows([_raw(vol=14500)])
    d = mark_vol_deltas(fresh_engine, rows2)
    assert d[rows2[0]["ckey"]] == 4500


def test_session_rollover_resets_to_full_volume(fresh_engine):
    rows = norm_rows([_raw(vol=30000)])
    mark_vol_deltas(fresh_engine, rows)
    rows2 = norm_rows([_raw(vol=2000)])               # new day: cumulative reset
    d = mark_vol_deltas(fresh_engine, rows2)
    assert d[rows2[0]["ckey"]] == 2000


# ── FRESH GATE ──────────────────────────────────────────────────────

def test_fresh_gate_suppresses_stale_intraday_alert():
    a = _alert(notional=10000 * 100 * 138.0)          # vol=10000
    kept = fresh_gate([a], {a["ckey"]: 120})          # only 120 new contracts
    assert kept == []


def test_fresh_gate_keeps_fresh_alert_and_unknown_delta():
    a = _alert(notional=10000 * 100 * 138.0)
    assert fresh_gate([a], {a["ckey"]: 5000}) == [a]
    assert fresh_gate([a], {}) == [a]                 # never seen → no gate
    assert fresh_gate([a], {a["ckey"]: None}) == [a]


def test_fresh_gate_never_touches_oiconf_or_sigma():
    a = _alert(rule="OICONF", notional=10000 * 100 * 138.0)
    b = _alert(rule="SIGMA", ckey="PLTR", notional=None, strike=None)
    assert fresh_gate([a, b], {"PLTR|call|138|2026-08-01": 0, "PLTR": 0}) == [a, b]


def test_fresh_gate_fractional_rule_for_big_contracts():
    # vol 100k: 3k new is < 10% — stale re-print despite clearing min_abs
    a = _alert(notional=100000 * 100 * 138.0)
    assert fresh_gate([a], {a["ckey"]: 3000}) == []


# ── CAMPAIGN ────────────────────────────────────────────────────────

def test_prior_alert_days_counts_distinct_prior_sessions(fresh_engine, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 11, 12, tzinfo=tz)
    monkeypatch.setattr("services.flow_desk.datetime", FixedDateTime)
    init_flow_alert_tables(fresh_engine)
    alert = {**_alert(), "asof": "2026-09-11T12:00:00", "type": "call", "exp": "2026-09-18"}
    for day in ("2026-09-09", "2026-09-10", "2026-09-11"):
        # Same contract has two distinct rules each day, and one repeated upsert.
        second = {**alert, "key": "whale|" + alert["ckey"], "rule": "WHALE"}
        assert persist_alerts(fresh_engine, [alert, second], snapshot_date=day) == 2
        assert persist_alerts(fresh_engine, [alert], snapshot_date=day) == 1
    assert persist_alerts(fresh_engine, [alert], snapshot_date="2026-08-20") == 1
    days = read_prior_alert_days(fresh_engine, [alert["ckey"]])
    assert days == {alert["ckey"]: 2}  # today, duplicates and outside-lookback rows excluded


def test_apply_campaign_promotes_one_notch_with_reason():
    a = _alert(tier="SILVER")
    n = apply_campaign([a], {a["ckey"]: 3})
    assert n == 1 and a["tier"] == "GOLD" and "campaign" in a["why"]


def test_apply_campaign_ignores_short_history_and_directionless():
    a = _alert(tier="SILVER")
    assert apply_campaign([a], {a["ckey"]: 1}) == 0 and a["tier"] == "SILVER"
    b = _alert(tier="BRONZE", bias=None)
    assert apply_campaign([b], {b["ckey"]: 5}) == 0 and b["tier"] == "BRONZE"


# ── IV CONTEXT ──────────────────────────────────────────────────────

def test_record_iv_daily_upserts_median(fresh_engine):
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(occ="O:1", strike=130.0, exp=exp, iv=0.50),
        _raw(occ="O:2", strike=138.0, exp=exp, iv=0.60),
        _raw(occ="O:3", strike=145.0, exp=exp, iv=0.70),
    ])
    assert record_iv_daily(fresh_engine, rows) == 1
    assert record_iv_daily(fresh_engine, rows) == 1   # idempotent upsert


def test_iv_context_demotes_directional_alert_in_rich_vol(fresh_engine):
    d0 = date.today()
    for i in range(6):                                # 6 prior days at IV .30
        rows = norm_rows([_raw(iv=0.30)])
        record_iv_daily(fresh_engine, rows, snapshot_date=(d0 - timedelta(days=6 - i)).isoformat())
    today_rows = norm_rows([_raw(iv=0.90)])           # today: extreme rich
    record_iv_daily(fresh_engine, today_rows)
    a = _alert(tier="GOLD")
    n = iv_context(fresh_engine, [a])
    assert n == 1 and a["tier"] == "SILVER" and "IV" in a["why"]


def test_iv_context_noop_with_thin_history(fresh_engine):
    record_iv_daily(fresh_engine, norm_rows([_raw(iv=0.90)]))
    a = _alert(tier="GOLD")
    assert iv_context(fresh_engine, [a]) == 0 and a["tier"] == "GOLD"


# ── DESK PASS ───────────────────────────────────────────────────────

def test_desk_pass_composes_and_returns_alert_list(fresh_engine):
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([_raw(vol=60000, oi=1500, delta=0.25)])
    alerts = eval_institutional(rows)
    out = desk_pass(fresh_engine, rows, alerts)
    assert isinstance(out, list) and out               # first sight: nothing gated
    out2 = desk_pass(fresh_engine, rows, eval_institutional(rows))
    assert out2 == []                                  # same cumulative vol: stale
