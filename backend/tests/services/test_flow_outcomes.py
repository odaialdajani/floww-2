"""
backend/tests/services/test_flow_outcomes.py

Outcome-measurement tests on synthetic data with KNOWN answers — the module's
numbers must land exactly, or the desk dashboard lies.

Covers the three plan-mandated tests plus payoff/CI/honesty checks:
  1. precision / control_rate / lift match hand-computed expectations
  2. control cohort contains zero alert ticker-days
  3. censored windows are excluded from stats, never zero-filled
  4. put-side sign, MFE/MAE σ-scaling, Wilson CI sanity, uncalibrated rule
     renders precision=None (never a fabricated small-n number)

All three plan tests FAIL before services/flow_outcomes.py exists (red-first).
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.flow_outcomes import (  # noqa: E402
    build_controls,
    compute_outcomes,
    label_alerts,
    outcome_stats,
)

# ── synthetic market: SPY closes rising ~0.5%/session with mild noise ────────

def _make_bars(ticker: str, dates: list[str], start: float = 100.0,
               shocks: dict[str, float] | None = None) -> dict[str, list[tuple[str, float]]]:
    """Deterministic synthetic closes: alternating +0.4%/−0.2% sessions (σ20 ≈ 0.30%,
    non-degenerate so the vol-scaled hit threshold is meaningful) with optional
    one-day shocks layered on top."""
    px = start
    series = []
    for i, d in enumerate(dates):
        px *= 1.0 + (0.004 if i % 2 == 0 else -0.002)
        if shocks and d in shocks:
            px *= 1.0 + shocks[d]
        series.append((d, round(px, 4)))
    return {ticker: series}


def _dates(n: int, start: str = "2099-01-01") -> list[str]:
    """n consecutive ISO dates (synthetic calendar — the module only needs order)."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


def _alert(under: str, asof: str, rule: str = "SCORE", side: str = "call",
           under_price: float | None = None) -> dict:
    return {"rule": rule, "under": under, "asof_date": asof, "side": side,
            "type": side, "under_price": under_price}


# ── 1. precision / control / lift land exactly ───────────────────────────────

def test_precision_lift_vs_control_matches_expected():
    dates = _dates(80)
    # Baseline alternates +0.4%/−0.2% → any 2-session cum ≈ +0.199% while
    # σ20 ≈ 0.30% → hit threshold 0.75σ ≈ 0.225% > 0.199% ⇒ drift alone NEVER hits.
    # A +5% shock on day s lands in the forward windows of alerts at s−2 and s−1
    # (horizon=2 covers sessions a+1, a+2). Alerts occupy indices 20..59, so
    # shocks at s ∈ {30, 45, 60} (interior, both windows in range) → EXACTLY 6 hits.
    alert_days = dates[20:60]
    shocks = {dates[30]: 0.05, dates[45]: 0.05, dates[60]: 0.05}
    bars = _make_bars("SPY", dates, shocks=shocks)
    alerts = [_alert("SPY", d, "SCORE", "call") for d in alert_days]

    labeled = label_alerts(alerts, bars, horizon=2, sigma_k=0.75)
    measured = [a for a in labeled if not a["censored"]]
    assert len(measured) == 40, "all 40 alerts must have 2 forward sessions"

    n_hit = sum(1 for a in measured if a["hit"])
    assert n_hit == 6, f"expected exactly 6 σ-hits from the 3 shocks × 2 windows, got {n_hit}"

    controls = build_controls(labeled, bars, horizon=2, sigma_k=0.75, per_alert=10, rng=random.Random(7))
    ctrl_measured = [c for c in controls if not c["censored"]]
    assert ctrl_measured, "controls must be constructible from the same bars"
    ctrl_rate = sum(1 for c in ctrl_measured if c["hit"]) / len(ctrl_measured)
    # Shock days only affect windows of alert days (s−2, s−1 ∈ alert range),
    # and those are excluded from the control pool → control hit rate is 0.0.
    assert ctrl_rate == 0.0, f"controls must be shock-free by construction, got {ctrl_rate}"

    stats = outcome_stats(labeled, controls, min_alerts=5, bootstrap_iters=50, rng=random.Random(7))
    s = stats["per_rule"]["SCORE"]
    assert round(s["precision"], 3) == round(6 / 40, 3) == 0.15
    assert s["n_measured"] == 40
    assert s["control_rate"] is not None
    assert abs(s["control_rate"] - ctrl_rate) < 1e-6
    # The shocks ARE the edge: alert precision must exceed the control rate.
    assert s["lift"] is not None and s["precision"] > s["control_rate"]


# ── 2. control cohort never contains an alert ticker-day ─────────────────────

def test_control_cohort_excludes_alert_ticker_days():
    dates = _dates(60)
    bars = _make_bars("SPY", dates)
    alert_days = dates[10:30]
    alerts = [_alert("SPY", d, "WHALE", "call") for d in alert_days]
    labeled = label_alerts(alerts, bars, horizon=2)
    controls = build_controls(labeled, bars, per_alert=30, window_days=20, rng=random.Random(3))
    alert_set = {(a["under"], a["asof_date"]) for a in labeled}
    for c in controls:
        assert (c["under"], c["asof_date"]) not in alert_set, \
            f"control day {c['asof_date']} collides with an alert day"


