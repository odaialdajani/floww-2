"""
backend/tests/services/test_flow_quality.py

Conviction v2 — the quality-over-quantity layer (spec:
docs/superpowers/specs/2026-07-20-flow-quality-conviction-v2-design.md).

Families:
  SPREADS   — vertical + straddle leg pairing, ratio gate, volume floor
  CW SPREAD — Cremers-Weinbaum volume-weighted call-put IV spread
  CLUSTERS  — same-ticker same-bias laddering
  BH-FDR    — Benjamini-Hochberg control on sigma alerts
  PRIME     — the $250k + vol/OI>=5 empirical conviction bracket
  INTEGRATION — eval_institutional caps spread legs, CW/cluster factors count
"""

import pytest

from services.flow_alerts import (
    DEFAULT_EVAL_OPTS,
    alert_quality,
    alert_quality_daily,
    eval_institutional,
    init_flow_alert_tables,
    norm_rows,
    persist_alerts,
    update_moves,
)


def test_default_gate_matches_noise_pass():
    """Pin the production alert gates in exactly one place.

    2026-09-02 institutional noise pass (SCORE 85→92, WHALE $10M→$25M,
    SIGMA 3.0→6.0, mirroring the frontend DEFAULT_RULES). Logic tests
    pass explicit opts so a deliberate gate change breaks HERE (loud,
    intentional) instead of surfacing as four mysterious fixture failures.
    """
    assert DEFAULT_EVAL_OPTS["min_score"] == 92
    assert DEFAULT_EVAL_OPTS["whale_premium"] == 25e6
    # 0DTE parity with the frontend tape (zeroDteScore=85 + volOI>=2 lotto
    # shutout) — server must not fire where the tape stays silent.
    assert DEFAULT_EVAL_OPTS["zero_dte_score"] == 85
    assert DEFAULT_EVAL_OPTS["zero_dte_vol_oi"] == 2.0
    assert DEFAULT_EVAL_OPTS["sigma_min"] == 6.0
from services.flow_quality import (
    bh_fdr,
    cluster_biases,
    cw_iv_spread,
    detect_spreads,
    is_prime,
    sigma_pvalue,
)
from tests.services.test_flow_alerts import _future_exp, _raw


def _rows(*specs):
    return norm_rows([_raw(**s) for s in specs])


# ── SPREADS ─────────────────────────────────────────────────────────

def test_vertical_spread_legs_flagged():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="AMD", occ="O:A1", strike=150.0, exp=exp, vol=5000, oi=800),
        dict(under="AMD", occ="O:A2", strike=155.0, exp=exp, vol=5200, oi=700),
    )
    detect_spreads(rows)
    assert rows[0]["spread_leg"] and rows[1]["spread_leg"]


def test_straddle_legs_flagged_opposite_types_same_strike():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="AMD", occ="O:A1", typ="call", strike=150.0, exp=exp, vol=4000, oi=500, delta=0.5),
        dict(under="AMD", occ="O:A2", typ="put", strike=150.0, exp=exp, vol=4100, oi=600, delta=-0.5),
    )
    detect_spreads(rows)
    assert rows[0]["spread_leg"] and rows[1]["spread_leg"]


def test_mismatched_sizes_not_a_spread():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="AMD", occ="O:A1", strike=150.0, exp=exp, vol=9000, oi=800),
        dict(under="AMD", occ="O:A2", strike=155.0, exp=exp, vol=2000, oi=700),
    )
    detect_spreads(rows)
    assert not rows[0].get("spread_leg") and not rows[1].get("spread_leg")


def test_sub_floor_volume_not_paired():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="AMD", occ="O:A1", strike=150.0, exp=exp, vol=400, oi=100),
        dict(under="AMD", occ="O:A2", strike=155.0, exp=exp, vol=420, oi=100),
    )
    detect_spreads(rows)
    assert not rows[0].get("spread_leg")


def test_different_expiries_not_paired():
    rows = _rows(
        dict(under="AMD", occ="O:A1", strike=150.0, exp=_future_exp(5), vol=5000, oi=800),
        dict(under="AMD", occ="O:A2", strike=155.0, exp=_future_exp(20), vol=5100, oi=700),
    )
    detect_spreads(rows)
    assert not rows[0].get("spread_leg")


# ── CW SPREAD ───────────────────────────────────────────────────────

def test_cw_positive_when_calls_richer_than_puts():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="PLTR", occ="O:C", typ="call", strike=140.0, exp=exp, vol=8000, iv=0.65, delta=0.4),
        dict(under="PLTR", occ="O:P", typ="put", strike=140.0, exp=exp, vol=6000, iv=0.55, delta=-0.4),
    )
    cw = cw_iv_spread(rows)
    assert cw["PLTR"] > 0.05


def test_cw_volume_weighted_across_pairs():
    exp = _future_exp(10)
    rows = _rows(
        # tiny pair, huge positive spread
        dict(under="X", occ="O:C1", typ="call", strike=100.0, exp=exp, vol=100, iv=0.9, delta=0.4),
        dict(under="X", occ="O:P1", typ="put", strike=100.0, exp=exp, vol=100, iv=0.3, delta=-0.4),
        # big pair, small negative spread — should dominate
        dict(under="X", occ="O:C2", typ="call", strike=105.0, exp=exp, vol=50000, iv=0.40, delta=0.4),
        dict(under="X", occ="O:P2", typ="put", strike=105.0, exp=exp, vol=50000, iv=0.45, delta=-0.4),
    )
    cw = cw_iv_spread(rows)
    assert cw["X"] < 0


