"""
backend/tests/services/test_flow_alerts.py

Institutional flow-alert engine (server-side port of scanLogic.js evalAlerts
+ enrichment the frontend never had: BS entry price, side/bias inference,
GOLD/SILVER/BRONZE conviction tiers, DuckDB-persisted feed with dedup TTLs
and move-since-alert tracking).

Families:
  NORMALIZATION      — cvforge screen list-rows → dicts, biz-day DTE
  SCORING PARITY     — scan_score mirrors scanLogic.scanScoreOf semantics
  ENTRY PRICE        — Black-Scholes per-contract entry estimate
  SIDE / BIAS        — opening-flow inference
  TIERING            — deterministic factor-count table
  EVAL               — rule emission (OICONF cap, SCORE, WHALE, 0DTE, SIGMA)
  DUCKDB I/O         — init idempotent, persist/read round-trip, dedup TTL,
                       move-since-alert update
"""

from datetime import date, timedelta

import pytest

from services.flow_alerts import (
    SCAN_COLUMNS,
    biz_dte,
    dedup_filter,
    est_entry,
    eval_institutional,
    infer_side_bias,
    init_flow_alert_tables,
    norm_rows,
    persist_alerts,
    read_alert_feed,
    scan_score,
    tier_of,
    update_moves,
)


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe

    engine = dbe.DuckDBEngine(":memory:")
    yield engine


def _future_exp(biz_days: int) -> str:
    """An expiry string `biz_days` business days out from today."""
    d = date.today()
    added = 0
    while added < biz_days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.isoformat()


def _raw(under="PLTR", occ="O:PLTR260724C00138000", typ="call", strike=138.0,
         exp=None, vol=18000, oi=1200, iv=0.62, delta=0.38, spot=133.0):
    """One cvforge screen row in list form, ordered per SCAN_COLUMNS."""
    return [under, occ, typ, strike, exp or _future_exp(4), vol, oi, iv, delta, spot]


# ── NORMALIZATION ────────────────────────────────────────────────────

def test_norm_rows_maps_columns_and_derives_metrics():
    rows = norm_rows([_raw()])
    assert len(rows) == 1
    r = rows[0]
    assert r["under"] == "PLTR" and r["type"] == "call" and r["strike"] == 138.0
    assert r["vol"] == 18000 and r["oi"] == 1200
    assert r["vol_oi"] == pytest.approx(15.0)
    assert r["spot"] == 133.0
    assert r["dte"] >= 1
    assert r["notional"] == pytest.approx(18000 * 100 * 138.0)
    assert r["premium"] is not None and r["premium"] > 0


def test_norm_rows_drops_malformed_rows_not_crash():
    rows = norm_rows([
        _raw(),
        ["MSFT"],                       # truncated
        None,                           # junk
        _raw(under="", strike=None),    # unusable
    ])
    assert len(rows) == 1


@pytest.mark.flaky_env
def test_biz_dte_same_day_is_zero_and_skips_weekends():
    assert biz_dte(date.today().isoformat()) == 0
    assert biz_dte(_future_exp(3)) == 3


# ── SCORING PARITY ──────────────────────────────────────────────────

def test_scan_score_high_conviction_row_scores_high():
    r = norm_rows([_raw(vol=60000, oi=1500, delta=0.25)])[0]
    assert scan_score(r) >= 85


def test_scan_score_sleepy_row_scores_well_below_alert_floor():
    # Deep-ITM low-vol/OI churn: the parity formula lands ~43 (notional term)
    # — what matters is it can never reach the 85 SCORE alert floor.
    r = norm_rows([_raw(vol=1200, oi=40000, delta=0.9, strike=140, iv=0.2)])[0]
    assert scan_score(r) <= 55


def test_scan_score_negative_gamma_regime_nudges_short_dte_up():
    r = norm_rows([_raw(exp=_future_exp(2))])[0]
    assert scan_score(r, regime="negative") >= scan_score(r) + 4


def test_scan_score_clamped_0_100():
    r = norm_rows([_raw(vol=10_000_000, oi=1)])[0]
    assert 0 <= scan_score(r) <= 100


# ── ENTRY PRICE ─────────────────────────────────────────────────────

