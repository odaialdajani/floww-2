"""Paid Public Advanced API advantage: adapter quote-truth, public scanner,
PRIME/CLUSTER alert rules, and scan coverage honesty.

Covers the 2026-09-05 backend hardening (SNDK gap):
  - OptionContract carries bid/ask sizes + mid; the adapter preserves
    last/mid/sizes so side inference uses NBBO truth, not the vol/OI proxy.
  - services.public_scanner pure helpers (cursor rotation, unusual-row
    extraction, slice merge with TTL honesty).
  - PRIME (prime bracket standalone) + CLUSTER (laddered accumulation)
    fire where SCORE>=92 stayed silent.
  - /scan payload carries truncated/coverage flags.
  - New flowseeker routes (/public/chain, /scan-public) shape + degrade.
"""
import asyncio
import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _h2_isolated_public_budget(monkeypatch):
    """H2: adapter-level acquire debits the shared singleton even behind fake
    brokers. Isolate every test with a fresh high-capacity budget so file
    order can never starve a suite. Production behavior unchanged."""
    from services import public_budget as pb_mod
    monkeypatch.setattr(
        pb_mod, "budget",
        pb_mod.PublicBudget(capacity=10000, refill_per_sec=10000.0))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def _isolated_public_budget_singleton():
    # D1: the adapter debits the shared budget singleton per C8, so each
    # test starts from a full bucket; otherwise module order decides
    # who exhausts whom.
    from services.public_budget import budget

    budget.reset()
    yield
    budget.reset()

from tests.services.test_flow_alerts import _future_exp, _raw  # noqa: E402

# ── adapter quote-truth ─────────────────────────────────────────────

def _mock_oc(**over):
    base = dict(
        symbol="SPY260911C00760000", expiration="2026-09-11", strike=760.0,
        open_interest=1200, iv=0.25, delta=0.4, gamma=0.01, theta=-0.5,
        vega=0.3, bid=2.5, ask=2.7, volume=800,
        last=2.65, bid_size=40, ask_size=35,
    )
    base.update(over)
    oc = MagicMock()
    for k, v in base.items():
        setattr(oc, k, v)
    oc.mid = (base["bid"] + base["ask"]) / 2
    return oc


@pytest.mark.asyncio
async def test_adapter_preserves_last_mid_and_sizes():
    from services.public_api_adapter import _fetch_chain_live

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_option_expirations = AsyncMock(return_value=["2026-09-11"])
    broker.get_quotes = AsyncMock(return_value=[MagicMock(mid_price=760.0, last=760.5)])
    broker.get_option_chain_parsed = AsyncMock(
        return_value={"calls": [_mock_oc()], "puts": []}
    )
    out = await _fetch_chain_live(broker, "SPY", max_expiries=1)
    assert out is not None and len(out["contracts"]) == 1
    c = out["contracts"][0]
    assert c["last"] == 2.65
    assert c["mid"] == pytest.approx(2.6)
    assert c["bid_size"] == 40 and c["ask_size"] == 35


def test_parse_option_contract_reads_sizes():
    from services.public_api import PublicBroker

    pb = PublicBroker(secret_key="x")
    oc = pb._parse_option_contract(
        {"symbol": "SPY260904C00760000"},
        {"last": 2.65, "bid": 2.5, "ask": 2.7,
         "bidSize": 40, "askSize": 35, "volume": 800, "openInterest": 1200,
         "optionDetails": {"greeks": {"delta": 0.4}}},
    )
    assert oc.bid_size == 40 and oc.ask_size == 35
    assert oc.mid == pytest.approx(2.6)
    assert oc.last == 2.65


# ── public_scanner pure helpers ─────────────────────────────────────

def test_advance_cursor_rotates_and_wraps():
    from services.public_scanner import advance_cursor

    idx, cur = advance_cursor(0, 8, 40)
    assert idx == list(range(8)) and cur == 8
    idx, cur = advance_cursor(36, 8, 40)
    assert idx == [36, 37, 38, 39, 0, 1, 2, 3] and cur == 4
    assert advance_cursor(0, 0, 40) == ([], 0)


def _chain_contract(**over):
    base = dict(osi="O:X", expiry="2026-09-18", type="call", strike=100.0,
                volume=1000, oi=200, iv=0.4, delta=0.4)
    base.update(over)
    return base


def test_unusual_rows_filters_sorts_and_caps():
    from services.public_scanner import MAX_ROWS_PER_TICKER, unusual_rows_from_chain

    chain = {"ticker": "SNDK", "spot": 50.0, "contracts": [
        _chain_contract(osi="O:small", volume=100, oi=10000),          # below floor
        _chain_contract(osi="O:thin", volume=300, oi=100),             # 3x -> keep
        _chain_contract(osi="O:big", volume=5000, oi=50000),           # big vol -> keep
        _chain_contract(osi="O:churn", volume=300, oi=10000),          # 0.03x, small -> drop
        {"bogus": True},                                               # malformed -> drop
    ]}
    rows, xtras = unusual_rows_from_chain(chain)
    occs = [r[1] for r in rows]
    assert "O:thin" in occs and "O:big" in occs
    assert "O:small" not in occs and "O:churn" not in occs
    assert len(rows) <= MAX_ROWS_PER_TICKER
    # strongest vol/OI leads
    assert rows[0][1] == "O:thin"
    # cvserver column order parity
    assert rows[0][0] == "SNDK" and rows[0][2] == "call" and rows[0][9] == 50.0
    # extras keyed by ckey for the emitted rows only
    assert set(xtras) == {"SNDK|call|100|2026-09-18"}
    x = xtras["SNDK|call|100|2026-09-18"]
    assert x["premium_true"] is None  # no bid/ask/last in fixture
    assert x["side"] == "FLOW" and x["bias"] is None
    assert x["vol_delta"] is None and x["velocity_per_min"] is None  # first sight