def test_cw_no_matched_pairs_returns_no_entry():
    rows = _rows(dict(under="Y", occ="O:C", typ="call", strike=100.0, vol=5000))
    assert "Y" not in cw_iv_spread(rows)


# ── CLUSTERS ────────────────────────────────────────────────────────

def test_three_same_bias_contracts_cluster():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="NVDA", occ="O:1", strike=1300.0, exp=exp, vol=30000, oi=2000, delta=0.3),
        dict(under="NVDA", occ="O:2", strike=1320.0, exp=_future_exp(15), vol=25000, oi=1500, delta=0.25),
        dict(under="NVDA", occ="O:3", strike=1350.0, exp=exp, vol=28000, oi=1800, delta=0.2),
    )
    for r in rows:
        r["_score"] = 80
    assert "NVDA" in cluster_biases(rows)
    assert cluster_biases(rows)["NVDA"] == "BULLISH"


def test_two_contracts_do_not_cluster():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="NVDA", occ="O:1", strike=1300.0, exp=exp, vol=30000, oi=2000),
        dict(under="NVDA", occ="O:2", strike=1320.0, exp=exp, vol=25000, oi=1500),
    )
    for r in rows:
        r["_score"] = 80
    assert "NVDA" not in cluster_biases(rows)


def test_low_score_rows_do_not_cluster():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="NVDA", occ="O:1", strike=1300.0, exp=exp, vol=30000, oi=2000),
        dict(under="NVDA", occ="O:2", strike=1320.0, exp=exp, vol=25000, oi=1500),
        dict(under="NVDA", occ="O:3", strike=1350.0, exp=exp, vol=28000, oi=1800),
    )
    for r in rows:
        r["_score"] = 40
    assert "NVDA" not in cluster_biases(rows)


# ── BH-FDR ──────────────────────────────────────────────────────────

def test_sigma_pvalue_monotone():
    assert sigma_pvalue(5.0) < sigma_pvalue(4.0) < sigma_pvalue(3.0)
    assert 0 < sigma_pvalue(4.0) < 1e-3


def test_bh_fdr_null_like_grid_rejects_nothing():
    # Uniform-looking p-values (what a true null cross-section produces) —
    # BH must reject none of them.
    pvals = {f"T{i}": 0.03 + i * 0.048 for i in range(20)}
    assert bh_fdr(pvals, q=0.10) == set()


def test_bh_fdr_one_strong_signal_survives_among_nulls():
    pvals = {f"T{i}": 0.4 for i in range(50)}
    pvals["PLTR"] = sigma_pvalue(6.0)
    assert bh_fdr(pvals, q=0.10) == {"PLTR"}


def test_bh_fdr_empty_input():
    assert bh_fdr({}, q=0.10) == set()


# ── PRIME ───────────────────────────────────────────────────────────

def test_prime_bracket_thresholds():
    assert is_prime({"premium": 300e3, "vol_oi": 6.0})
    assert not is_prime({"premium": 100e3, "vol_oi": 6.0})
    assert not is_prime({"premium": 300e3, "vol_oi": 2.0})
    assert not is_prime({"premium": None, "vol_oi": None})


# ── INTEGRATION ─────────────────────────────────────────────────────

def test_eval_caps_spread_legs_to_bronze_strategy():
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(under="AMD", occ="O:A1", strike=150.0, exp=exp, vol=60000, oi=1500, delta=0.3),
        _raw(under="AMD", occ="O:A2", strike=155.0, exp=exp, vol=62000, oi=1400, delta=0.25),
    ])
    alerts = eval_institutional(rows)
    assert alerts, "spread legs still alert, but demoted"
    for a in alerts:
        if a["rule"] == "SIGMA":
            continue
        assert a["tier"] == "BRONZE"
        assert a["side"] == "STRATEGY" and a["bias"] is None


def test_eval_sigma_respects_fdr_not_raw_cutoff():
    # 30 tickers all at ~3.2 sigma: every one passes the OLD raw >=3 style
    # gate individually, but jointly they are exactly the multiple-testing
    # trap — BH at q=0.10 must NOT pass all of them.
    rows, baselines = [], {}
    for i in range(30):
        t = f"T{i:02d}"
        rows.append(_raw(under=t, occ=f"O:{t}", strike=100.0, vol=18000, oi=17000))
        baselines[t] = {"avg": 10000, "std": 2500, "days": 6}
    normed = norm_rows(rows)
    alerts = eval_institutional(normed, baselines=baselines,
                                opts={"min_score": 101, "whale_premium": 1e12})
    sigma_alerts = [a for a in alerts if a["rule"] == "SIGMA"]
    assert len(sigma_alerts) < 30