def test_est_entry_atm_call_reasonable_and_positive():
    r = norm_rows([_raw(strike=133.0, delta=0.5)])[0]
    px = est_entry(r)
    # ATM weekly on a $133 underlying at 62 vol ≈ low single digits
    assert px is not None and 0.5 < px < 15.0


def test_est_entry_deep_otm_cheaper_than_atm():
    atm = est_entry(norm_rows([_raw(strike=133.0, delta=0.5)])[0])
    otm = est_entry(norm_rows([_raw(strike=175.0, delta=0.05)])[0])
    assert otm < atm


def test_est_entry_floor_never_below_five_cents():
    r = norm_rows([_raw(strike=400.0, delta=0.001, iv=0.15)])[0]
    assert est_entry(r) >= 0.05


def test_est_entry_missing_iv_returns_none():
    r = norm_rows([_raw(iv=None)])[0]
    assert est_entry(r) is None


# ── SIDE / BIAS ─────────────────────────────────────────────────────

def test_opening_call_flow_is_buy_bullish():
    r = norm_rows([_raw(typ="call", vol=9000, oi=900)])[0]
    side, bias = infer_side_bias(r)
    assert side == "BUY" and bias == "BULLISH"


def test_opening_put_flow_is_buy_bearish():
    r = norm_rows([_raw(typ="put", vol=9000, oi=900, delta=-0.3)])[0]
    side, bias = infer_side_bias(r)
    assert side == "BUY" and bias == "BEARISH"


def test_low_vol_oi_is_flow_with_no_bias_claim():
    r = norm_rows([_raw(vol=500, oi=9000)])[0]
    side, bias = infer_side_bias(r)
    assert side == "FLOW" and bias is None


# ── TIERING ─────────────────────────────────────────────────────────

def test_tier_three_factors_is_gold():
    assert tier_of({"oiconf": True, "sigma": True, "score90": True}) == "GOLD"


def test_tier_two_factors_is_silver():
    assert tier_of({"whale": True, "informed_band": True}) == "SILVER"


def test_tier_one_factor_is_bronze_zero_is_none():
    assert tier_of({"score90": True}) == "BRONZE"
    assert tier_of({}) is None
    assert tier_of({"oiconf": False}) is None


# ── EVAL ────────────────────────────────────────────────────────────

def test_eval_score_rule_fires_with_entry_side_tier():
    rows = norm_rows([_raw(vol=60000, oi=1500, delta=0.25)])
    alerts = eval_institutional(rows)
    assert len(alerts) == 1
    a = alerts[0]
    assert a["rule"] == "SCORE" and a["under"] == "PLTR"
    assert a["side"] == "BUY" and a["bias"] == "BULLISH"
    assert a["est_entry"] is not None and a["est_entry"] > 0
    assert a["tier"] in ("GOLD", "SILVER", "BRONZE")
    assert a["under_price"] == 133.0
    assert "why" in a and a["why"]


def test_eval_whale_rule_premium_floor():
    # Enormous premium but middling score → WHALE catches it
    rows = norm_rows([_raw(vol=250000, oi=200000, strike=500, spot=495,
                           iv=0.5, delta=0.5, exp=_future_exp(40))])
    alerts = eval_institutional(rows, opts={"min_score": 101})
    assert any(a["rule"] == "WHALE" for a in alerts)


def test_calibration_attached_stage0_uncalibrated_never_blocks():
    """Stage-0 calibration → every fired alert carries p_move=None +
    method 'uncalibrated' and NO alert is suppressed (None never gates)."""
    rows = norm_rows([_raw(vol=60000, oi=1500)])
    cal = {"stage": 0, "model": None, "n": 42, "method_note": "uncalibrated: n=42 < 60"}
    alerts = eval_institutional(rows, opts={"min_score": 1, "whale_premium": 1.0,
                                            "calibration": cal})
    assert alerts, "alerts must still fire with an uncalibrated model"
    for a in alerts:
        assert a["p_move"] is None
        assert a["p_method"] == "uncalibrated"
        assert a["p_n"] == 42