def test_nbbo_side_matrix_and_mid_print_unknown():
    from services.public_scanner import nbbo_side, side_bias

    assert nbbo_side(2.70, 2.50, 2.70) == "ASK"   # lifted at ask
    assert nbbo_side(2.50, 2.50, 2.70) == "BID"   # hit at bid
    assert nbbo_side(2.60, 2.50, 2.70) is None   # mid-print: unknown, not a guess
    assert nbbo_side(None, 2.50, 2.70) is None
    assert nbbo_side(2.65, 2.70, 2.50) is None   # crossed quote: unknown
    assert side_bias("call", "ASK") == ("BUY", "BULLISH")
    assert side_bias("put", "ASK") == ("BUY", "BEARISH")
    assert side_bias("call", "BID") == ("SELL", "BEARISH")
    assert side_bias("put", "BID") == ("SELL", "BULLISH")
    assert side_bias("call", None) == ("FLOW", None)


def test_mid_rings_feed_ticker_roll_read():
    """A9: sweeper stamps capped mid rings; dealer carries the pooled Roll read."""
    import services.public_scanner as ps

    ps._reset_state()
    try:
        chain = {"ticker": "SNDK", "spot": 50.0, "contracts": [
            {"osi": "O:R1", "expiry": "2026-09-18", "type": "call", "strike": 50.0,
             "volume": 500, "oi": 100, "iv": 0.4, "delta": 0.5,
             "bid": 1.0, "ask": 1.2, "mid": 1.1, "last": 1.2},
            {"osi": "O:R2", "expiry": "2026-09-18", "type": "put", "strike": 50.0,
             "volume": 400, "oi": 100, "iv": 0.4, "delta": -0.5,
             "bid": 1.0, "ask": 1.2, "mid": 1.1, "last": 1.0},
        ]}
        out = ps.unusual_rows_from_chain(
            chain, vol_marks=ps._vol_marks, mid_marks=ps._mid_marks, now=1000.0)[0]
        assert len(out) == 2
        ps._stamp_marks(chain["contracts"], 1000.0)
        assert ps._mid_rings["O:R1"] == [1.1]
        assert ps._mid_marks["O:R1"] == 1.1
        dealer = ps.dealer_context(chain["contracts"], 50.0)
        tick_rings = {"O:R1": ps._mid_rings["O:R1"], "O:R2": ps._mid_rings["O:R2"]}
        from services.roll_spread import roll_pooled_for
        read = roll_pooled_for(tick_rings)
        assert read["building"] is True  # 2 mids -> 0 deltas, honest warmup
        dealer["roll_spread"] = read
        assert dealer["roll_spread"]["spread"] is None
    finally:
        ps._reset_state()