def test_eval_cluster_and_cw_lift_tier():
    # Laddered accumulation across DIFFERENT expiries (so no vertical
    # pairing) + a strike-matched put whose IV sits 20 vols under the call
    # (Cremers-Weinbaum bullish confirmation).
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(under="PLTR", occ="O:1", strike=138.0, exp=exp, vol=60000, oi=1500, delta=0.35, iv=0.70),
        _raw(under="PLTR", occ="O:2", strike=142.0, exp=_future_exp(15), vol=55000, oi=1300, delta=0.30, iv=0.70),
        _raw(under="PLTR", occ="O:3", strike=145.0, exp=_future_exp(20), vol=50000, oi=1200, delta=0.25, iv=0.70),
        _raw(under="PLTR", occ="O:P", typ="put", strike=138.0, exp=exp, vol=8000, oi=9000, delta=-0.35, iv=0.50),
    ])
    alerts = eval_institutional(rows)
    top = [a for a in alerts if a["rule"] in ("SCORE", "WHALE")]
    assert top and top[0]["tier"] == "GOLD"
    assert top[0].get("cw_spread") is not None and top[0]["cw_spread"] > 0


def test_eval_stamps_cluster_field_per_ticker():
    # cluster_biases is per-ticker: any PLTR alert fired in the snapshot
    # should carry cluster=True once ≥3 same-bias laddering rows qualify.
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(under="PLTR", occ="O:1", strike=138.0, exp=exp, vol=60000, oi=1500, delta=0.35),
        _raw(under="PLTR", occ="O:2", strike=142.0, exp=_future_exp(15), vol=55000, oi=1300, delta=0.30),
        _raw(under="PLTR", occ="O:3", strike=145.0, exp=_future_exp(20), vol=50000, oi=1200, delta=0.25),
    ])
    for r in rows:
        r["_score"] = 90   # force the SCORE rule above the 85-floor
    alerts = eval_institutional(rows)
    pltr_alerts = [a for a in alerts if a["under"] == "PLTR"]
    assert pltr_alerts, "PLTR should fire"
    assert all(a["cluster"] is True for a in pltr_alerts), \
        "every PLTR alert in a 3-leg laddering snapshot must carry cluster=True"


# ── v2 PRE-FLIGHT: 3-leg ladder + CW-confirm + prime bracket all stack ──
#
# Live-demo gap the user reported: the display room only stacks 2 of the 3
# conviction layers at once. This test PROVES that 4-leg PLTR fixture —
# three bullish calls at laddering strikes/expiries (so they cluster but
# do NOT pair as a vertical spread) + one matched put whose IV sits 20
# vols UNDER the call (Cremers-Weinbaum bullish confirmation) — produces
# a single alert that simultaneously carries:
#   • tier == GOLD    (5 factors true ≥ 3 floor)
#   • cluster == True (the v2 surfaced lacboost stamp the Scanner panel
#                       reads to render a CLUSTER chip)
#   • prime  == True  (premium ≥ $250k AND vol_oi ≥ 5)
#   • cw_spread > 0   (the CW confirming signal the layer uses to upgrade
#                       conviction; > _CW_CONFIRM = 0.015)
# Stamping all four on one row is the cross-receipt that closes the
# "one factor short" gap in the live demo.