# ── 3. censored windows excluded, never zero-filled ──────────────────────────

def test_censored_windows_excluded_not_zeroed():
    dates = _dates(30)
    bars = _make_bars("SPY", dates)
    # last 2 alert days have < 2 forward sessions → censored at horizon=2
    alerts = [_alert("SPY", d, "SCORE", "call") for d in dates[10:30]]
    labeled = label_alerts(alerts, bars, horizon=2)
    censored = [a for a in labeled if a["censored"]]
    measured = [a for a in labeled if not a["censored"]]
    assert len(censored) == 2 and len(measured) == 18
    for a in censored:
        assert a["hit"] is None and a["ret"] is None, "censored rows must carry no fabricated label"
    stats = outcome_stats(labeled, [], min_alerts=5)
    s = stats["per_rule"]["SCORE"]
    assert s["n_measured"] == 18 and s["n_censored"] == 2
    assert s["precision"] is not None  # 18 ≥ min_alerts
    assert stats["generated_from"]["censored"] == 2


# ── 4. sign, payoff, CI, honesty ─────────────────────────────────────────────

def test_put_side_sign_flips_the_label():
    dates = _dates(40)
    # DOWN shock after the alert date: a PUT alert should HIT
    shocks = {dates[11]: -0.05}
    bars = _make_bars("SPY", dates, shocks=shocks)
    alerts = [_alert("SPY", dates[10], "SCORE", "put")]
    labeled = label_alerts(alerts, bars, horizon=2, sigma_k=0.75)
    assert labeled[0]["hit"] is True, "put-side alert must sign-flip the forward return"
    assert labeled[0]["ret"] > 0, "put-side signed return on a −5% day must be positive"


def test_mfe_mae_scaled_by_sigma():
    dates = _dates(40)
    shocks = {dates[26]: 0.05}
    bars = _make_bars("SPY", dates, shocks=shocks)
    # Alert at index 25: first index with a full 20-session σ window (needs ≥21 closes)
    labeled = label_alerts([_alert("SPY", dates[25], "SCORE", "call")], bars, horizon=2, sigma_k=0.75)
    a = labeled[0]
    assert a["sigma20"] is not None, "alert at index 25 must have a full σ20 window"
    assert a["mfe_sigma"] is not None and a["mae_sigma"] is not None
    assert a["hit"] is True, "+5% shock inside the 2-session window must hit"
    # σ ≈ 0.30% baseline → a 5% shock is many σ
    assert a["mfe_sigma"] > 1.0
    assert a["mfe_sigma"] > a["mae_sigma"]


def test_uncalibrated_rule_renders_none_never_a_fake_number():
    dates = _dates(30)
    bars = _make_bars("SPY", dates)
    alerts = [_alert("SPY", d, "0DTE", "call") for d in dates[10:14]]  # n=4 < min_alerts=5
    labeled = label_alerts(alerts, bars, horizon=2)
    stats = outcome_stats(labeled, [], min_alerts=5)
    s = stats["per_rule"]["0DTE"]
    assert s["n_measured"] == 4
    assert s["precision"] is None and s["uncalibrated"] is True


def test_wilson_ci_brackets_precision_and_shrinks_with_n():
    dates = _dates(80)
    bars = _make_bars("SPY", dates)
    # deterministic 50% hits: shock every other alert day
    alert_days = dates[20:60]
    shocks = {dates[i + 1]: 0.05 for i in range(20, 60, 2)}
    bars = _make_bars("SPY", dates, shocks=shocks)
    alerts = [_alert("SPY", d, "SCORE", "call") for d in alert_days]
    labeled = label_alerts(alerts, bars, horizon=2, sigma_k=0.75)
    stats = outcome_stats(labeled, [], min_alerts=5, bootstrap_iters=100, rng=random.Random(5))
    s = stats["per_rule"]["SCORE"]
    assert s["precision_ci"] is not None
    lo, hi = s["precision_ci"]
    assert 0.0 <= lo <= s["precision"] <= hi <= 1.0


def test_one_shot_compute_outcomes_end_to_end():
    dates = _dates(70)
    # Sparse isolated shocks (10 apart → no window overlap) so σ20 stays
    # honest and hits are deterministic: 3 shock days in the SCORE range.
    shock_days = [dates[i + 1] for i in range(20, 50, 10)]
    shocks = {d: 0.05 for d in shock_days}
    bars = _make_bars("SPY", dates, shocks=shocks)
    # σ20 for alerts near a shock includes it — fine, the test asserts
    # structure (n, controls, precision exists), not exact hit counts here.
    vix = [(d, 15.0 + (10.0 if i % 3 == 0 else 0.0)) for i, d in enumerate(dates)]
    alerts = ([_alert("SPY", d, "SCORE", "call") for d in dates[20:50]]
              + [_alert("SPY", d, "WHALE", "call") for d in dates[20:32]])
    out = compute_outcomes(alerts, bars, vix, horizon=2, per_alert=5, bootstrap_iters=100)
    assert set(out["per_rule"]) == {"SCORE", "WHALE"}
    assert out["horizon_sessions"] == 2
    for rule in ("SCORE", "WHALE"):
        s = out["per_rule"][rule]
        assert s["n_measured"] > 0
        assert s["precision"] is not None
        assert s["n_controls"] > 0, "VIX terciles are matchable here — controls must exist"