def test_ckey_matches_norm_rows_and_frontend():
    from services.flow_alerts import norm_rows
    from services.public_scanner import ckey_of

    raw = [["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]]
    r = norm_rows(raw)[0]
    assert ckey_of("SNDK", "call", 50.0, "2026-09-18") == r["ckey"] == "SNDK|call|50|2026-09-18"
    assert ckey_of("SNDK", "call", 142.5, "2026-09-18") == "SNDK|call|142.5|2026-09-18"


def test_velocity_marks_turn_cumulative_into_arrival():
    from services.public_scanner import unusual_rows_from_chain

    def chain_with(vol):
        return {"ticker": "SNDK", "spot": 50.0, "contracts": [
            _chain_contract(osi="O:V", volume=vol, oi=100, bid=1.0, ask=1.2, last=1.2),
        ]}
    marks: dict = {}
    rows1, x1 = unusual_rows_from_chain(chain_with(1000), vol_marks=marks, now=1000.0)
    assert x1["SNDK|call|100|2026-09-18"]["velocity_per_min"] is None
    marks["O:V"] = (1000.0, 1000.0)  # what _stamp_marks would record
    rows2, x2 = unusual_rows_from_chain(chain_with(1600), vol_marks=marks, now=1060.0)
    x = x2["SNDK|call|100|2026-09-18"]
    assert x["vol_delta"] == 600.0
    assert x["velocity_per_min"] == pytest.approx(600.0)
    assert x["side"] == "BUY" and x["bias"] == "BULLISH"  # last lifted at ask
    assert x["premium_true"] == pytest.approx(1600 * 100 * 1.1)


def test_lee_ready_signing_rides_sweep_mids():
    """A2: quote rule on this sweep, tick test on the previous sweep's mid."""
    from services.public_scanner import unusual_rows_from_chain

    def chain_with(**over):
        base = dict(osi="O:LR", expiry="2026-09-18", type="call", strike=100.0,
                    volume=1000, oi=100, iv=0.4, delta=0.4)
        base.update(over)
        return {"ticker": "SNDK", "spot": 50.0, "contracts": [base]}

    # First sight, last lifted at ask -> quote ASK, no prev needed.
    _, x1 = unusual_rows_from_chain(
        chain_with(bid=1.0, ask=1.2, last=1.2, mid=1.1), mid_marks={}, now=1000.0)
    x = x1["SNDK|call|100|2026-09-18"]
    assert x["signed_side"] == "ASK" and x["sign_method"] == "quote"
    # Mid-print with rising sweep mid -> tick ASK.
    _, x2 = unusual_rows_from_chain(
        chain_with(bid=1.0, ask=1.2, last=1.1, mid=1.1),
        mid_marks={"O:LR": 1.0}, now=1060.0)
    x = x2["SNDK|call|100|2026-09-18"]
    assert x["signed_side"] == "ASK" and x["sign_method"] == "tick"
    # Mid-print, no lag anchor -> signed honestly absent (None, not UNKNOWN).
    _, x3 = unusual_rows_from_chain(
        chain_with(bid=1.0, ask=1.2, last=1.1, mid=1.1), mid_marks={}, now=1060.0)
    assert x3["SNDK|call|100|2026-09-18"]["signed_side"] is None


def test_engine_prefers_signed_over_touch_and_grades_conviction():
    """Signed BID beats a touch-ASK proxy; tick evidence weighs half of quote."""
    from services.flow_alerts import (
        apply_quote_truth,
        infer_side_bias,
        norm_rows,
        scan_score,
        score_conviction,
    )

    rows = norm_rows([["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]])
    extras = {"SNDK|call|50|2026-09-18": {
        "premium_true": 600000.0, "nbbo_side": "ASK",
        "signed_side": "BID", "sign_method": "quote",
        "velocity_per_min": 100.0}}
    apply_quote_truth(rows, extras)
    r = rows[0]
    assert r["signed_side"] == "BID" and r["sign_method"] == "quote"
    assert infer_side_bias(r) == ("SELL", "BEARISH")  # signed truth beats touch proxy
    r["_score"] = scan_score(r)
    quote_conv = score_conviction(r, {})
    r["sign_method"] = "tick"
    assert score_conviction(r, {}) == quote_conv - 1  # tick weighs half of quote


def test_dealer_context_walls_and_regime():
    from services.public_scanner import dealer_context

    contracts = [
        {"strike": 100.0, "type": "call", "oi": 5000, "gamma": 0.02},
        {"strike": 105.0, "type": "call", "oi": 9000, "gamma": 0.015},
        {"strike": 95.0, "type": "put", "oi": 12000, "gamma": 0.018},
    ]
    d = dealer_context(contracts, 100.0)
    assert d["call_wall"] == 105.0 and d["put_wall"] == 95.0
    assert d["max_oi_strike"] == 95.0
    assert d["net_gex"] is not None and d["net_gex"] < 0  # dealers short gamma
    assert d["regime"] == "negative"
    assert dealer_context([], 100.0)["regime"] is None
    assert dealer_context([{"strike": 1, "type": "call", "oi": 5}], 100.0)["regime"] is None


def test_get_universe_env_override():
    import services.public_scanner as ps

    assert "SNDK" in ps.get_universe() and len(ps.get_universe()) == 40
    with patch.dict("os.environ", {"FLOWW_PUBLIC_UNIVERSE": "SPY, QQQ, SPY, SNDK"}):
        assert ps.get_universe() == ["SPY", "QQQ", "SNDK"]


def test_merge_slices_drops_stale_and_reports_coverage():
    from services.public_scanner import UNIVERSE, merge_slices

    now = time.time()
    slices = {
        "SPY": {"ts": now - 10, "rows": [["SPY", "O:1", "call", 1, "2026-09-18", 9, 1, 0.2, 0.5, 1]]},
        "QQQ": {"ts": now - 9999, "rows": [["QQQ", "O:2", "call", 1, "2026-09-18", 1, 1, 0.2, 0.5, 1]]},
    }
    rows, xtras, cov = merge_slices(slices, now=now, ttl_s=600.0)
    assert [r[0] for r in rows] == ["SPY"]
    assert cov["universe"] == len(UNIVERSE)
    assert cov["fresh"] == 1 and cov["stale_dropped"] == ["QQQ"]


@pytest.mark.asyncio
async def test_scan_next_merges_and_never_wipes_on_failure():
    import services.public_scanner as ps

    ps._reset_state()
    try:
        async def fake_slice(tickers, max_expiries=2, concurrency=3):
            return {t: {"rows": [[t, f"O:{t}", "call", 100.0, "2026-09-18",
                                  500, 100, 0.4, 0.4, 99.0]],
                        "extras": {}, "dealer": {"regime": "positive"}} for t in tickers}
        with patch.object(ps, "scan_slice", side_effect=fake_slice):
            uni = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
            v1 = await ps.scan_next(slice_size=8, universe=uni)
            assert v1["count"] == 8 and v1["coverage"]["fresh"] == 8
            assert "quote_truth" in v1 and "dealer" in v1
            assert v1["dealer"]["T1"] == {"regime": "positive"}

            async def fail_slice(tickers, max_expiries=2, concurrency=3):
                return {t: {"rows": [], "extras": {}, "dealer": None} for t in tickers}
            with patch.object(ps, "scan_slice", side_effect=fail_slice):
                v2 = await ps.scan_next(slice_size=8, universe=uni)
                # failures map to [] and must NOT wipe prior good slices
                assert v2["count"] == 8
    finally:
        ps._reset_state()


# ── PRIME + CLUSTER rules ───────────────────────────────────────────

def test_prime_fires_below_score_bar():
    """SNDK-type row: score 82, $663k premium at 6x OI — silent before PRIME."""
    from services.flow_alerts import eval_institutional, norm_rows, scan_score

    rows = norm_rows([["SNDK", "O:X", "call", 120.0, _future_exp(4),
                       3000, 500, 0.62, 0.38, 118.0]])
    assert scan_score(rows[0]) < 92
    alerts = eval_institutional(rows)
    assert len(alerts) == 1
    a = alerts[0]
    assert a["rule"] == "PRIME" and a["under"] == "SNDK"
    assert a["key"].startswith("prime|") and a["ttl_s"] == 2 * 3600


def test_prime_yields_to_score_and_whale():
    from services.flow_alerts import eval_institutional, norm_rows

    rows = norm_rows([_raw(vol=60000, oi=1500, delta=0.25)])
    assert eval_institutional(rows)[0]["rule"] == "SCORE"
    # whale-sized premium in the prime bracket -> WHALE wins (size first)
    rows = norm_rows([_raw(vol=30000, oi=1000, strike=500, spot=495,
                           iv=0.5, delta=0.5, exp=_future_exp(40))])
    alerts = eval_institutional(rows, opts={"min_score": 101, "whale_premium": 1e6})
    assert alerts and alerts[0]["rule"] == "WHALE"
    # same shape but below the whale floor -> PRIME catches it
    alerts = eval_institutional(rows, opts={"min_score": 101, "whale_premium": 1e12})
    assert alerts and alerts[0]["rule"] == "PRIME"


def test_cluster_fires_on_ladder_with_no_single_line_qualifying():
    """3-leg ladder, scores 74-77, $15k premiums — zero contract rules fire,
    exactly one CLUSTER anchors the ticker."""
    from services.flow_alerts import eval_institutional, norm_rows

    rows = norm_rows([
        _raw(under="PLTR", occ="O:1", strike=138.0, exp=_future_exp(7),
             vol=3000, oi=1200, iv=0.05, delta=0.35),
        _raw(under="PLTR", occ="O:2", strike=142.0, exp=_future_exp(8),
             vol=3000, oi=1200, iv=0.05, delta=0.32),
        _raw(under="PLTR", occ="O:3", strike=145.0, exp=_future_exp(9),
             vol=3000, oi=1200, iv=0.05, delta=0.30),
    ])
    alerts = eval_institutional(rows)
    assert len(alerts) == 1, f"expected only CLUSTER, got {[a['rule'] for a in alerts]}"
    a = alerts[0]
    assert a["rule"] == "CLUSTER" and a["key"] == "cluster|PLTR"
    assert a["ttl_s"] == 4 * 3600
    assert "laddered" in a["why"]


# ── engine: quote truth + dealer regime ─────────────────────────────

def test_alerts_always_carry_provenance_keys():
    """CONTRACTS C6: premium_truth / p_move / p_method exist on every alert,
    uncalibrated until a stage is explicitly passed."""
    from services.flow_alerts import eval_institutional, norm_rows

    rows = norm_rows([["SNDK", "O:X", "call", 120.0, _future_exp(4),
                       3000, 500, 0.62, 0.38, 118.0]])
    alerts = eval_institutional(rows)
    assert alerts
    for a in alerts:
        assert a["premium_truth"] is False  # BS-estimated row, no paid overlay
        assert a["p_move"] is None and a["p_method"] == "uncalibrated"


def test_zero_dte_matches_tape_gate():
    """Backend 0DTE ≡ frontend: score>=85 AND vol_oi>=2 AND dte<=1."""
    from services.flow_alerts import eval_institutional, norm_rows

    def fire(vol, oi, delta=0.45):
        rows = norm_rows([["SPY", "O:Z", "call", 760.0, _future_exp(0),
                           vol, oi, 0.9, delta, 760.0]])
        return [a for a in eval_institutional(rows, opts={"min_score": 101, "whale_premium": 1e12})
                if a["rule"] == "0DTE"]

    assert fire(8000, 2000) != []      # vol_oi=4, score ~87 -> fires
    # score ~85 but vol_oi=1.7 < 2 -> vol gate blocks (lotto shut out)
    assert fire(60000, 35000, delta=0.05) == []


def test_dealer_regime_without_magnitude_never_confluent():
    """pct None propagates regime but forces confluence False (no fabrication)."""
    from services.flow_alerts import _common_factors, norm_rows

    rows = norm_rows([_raw(vol=60000, oi=1500)])
    ctx = {"PLTR": {"gamma_imbalance": {"gamma_imbalance_pct": None,
                                        "regime": "negative"}}}
    f = _common_factors(rows[0], {}, set(), {}, {}, gex_context=ctx)
    assert f["gex_confluent"] is False
    assert f["gex_regime"] == "negative"

def test_apply_quote_truth_overlays_premium_side_velocity():
    from services.flow_alerts import apply_quote_truth, infer_side_bias, norm_rows

    rows = norm_rows([["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]])
    # vol_oi=6 proxy would say BUY/BULLISH; NBBO says seller hit the bid.
    extras = {"SNDK|call|50|2026-09-18": {
        "premium_true": 600000.0, "nbbo_side": "BID",
        "velocity_per_min": 450.0, "side": "SELL", "bias": "BEARISH"}}
    apply_quote_truth(rows, extras)
    r = rows[0]
    assert r["premium"] == 600000.0 and r.get("premium_truth") is True
    assert r["velocity_per_min"] == 450.0
    assert infer_side_bias(r) == ("SELL", "BEARISH")  # NBBO truth beats proxy
    # no extras -> untouched vol/OI-proxy behavior
    rows2 = norm_rows([["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]])
    apply_quote_truth(rows2, None)
    assert infer_side_bias(rows2[0]) == ("BUY", "BULLISH")


def test_ticker_keyed_gex_context_drives_confluence_and_levels():
    """Production shape {under: {gamma_imbalance}} — the flat-shape unit
    tests pinned factor math, but no production caller ever sent flat."""
    from services.flow_alerts import (
        _common_factors,
        build_key_levels,
        eval_institutional,
        norm_rows,
    )

    rows = norm_rows([["PLTR", "O:1", "put", 130.0, _future_exp(10),
                       60000, 1500, 0.7, -0.4, 133.0]])
    ctx = {"PLTR": {"gamma_imbalance": {"gamma_imbalance_pct": -2.0,
                                        "regime": "negative_gamma"}}}
    f = _common_factors(rows[0], {}, set(), {}, {}, gex_context=ctx)
    assert f["gex_confluent"] is True and f["gex_regime"] == "negative"
    # regime propagates to wider bearish targets (5.5% vs 3.5%)
    neg = build_key_levels({"spot": 100.0}, "BEARISH", "negative")
    pos = build_key_levels({"spot": 100.0}, "BEARISH", "positive")
    assert neg["target"] < pos["target"]
    # end to end: dealer regime from the public scanner feeds eval
    alerts = eval_institutional(rows, gex_context=ctx)
    assert alerts and alerts[0]["context"]["market_regime"] == "NEGATIVE_GAMMA"


def test_conviction_rewards_measured_urgency_only():
    from services.flow_alerts import norm_rows, scan_score, score_conviction

    rows = norm_rows([["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]])
    r = rows[0]
    r["_score"] = scan_score(r)
    base = score_conviction(r, {})
    r["velocity_per_min"] = 1200.0
    r["nbbo_side"] = "ASK"
    boosted = score_conviction(r, {})
    assert boosted == base + 6  # +4 velocity, +2 known initiation
    assert boosted <= 100


# ── routes ──────────────────────────────────────────────────────────

def _route_module():
    import routes.flowseeker as fs
    return fs


@pytest.mark.asyncio
async def test_public_chain_route_flat_shape():
    fs = _route_module()
    payload = {
        "ticker": "SPY", "spot": 760.0, "expiries": ["2026-09-04"],
        "data_source": "public_api", "stale": False,
        "contracts": [{
            "osi": "SPY260904C00760000", "expiry": "2026-09-04", "T": 0.01,
            "type": "call", "strike": 760.0, "oi": 1200, "iv": 0.25,
            "delta": 0.4, "gamma": 0.01, "theta": -0.5, "vega": 0.3,
            "bid": 2.5, "ask": 2.7, "mid": 2.6, "last": 2.65,
            "bid_size": 40, "ask_size": 35, "volume": 800,
        }],
    }

    class Budget:
        async def acquire(self, host="public"):
            return None

        def release(self):
            return None

    with patch("services.public_api_adapter.fetch_chain_from_public_api",
               new=AsyncMock(return_value=payload)), \
         patch("services.public_budget.budget", Budget()):
        out = await fs.public_chain_flat("SPY", expirations=4, expiration=None, fields=None)
    assert out["ok"] is True and out["data_source"] == "public_api"
    assert len(out["contracts"]) == 1
    c = out["contracts"][0]
    # frontend mapPublicChainToRows keys
    for k in ("strike", "type", "expiry", "volume", "oi", "iv",
              "bid", "ask", "last", "mid"):
        assert k in c, f"missing {k}"
    assert c["last"] == 2.65 and c["mid"] == pytest.approx(2.6)


@pytest.mark.asyncio
async def test_public_chain_route_degrades():
    from fastapi import HTTPException

    fs = _route_module()

    class Budget:
        async def acquire(self, host="public"):
            return None

        def release(self):
            return None

    with patch("services.public_api_adapter.fetch_chain_from_public_api",
               new=AsyncMock(return_value=None)), \
         patch("services.public_budget.budget", Budget()):
        with pytest.raises(HTTPException) as e:
            await fs.public_chain_flat("SPY", expirations=4, expiration=None, fields=None)
        assert e.value.status_code == 502

    class DeadBudget:
        from services.public_budget import BudgetExhausted

        async def acquire(self, host="public"):
            raise DeadBudget.BudgetExhausted(retry_after=7)

        def release(self):
            return None

    with patch("services.public_budget.budget", DeadBudget()):
        with pytest.raises(HTTPException) as e:
            await fs.public_chain_flat("SPY", expirations=4, expiration=None, fields=None)
        assert e.value.status_code == 503


@pytest.mark.asyncio
async def test_scan_public_serves_merged_view():
    fs = _route_module()
    view = {
        "columns": ["underlying_ticker", "ticker", "contract_type", "strike_price",
                    "expiration_date", "day_volume", "open_interest",
                    "implied_volatility", "delta", "underlying_price"],
        "rows": [["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]],
        "count": 1,
        "quote_truth": {"SNDK|call|50|2026-09-18": {"premium_true": 600000.0, "side": "BUY"}},
        "dealer": {"SNDK": {"regime": "negative"}},
        "coverage": {"universe": 40, "fresh": 8, "stale_dropped": [], "max_age_s": 12.0},
        "tickers": ["SNDK"],
    }

    class Budget:
        async def acquire(self, host="public"):
            return None

        def release(self):
            return None

        def status(self, now=None):
            return {}

    async def no_baselines():
        return {}

    async def no_prev():
        return {}

    async def no_record(rows):
        return None

    async def no_alerts(rows, extras=None, dealer=None):
        return None

    with patch("services.public_scanner.scan_next", new=AsyncMock(return_value=view)), \
         patch("services.public_budget.budget", Budget()), \
         patch.object(fs, "_volume_baselines", no_baselines), \
         patch.object(fs, "_prev_contract_oi", no_prev), \
         patch.object(fs, "_record_scan_baseline", no_record), \
         patch.object(fs, "_run_institutional_alerts", no_alerts), \
         patch.object(fs, "_cached_regimes", lambda: {}):
        out = await fs.public_market_scan(slice_size=8, max_expiries=2)
    assert out["source"] == "public-scan" and out["count"] == 1
    assert out["columns"][0] == "underlying_ticker"
    assert out["coverage"]["fresh"] == 8
    assert out["quote_truth"]["SNDK|call|50|2026-09-18"]["side"] == "BUY"
    assert out["dealer"] == {"SNDK": {"regime": "negative"}}


def test_public_to_nested_shape_matches_cvserver_contract():
    from services.public_api_adapter import public_to_nested

    result = {
        "ticker": "SPY", "spot": 760.0,
        "contracts": [
            {"osi": "O:C", "expiry": "2026-09-04", "type": "call", "strike": 760.0,
             "bid": 2.5, "ask": 2.7, "mid": 2.6, "last": 2.65, "volume": 800,
             "oi": 1200, "iv": 0.25},
            {"osi": "O:P", "expiry": "2026-09-04", "type": "put", "strike": 760.0,
             "bid": 2.4, "ask": 2.6, "mid": 2.5, "last": None, "volume": 400,
             "oi": 900, "iv": 0.26},
        ],
    }
    out = public_to_nested(result)
    assert out["symbol"] == "SPY"
    assert out["params"] == ["strike", "bid", "ask", "lastPrice", "volume",
                             "openInterest", "impliedVolatility"]
    assert len(out["chain"]) == 1 and len(out["chain"][0]["strikes"]) == 1
    strike, calls, puts = out["chain"][0]["strikes"][0]
    assert strike == 760.0
    assert calls == [2.5, 2.7, 2.65, 800, 1200, 0.25]
    assert puts == [2.4, 2.6, 2.5, 400, 900, 0.26]  # last None -> mid fallback
    assert public_to_nested(None) is None
    assert public_to_nested({"ticker": "X", "contracts": []}) is None


@pytest.mark.asyncio
async def test_chain_route_prefers_public_then_cvserver():
    fs = _route_module()

    pub = {"ticker": "SPY", "spot": 760.0, "contracts": [
        {"osi": "O:C", "expiry": "2026-09-04", "type": "call", "strike": 760.0,
         "bid": 2.5, "ask": 2.7, "mid": 2.6, "last": 2.65, "volume": 800,
         "oi": 1200, "iv": 0.25},
    ]}

    class Budget:
        async def acquire(self, host="public"):
            return None

        def release(self):
            return None

    fs._chain_cache.clear()
    try:
        with patch("services.public_api_adapter.fetch_chain_from_public_api",
                   new=AsyncMock(return_value=pub)), \
             patch("services.public_budget.budget", Budget()):
            out = await fs.options_chain("SPY")
        assert out["symbol"] == "SPY" and out["params"][0] == "strike"
        assert out["chain"][0]["strikes"][0][1][2] == 2.65  # paid last, not midpoint

        # Public empty -> cvserver fallback (never yfinance in this test).
        fs._chain_cache.clear()
        cv = {"symbol": "SPY", "params": ["strike"], "chain": [{"expiration": "2026-09-04",
              "strikes": [[760.0, [1], [2]]]}]}
        with patch("services.public_api_adapter.fetch_chain_from_public_api",
                   new=AsyncMock(return_value=None)), \
             patch("services.public_budget.budget", Budget()), \
             patch.object(fs, "_cvforge_chain", new=AsyncMock(return_value=cv)):
            out2 = await fs.options_chain("SPY")
        assert out2 == cv
    finally:
        fs._chain_cache.clear()


# ── sweep_once + gex merge + server loop ────────────────────────────

@pytest.mark.asyncio
async def test_sweep_once_skips_cleanly_on_spent_budget():
    import services.public_scanner as ps
    from services.public_budget import BudgetExhausted

    class DeadBudget:
        async def acquire(self, host="public"):
            raise BudgetExhausted(retry_after=30)

        def release(self):
            return None

    with patch("services.public_budget.budget", DeadBudget()):
        assert await ps.sweep_once() is None


@pytest.mark.asyncio
async def test_sweep_once_runs_pipeline_and_returns_view():
    import services.public_scanner as ps

    view = {
        "columns": ps.SCAN_COLUMNS,
        "rows": [["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]],
        "count": 1,
        "quote_truth": {"SNDK|call|50|2026-09-18": {"premium_true": 1.0}},
        "dealer": {"SNDK": {"regime": "negative"}},
        "coverage": {}, "tickers": ["SNDK"],
    }
    seen: dict = {}

    async def fake_next(slice_size=8, max_expiries=2, universe=None):
        return view

    async def fake_record(rows):
        seen["rows"] = rows

    async def fake_alerts(rows, extras=None, dealer=None):
        seen["extras"] = extras
        seen["dealer"] = dealer

    class Budget:
        async def acquire(self, host="public"):
            return None

        def release(self):
            return None

    ps._reset_state()
    try:
        with patch("services.public_budget.budget", Budget()), \
             patch.object(ps, "scan_next", side_effect=fake_next), \
             patch("routes.flowseeker._record_scan_baseline", fake_record), \
             patch("routes.flowseeker._run_institutional_alerts", fake_alerts):
            out = await ps.sweep_once()
        assert out is view
        assert seen["rows"] == view["rows"]
        assert seen["extras"] == view["quote_truth"]
        assert seen["dealer"] == view["dealer"]
    finally:
        ps._reset_state()


def test_dealer_gib_pct_needs_measured_adv():
    """B2: real ΓIB pct = net_gex/(spot²·0.01·adv)·100; None without ADV."""
    from services.public_scanner import dealer_context

    contracts = [
        {"strike": 100.0, "type": "call", "oi": 5000, "gamma": 0.02},
        {"strike": 95.0, "type": "put", "oi": 12000, "gamma": 0.018},
    ]
    d0 = dealer_context(contracts, 100.0)
    assert d0["gamma_imbalance_pct"] is None and d0["regime"] == "negative"
    d1 = dealer_context(contracts, 100.0, adv_shares=10_000_000)
    net = -(0.02 * 5000 + 0.018 * 12000) * 100 * 100.0**2 * 0.01
    assert d1["gamma_imbalance_pct"] == pytest.approx(
        (net / (100.0**2 * 0.01 * 10_000_000)) * 100.0)
    assert d1["adv_shares"] == 10_000_000
    # junk ADV degrades to regime-only, never crashes
    d2 = dealer_context(contracts, 100.0, adv_shares=0)
    assert d2["gamma_imbalance_pct"] is None and d2["regime"] == "negative"


def test_get_universe_rejects_garbage_never_crashes():
    import services.public_scanner as ps

    with patch.dict("os.environ", {"FLOWW_PUBLIC_UNIVERSE": "SPY, $$$ , TOOLONGTICKERNAME123, 123ABC, ok-name.x"}):
        out = ps.get_universe()
    assert out == ["SPY", "OK-NAME.X"]
    with patch.dict("os.environ", {"FLOWW_PUBLIC_UNIVERSE": "!!!, ???"}):
        assert ps.get_universe() == ps.UNIVERSE  # all rejected -> default


def test_extras_carry_rel_spread():
    from services.public_scanner import unusual_rows_from_chain

    chain = {"ticker": "SNDK", "spot": 50.0, "contracts": [
        {"osi": "O:A", "expiry": "2026-09-18", "type": "call", "strike": 50.0,
         "volume": 500, "oi": 100, "iv": 0.4, "delta": 0.5,
         "bid": 1.0, "ask": 1.2, "mid": 1.1, "last": 1.2},
        {"osi": "O:B", "expiry": "2026-09-18", "type": "call", "strike": 55.0,
         "volume": 500, "oi": 100, "iv": 0.4, "delta": 0.4},  # no quote
    ]}
    _, xtras = unusual_rows_from_chain(chain)
    assert xtras["SNDK|call|50|2026-09-18"]["rel_spread"] == pytest.approx(0.2 / 1.1)
    assert xtras["SNDK|call|55|2026-09-18"]["rel_spread"] is None


def test_alert_carries_rel_spread_when_measured():
    from services.flow_alerts import apply_quote_truth, eval_institutional, norm_rows

    rows = norm_rows([["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]])
    apply_quote_truth(rows, {"SNDK|call|50|2026-09-18": {
        "premium_true": 600000.0, "rel_spread": 0.04}})
    alerts = eval_institutional(rows)
    assert alerts and alerts[0]["rel_spread"] == 0.04
    rows2 = norm_rows([["SNDK", "O:S", "call", 50.0, "2026-09-18", 3000, 500, 0.5, 0.4, 49.0]])
    assert eval_institutional(rows2)[0]["rel_spread"] is None


def test_merged_gex_prefers_measured_dealer_pct():
    import routes.flowseeker as fs

    dealer = {"SNDK": {"regime": "negative", "gamma_imbalance_pct": -2.5,
                       "call_wall": 55.0, "put_wall": 45.0}}
    with patch.object(fs, "_cached_gex_context", return_value={}):
        out = fs._merged_gex_context(["SNDK"], dealer)
    assert out["SNDK"]["gamma_imbalance"]["gamma_imbalance_pct"] == -2.5
    assert out["SNDK"]["gamma_imbalance"]["regime"] == "negative"


def test_merged_gex_context_cache_wins_dealer_fills_gaps():
    fs = _route_module()
    cached = {"SPY": {"gamma_imbalance": {"gamma_imbalance_pct": 2.0, "regime": "x"}}}
    dealer = {
        "SPY": {"regime": "negative"},                       # cache wins
        "SNDK": {"regime": "negative", "call_wall": 55.0, "put_wall": 45.0},
        "JUNK": {"regime": "sideways"},                       # not a regime: skipped
        "EMPTY": {},                                          # no regime: skipped
    }
    with patch.object(fs, "_cached_gex_context", return_value=cached):
        out = fs._merged_gex_context(["SPY", "SNDK", "JUNK", "EMPTY"], dealer)
    assert out["SPY"] == cached["SPY"]
    assert out["SNDK"]["gamma_imbalance"]["regime"] == "negative"
    assert out["SNDK"]["gamma_imbalance"]["gamma_imbalance_pct"] is None  # unknown, never 0.0
    assert out["SNDK"]["gamma_imbalance"]["dealer_walls"] == {"call": 55.0, "put": 45.0}
    assert "JUNK" not in out and "EMPTY" not in out


@pytest.mark.asyncio
async def test_public_sweep_loop_kill_switch_and_shutdown():
    import server as srv

    with patch.dict("os.environ", {"FLOWW_PUBLIC_SWEEP": "0"}):
        await srv._public_sweep_loop()  # returns immediately, no network
    # shutdown event set -> loop body never runs
    srv._shutdown_event.set()
    try:
        with patch.dict("os.environ", {"FLOWW_PUBLIC_SWEEP": "1",
                                       "FLOWW_PUBLIC_SWEEP_RTH_S": "45"}):
            await srv._public_sweep_loop()
    finally:
        srv._shutdown_event.clear()


# ── B4 honest budget: acquire_n + per-ticker debit + adaptive trim ──

def test_acquire_n_atomic_no_partial_spend():
    from services.public_budget import BudgetExhausted, PublicBudget

    async def run():
        b = PublicBudget(capacity=10, refill_per_sec=0.0)
        await b.acquire_n(4, now=1000.0)
        assert b._tokens == 6.0
        with pytest.raises(BudgetExhausted) as e:
            await b.acquire_n(7, now=1000.0)
        assert e.value.reason == "token_bucket"
        assert b._tokens == 6.0  # refusal debits nothing
        b.release()
        await b.acquire_n(6, now=1000.0)  # slot freed, tokens exact-fit
        assert b._tokens == 0.0

    asyncio.run(run())


def test_peek_available_honors_idle_refill():
    from services.public_budget import PublicBudget

    async def run():
        b = PublicBudget(capacity=10, refill_per_sec=1.0)
        await b.acquire_n(10, now=1000.0)
        assert await b.peek_available(now=1005.0) == 5.0
        b.release()

    asyncio.run(run())


@pytest.mark.asyncio
async def test_scan_slice_maps_refused_fetch_to_empty_rows(monkeypatch):
    # D2: admission lives in the adapter (C8 choke point). A budget
    # refusal there surfaces as chain None -> empty rows; the scanner
    # performs no acquisition of its own (no double debit) and the
    # caller keeps the prior slice.
    import services.public_scanner as ps

    async def refused(ticker, max_expiries=2):
        return None

    monkeypatch.setattr("services.public_api_adapter.fetch_chain_from_public_api", refused)
    out = await ps.scan_slice(["SPY"], max_expiries=2)
    assert out["SPY"]["rows"] == [] and "skipped" not in out["SPY"]


@pytest.mark.asyncio
async def test_scan_next_trims_slice_to_affordability(monkeypatch):
    import services.public_scanner as ps
    from services.public_budget import PublicBudget

    ps._reset_state()
    try:
        seen: list = []

        async def fake_slice(tickers, max_expiries=2, concurrency=3):
            seen.extend(tickers)
            return {t: {"rows": [[t, f"O:{t}", "call", 100.0, "2026-09-18",
                                  500, 100, 0.4, 0.4, 99.0]],
                        "extras": {}, "dealer": None} for t in tickers}

        # capacity 9, cost 4/ticker -> afford 2 of 8 requested
        monkeypatch.setattr("services.public_budget.budget",
                            PublicBudget(capacity=9, refill_per_sec=0.0))
        with patch.object(ps, "scan_slice", side_effect=fake_slice):
            v = await ps.scan_next(slice_size=8, max_expiries=2,
                                   universe=[f"T{i}" for i in range(8)])
        assert len(seen) == 2 and v["count"] == 2
    finally:
        ps._reset_state()


@pytest.mark.asyncio
async def test_scan_public_503_when_slice_unaffordable(monkeypatch):
    from fastapi import HTTPException

    from services.public_budget import BudgetExhausted

    fs = _route_module()

    class Budget:
        async def acquire(self, host="public"):
            return None

        def release(self):
            return None

    async def no_baselines():
        return {}

    async def no_prev():
        return {}

    async def exhausted_slice(**kw):
        raise BudgetExhausted(retry_after=11, reason="slice-unaffordable")

    with patch("services.public_budget.budget", Budget()), \
         patch("services.public_scanner.scan_next", side_effect=exhausted_slice), \
         patch.object(fs, "_volume_baselines", no_baselines), \
         patch.object(fs, "_prev_contract_oi", no_prev):
        with pytest.raises(HTTPException) as e:
            await fs.public_market_scan(slice_size=8, max_expiries=2)
    assert e.value.status_code == 503
    assert e.value.detail["error"] == "public slice unaffordable"


def test_scan_payload_truncated_and_coverage():
    fs = _route_module()
    rows = [["SPY", "O:1", "call", 1, "2026-09-18", 9, 1, 0.2, 0.5, 1],
            ["QQQ", "O:2", "call", 1, "2026-09-18", 8, 1, 0.2, 0.5, 1]]
    with patch.object(fs, "_cached_regimes", lambda: {}):
        full = fs._scan_payload(rows, False, "asof", ["c"], limit=2)
        assert full["truncated"] is True
        assert full["coverage"] == {"tickers": 2, "limit": 2}
        room = fs._scan_payload(rows, False, "asof", ["c"], limit=500)
        assert room["truncated"] is False