def test_preflight_three_factor_cluster_cw_prime_stack_to_gold():
    # 3 calls at DIFFERENT expiries (so detect_spreads cannot pair any two
    # as a vertical; would otherwise demote to STRATEGY / BRONZE and zero
    # the cluster). One matched put at strike 138, exp sharing #1 only,
    # with mismatched volume ratio (8000/60000 = 0.133 << _SPREAD_RATIO_LO
    # = 0.7) so the straddle fingerprint ALSO fails. Crucially the put's
    # IV (0.50) sits 20 vols UNDER the matching call (0.70), which yields
    # the positive CW spread that the layer refiles as 'informed
    # bullish pressure' and uses to upgrade tier.
    exp_a = _future_exp(10)
    exp_b = _future_exp(15)
    exp_c = _future_exp(20)
    rows = norm_rows([
        _raw(under="PLTR", occ="O:PF_1", strike=138.0, exp=exp_a,
             vol=60000, oi=1500, iv=0.70, delta=0.35, spot=133.0),
        _raw(under="PLTR", occ="O:PF_2", strike=142.0, exp=exp_b,
             vol=55000, oi=1300, iv=0.70, delta=0.30, spot=133.0),
        _raw(under="PLTR", occ="O:PF_3", strike=145.0, exp=exp_c,
             vol=50000, oi=1200, iv=0.70, delta=0.25, spot=133.0),
        # vol=8000 (NOT 80000) — ratio 60000/8000 = 7.5 > _SPREAD_RATIO_HI ≈ 1.43,
        # so detect_spreads does NOT pair this put with call #1 as a straddle.
        # This is what keeps call #1 on the laddering-stamp list (no
        # _finalize demotion to STRATEGY / bias=None / tier=BRONZE).
        _raw(under="PLTR", occ="O:PF_P", typ="put", strike=138.0, exp=exp_a,
             vol=8000, oi=9000, iv=0.50, delta=-0.35, spot=133.0),
    ])
    alerts = eval_institutional(rows, regimes={"PLTR": "positive"})
    # Carrier: pick the highest-tier PLTR alert under SCORE/WHALE rule.
    # SIGMA may co-fire but is directionless and gets excluded from the
    # cluster-tied stamping logic in the panel anyway.
    directed = [a for a in alerts
                if a["under"] == "PLTR"
                and a.get("rule") in ("SCORE", "WHALE")
                and a.get("tier") == "GOLD"]
    assert directed, (
        "no GOLD SCORE/WHALE PLTR alert fired in the 4-leg fixture; GOT: " +
        repr([(a.get('rule'), a.get('tier'), a.get('cluster')) for a in alerts])
    )
    # Stamping-v2x cross-receipt: every GOLD PLTR row in the survivor
    # list independently carries all four conviction layers. This is
    # the STRUCTURAL receipt -- if even one laddering row regresses to
    # cluster=False (or any other stamp flips off), this test fails.
    # The max(directed, key=...) hoist was too narrow: it could pass
    # on a lucky one-row output even if the other laddering rows
    # were silently demoted (e.g. through spread-leg pairing).
    for starred in directed:
        assert starred['cluster'] is True, (
            f"cluster=true stamp MISSING on a GOLD row: under={starred.get('under')} "
            f" rule={starred.get('rule')} score={starred.get('score')} "
            f" cluster={starred.get('cluster')}"
        )
        # prime bracket receipt -- re-derived from surfaced fields since
        # the factor dict isn't emitted to the feed.
        assert (starred.get('premium') or 0) >= 250e3, (
            f"prime bracket requires premium >= $250k; "
            f"got ${starred.get('premium'):.0f}"
        )
        assert (starred.get('vol_oi') or 0) >= 5.0, (
            f"prime bracket requires vol_oi >= 5; "
            f"got {starred.get('vol_oi'):.2f}"
        )
        assert starred.get('cw_spread') is not None and starred['cw_spread'] > 0.015, (
            f"CW confirming signal absent: cw_spread={starred.get('cw_spread')}"
        )
        # Row must NOT be a strategy-leg demotion. STRATEGY/bias=None
        # would annihilate the GOLD stamping even if 8 factors were True.
        assert starred.get('side') == 'BUY', (
            f"cluster+CW+prime stack but side='{starred.get('side')}' "
            f"- spread-leg demotion undefeated the trap"
        )
        assert starred.get('bias') == 'BULLISH', (
            f"bias not BULLISH: {starred.get('bias')}"
        )
    # ALSO: every PLTR alert (regardless of rule) should carry the same
    # cluster stamp, because cluster_biases is a per-TICKER aggregate
    # and _finalize does NOT clear the cluster field on STRATEGY demotion.
    pltr_all = [a for a in alerts if a["under"] == "PLTR"]
    assert pltr_all, "no PLTR alerts fired"
    assert all(p["cluster"] is True for p in pltr_all), (
        f"not every PLTR alert carries cluster=True: "
        f"{[(p.get('rule'), p.get('cluster')) for p in pltr_all]}"
    )

def test_eval_does_not_stamp_cluster_for_two_legs():
    # Two same-bias qualifying contracts aren't a cluster yet — the
    # frontend chip must NOT light up under that threshold. Use non-matching
    # volumes (60k vs 12k) so detect_spreads leaves both rows as BUY/BULLISH
    # (otherwise the test would pass for the wrong reason — via vertical
    # spread demotion to STRATEGY, never entering cluster_biases).
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(under="PLTR", occ="O:1", strike=138.0, exp=exp, vol=60000, oi=1500, delta=0.35),
        _raw(under="PLTR", occ="O:2", strike=142.0, exp=exp, vol=12000, oi=1300, delta=0.30),
    ])
    # Gate is min_score=92 (institutional noise pass raised it from 85).
    # This test pins CLUSTER-threshold logic, not the gate value (pinned
    # once in test_default_gate_matches_noise_pass), so it runs below gate.
    alerts = eval_institutional(rows, opts={"min_score": 80})
    pltr_alerts = [a for a in alerts if a["under"] == "PLTR"]
    assert pltr_alerts, "PLTR should fire on score"
    assert all(a["cluster"] is False for a in pltr_alerts), \
        "two legs doesn't meet the ≥3 cluster threshold; cluster must stay False"


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe

    engine = dbe.DuckDBEngine(":memory:")
    yield engine


def test_alert_quality_hit_rate_round_trip(fresh_engine):
    # BULLISH alert at spot 133 → spot moves to 138.2 (+3.9%) = a hit.
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([_raw(vol=60000, oi=1500, delta=0.25, spot=133.0)])
    persist_alerts(fresh_engine, eval_institutional(rows))
    update_moves(fresh_engine, {"PLTR": 138.2})
    q = alert_quality(fresh_engine, days=3)
    assert q, "quality report has a row"
    row = q[0]
    assert row["n"] == 1 and row["n_measured"] == 1
    assert row["hit_rate"] == pytest.approx(1.0)
    assert row["avg_move_pct"] == pytest.approx(3.9, abs=0.1)
    # v2.3 — wins column is the bit-exact integer count (not float-rounded
    # AVG-derived). The frontend consumer (summarizeQuality) reads it
    # directly when non-null and falls back to Math.round(x.hits) only
    # when the column is absent. Decimal precision at small n is the actual
    # reason to ship this column instead of reconstructing from hit_rate.
    assert row["wins"] == 1
    assert isinstance(row["wins"], int), "backend SUM must produce integer wins, not a float reconstruction"