def test_calibration_attached_stage1_real_p_on_alerts():
    """Stage-1 decile model → fired alerts carry the measured decile p."""
    rows = norm_rows([_raw(vol=60000, oi=1500)])
    # Fixture alert scores 89 → decile 8. Cover BOTH 8 and 9 so the test
    # pins the p-attach contract, not the fixture's exact score.
    cal = {"stage": 1, "n": 120, "method_note": "decile",
           "model": {"kind": "decile", "n": 120,
                     "table": {"8": {"n": 40, "hits": 16, "p": 0.4, "ci": [0.26, 0.56]},
                               "9": {"n": 40, "hits": 20, "p": 0.5, "ci": [0.35, 0.65]}}}}
    alerts = eval_institutional(rows, opts={"min_score": 1, "whale_premium": 1.0,
                                            "calibration": cal})
    scored = [a for a in alerts if a.get("score") is not None and (a["score"] or 0) >= 80]
    assert scored, "fixture must produce a SCORE-band alert"
    for a in scored:
        d = str(min(9, int(a["score"] or 0) // 10))
        assert a["p_move"] == cal["model"]["table"][d]["p"]
        assert a["p_method"] == "decile"


def test_eval_oiconf_capped_at_top5_by_pct():
    rows = []
    for i in range(8):
        rows.append(_raw(under=f"T{i}", occ=f"O:T{i}", strike=100 + i, vol=5000, oi=4000))
    normed = norm_rows(rows)
    # prior OI small → today's OI is a big % build for every contract
    prev = {r["ckey"]: 1000 for r in normed}
    alerts = eval_institutional(normed, prev_oi=prev, opts={"min_score": 101, "whale_premium": 1e12})
    oiconf = [a for a in alerts if a["rule"] == "OICONF"]
    assert len(oiconf) == 5


def test_eval_sigma_rule_needs_baseline_std():
    rows = norm_rows([_raw(vol=50000, oi=45000)])
    baselines = {"PLTR": {"avg": 8000, "std": 4000, "days": 5}}
    alerts = eval_institutional(rows, baselines=baselines,
                                opts={"min_score": 101, "whale_premium": 1e12})
    sig = [a for a in alerts if a["rule"] == "SIGMA"]
    assert len(sig) == 1 and sig[0]["sigma"] >= 4
    # no std → no SIGMA
    assert not [a for a in eval_institutional(rows, baselines={"PLTR": {"avg": 8000, "std": 0, "days": 5}},
                                              opts={"min_score": 101, "whale_premium": 1e12})
                if a["rule"] == "SIGMA"]


def test_eval_one_alert_per_contract_strongest_rule_wins():
    rows = norm_rows([_raw(vol=60000, oi=1500)])
    prev = {rows[0]["ckey"]: 100}
    alerts = eval_institutional(rows, prev_oi=prev)
    assert len([a for a in alerts if a["ckey"] == rows[0]["ckey"]]) == 1
    assert alerts[0]["rule"] == "OICONF"


# ── DUCKDB I/O ──────────────────────────────────────────────────────

def test_init_tables_idempotent(fresh_engine):
    init_flow_alert_tables(fresh_engine)
    init_flow_alert_tables(fresh_engine)


def test_persist_and_read_round_trip(fresh_engine):
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([_raw(vol=60000, oi=1500, delta=0.25)])
    alerts = eval_institutional(rows)
    n = persist_alerts(fresh_engine, alerts)
    assert n == 1
    feed = read_alert_feed(fresh_engine, days=3)
    assert len(feed) == 1
    f = feed[0]
    assert f["under"] == "PLTR" and f["rule"] == "SCORE"
    assert f["est_entry"] is not None and f["tier"]


def test_dedup_filter_suppresses_within_ttl_and_refires_after(fresh_engine):
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([_raw(vol=60000, oi=1500)])
    # Low the alert gates so this tests the DEDUP mechanics, not the alert
    # thresholds (which tightened in the 2026-09-02 noise pass).
    alerts = eval_institutional(rows, opts={"min_score": 1, "whale_premium": 1.0})
    first = dedup_filter(fresh_engine, alerts, now=1000.0)
    assert len(first) == 1
    again = dedup_filter(fresh_engine, alerts, now=1000.0 + 60)
    assert len(again) == 0
    later = dedup_filter(fresh_engine, alerts, now=1000.0 + alerts[0]["ttl_s"] + 1)
    assert len(later) == 1


def test_update_moves_sets_move_pct_from_new_spot(fresh_engine):
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([_raw(vol=60000, oi=1500, spot=133.0)])
    persist_alerts(fresh_engine, eval_institutional(rows, opts={"min_score": 1, "whale_premium": 1.0}))
    changed = update_moves(fresh_engine, {"PLTR": 138.2})
    assert changed == 1
    f = read_alert_feed(fresh_engine, days=3)[0]
    assert f["last_price"] == pytest.approx(138.2)
    assert f["move_pct"] == pytest.approx((138.2 - 133.0) / 133.0 * 100, rel=1e-3)


def test_read_alert_feed_min_tier_filter_and_order(fresh_engine):
    init_flow_alert_tables(fresh_engine)
    gold_rows = norm_rows([_raw(vol=60000, oi=1500)])
    prev = {gold_rows[0]["ckey"]: 100}
    baselines = {"PLTR": {"avg": 8000, "std": 4000, "days": 5}}
    a1 = eval_institutional(gold_rows, prev_oi=prev, baselines=baselines)
    bronze_rows = norm_rows([_raw(under="XYZ", occ="O:XYZ", vol=30000, oi=2500, delta=0.3)])
    a2 = eval_institutional(bronze_rows)
    persist_alerts(fresh_engine, a1 + a2)
    all_feed = read_alert_feed(fresh_engine, days=3)
    assert len(all_feed) >= 2
    tiers = [f["tier"] for f in all_feed]
    assert tiers == sorted(tiers, key=lambda t: {"GOLD": 0, "SILVER": 1, "BRONZE": 2}[t])
    top_only = read_alert_feed(fresh_engine, days=3, min_tier="SILVER")
    assert all(f["tier"] in ("GOLD", "SILVER") for f in top_only)


def test_persist_same_key_same_day_upserts_not_duplicates(fresh_engine):
    init_flow_alert_tables(fresh_engine)
    alerts = eval_institutional(norm_rows([_raw(vol=60000, oi=1500)]),
                                opts={"min_score": 1, "whale_premium": 1.0})
    persist_alerts(fresh_engine, alerts)
    persist_alerts(fresh_engine, alerts)
    assert len(read_alert_feed(fresh_engine, days=3)) == 1


# ── GEX CONFLUENCE (Conviction v2) ──────────────────────────────────

def _bearish_raw(**kw):
    return _raw(typ="put", vol=60000, oi=1500, **kw)


def test_gex_confluent_fires_on_lowercase_bias_vs_negative_gamma():
    """bias 'BEARISH' (uppercase from infer_side_bias) must match negative
    gamma regime — the historical bug was a case-sensitive comparison."""
    from services.flow_alerts import _common_factors
    r = dict(norm_rows([_bearish_raw()])[0])
    r["bias"] = "BEARISH"
    gex_ctx = {"PLTR": {"gamma_imbalance": {"gamma_imbalance_pct": -1.2,
                                            "regime": "negative_gamma"}}}
    f = _common_factors(r, {}, set(), {}, {}, gex_context=gex_ctx)
    assert f["gex_confluent"] is True
    assert f["gex_regime"] == "negative"


def test_gex_confluent_fires_bullish_positive_gamma():
    from services.flow_alerts import _common_factors
    r = dict(norm_rows([_raw(vol=60000, oi=1500)])[0])
    gex_ctx = {"PLTR": {"gamma_imbalance": {"gamma_imbalance_pct": 0.9,
                                            "regime": "positive_gamma"}}}
    f = _common_factors(r, {}, set(), {}, {}, gex_context=gex_ctx)
    assert f["gex_confluent"] is True
    assert f["gex_regime"] == "positive"


def test_gex_confluent_false_when_opposed():
    from services.flow_alerts import _common_factors
    r = dict(norm_rows([_raw(vol=60000, oi=1500)])[0])
    gex_ctx = {"PLTR": {"gamma_imbalance": {"gamma_imbalance_pct": -1.2,
                                            "regime": "negative_gamma"}}}
    f = _common_factors(r, {}, set(), {}, {}, gex_context=gex_ctx)
    assert f["gex_confluent"] is False


def test_gex_confluent_false_without_context():
    from services.flow_alerts import _common_factors
    r = dict(norm_rows([_raw(vol=60000, oi=1500)])[0])
    f = _common_factors(r, {}, set(), {}, {})
    assert f["gex_confluent"] is False
    assert f["gex_regime"] is None