def test_alert_quality_wins_is_bit_exact_with_mixed_outcomes(fresh_engine):
    # v2.3 close-out: 4 distinct tickers, 1 hits (>=0.5% move in BULLISH
    # direction) and 3 miss. Each ticker has explicit distinct `under` so
    # update_moves can stamp the per-ticker move_pct correctly (under is
    # the join key, NOT occ). wins must equal exactly 1 as a literal
    # integer -- the SUM column is what the frontend's summarizeQuality
    # prefers over the float-round fallback.
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([
        _raw(under="T_HIT",  occ="O:HIT_1234567",    strike=133.0, vol=60000, oi=1500, delta=0.25, spot=133.0),  # hits (133->138.2 = +3.9%)
        _raw(under="T_MISS", occ="O:MISS_A0123456",  strike=200.0, vol=60000, oi=1500, delta=0.25, spot=200.0),  # miss (200->195 = -2.5%)
        _raw(under="T_MISS2", occ="O:MISS_B0123456", strike=200.0, vol=60000, oi=1500, delta=0.25, spot=200.0),  # miss
        _raw(under="T_MISS3", occ="O:MISS_C0123456", strike=200.0, vol=60000, oi=1500, delta=0.25, spot=200.0),  # miss
    ])
    persist_alerts(fresh_engine, eval_institutional(rows))
    # update_moves keys by `under` (the column in flow_alerts_daily), not by occ.
    update_moves(fresh_engine, {
        "T_HIT":  138.2,   # +3.9% (BULLISH >= 0.5 --> HIT)
        "T_MISS": 195.0,   # -2.5% (BULLISH < 0.5 --> miss)
        "T_MISS2": 195.0,
        "T_MISS3": 195.0,
    })
    q = alert_quality(fresh_engine, days=3)
    assert q, "quality rows emitted"
    total_wins = sum(r["wins"] for r in q)
    total_measured = sum(r["n_measured"] for r in q)
    assert total_measured == 4, "every alert had a measurable move_pct"
    assert total_wins == 1, "exactly one of the four alerts scored a hit"
    assert isinstance(total_wins, int), "wins aggregate must stay integer (no float drift)"
    # Per-row wins are bit-exact integers (CAST AS BIGINT) -- the SUM column
    # the frontend prefers over Math.round(x.hits).
    for r in q:
        assert isinstance(r["wins"], int), f"row wins must be integer, got {type(r['wins'])}"
    # hit_rate averaging matches: 1/4 = 0.25.
    assert pytest.approx(
        sum(r["hit_rate"] * r["n_measured"] for r in q) / total_measured,
        abs=1e-6,
    ) == 0.25


def test_init_flow_alert_tables_migrates_legacy_table_to_v2_3(fresh_engine):
    # v2.3.1 migration canary: pre-create flow_alerts_daily with the v2.2
    # schema (no `wins` column), then call init_flow_alert_tables() and
    # verify the column was added in-place. Without this, the prod upgrade
    # path from v2.2 -> v2.3 silently fails on the first alert_quality()
    # call after deploy (DuckDB error: "column wins does not exist").
    fresh_engine.execute_write("""
        CREATE TABLE flow_alerts_daily (
            asof_date DATE, asof_ts TIMESTAMP, key TEXT, ckey TEXT,
            rule TEXT, tier TEXT, side TEXT, bias TEXT,
            under TEXT, type TEXT, strike DOUBLE, exp TEXT, dte INTEGER,
            score INTEGER, est_entry DOUBLE, premium DOUBLE, notional DOUBLE,
            vol_oi DOUBLE, sigma DOUBLE, oi_chg_pct DOUBLE,
            under_price DOUBLE, last_price DOUBLE, move_pct DOUBLE,
            cw_spread DOUBLE, cluster BOOLEAN, why TEXT,
            PRIMARY KEY (asof_date, key)
        )
    """)
    # Pre-v2.3 prod module wouldn't have a `wins` BIGINT column here.
    init_flow_alert_tables(fresh_engine)
    # Schema probe -- wins column must exist and be queryable.
    cols = fresh_engine.query("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'flow_alerts_daily' AND column_name = 'wins'
    """)
    assert cols, "wins column was not added by init_flow_alert_tables migration"
    data_type = cols[0]["data_type"].upper()
    # Strict equality. DuckDB returns exactly "BIGINT" given the explicit
    # CAST AS BIGINT in alert_quality's SQL. A regression to INTEGER (or any
    # smaller family) would silently pass a looser LIKE check and break
    # JSON number precision on the DuckDB → JS JSON boundary (JS numbers
    # lose precision above 2^53; cumulative tier wins over months can
    # approach that range when a tier has thousands of alerts).
    assert data_type == "BIGINT", \
        f"wins column must be exactly BIGINT (got {data_type})"
    # Round-trip alert_quality() MUST NOT throw "column wins does not exist"
    # on the migrated table -- the canary passes iff the SQL succeeds.
    rows = norm_rows([_raw(under="T_LEGACY", vol=60000, oi=1500, delta=0.25, spot=100.0)])
    persist_alerts(fresh_engine, eval_institutional(rows))
    update_moves(fresh_engine, {"T_LEGACY": 104.0})  # +4% BULLISH hit
    q = alert_quality(fresh_engine, days=3)
    assert q and q[0]["wins"] == 1, "wins column queryable + first row integer 1"


def test_alert_quality_returns_one_row_per_rule_tier_pair(fresh_engine):
    # The aggregation groups by (rule, tier). With two rules firing into
    # different tiers you get exactly as many rows as (rule × tier) seen.
    # This is the invariant the trend sparkline relies on — every window
    # in the batched response shares the same key set.
    init_flow_alert_tables(fresh_engine)
    rows = [
        _raw(under="SPY", occ="O:1", strike=100.0, exp=_future_exp(10), vol=25000, oi=2000, delta=0.4, spot=100.0),
        _raw(under="SPY", occ="O:2", strike=110.0, exp=_future_exp(15), vol=10000, oi=2000, delta=0.4, spot=100.0),
    ]
    persist_alerts(fresh_engine, eval_institutional(norm_rows(rows)))
    update_moves(fresh_engine, {"SPY": 102.0, "_rest_": 102.0})
    q7 = alert_quality(fresh_engine, days=7)
    keys7 = {(r["rule"], r["tier"]) for r in q7}
    # Each call returns the same shape → the trend sparkline helper can
    # index by tier across windows.
    q14 = alert_quality(fresh_engine, days=14)
    keys14 = {(r["rule"], r["tier"]) for r in q14}
    assert keys7 == keys14, "window length must not change the (rule, tier) keyset"


def test_eval_market_wide_volume_day_suppressed_by_median_removal():
    # 30 tickers ALL at ~3.2 sigma simultaneously = a market-wide volume
    # day, not 30 independent institutional footprints. Cross-sectional
    # median removal must suppress essentially all of them.
    rows, baselines = [], {}
    for i in range(30):
        t = f"T{i:02d}"
        rows.append(_raw(under=t, occ=f"O:{t}", strike=100.0, vol=18000, oi=17000))
        baselines[t] = {"avg": 10000, "std": 2500, "days": 6}
    normed = norm_rows(rows)
    alerts = eval_institutional(normed, baselines=baselines,
                                opts={"min_score": 101, "whale_premium": 1e12})
    assert len([a for a in alerts if a["rule"] == "SIGMA"]) == 0


# ── v2.5 DAILY SERIES ─────────────────────────────────────────────
# Sparkline-shape support: per-(date, tier) aggregation. Same hit logic as
# alert_quality (≥0.5% |move| in claimed direction), but indexed by day so
# the frontend renders one dot per trading day rather than 3 aggregated
# window endpoints. Missing dates are intentionally NOT backfilled — a
# zero-alert day is information (no signal), not a 0% loss.
#
# Test strategy: persist alerts on three explicit dates with known
# hit/miss outcomes and verify daily_series returns them grouped by tier
# with the right hit_rate and integer wins column.

def test_alert_quality_daily_returns_one_row_per_day_per_tier(fresh_engine):
    # v2.5 layout: 4 GOLD alerts persisted on 4 DIFFERENT dates so the
    # GROUP BY (asof_date, tier) splits into 4 (date, GOLD) rows.
    #
    # IMPORTANT: each underlying ticker is DISTINCT so update_moves (which
    # keys by under, not strike) stamps a unique verified price per alert
    # and every BULLISH alert can hit the >=0.5% threshold independently.
    # Using PLTR for two strikes (e.g. 140 + 145) would re-use the same
    # under key in update_moves and stamp both rows with the same last
    # price — one would miss if its strike differed from the spot, breaking
    # the strict assertion. Distinct underlyers sidestep that completely.
    init_flow_alert_tables(fresh_engine)
    from datetime import date, timedelta
    today = date.today()
    rows = norm_rows([
        _raw(under="PLTR",  occ="O:D_PLTR",  strike=140.0, vol=60000, oi=1500, iv=0.70, delta=0.30, spot=140.0, exp=_future_exp(10)),
        _raw(under="NVDA",  occ="O:D_NVDA",  strike=1300.0, vol=45000, oi=3000, iv=0.55, delta=0.30, spot=1300.0, exp=_future_exp(20)),
        _raw(under="AAPL",  occ="O:D_AAPL",  strike=200.0, vol=60000, oi=2500, iv=0.45, delta=0.30, spot=200.0, exp=_future_exp(25)),
        _raw(under="TSLA",  occ="O:D_TSLA",  strike=260.0, vol=55000, oi=2000, iv=0.50, delta=0.30, spot=260.0, exp=_future_exp(30)),
    ])
    alerts = eval_institutional(rows)
    directional = [a for a in alerts
                   if a.get("rule") in ("SCORE", "WHALE", "0DTE")
                   and a.get("bias") in ("BULLISH", "BEARISH")]
    assert len(directional) >= 4, \
        f"expected ≥4 directional alerts, got {len(directional)}: {[(a.get('under'), a.get('tier')) for a in directional]}"
    # Stamp each alert on a distinct date (D-4 through D-0); the keys
    # are distinct ckeys so ON CONFLICT does not fire.
    for offset, alert in enumerate(directional[:4]):
        persist_alerts(fresh_engine, [alert],
                       snapshot_date=(today - timedelta(days=4 - offset)).isoformat())
    # Each underlying uses spot==strike AND a positive update_moves stamp
    # so change > 0.5% hits the BULLISH threshold. update_moves keys by
    # under so 4 unique keys → 4 unique verified moves.
    update_moves(fresh_engine, {
        "PLTR": 142.8,   # 140 → 142.8 = +2%   BULLISH hit
        "NVDA": 1326.0,  # 1300 → 1326 = +2%   BULLISH hit
        "AAPL": 203.5,   # 200 → 203.5 = +1.75% BULLISH hit
        "TSLA": 266.0,   # 260 → 266  = +2.3%  BULLISH hit
    })
    series = alert_quality_daily(fresh_engine, days=30)
    assert series, "daily series has rows"
    by_tier: dict[str, list] = {"GOLD": [], "SILVER": [], "BRONZE": []}
    for r in series:
        t = str(r.get("tier") or "").upper()
        if t in by_tier:
            by_tier[t].append(r)
    # The fixtures all have vol_oi >= 15 (so prime=True), dte ∈ [10,30]
    # (so informed_band=True), and a high score (so score90=True when
    # notional is large enough). Assert that the schema path lands the
    # rows in their respective tiers without forcing all to GOLD — exact
    # tier depends on score math that we don't pin here.
    total_rows = sum(len(by_tier[t]) for t in by_tier)
    assert total_rows >= 4, \
        f"expected ≥4 daily rows (1 per alert on a distinct date), got {total_rows}"
    # wins is integer (mirrors CAST AS BIGINT in alert_quality).
    for r in series:
        assert isinstance(r.get("wins"), int), \
            f"daily-series wins must be integer, got {type(r.get('wins'))}"
    # Sum the moves — 4 distinct underlyings each with a positive spot
    # move. n_measured across the daily series sums to 4 (every alert
    # got a verified move_pct). All 4 BULLISH puts register hits under
    # the documented >=0.5% threshold.
    total_measured = sum((r.get("n_measured") or 0) for r in series)
    total_wins = sum((r.get("wins") or 0) for r in series)
    assert total_measured == 4, f"4 alerts all measured, got {total_measured}"
    assert total_wins == 4, f"all 4 alerts +ve BULLISH hits, got {total_wins}"


def test_alert_quality_daily_missing_dates_not_backfilled_with_zeros(fresh_engine):
    # v2.5 sparkline design: a day with NO alerts is rendered as a GAP in
    # the line (the visual breaks), not as a 0% hit-rate point. The query
    # must NOT synthesize a fake zero day.
    init_flow_alert_tables(fresh_engine)
    from datetime import date, timedelta
    today = date.today()
    # Only D1 has a row, D2 and D3 have nothing in the table.
    rows = norm_rows([_raw(under="TSLA", occ="O:T1", strike=260.0, vol=55000, oi=2000, delta=0.30, spot=260.0)])
    alerts = eval_institutional(rows)
    persist_alerts(fresh_engine, alerts, snapshot_date=(today - timedelta(days=2)).isoformat())
    update_moves(fresh_engine, {"TSLA": 265.2})  # +2% BULLISH hit
    series = alert_quality_daily(fresh_engine, days=30)
    # Exactly one row -- the one day we wrote. No fake zero-row on D2/D3.
    matching = [r for r in series if r.get("tier") in ("GOLD", "SILVER", "BRONZE")]
    assert len(matching) == 1, f"expected 1 daily row, got {len(matching)} ({matching})"
    only = matching[0]
    # Date is an ISO string, never a datetime.date JSON disaster.
    assert isinstance(only["date"], str)
    assert only["n_measured"] == 1
    assert only["wins"] == 1
    # The query only returns days that have at least one alert. A desk
    # reading the sparkline sees ONE dot in the strip, not four flat ones.
    assert sum(r.get("n", 0) for r in series) == only["n"]


def test_alert_quality_daily_excludes_directionless_strategic_rows(fresh_engine):
    # Spread legs land in the feed as side="STRATEGY" / tier="BRONZE" /
    # bias=None. They MUST NOT contribute to the daily sparkline -- a
    # directionless row can't claim a directional hit by definition.
    # Mirrors the bias IS NOT NULL filter in alert_quality().
    #
    # The simplest, schema-stable path: produce a real STRATEGY row through
    # eval_institutional (which automatically demotes paired legs), then
    # persist via persist_alerts. No raw INSERT means no column-count
    # alignment bug surface — the assertion becomes schema-free.
    init_flow_alert_tables(fresh_engine)
    from datetime import date
    exp = _future_exp(10)
    rows = norm_rows([
        # Two legs with matched volumes + same (under, exp) + different
        # strikes → vertical-spread fingerprint. detect_spreads flags both,
        # _finalize demotes side to STRATEGY / bias to NULL / tier to BRONZE.
        _raw(under="AMD", occ="O:DEMO_A1", strike=150.0, exp=exp, vol=5000, oi=800, delta=0.30, spot=150.0),
        _raw(under="AMD", occ="O:DEMO_A2", strike=155.0, exp=exp, vol=5200, oi=700, delta=0.25, spot=155.0),
    ])
    # Logic under test is spread-demotion, not the production gate
    # (pinned once in test_default_gate_matches_noise_pass).
    alerts = eval_institutional(rows, opts={"min_score": 80})
    strategy_alerts = [a for a in alerts if a.get("side") == "STRATEGY"]
    assert strategy_alerts, \
        "eval_institutional should produce at least one STRATEGY row for the vertical pair fixture"
    assert all(a.get("bias") is None for a in strategy_alerts), \
        "STRATEGY alerts must have bias=None so the SQL filter excludes them"
    # Persist + verify no measurement gets counted. We deliberately DO
    # NOT update_moves — STRATEGY rows with no resolved path through the
    # filter would be a question for a different test.
    persist_alerts(fresh_engine, strategy_alerts, snapshot_date=date.today().isoformat())
    # Drop any directional rows the same snapshot might have produced
    # (tolerated by the algebra — what matters is directionless=False).
    series = alert_quality_daily(fresh_engine, days=30)
    # The ONLY rows the daily query returns are ones with bias IS NOT
    # NULL. STRATEGY rows have bias=None → they CANNOT leak through.
    # Any STRATEGY-shaped row leaking to series is a regression.
    for r in series:
        t = str(r.get("tier") or "").upper()
        assert t in {"GOLD", "SILVER", "BRONZE"}, \
            f"unknown tier {t!r} in daily_series — STRATEGY leak?"
        n = r.get("n_measured") or 0
        w = r.get("wins") or 0
        assert n >= 0 and w >= 0
    # The strict invariant: every row returned has positive/zero
    # measured counts. STRATEGY rows specifically were persisted but
    # must NOT appear here.
    strategy_keys = {a["key"] for a in strategy_alerts}
    returned_keys = {r.get("key") or "" for r in series}
    leaked = strategy_keys & returned_keys
    assert not leaked, \
        f"STRATEGY alert keys leaked through the bias filter: {leaked}"
    # Independently verify the row IS in the table (so the test is not
    # passing because persist_alerts silently dropped it).
    raw = fresh_engine.query(
        "SELECT count(*) AS c FROM flow_alerts_daily WHERE tier = 'BRONZE' AND side = 'STRATEGY'")
    assert raw[0]["c"] >= 1, \
        "STRATEGY row was not persisted — test is not exercising the filter"


def test_alert_quality_daily_tier_filter_returns_subset(fresh_engine):
    # The new tier= filter adds a tiny optimization when the front-end
    # only needs one tier's series. Verifies the SQL path forward-compat.
    init_flow_alert_tables(fresh_engine)
    from datetime import date, timedelta
    today = date.today()
    rows = norm_rows([
        _raw(under="X", occ="O:X1", strike=100.0, vol=60000, oi=2000, delta=0.30, spot=100.0),
    ])
    alerts = eval_institutional(rows, opts={"min_score": 80})
    persist_alerts(fresh_engine, alerts, snapshot_date=(today - timedelta(days=1)).isoformat())
    update_moves(fresh_engine, {"X": 102.5})  # +2.5% BULLISH hit
    only_gold = alert_quality_daily(fresh_engine, tier="GOLD", days=30)
    only_silver = alert_quality_daily(fresh_engine, tier="SILVER", days=30)
    only_bronze = alert_quality_daily(fresh_engine, tier="BRONZE", days=30)
    # The single fixture may be GOLD or SILVER depending on factor counts;
    # either way, exactly one of [GOLD, SILVER, BRONZE] is non-empty and
    # the others are empty.
    nonempty = sum(1 for s in (only_gold, only_silver, only_bronze) if s)
    assert nonempty == 1, f"one tier should match, got {[len(s) for s in (only_gold, only_silver, only_bronze)]}"


def test_alert_quality_daily_date_is_serialized_to_iso(fresh_engine):
    # DuckDB date columns come back as datetime.date on the python side;
    # the v2.5 contract requires an ISO string for the JSON boundary to
    # React (avoiding the JS Date round-trip dropping quiet hours).
    init_flow_alert_tables(fresh_engine)
    from datetime import date, timedelta
    today = date.today()
    rows = norm_rows([_raw(under="QQ", occ="O:Q1", strike=90.0, vol=30000, oi=2000, delta=0.25, spot=90.0)])
    alerts = eval_institutional(rows, opts={"min_score": 80})
    persist_alerts(fresh_engine, alerts, snapshot_date=(today - timedelta(days=1)).isoformat())
    update_moves(fresh_engine, {"QQ": 91.0})  # +1.1% BULLISH hit
    series = alert_quality_daily(fresh_engine, days=30)
    assert series, "daily series populated"
    d = series[0]["date"]
    # ISO YYYY-MM-DD format, not a datetime.date, NOT a datetime string.
    assert isinstance(d, str), f"expected ISO string, got {type(d).__name__}"
    assert len(d) == 10 and d[4] == "-" and d[7] == "-", \
        f"expected YYYY-MM-DD, got {d!r}"
